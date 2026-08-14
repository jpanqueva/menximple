"""Servidor MCP (FastMCP, Streamable HTTP). Única fuente de verdad vía API.

La cuenta se deriva de la apikey (header X-API-Key) — no se pasa como argumento.
Las tools envuelven el repositorio y traducen MemoriaError -> ToolError con mensaje
accionable. Los errores inesperados se propagan (fail-fast, sin silenciar)."""
from fastmcp import FastMCP
from fastmcp.exceptions import ToolError

from . import auth
from . import canales
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
def listar(folder_id: str | None = None, incluir_archivadas: bool = False) -> dict:
    """Lista el contenido de una carpeta (subcarpetas y entradas).
    Sin `folder_id` devuelve la raíz **más la guía para mantener la cuenta
    ordenada**: pídela antes de crear carpetas o reorganizar. Para ver todo de un
    vistazo usa `arbol`. Lo borrado no sale salvo `incluir_archivadas=True`."""
    return _g(repo.listar, auth.cuenta_actual(), folder_id, incluir_archivadas)


@mcp.tool
def arbol(folder_id: str | None = None, profundidad: int = 6,
          con_memorias: bool = True, incluir_archivadas: bool = False) -> dict:
    """El árbol de la cuenta en texto: consecutivo, tipo, estado, tamaño y uso de
    cada memoria (`340 tok · 4 cargas · hace 2 h`, o `nunca cargada`).

    **Si no conoces la cuenta, empieza por el mapa barato:**

        arbol(con_memorias=False, profundidad=3)

    Eso te da solo las carpetas — de qué van los proyectos, cómo están organizados —
    en una respuesta pequeña. Con ese mapa ya puedes bajar a la rama que importa
    (`arbol(folder_id="radicapro/clientes/insumedic")`) o filtrar la búsqueda
    (`buscar(query=..., folder_id="insumedic")`) sin traerte la cuenta entera.

    El árbol completo con memorias es útil cuando pregunten "qué memorias tengo",
    **cuando algo no aparezca buscando** (enséñaselo antes de decir que no existe),
    y para que elijan por número si no hay selector visual. Pero en una cuenta
    grande es mucho contexto: no es el primer reflejo, es el segundo.

    `folder_id` acepta id, nombre o ruta; `profundidad` cuenta desde ahí (lo cortado
    se anuncia); `con_memorias=False` deja solo las carpetas."""
    return _g(repo.arbol, auth.cuenta_actual(), folder_id, profundidad,
              con_memorias, incluir_archivadas)


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
                  tipo: str, tags: list[str] | None = None,
                  estado: str | None = None) -> dict:
    """Guarda una memoria en una carpeta. `tipo`: credencial|skill|general|historical.
    `folder_id` acepta el id, el nombre o la ruta (`radicapro/clientes/insumedic`).

    El `resumen` es lo que se indexa: escríbelo con las palabras que el usuario
    usaría al preguntar, no con las del título.

    `estado` (opcional): pendiente|en_curso|hecho|bloqueado. Ponlo si la memoria
    describe trabajo; déjalo vacío para lo que no tiene estado (una credencial,
    un glosario). No metas el estado en el título — para eso está este campo.

    **Si el hecho se puede comprobar, incluye en el `contexto` el comando exacto
    que lo comprueba.** Una memoria técnica sin forma de re-verificarse envejece
    sin que nadie lo note, y el que venga después no tiene cómo saber si sigue
    siendo cierta."""
    return _g(repo.crear_entrada, auth.cuenta_actual(), folder_id, titulo, resumen,
              contexto, tipo, tags, estado)


@mcp.tool
def editar_entrada(entry_id: str, titulo: str | None = None, resumen: str | None = None,
                   contexto: str | None = None, tipo: str | None = None,
                   tags: list[str] | None = None, mover_a: str | None = None,
                   estado: str | None = None) -> dict:
    """Edita una entrada. Guarda snapshot de la versión previa en el historial y
    re-embebe si cambió el `resumen`. `mover_a` = carpeta destino (id, nombre o
    ruta; una entrada siempre vive dentro de una carpeta, así que no admite raíz).

    **Solo se toca lo que mandes**: omitir `contexto` lo deja intacto, así que
    cambiar el estado o el título no te obliga a reenviar el cuerpo.
    **Para agregar información usa `anexar_entrada`**, no esta: reescribir el
    contexto entero para añadir un párrafo es como se pierden párrafos.

    `estado`: pendiente|en_curso|hecho|bloqueado, o `""` para quitarlo."""
    return _g(repo.editar_entrada, auth.cuenta_actual(), entry_id, titulo, resumen,
              contexto, tipo, tags, mover_a, estado)


