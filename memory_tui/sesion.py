"""Qué memorias ya se cargaron **en esta conversación** de Claude Code.

Es estado efímero de cliente, no del hub: vive en un archivo temporal indexado
por la conversación. Guardarlo así, y no en la memoria del proceso MCP, es lo que
hace que una terminal nueva arranque limpia y que un `/resume` recupere lo ya
cargado.

**Ojo con el id.** Claude Code reparte dos valores distintos de
`CLAUDE_CODE_SESSION_ID`: a las herramientas les da el de la conversación, pero a
los servidores MCP les da uno nuevo en cada arranque del proceso (no tiene
transcript en `~/.claude/projects/`). Usar ese sería romper justamente el caso
`/resume`. Por eso el id se resuelve así: el que nos pasen, si no el del
transcript activo, y sólo como último recurso el del entorno.

Lo que NO se puede resolver solo: un **compact** vacía el contexto del modelo sin
que ningún servidor MCP se entere — no hay señal que observar. Por eso limpiarlo
es explícito: la tool `olvidar_cargadas` o Ctrl+L dentro del navegador."""
import json
import os
import re
import tempfile


def _sesion_por_transcript() -> str | None:
    """La conversación viva es el .jsonl que Claude Code está escribiendo ahora."""
    proyecto = os.environ.get("CLAUDE_PROJECT_DIR")
    if not proyecto:
        return None
    carpeta = os.path.join(os.path.expanduser("~"), ".claude", "projects",
                           re.sub(r"[^A-Za-z0-9]", "-", proyecto))
    try:
        transcripts = [(os.path.getmtime(os.path.join(carpeta, f)), f[:-6])
                       for f in os.listdir(carpeta) if f.endswith(".jsonl")]
    except OSError:
        return None
    return max(transcripts)[1] if transcripts else None


def id_actual(explicito: str | None = None) -> str:
    return (explicito or _sesion_por_transcript()
            or os.environ.get("CLAUDE_CODE_SESSION_ID") or "sin-sesion")


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
