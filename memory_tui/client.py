"""Cliente del MCP Memory Server. Envuelve fastmcp.Client y expone helpers síncronos.

Config por entorno:
  MEMORY_BASE_URL     (default http://localhost:8000/mcp)
  MEMORY_APIKEY       apikey de la cuenta (header X-API-Key)
  MEMORY_ADMIN_TOKEN  token admin para crear/listar cuentas (header X-Admin-Token)

La conexión se reutiliza. Antes cada `llamar()` abría un Client nuevo, hacía el
handshake MCP completo (initialize + initialized) y lo cerraba: ~2 s por llamada
contra producción, de los cuales ~60 ms eran trabajo real. Ahora hay un event loop
en un hilo de fondo con un Client vivo por cuenta, y cada llamada cuesta un solo
round-trip. Si la sesión se cae (reinicio del server, expiración) se reconecta y
se reintenta una vez; los errores de la tool en sí no se reintentan.
"""
import asyncio
import atexit
import logging
import os
import threading

from fastmcp import Client
from fastmcp.client.transports import StreamableHttpTransport
from fastmcp.exceptions import ToolError

BASE_URL = os.environ.get("MEMORY_BASE_URL", "http://localhost:8000/mcp")

_arranque = threading.Lock()
_loop: asyncio.AbstractEventLoop | None = None
_clientes: dict[tuple, Client] = {}
_cerrojos: dict[tuple, asyncio.Lock] = {}


def _transport(apikey: str | None, admin: str | None) -> StreamableHttpTransport:
    headers: dict[str, str] = {}
    if apikey:
        headers["X-API-Key"] = apikey
    if admin:
        headers["X-Admin-Token"] = admin
    return StreamableHttpTransport(BASE_URL, headers=headers)


def _bucle() -> asyncio.AbstractEventLoop:
    """El event loop de fondo, creado la primera vez que hace falta."""
    global _loop
    if _loop is not None:
        return _loop
    with _arranque:
        if _loop is None:
            lazo = asyncio.new_event_loop()
            threading.Thread(target=lazo.run_forever, name="menx-io",
                             daemon=True).start()
            _loop = lazo
    return _loop


async def _descartar(clave: tuple, c: Client) -> None:
    """Tira una conexión rota sin dejar que su cierre propague."""
    if _clientes.get(clave) is c:
        del _clientes[clave]
    try:
        await c.__aexit__(None, None, None)
    except Exception:
        pass


async def _cliente(clave: tuple, apikey: str | None, admin: str | None) -> Client:
    c = _clientes.get(clave)
    if c is not None and c.is_connected():
        return c
    # El cerrojo evita que dos llamadas simultáneas abran dos sesiones.
    cerrojo = _cerrojos.setdefault(clave, asyncio.Lock())
    async with cerrojo:
        c = _clientes.get(clave)
        if c is not None and c.is_connected():
            return c
        c = Client(_transport(apikey, admin))
        await c.__aenter__()
        _clientes[clave] = c
        return c


async def _acall(tool: str, args: dict, apikey: str | None, admin: str | None):
    clave = (apikey, admin)
    for ultimo in (False, True):
        c = await _cliente(clave, apikey, admin)
        try:
            res = await c.call_tool(tool, args)
            return res.data
        except ToolError:
            raise                      # error de la tool: reintentar no arregla nada
        except Exception:
            await _descartar(clave, c)
            if ultimo:
                raise


def llamar(tool: str, apikey: str | None = None, admin: str | None = None, **args):
    """Llama una tool del API y devuelve su resultado (dict/list). Síncrono.

    Bloquea el hilo llamante, nunca un event loop: los consumidores (el TUI con
    `@work(thread=True)`, el MCP local con `asyncio.to_thread`) ya llaman desde hilos.
    """
    apikey = apikey or os.environ.get("MEMORY_APIKEY") or None
    admin = admin or os.environ.get("MEMORY_ADMIN_TOKEN") or None
    tarea = asyncio.run_coroutine_threadsafe(
        _acall(tool, args, apikey, admin), _bucle())
    return tarea.result()


@atexit.register
def cerrar() -> None:
    """Suelta las sesiones al salir. Best-effort: salir nunca se queda colgado.

    Se calla `mcp.client.streamable_http`: si el intérprete ya empezó a apagarse, el
    DELETE de cierre no encuentra hilos y loguea un warning que no le sirve a nadie
    (la sesión igual muere sola en el servidor)."""
    if _loop is None:
        return
    logging.getLogger("mcp.client.streamable_http").setLevel(logging.CRITICAL)

    async def _todas():
        for clave, c in list(_clientes.items()):
            await _descartar(clave, c)

    try:
        asyncio.run_coroutine_threadsafe(_todas(), _loop).result(timeout=3)
    except Exception:
        pass


# --- Atajos de uso frecuente (la apikey sale de MEMORY_APIKEY si no se pasa) --- #

def buscar(query="", tipo=None, folder_id=None, tags=None, limit=10, apikey=None):
    return llamar("buscar", apikey=apikey, query=query, tipo=tipo,
                  folder_id=folder_id, tags=tags, limit=limit)


def listar(folder_id=None, apikey=None):
    return llamar("listar", apikey=apikey, folder_id=folder_id)


def listar_recientes(limit=10, apikey=None):
    return llamar("listar_recientes", apikey=apikey, limit=limit)


def cargar_contexto(entry_ids, apikey=None):
    """Las memorias completas, siempre como lista.

    El servidor devuelve `{"memorias": [...], "recuerda": ...}` — el recordatorio de
    citar el número va dirigido al agente, no al TUI. Se acepta también la lista
    pelada para no romper contra servidores viejos."""
    r = llamar("cargar_contexto", apikey=apikey, entry_ids=entry_ids)
    return r.get("memorias", []) if isinstance(r, dict) else r


def obtener_entrada(entry_id, marcar_uso=True, apikey=None):
    """Trae una entrada con su `contexto`. `marcar_uso=False` = solo previsualizar."""
    return llamar("obtener_entrada", apikey=apikey, entry_id=entry_id, marcar_uso=marcar_uso)


def crear_carpeta(nombre, parent_id=None, descripcion=None, apikey=None):
    return llamar("crear_carpeta", apikey=apikey, nombre=nombre,
                  parent_id=parent_id, descripcion=descripcion)


def crear_entrada(folder_id, titulo, resumen, contexto, tipo, tags=None, apikey=None):
    return llamar("crear_entrada", apikey=apikey, folder_id=folder_id, titulo=titulo,
                  resumen=resumen, contexto=contexto, tipo=tipo, tags=tags)


# --- Admin --- #

def crear_cuenta(slug, nombre=None, admin=None):
    return llamar("crear_cuenta", admin=admin, slug=slug, nombre=nombre)


def listar_cuentas(admin=None):
    return llamar("listar_cuentas", admin=admin)