@mcp.tool
def anexar_entrada(entry_id: str, texto: str, resumen: str | None = None,
                   estado: str | None = None) -> dict:
    """Añade `texto` al final del contexto de una memoria, **sin reenviar lo que ya
    tenía**. Es la forma correcta de sumar un hallazgo, una corrección o un avance.

    Úsala en vez de `editar_entrada(contexto=...)` siempre que estés agregando y no
    reemplazando: lo anterior queda intacto, no depende de que lo tengas en
    contexto, y no pisas el trabajo de otro agente.

    Puedes actualizar de paso el `resumen` (es el campo por el que se busca: si lo
    dejas viejo, la memoria se vuelve difícil de encontrar) y el `estado`.
    `entry_id` acepta el consecutivo (`"82"`)."""
    return _g(repo.anexar_entrada, auth.cuenta_actual(), entry_id, texto, resumen, estado)


@mcp.tool
def obtener_entrada(entry_id: str, marcar_uso: bool = True) -> dict:
    """Devuelve una entrada completa (incluye `contexto`) y marca su uso.
    `entry_id` acepta el uuid o el consecutivo (`"11"` o `"#11"`).
    Usa `marcar_uso=False` solo para previsualizar sin registrar la carga."""
    return _g(repo.obtener_entrada, auth.cuenta_actual(), entry_id, marcar_uso)


@mcp.tool
def cargar_carpeta(carpeta: str, con_subcarpetas: bool = True) -> dict:
    """Carga **todas** las memorias de una carpeta de una vez ("cárgame todo insumedic").

    `carpeta` acepta el id, el nombre (`rips`) o la ruta (`insumedic/rips`); si el
    nombre se repite en varios sitios te dice cuáles son para que elijas.
    `con_subcarpetas=False` se queda en el primer nivel.

    **Mira el tamaño antes.** El `arbol()` da los tokens de cada memoria: una rama
    entera puede ser mucho contexto y el usuario lo paga en toda la conversación.
    Si suma demasiado, enséñale el árbol y que elija por número. La respuesta trae
    `tokens` con el total cargado."""
    return _g(repo.cargar_carpeta, auth.cuenta_actual(), carpeta, con_subcarpetas)


@mcp.tool
def cargar_contexto(entry_ids: list[str]) -> dict:
    """Devuelve el `contexto` completo de varias entradas y marca su uso.
    Es la tool para cargar memorias al contexto del agente.

    Cada id puede ser el uuid o el **consecutivo**: si el usuario dice "carga la 11
    y la 4", llama directamente con `["11", "4"]` — no busques primero.

    Al usar lo que traigas, **cita el número** ("según #82, el bug está en
    Armado.vue"). El usuario no puede distinguir una memoria leída de una
    suposición tuya que suena bien; el número es lo que se lo hace comprobable."""
    memorias = _g(repo.cargar_contexto, auth.cuenta_actual(), entry_ids)
    return {
        "memorias": memorias,
        "recuerda": "cita el #numero de la memoria cuando te apoyes en ella; "
                    "si algo no salió de aquí, dilo.",
    }


# --- Borrar = archivar (reversible) ---

@mcp.tool
def borrar_entrada(entry_id: str, motivo: str | None = None) -> dict:
    """Borra una memoria. **No la destruye**: la archiva, así que deja de salir en
    `listar`/`buscar` pero vuelve con `restaurar_entrada`. Confírmalo igual con el
    usuario: para él es un borrado. `motivo` queda guardado."""
    return _g(repo.archivar_entrada, auth.cuenta_actual(), entry_id, True, motivo)


@mcp.tool
def restaurar_entrada(entry_id: str) -> dict:
    """Devuelve al árbol una memoria borrada."""
    return _g(repo.archivar_entrada, auth.cuenta_actual(), entry_id, False, None)


@mcp.tool
def borrar_carpeta(folder_id: str, motivo: str | None = None) -> dict:
    """Borra una carpeta **con todo lo que cuelga de ella**. Tampoco destruye:
    archiva, y `arrastradas` dice cuántas cosas se fueron con ella. Confírmalo con
    el usuario: puede llevarse mucho más de lo que él cree."""
    return _g(repo.archivar_carpeta, auth.cuenta_actual(), folder_id, True, motivo)


@mcp.tool
def restaurar_carpeta(folder_id: str) -> dict:
    """Devuelve al árbol una carpeta borrada y lo que se archivó junto con ella.
    Lo que ya estaba borrado por su cuenta se queda borrado."""
    return _g(repo.archivar_carpeta, auth.cuenta_actual(), folder_id, False, None)


@mcp.tool
def ver_historial(entry_id: str) -> dict:
    """Versiones anteriores de una memoria, de la más nueva a la más vieja.

    Cada `editar_entrada` guarda la versión previa completa. Úsala para ver qué
    decía antes o para recuperar un texto que se sobrescribió."""
    return _g(repo.ver_historial, auth.cuenta_actual(), entry_id)


# --- Búsqueda ---

