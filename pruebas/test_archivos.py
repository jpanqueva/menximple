"""Archivos publicados, de punta a punta pero sin salir de la máquina.

Levanta el hub de verdad (uvicorn, en un hilo) contra el Qdrant desechable y sube
con `_subir`, la misma función que usa la tool local `publicar_archivo`. Así se
prueba lo que de verdad se rompe: la ruta HTTP, las cabeceras, el disco y el
cliente, no solo el módulo."""
import asyncio
import os
import socket
import tempfile
import threading
import time
from pathlib import Path

DISCO = Path(tempfile.mkdtemp(prefix="menx-archivos-"))
os.environ.setdefault("QDRANT_URL", "http://127.0.0.1:6399")
os.environ["EMBEDDINGS_ENABLED"] = "false"
os.environ["ARCHIVOS_DIR"] = str(DISCO)
os.environ["ARCHIVOS_MAX_MB"] = "1"
os.environ["ARCHIVOS_CUOTA_MB"] = "3"

with socket.socket() as s:
    s.bind(("127.0.0.1", 0))
    PUERTO = s.getsockname()[1]
BASE = f"http://127.0.0.1:{PUERTO}"
os.environ["PUBLIC_BASE_URL"] = BASE
os.environ["MEMORY_BASE_URL"] = f"{BASE}/mcp"

import httpx                                                  # noqa: E402
import uvicorn                                                # noqa: E402
from fastmcp import Client                                    # noqa: E402
from fastmcp.client.transports import StreamableHttpTransport  # noqa: E402
from fastmcp.exceptions import ToolError                      # noqa: E402

from memory_server import repository as repo, store           # noqa: E402
from memory_server.server import mcp                          # noqa: E402
from memory_tui.mcp_local import _subir                       # noqa: E402

store.ensure_collections()
fallos = []
MB = 1024 * 1024


def chk(c, m):
    print(("  OK   " if c else "  FALLO") + "  " + m)
    if not c:
        fallos.append(m)


def falla_subir(trozo, m, *a, key=None):
    if key is not None:
        os.environ["MEMORY_APIKEY"] = key
    try:
        _subir(*a)
        chk(False, m + " (no lanzó)")
    except ToolError as e:
        chk(trozo in str(e), f"{m} -> {e}")


def cuenta(slug):
    sufijo = str(int(time.time() * 1000))[-7:]
    return repo.crear_cuenta(f"{slug}-{sufijo}")["apikey"]


def como(key):
    os.environ["MEMORY_APIKEY"] = key


def local(nombre, datos):
    p = DISCO.parent / f"origen-{time.time_ns()}-{nombre}"
    p.write_bytes(datos)
    return str(p)


srv = uvicorn.Server(uvicorn.Config(mcp.http_app(path="/mcp"), host="127.0.0.1",
                                    port=PUERTO, log_level="warning"))
threading.Thread(target=srv.run, daemon=True).start()
for _ in range(50):
    if srv.started:
        break
    time.sleep(0.1)

A, B = cuenta("archivos-a"), cuenta("archivos-b")

print("== subir y abrir el link sin apikey ==")
pdf = b"%PDF-1.4\n" + os.urandom(2000)
como(A)
f1 = _subir(local("x.pdf", pdf), "Informe ñandú (final).pdf", None, "para el cliente")
chk(f1["url"].startswith(f"{BASE}/f/"), f"la URL es pública -> {f1['url']}")
chk(f1["nombre"] == "Informe-nandu-final-.pdf", f"nombre limpio -> {f1['nombre']}")
r = httpx.get(f1["url"])
chk(r.status_code == 200 and r.content == pdf, "abre sin apikey y los bytes son los mismos")
chk(r.headers["content-type"] == "application/pdf", f"mime -> {r.headers['content-type']}")
chk("content-security-policy" not in r.headers,
    "un PDF va sin CSP sandbox (Chrome no lo abriría)")
chk(r.headers.get("referrer-policy") == "no-referrer", "no filtra el token por Referer")

token = f1["url"].split("/f/")[1].split("/")[0]
chk(len(token) >= 30, f"token largo -> {len(token)} caracteres")
chk(httpx.get(f"{BASE}/f/{token}/otro-nombre.exe").content == pdf,
    "el nombre de la URL es decorativo: cambiarlo abre el mismo archivo")
chk(httpx.get(f"{BASE}/f/{token}").content == pdf, "y sin nombre también abre")
chk(httpx.get(f"{BASE}/f/{token[:-1]}X/x.pdf").status_code == 404,
    "un token casi igual no abre")

print("== un HTML publicado no corre con el origen del hub ==")
f2 = _subir(local("r.html", b"<script>alert(1)</script>"), None, None, None)
r = httpx.get(f2["url"])
chk(r.headers["content-type"].startswith("text/html"), f"mime -> {r.headers['content-type']}")
chk("sandbox" in r.headers.get("content-security-policy", ""),
    f"lleva CSP sandbox -> {r.headers.get('content-security-policy')}")
chk("allow-same-origin" not in r.headers.get("content-security-policy", ""),
    "y sin allow-same-origin, que anularía el sandbox")

