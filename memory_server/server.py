"""Servidor MCP (FastMCP, Streamable HTTP). Única fuente de verdad vía API.

La cuenta se deriva de la apikey (header X-API-Key) — no se pasa como argumento.
Las tools envuelven el repositorio y traducen MemoriaError -> ToolError con mensaje
accionable. Los errores inesperados se propagan (fail-fast, sin silenciar)."""
from fastmcp import FastMCP
from fastmcp.exceptions import ToolError

from . import auth
from . import repository as repo
from . import store
from .config import settings
from .instructions import INSTRUCCIONES
from .models import MemoriaError

mcp = FastMCP(name="menximple", instructions=INSTRUCCIONES)


def _g(fn, *args, **kwargs):
    try:
        return fn(*args, **kwargs)
    except MemoriaError as e:
        raise ToolError(str(e))


# --- Navegación ---

@mcp.tool
def listar(folder_id: str | None = None) -> dict:
    """Lista el contenido de una carpeta (subcarpetas y entradas).
    Sin `folder_id` devuelve la raíz de la cuenta más la documentación de uso."""
    return _g(repo.listar, auth.cuenta_actual(), folder_id)


# --- Carpetas ---

@mcp.tool
def crear_carpeta(nombre: str, parent_id: str | None = None,
                  descripcion: str | None = None) -> dict:
    """Crea una carpeta (proyecto/subproyecto/agrupación libre). `parent_id` vacío = raíz."""
    return _g(repo.crear_carpeta, auth.cuenta_actual(), nombre, parent_id, descripcion)


@mcp.tool
def editar_carpeta(folder_id: str, nombre: str | None = None,
                   descripcion: str | None = None, mover_a: str | None = None) -> dict:
    """Renombra, describe o mueve una carpeta. `mover_a` = id de la nueva carpeta padre ('' = raíz)."""
    return _g(repo.editar_carpeta, auth.cuenta_actual(), folder_id, nombre, descripcion, mover_a)


# --- Entradas ---

@mcp.tool
def crear_entrada(folder_id: str, titulo: str, resumen: str, contexto: str,
                  tipo: str, tags: list[str] | None = None) -> dict:
    """Guarda una memoria en una carpeta. `tipo`: credencial|skill|general|historical.
    El `resumen` es lo que se indexa/embebe. Rechaza si falta algún campo o el tipo
    es inválido (pídele el dato al usuario y reintenta)."""
    return _g(repo.crear_entrada, auth.cuenta_actual(), folder_id, titulo, resumen, contexto, tipo, tags)


@mcp.tool
def editar_entrada(entry_id: str, titulo: str | None = None, resumen: str | None = None,
                   contexto: str | None = None, tipo: str | None = None,
                   tags: list[str] | None = None, mover_a: str | None = None) -> dict:
    """Edita una entrada. Guarda snapshot de la versión previa en el historial y
    re-embebe si cambió el `resumen`. `mover_a` = id de la carpeta destino (una
    entrada siempre vive dentro de una carpeta, así que no admite raíz)."""
    return _g(repo.editar_entrada, auth.cuenta_actual(), entry_id, titulo, resumen,
              contexto, tipo, tags, mover_a)


@mcp.tool
def obtener_entrada(entry_id: str, marcar_uso: bool = True) -> dict:
    """Devuelve una entrada completa (incluye `contexto`) y marca su uso.
    Usa `marcar_uso=False` solo para previsualizar sin registrar la carga."""
    return _g(repo.obtener_entrada, auth.cuenta_actual(), entry_id, marcar_uso)


@mcp.tool
def cargar_contexto(entry_ids: list[str]) -> list[dict]:
    """Devuelve el `contexto` completo de varias entradas y marca su uso.
    Es la tool para cargar memorias al contexto del agente."""
    return _g(repo.cargar_contexto, auth.cuenta_actual(), entry_ids)


# --- Búsqueda ---

@mcp.tool
def buscar(query: str = "", tipo: str | None = None, folder_id: str | None = None,
           tags: list[str] | None = None, limit: int = 10) -> list[dict]:
    """Busca entradas por texto/vector + filtros de metadatos (tipo, carpeta, tags).
    Devuelve resúmenes (no el contexto completo). `folder_id` restringe al subárbol."""
    return _g(repo.buscar, auth.cuenta_actual(), query, tipo, folder_id, tags, limit)


@mcp.tool
def buscar_relacionadas(texto: str | None = None, entry_id: str | None = None,
                        limit: int = 10) -> list[dict]:
    """Búsqueda más amplia cuando `buscar` no encuentra: vecinos por significado
    (o por el resumen de una entrada dada). Útil sobre todo en modo chat."""
    return _g(repo.buscar_relacionadas, auth.cuenta_actual(), texto, entry_id, limit)


@mcp.tool
def listar_recientes(limit: int = 10) -> list[dict]:
    """Últimas memorias usadas de la cuenta (para ofrecer contextos probables en modo chat)."""
    return _g(repo.listar_recientes, auth.cuenta_actual(), limit)


# --- Administración de cuentas (protegida por X-Admin-Token) ---

@mcp.tool
def crear_cuenta(slug: str, nombre: str | None = None) -> dict:
    """[admin] Crea una cuenta con memorias privadas y devuelve su apikey UNA sola vez.
    Requiere el header X-Admin-Token si está configurado."""
    auth.exigir_admin()
    return _g(repo.crear_cuenta, slug, nombre)


@mcp.tool
def listar_cuentas() -> list[dict]:
    """[admin] Lista las cuentas registradas (sin exponer apikeys)."""
    auth.exigir_admin()
    return _g(repo.listar_cuentas)


def main() -> None:
    store.ensure_collections()
    # El MCP se sirve en /mcp; la ofuscación del path público (ej. /Yu4/api) la hace el
    # reverse proxy (nginx) mapeando /Yu4/api -> /mcp.
    mcp.run(transport="http", host=settings.mcp_host, port=settings.mcp_port)


if __name__ == "__main__":
    main()