@mcp.tool
def buscar(query: str = "", tipo: str | None = None, folder_id: str | None = None,
           tags: list[str] | None = None, limit: int = 15,
           incluir_archivadas: bool = False, estado: str | None = None,
           alcance: str = "resumen", detallado: bool = False) -> list[dict]:
    """Busca entradas. Devuelve resúmenes, no el contexto: para eso está
    `cargar_contexto`. Pásale la frase del usuario tal cual: casa por palabra suelta
    y por prefijo, ignora tildes y ordena por aciertos. Un `query` que sea solo un
    número (o `#12`) busca por consecutivo.

    **Filtra en vez de traerlo todo** — es más barato y más preciso que leer el árbol:
    - `estado`: pendiente|en_curso|hecho|bloqueado. `buscar(estado="pendiente")`
      responde "¿qué me queda pendiente?" en una llamada.
    - `tipo`: credencial|skill|general|historical
    - `folder_id`: acota a una rama; acepta id, nombre o ruta (`insumedic/rips`)
    - `tags`: transversales (`["facturacion"]`)

    `alcance` decide qué tan hondo mira:
    - `"resumen"` (default): título, resumen y tags. Es lo que quieres casi siempre.
    - `"completo"`: además busca **dentro del cuerpo** de las memorias. Úsalo cuando
      busques algo mencionado de pasada —un comando, un id, un nombre de archivo, un
      error— que no estaría en ningún resumen. Trae más ruido.

    `detallado=True` agrega uuid, tags, versión y fechas; por defecto la respuesta es
    compacta para no gastar contexto en metadatos que no vas a usar."""
    return _g(repo.buscar, auth.cuenta_actual(), query, tipo, folder_id, tags, limit,
              incluir_archivadas, estado, alcance, detallado)


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


# --- Canales entre agentes ---
#
# Un canal es una sala de DOS agentes, que pueden estar en máquinas y cuentas
# distintas. A diferencia de las memorias, los canales NO están aislados por
# cuenta: de eso se trata. El aislamiento lo da la membresía.
#
# El hub guarda y entrega. Quien DESPIERTA a un agente que está esperando es el
# puente local (`canal/menx-canal.mjs`), que empuja lo que llega a la sesión de
# Claude Code como evento de canal.

@mcp.tool
def crear_canal(nombre: str, descripcion: str | None = None,
                agente: str | None = None) -> dict:
    """Crea un canal para hablar con otro agente. El nombre se normaliza a
    minúsculas y es como se entra desde el otro lado.

    **Pasa `agente` con tu nombre**: crear el canal no te mete en él, y sin eso tu
    primer `enviar_mensaje` falla."""
    return _g(canales.crear_canal, nombre, descripcion, agente)


@mcp.tool
def listar_canales() -> list[dict]:
    """Los canales que existen, quién está en cada uno y cuántos cupos quedan
    (son 2 por canal). Empieza por aquí antes de crear uno."""
    return _g(canales.listar_canales)


@mcp.tool
def unirse_canal(canal: str, agente: str) -> dict:
    """Entra a un canal con un nombre de agente (`qa-ubuntu`, `jhon-windows`).

    Ese nombre es como te llama el otro lado, así que ponlo reconocible. Un canal
    admite 2 agentes; **tú puedes estar en varios canales a la vez**. Volver a
    entrar con el mismo nombre no es error: retomas donde ibas."""
    return _g(canales.unirse_canal, canal, agente)


@mcp.tool
def salir_canal(canal: str, agente: str) -> dict:
    """Deja el canal y libera el cupo."""
    return _g(canales.salir_canal, canal, agente)


@mcp.tool
def enviar_mensaje(canal: str, agente: str, texto: str, acuse: bool = False) -> dict:
    """Escribe en el canal. `agente` eres tú, no el destinatario: como son dos, el
    mensaje va al otro sin que haya que decir a quién.

    Si el otro tiene el puente local corriendo, esto **le interrumpe la espera** y
    lo pone a trabajar. Escribe el mensaje completo: el otro no ve tu conversación
    ni tus archivos, solo este texto.

    `acuse=True` lo marca como acuse de recibo, para que el otro lado no conteste
    un acuse con otro acuse. Normalmente no lo pones tú: lo manda el puente solo."""
    return _g(canales.enviar_mensaje, canal, agente, texto, acuse)


@mcp.tool
def recibir_mensajes(canal: str, agente: str, espera: int = 0) -> dict:
    """Lo que te hayan escrito y no hayas leído. `espera` en segundos deja la
    llamada colgada hasta que llegue algo (máximo 110; Claude Code corta a los 120).

    Úsala para esperar la respuesta después de preguntar algo. Si vuelve vacía, el
    otro no ha contestado: puedes reintentar o seguir con lo tuyo."""
    return _g(canales.recibir, canal, agente, espera)


@mcp.tool
def mis_canales(agente: str) -> list[dict]:
    """En qué canales estás con ese nombre de agente."""
    return _g(canales.mis_canales, agente)


@mcp.tool
def recibir_de_todos(agente: str, espera: int = 0) -> dict:
    """Lo pendiente en **todos** tus canales de una vez. Es lo que usa el puente
    local; a mano sirve para "¿me escribió alguien?" sin ir canal por canal."""
    return _g(canales.recibir_todo, agente, espera)


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
