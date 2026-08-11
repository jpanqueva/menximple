"""Qué memorias ya se cargaron **en esta conversación** de Claude Code.

Es estado efímero de cliente, no del hub: vive en un archivo temporal indexado
por `CLAUDE_CODE_SESSION_ID`. Guardarlo así, y no en la memoria del proceso MCP,
es lo que hace que:

- una terminal nueva arranque limpia (otra conversación = otro id = otro archivo);
- un `/resume` recupere lo ya cargado (reanudar conserva el id).

Lo que NO se puede resolver solo: un **compact** vacía el contexto del modelo sin
que ningún servidor MCP se entere — no hay señal que observar. Por eso limpiarlo
es explícito: la tool `olvidar_cargadas` o Ctrl+L dentro del navegador."""
import json
import os
import tempfile


def id_actual(explicito: str | None = None) -> str:
    return explicito or os.environ.get("CLAUDE_CODE_SESSION_ID") or "sin-sesion"


def _ruta(sesion: str) -> str:
    seguro = "".join(c for c in sesion if c.isalnum() or c in "-_")[:64] or "sin-sesion"
    return os.path.join(tempfile.gettempdir(), f"menximple-cargadas-{seguro}.json")


def leer(sesion: str) -> list[str]:
    try:
        with open(_ruta(sesion), encoding="utf-8") as f:
            return list(json.load(f).get("ids", []))
    except (OSError, ValueError):
        return []


def agregar(sesion: str, ids: list[str]) -> list[str]:
    """Registra ids como cargados (sin duplicar) y devuelve la lista completa."""
    todos = leer(sesion)
    todos += [i for i in ids if i not in todos]
    try:
        with open(_ruta(sesion), "w", encoding="utf-8") as f:
            json.dump({"ids": todos}, f)
    except OSError:
        pass
    return todos


def limpiar(sesion: str) -> None:
    try:
        os.remove(_ruta(sesion))
    except OSError:
        pass