print("== autenticación de la subida ==")
r = httpx.post(f"{BASE}/mcp/archivos", params={"nombre": "a.txt"}, content=b"hola")
chk(r.status_code == 401 and "falta apikey" in r.json()["error"],
    f"sin apikey -> {r.status_code} {r.text}")
falla_subir("inválida", "apikey falsa", local("a.txt", b"hola"), None, None, None,
            key="no-es-una-apikey")
como(A)

print("== límites ==")
falla_subir("no existe el archivo", "ruta que no existe",
            str(DISCO / "no-esta.pdf"), None, None, None)
falla_subir("vacío", "archivo vacío", local("v.txt", b""), None, None, None)
falla_subir("máximo es 1 MB", "más del máximo, con Content-Length",
            local("g.bin", b"0" * (MB + 1)), None, None, None)
# Sin Content-Length: el servidor tiene que contar lo que llega, no fiarse.
r = httpx.post(f"{BASE}/mcp/archivos", params={"nombre": "g.bin"},
               content=(b"0" * 65536 for _ in range(20)), headers={"X-API-Key": A})
chk(r.status_code == 413, f"más del máximo, en trozos sin Content-Length -> {r.status_code}")
falla_subir("mayor que 0", "expira_dias=0", local("e.txt", b"x"), None, 0, None)

print("== cuota por cuenta ==")
subidos, ultimo = 0, ""
try:
    for i in range(3):
        _subir(local(f"c{i}.bin", os.urandom(MB - 100)), None, None, None)
        subidos += 1
except ToolError as e:
    ultimo = str(e)
chk(subidos == 2, f"caben dos de ~1 MB junto a lo anterior, no tres -> {subidos}")
chk("no cabe" in ultimo, f"y el tercero dice por qué -> {ultimo}")
como(B)
chk(_subir(local("b.txt", b"de b"), None, None, None)["tamano"] == 4,
    "la cuota de A no afecta a B")

print("== nombres con ruta no escriben fuera ==")
como(A)
antes = set(DISCO.parent.iterdir())
f3 = _subir(local("t.txt", b"t"), "../../../escapado.txt", None, None)
chk(f3["nombre"] == "escapado.txt", f"se queda con la última parte -> {f3['nombre']}")
nuevos = {p.name for p in set(DISCO.parent.iterdir()) - antes}
chk(not any("escapado" in n for n in nuevos) and (DISCO / f3["id"]).is_file(),
    f"en disco va por id dentro de la carpeta -> nuevos fuera: {nuevos}")


async def tools(key, nombre, **args):
    c = Client(StreamableHttpTransport(f"{BASE}/mcp", headers={"X-API-Key": key}))
    async with c:
        return await c.call_tool(nombre, args, raise_on_error=False)


print("== listar y borrar por las tools del hub, aislado por cuenta ==")
r = asyncio.run(tools(A, "listar_archivos"))
urls_a = [x["url"] for x in r.structured_content["result"]]
chk(f1["url"] in urls_a and len(urls_a) == 5, f"A ve los suyos -> {len(urls_a)}")
r = asyncio.run(tools(B, "listar_archivos"))
chk(len(r.structured_content["result"]) == 1 and f1["url"] not in
    [x["url"] for x in r.structured_content["result"]], "B no ve los de A")

r = asyncio.run(tools(B, "borrar_archivo", archivo=f1["url"]))
chk(r.is_error and "no hay ningún archivo tuyo" in r.content[0].text,
    f"B no puede borrar el de A -> {r.content[0].text}")
chk(httpx.get(f1["url"]).status_code == 200, "y después del intento sigue abriendo")

r = asyncio.run(tools(A, "borrar_archivo", archivo=f1["url"]))
chk(not r.is_error and r.structured_content["borrado"] == f1["nombre"],
    f"A lo borra por URL -> {r.structured_content}")
chk(httpx.get(f1["url"]).status_code == 404, "el link deja de abrir")
chk(not (DISCO / f1["id"]).exists(), "y el disco se libera")
r = asyncio.run(tools(A, "borrar_archivo", archivo=f2["id"]))
chk(not r.is_error, "también se borra por id")
chk(len(asyncio.run(tools(A, "listar_archivos")).structured_content["result"]) == 3,
    "ya no salen en la lista")

print("== links que vencen ==")
como(B)
f4 = _subir(local("v.txt", b"vence"), None, 1.5 / 86400, None)   # 1.5 s
chk(f4["expira"] is not None, f"trae la fecha -> {f4['expira']}")
chk(httpx.get(f4["url"]).status_code == 200, "abre antes de vencer")
time.sleep(2)
chk(httpx.get(f4["url"]).status_code == 404, "no abre después")
lista = asyncio.run(tools(B, "listar_archivos")).structured_content["result"]
chk(any(x["id"] == f4["id"] and x["vencido"] for x in lista),
    "y en la lista sale como vencido (sigue ocupando cuota hasta borrarlo)")

srv.should_exit = True
print()
print("FALLOS:", len(fallos))
raise SystemExit(1 if fallos else 0)
