"""Que las esperas de los canales no ahoguen al hub.

El incidente del 17/09/2026: `recibir_mensajes` y `recibir_de_todos` eran tools
síncronas con `time.sleep` dentro, y FastMCP corre las síncronas en el pool de
anyio, que tiene **40 hilos** compartidos con TODAS las tools. Cuarenta agentes
esperando dejaban el hub vivo pero sin atender ni un `buscar`.

La prueba abre más esperas que hilos (60 > 40) y mide una llamada trivial
mientras están colgadas. Tiene que FALLAR contra el código de antes: si pasa en
los dos, no prueba nada. Levanta el hub de verdad (uvicorn) porque el pool solo
existe detrás de FastMCP, no llamando a `canales` directo."""
import asyncio
import os
import socket
import threading
import time

os.environ.setdefault("QDRANT_URL", "http://127.0.0.1:6399")
os.environ["EMBEDDINGS_ENABLED"] = "false"

with socket.socket() as s:
    s.bind(("127.0.0.1", 0))
    PUERTO = s.getsockname()[1]
BASE = f"http://127.0.0.1:{PUERTO}/mcp"

import uvicorn                                                # noqa: E402
from fastmcp import Client                                    # noqa: E402
from fastmcp.client.transports import StreamableHttpTransport  # noqa: E402

from memory_server import canales as ch, repository as repo, store  # noqa: E402
from memory_server.server import mcp                          # noqa: E402

store.ensure_collections()
fallos = []
ESPERAS = 60          # más que los 40 hilos del pool de anyio
ESPERA = 90           # lo que queda colgada cada una: de sobra para que conecten las 60
PAREJAS = 5           # de las 60, cuántas esperan en un canal real para verificar entrega


def chk(c, m):
    print(("  OK   " if c else "  FALLO") + "  " + m)
    if not c:
        fallos.append(m)


srv = uvicorn.Server(uvicorn.Config(mcp.http_app(path="/mcp"), host="127.0.0.1",
                                    port=PUERTO, log_level="warning"))
threading.Thread(target=srv.run, daemon=True).start()
for _ in range(50):
    if srv.started:
        break
    time.sleep(0.1)

sufijo = str(time.time_ns())[-8:]
KEY = repo.crear_cuenta(f"pool-{sufijo}")["apikey"]
canales = []
for i in range(PAREJAS):
    nombre = f"pool-{sufijo}-{i}"
    ch.crear_canal(nombre, agente=f"emisor-{i}", cta="x")
    ch.unirse_canal(nombre, f"receptor-{i}", cta="x")
    canales.append(nombre)


def cliente():
    return Client(StreamableHttpTransport(BASE, headers={"X-API-Key": KEY}), timeout=120)


# Cuándo entró cada espera. La primera versión de esta prueba medía a los 4 s "con
# las 60 colgadas" y en realidad no había conectado NINGUNA (conectar 60 sesiones
# tarda ~17 s aquí): pasó en verde sin probar nada. Ahora se espera a verlas.
CONECTADAS = []


async def esperar(i):
    async with cliente() as c:
        CONECTADAS.append(i)
        if i < PAREJAS:
            r = await c.call_tool("recibir_mensajes",
                                  {"canal": canales[i], "agente": f"receptor-{i}",
                                   "espera": ESPERA})
            textos = [m["texto"] for m in r.structured_content["mensajes"]]
        else:
            # Un agente sin canales: la espera más barata posible, solo ocupa el hueco.
            await c.call_tool("recibir_de_todos", {"agente": f"solo-{i}", "espera": ESPERA})
            textos = None
    return i, textos, time.monotonic()


async def main():
    tareas = [asyncio.create_task(esperar(i)) for i in range(ESPERAS)]
    t_inicio = time.monotonic()
    while len(CONECTADAS) < ESPERAS and time.monotonic() - t_inicio < 60:
        await asyncio.sleep(0.2)
    chk(len(CONECTADAS) == ESPERAS, f"las {ESPERAS} sesiones conectaron -> {len(CONECTADAS)}")
    await asyncio.sleep(3)            # que la llamada de cada una llegue al hub
    colgadas = sum(not t.done() for t in tareas)
    chk(colgadas == ESPERAS, f"las {ESPERAS} esperas están colgadas -> {colgadas}")

    print(f"== con {ESPERAS} esperas colgadas, una llamada trivial ==")
    t0 = time.monotonic()
    async with cliente() as c:
        await c.call_tool("listar_canales", {})
    dt = time.monotonic() - t0
    chk(dt < 3, f"listar_canales responde enseguida -> {dt:.1f} s")

    print("== y las esperas siguen entregando ==")
    chk(all(not t.done() for t in tareas),
        "al medir, las esperas SEGUÍAN colgadas (si no, la medida no prueba nada)")
    enviado = time.monotonic()
    for i, nombre in enumerate(canales):
        ch.enviar_mensaje(nombre, f"emisor-{i}", f"hola {i}")
    receptores = await asyncio.gather(*tareas[:PAREJAS])
    for i, textos, _ in receptores:
        chk(textos == [f"hola {i}"], f"receptor-{i} recibe su mensaje -> {textos}")
    # Llegan cuando se envían, no al agotar la espera: si no, el long-poll no sirve.
    tardanzas = [round(fin - enviado, 1) for _, _, fin in receptores]
    chk(all(0 <= t < 5 for t in tardanzas), f"y les llega al enviarse, no antes ni al agotar la espera -> {tardanzas} s")
    chk(sum(not t.done() for t in tareas[PAREJAS:]) == ESPERAS - PAREJAS,
        "las que no tenían nada siguen esperando (no vuelven vacías antes)")
    for t in tareas[PAREJAS:]:
        t.cancel()
    await asyncio.gather(*tareas[PAREJAS:], return_exceptions=True)


asyncio.run(main())
srv.should_exit = True
print()
print("FALLOS:", len(fallos))
raise SystemExit(1 if fallos else 0)
