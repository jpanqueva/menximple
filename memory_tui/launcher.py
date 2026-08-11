"""Launcher que ejecuta Claude. Abre la TUI (modo 1) o cae a modo chat (modo 2).

Imprime UN objeto JSON a stdout = lo que se inyecta en la conversación:
  - TUI ok:        {"modo":"tui","seleccion":[...contextos...]}
  - TUI cancelado: {"modo":"tui","cancelado":true,"motivo":"sin_seleccion"}
  - Sigue abierta: {"modo":"tui","pendiente":true,"token":"..."}
  - Modo chat:     {"modo":"chat","candidatos":[{id,titulo,resumen,tipo,path}...]}
El chat elige por número y luego llama `load --ids a,b` para traer los contextos.

Bloquea hasta que la ventana muere, pero **agotar el tiempo no la mata**: Claude
Code corta sus llamadas a los 120 s y matar la ventana ahí le daba al usuario
menos de dos minutos para escoger. En vez de eso se devuelve un token y se sigue
esperando con `recoger` las veces que haga falta.

Si no hay escritorio (servidor ciego / tmux) no abre ventana: usa modo chat."""
import argparse
import json
import os
import subprocess
import sys
import tempfile
import uuid

from . import client

# Ventanas abiertas que aún no han dado resultado, por token. Vive en memoria del
# proceso MCP local, que es de larga vida: sobrevive entre llamadas a tools.
_ABIERTAS: dict[str, dict] = {}


def _hay_escritorio() -> bool:
    if os.environ.get("MEMORY_TUI", "").lower() == "off":
        return False
    if sys.platform.startswith("win"):
        return True
    return bool(os.environ.get("DISPLAY") or os.environ.get("WAYLAND_DISPLAY"))


def _spawn_tui(out: str, query: str, folder: str | None, limit: int):
    cmd = [sys.executable, "-m", "memory_tui.browser", "--out", out,
           "--query", query, "--limit", str(limit)]
    if folder:
        cmd += ["--folder", folder]
    flags = subprocess.CREATE_NEW_CONSOLE if sys.platform.startswith("win") else 0
    # Sin consola propia la TUI heredaria nuestro stdout, y si quien nos llama es el
    # MCP local (stdio) eso corromperia el protocolo: en ese caso, a /dev/null.
    salida = None if flags else subprocess.DEVNULL
    entorno = {**os.environ, "PYTHONIOENCODING": "utf-8"}  # la TUI dibuja con Unicode
    return subprocess.Popen(cmd, creationflags=flags, stdout=salida, stderr=salida,
                            env=entorno)


def _pendiente(token: str) -> dict:
    return {"modo": "tui", "pendiente": True, "token": token,
            "mensaje": "La ventana sigue abierta; el usuario no ha terminado de "
                       "elegir. Vuelve a llamar `recoger_seleccion` con este token "
                       "(no abras otra ventana)."}


def _cosechar(token: str, timeout: int) -> dict:
    """Espera a que la ventana muera y traduce lo que dejó escrito. Si sigue viva
    al agotarse el tiempo la deja en paz y devuelve el token."""
    st = _ABIERTAS.get(token)
    if st is None:
        return {"error": f"token desconocido: {token}. La ventana ya se cosechó o "
                         "nunca existió; abre el selector de nuevo."}
    try:
        st["p"].wait(timeout=max(1, timeout))
    except subprocess.TimeoutExpired:
        return _pendiente(token)

    _ABIERTAS.pop(token, None)
    try:                          # si la ventana murió sin escribir -> sin selección
        with open(st["out"], encoding="utf-8") as f:
            ids = json.load(f)
    except (OSError, ValueError):
        ids = []
    try:
        os.remove(st["out"])
    except OSError:
        pass

    if not ids:
        return {"modo": "tui", "cancelado": True, "motivo": "sin_seleccion"}
    return {"modo": "tui", "seleccion": cargar(ids)["seleccion"]}


def seleccionar(query: str = "", folder: str | None = None, limit: int = 20,
                timeout: int = 110) -> dict:
    """Abre el selector y devuelve lo elegido. Es la entrada única: la usan el CLI
    (`menximple select`) y la tool `abrir_selector` del MCP local."""
    if not _hay_escritorio():
        cands = client.buscar(query=query, limit=limit) if query \
            else client.listar_recientes(limit=limit)
        return {"modo": "chat", "candidatos": [
            {k: c.get(k) for k in ("id", "titulo", "resumen", "tipo", "path")} for c in cands]}

    fd, out = tempfile.mkstemp(suffix=".json")
    os.close(fd)
    token = uuid.uuid4().hex[:8]
    _ABIERTAS[token] = {"p": _spawn_tui(out, query, folder, limit), "out": out}
    return _cosechar(token, timeout)


def recoger(token: str, timeout: int = 110) -> dict:
    """Sigue esperando por una ventana que quedó abierta (ver `seleccionar`)."""
    return _cosechar(token, timeout)


def cerrar(token: str) -> dict:
    """Cierra a la fuerza una ventana abandonada."""
    st = _ABIERTAS.pop(token, None)
    if st is None:
        return {"error": f"token desconocido: {token}"}
    st["p"].kill()
    try:
        os.remove(st["out"])
    except OSError:
        pass
    return {"cerrado": token}


def cargar(ids: list[str]) -> dict:
    """Trae el contexto completo de esas memorias (y marca su uso)."""
    return {"seleccion": client.cargar_contexto(ids)}


def _select(a) -> dict:
    """Desde la terminal no hay quien reintente: se espera hasta que el usuario cierre."""
    r = seleccionar(a.query, a.folder, a.limit, a.timeout)
    while r.get("pendiente"):
        r = recoger(r["token"], a.timeout)
    return r


def _load(a) -> dict:
    return cargar([x.strip() for x in a.ids.split(",") if x.strip()])


def main() -> None:
    ap = argparse.ArgumentParser(prog="memory_tui")
    sub = ap.add_subparsers(dest="cmd", required=True)

    s = sub.add_parser("select", help="abrir selector (TUI o modo chat)")
    s.add_argument("--query", default="")
    s.add_argument("--folder", default=None)
    s.add_argument("--limit", type=int, default=20)
    s.add_argument("--timeout", type=int, default=180)

    l = sub.add_parser("load", help="cargar contexto de ids (modo chat)")
    l.add_argument("--ids", required=True)

    a = ap.parse_args()
    fn = {"select": _select, "load": _load}[a.cmd]
    try:
        print(json.dumps(fn(a), ensure_ascii=False))
    except Exception as e:  # frontera CLI: el error viaja como JSON, no se silencia
        print(json.dumps({"error": str(e)}, ensure_ascii=False))
        sys.exit(1)


if __name__ == "__main__":
    main()
