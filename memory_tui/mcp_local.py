"""MCP **local** (stdio) que le da a Claude el selector visual de memorias.

Por qué existe: el hub de memoria vive en un servidor remoto y no puede abrir
ventanas en la máquina del usuario. Este servidor corre en esa máquina, así que
sí puede: abre la TUI, **bloquea** hasta que el usuario elige, y devuelve el
contexto seleccionado como resultado de la tool (= queda inyectado en el chat).

Habla con el hub por HTTP igual que el CLI: `MEMORY_BASE_URL` + `MEMORY_APIKEY`.

Arranque: `menximple-mcp` (stdio). Fuera de Windows no hay consola nueva que
abrir, así que se fuerza el modo chat para no corromper stdout."""
import asyncio
import os
import sys

from fastmcp import FastMCP

from . import launcher

INSTRUCCIONES = """Selector visual de memorias (corre en la máquina del usuario).

Usa `abrir_selector` cuando el usuario quiera **elegir él mismo** qué memorias
cargar ("carga contexto", "abre mis memorias", "déjame escoger"). Abre una
ventana en su escritorio y la llamada BLOQUEA hasta que confirme o cancele.
No la llames por tu cuenta a mitad de otra tarea: interrumpe al usuario.

Para buscar o guardar memorias sin interrumpirlo, usa las tools del hub remoto
(servidor `menximple`): `buscar`, `listar`, `crear_entrada`, `cargar_contexto`.

Respuestas de `abrir_selector`:
- `{"modo":"tui","seleccion":[...]}` → contexto elegido, ya listo para usar.
- `{"modo":"tui","pendiente":true,"token":"..."}` → la ventana **sigue abierta**,
  el usuario aún está mirando. Llama `recoger_seleccion` con ese token; repítelo
  cuantas veces haga falta. NO abras otra ventana ni des la elección por perdida.
- `{"modo":"tui","cancelado":true,"motivo":"sin_seleccion"}` → cerró sin elegir:
  sigue sin cargar contexto, no reintentes solo.
- `{"modo":"chat","candidatos":[...]}` → no había escritorio disponible: muéstrale
  la lista, pídele los números y luego llama `cargar_memorias` con esos ids."""

mcp = FastMCP("menximple-selector", instructions=INSTRUCCIONES)


@mcp.tool
async def abrir_selector(query: str = "", folder: str | None = None, limit: int = 20,
                         timeout: int = 110, sesion: str | None = None) -> dict:
    """Abre el selector de memorias en el escritorio del usuario y espera su elección.

    `query` filtra por tema (vacío = las memorias más recientes). `timeout` son los
    segundos que espero antes de devolver el control; déjalo por debajo de 120,
    que es donde Claude Code corta la llamada. Agotarlo **no cierra la ventana**:
    devuelve `pendiente` con un token para seguir esperando con `recoger_seleccion`.

    `sesion`: pasa el valor de `CLAUDE_CODE_SESSION_ID` de tu entorno si lo tienes.
    Es lo que permite marcar como ya cargadas las memorias de esta conversación —
    el que ve este servidor es distinto y cambia en cada arranque. Si no lo pasas,
    se deduce del transcript activo."""
    return await asyncio.to_thread(launcher.seleccionar, query, folder, limit,
                                   timeout, sesion)


@mcp.tool
async def recoger_seleccion(token: str, timeout: int = 110) -> dict:
    """Sigue esperando por una ventana que quedó abierta (respuesta `pendiente`).

    Devuelve lo mismo que `abrir_selector`: si el usuario todavía no ha terminado,
    otra vez `pendiente` con el mismo token — vuelve a llamarla. Elegir con calma es
    lo normal; no interpretes la espera como que canceló."""
    return await asyncio.to_thread(launcher.recoger, token, timeout)


@mcp.tool
async def cerrar_selector(token: str) -> dict:
    """Cierra a la fuerza una ventana que quedó abierta. Úsala solo si el usuario
    dice que ya no la quiere: le quita de la pantalla algo que él no pidió cerrar."""
    return await asyncio.to_thread(launcher.cerrar, token)


@mcp.tool
async def cargar_memorias(ids: list[str], sesion: str | None = None) -> dict:
    """Trae el contexto completo de esas memorias por id (y marca su uso).

    Es el segundo paso del modo chat: después de que el usuario elige por número.
    `sesion`: igual que en `abrir_selector`."""
    return await asyncio.to_thread(launcher.cargar, ids, sesion)


@mcp.tool
async def olvidar_cargadas(sesion: str | None = None) -> dict:
    """Olvida qué memorias se cargaron en esta conversación (las deja de marcar ●).

    Llámala cuando el contexto se haya vaciado y lo cargado ya no esté presente:
    típicamente **después de un compact**, del que ningún servidor MCP se entera.
    No la llames por otras razones: perder esas marcas hace que el usuario vuelva
    a cargar lo que ya tenía. `sesion`: igual que en `abrir_selector`."""
    return await asyncio.to_thread(launcher.olvidar, sesion)


def main() -> None:
    if not sys.platform.startswith("win"):
        os.environ.setdefault("MEMORY_TUI", "off")  # sin consola nueva -> modo chat
    mcp.run()  # stdio: stdout es del protocolo, nada más puede escribir ahí


if __name__ == "__main__":
    main()
