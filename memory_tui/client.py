"""Cliente del MCP Memory Server. Envuelve fastmcp.Client y expone helpers síncronos.

Config por entorno:
  MEMORY_BASE_URL     (default http://localhost:8000/mcp)
  MEMORY_APIKEY       apikey de la cuenta (header X-API-Key)
  MEMORY_ADMIN_TOKEN  token admin para crear/listar cuentas (header X-Admin-Token)
"""
import asyncio
import os

from fastmcp import Client
from fastmcp.client.transports import StreamableHttpTransport

BASE_URL = os.environ.get("MEMORY_BASE_URL", "http://localhost:8000/mcp")


def _transport(apikey: str | None, admin: str | None) -> StreamableHttpTransport:
    headers: dict[str, str] = {}
    if apikey:
        headers["X-API-Key"] = apikey
    if admin:
        headers["X-Admin-Token"] = admin
    return StreamableHttpTransport(BASE_URL, headers=headers)


async def _acall(tool: str, args: dict, apikey: str | None, admin: str | None):
    async with Client(_transport(apikey, admin)) as c:
        res = await c.call_tool(tool, args)
        return res.data


def llamar(tool: str, apikey: str | None = None, admin: str | None = None, **args):
    """Llama una tool del API y devuelve su resultado (dict/list). Síncrono."""
    apikey = apikey or os.environ.get("MEMORY_APIKEY") or None
    admin = admin or os.environ.get("MEMORY_ADMIN_TOKEN") or None
    return asyncio.run(_acall(tool, args, apikey, admin))


# --- Atajos de uso frecuente (la apikey sale de MEMORY_APIKEY si no se pasa) --- #

def buscar(query="", tipo=None, folder_id=None, tags=None, limit=10, apikey=None):
    return llamar("buscar", apikey=apikey, query=query, tipo=tipo,
                  folder_id=folder_id, tags=tags, limit=limit)


def listar(folder_id=None, apikey=None):
    return llamar("listar", apikey=apikey, folder_id=folder_id)


def listar_recientes(limit=10, apikey=None):
    return llamar("listar_recientes", apikey=apikey, limit=limit)


def cargar_contexto(entry_ids, apikey=None):
    return llamar("cargar_contexto", apikey=apikey, entry_ids=entry_ids)


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
