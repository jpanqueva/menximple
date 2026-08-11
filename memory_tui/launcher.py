"""Launcher que ejecuta Claude. Abre la TUI (modo 1) o cae a modo chat (modo 2).

Imprime UN objeto JSON a stdout = lo que se inyecta en la conversación:
  - TUI ok:        {"modo":"tui","seleccion":[...contextos...]}
  - TUI cancelado: {"modo":"tui","cancelado":true,"motivo":"timeout|sin_seleccion"}
  - Modo chat:     {"modo":"chat","candidatos":[{id,titulo,resumen,tipo,path}...]}
El chat elige por número y luego llama `load --ids a,b` para traer los contextos.

Bloquea hasta que la ventana muere; si se cuelga, la mata por timeout (chat liberado).
Si no hay escritorio (servidor ciego / tmux) no abre ventana: usa modo chat."""
import argparse
import json
import os
import subprocess
import sys
import tempfile

from . import client, sesion


def _hay_escritorio() -> bool:
    if os.environ.get("MEMORY_TUI", "").lower() == "off":
        return False
    if sys.platform.startswith("win"):
        return True
    return bool(os.environ.get("DISPLAY") or os.environ.get("WAYLAND_DISPLAY"))


def _spawn_tui(out: str, query: str, folder: str | None, limit: int,
               timeout: int, ses: str):
    cmd = [sys.executable, "-m", "memory_tui.browser", "--out", out,
           "--query", query, "--limit", str(limit), "--sesion", ses]
    if folder:
        cmd += ["--folder", folder]
    flags = subprocess.CREATE_NEW_CONSOLE if sys.platform.startswith("win") else 0
    # Sin consola propia la TUI heredaria nuestro stdout, y si quien nos llama es el
    # MCP local (stdio) eso corromperia el protocolo: en ese caso, a /dev/null.
    salida = None if flags else subprocess.DEVNULL
    entorno = {**os.environ, "PYTHONIOENCODING": "utf-8"}  # la TUI dibuja con Unicode
    p = subprocess.Popen(cmd, creationflags=flags, stdout=salida, stderr=salida, env=entorno)
    try:
        p.wait(timeout=timeout)          # bloquea hasta que la ventana muere
    except subprocess.TimeoutExpired:
        p.kill()                         # se colgó -> cancelar y liberar el chat
        return None
    try:                                 # si la ventana murió sin escribir -> sin selección
        with open(out, encoding="utf-8") as f:
            return json.load(f)
    except (OSError, ValueError):
        return []


def seleccionar(query: str = "", folder: str | None = None, limit: int = 20,
                timeout: int = 180, ses: str | None = None) -> dict:
    """Abre el selector y devuelve lo elegido. Es la entrada única: la usan el CLI
    (`menximple select`) y la tool `abrir_selector` del MCP local."""
    ses = sesion.id_actual(ses)
    if not _hay_escritorio():
        cands = client.buscar(query=query, limit=limit) if query \
            else client.listar_recientes(limit=limit)
        return {"modo": "chat", "candidatos": [
            {k: c.get(k) for k in ("id", "titulo", "resumen", "tipo", "path")} for c in cands]}

    fd, out = tempfile.mkstemp(suffix=".json")
    os.close(fd)
    ids = _spawn_tui(out, query, folder, limit, timeout, ses)
    try:
        os.remove(out)
    except OSError:
        pass

    if ids is None:
        return {"modo": "tui", "cancelado": True, "motivo": "timeout"}
    if not ids:
        return {"modo": "tui", "cancelado": True, "motivo": "sin_seleccion"}
    return {"modo": "tui", "seleccion": cargar(ids, ses)["seleccion"]}


def cargar(ids: list[str], ses: str | None = None) -> dict:
    """Trae el contexto completo de esas memorias (y marca su uso)."""
    seleccion = client.cargar_contexto(ids)
    sesion.agregar(sesion.id_actual(ses), ids)  # para pintarlas como ya cargadas
    return {"seleccion": seleccion}


def olvidar(ses: str | None = None) -> dict:
    """Borra el registro de 'ya cargadas' de esta conversación (post-compact)."""
    ses = sesion.id_actual(ses)
    sesion.limpiar(ses)
    return {"sesion": ses, "cargadas": []}


def _select(a) -> dict:
    return seleccionar(a.query, a.folder, a.limit, a.timeout)


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
