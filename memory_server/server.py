"""Servidor MCP (FastMCP, Streamable HTTP). Única fuente de verdad vía API.

La cuenta se deriva de la apikey (header X-API-Key) — no se pasa como argumento.
Las tools envuelven el repositorio y traducen MemoriaError -> ToolError con mensaje
accionable. Los errores inesperados se propagan (fail-fast, sin silenciar)."""
import asyncio
from urllib.parse import quote

from fastmcp import FastMCP
from fastmcp.exceptions import ToolError
from starlette.requests import Request
from starlette.responses import FileResponse, JSONResponse, PlainTextResponse

from . import archivos, registro
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


async def _ga(fn, *args, **kwargs):
    """Igual que `_g` para las tools async (las esperas de canal)."""
    try:
        return await fn(*args, **kwargs)
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


# --- Catálogo: equipos, ámbitos, actividades, agentes ---
#
# Nomenclatura estricta (decisión del usuario, sep-2026): agentes
# `agt-<equipo>-<ambito>-<rol>`, canales `canal-<equipo1>-<equipo2>-<actividad>`
# o `canal-<ambito>-<actividad>`. Equipos, ámbitos y actividades salen de este
# catálogo; lo que no esté aquí no puede ni identificarse ni crear canales.

@mcp.tool
def registro_ver(clase: str | None = None, nombre: str | None = None,
                 hostname: str | None = None) -> list[dict]:
    """El catálogo de nombres: `equipo` (máquinas, con su hostname), `ambito`
    (empresas y proyectos), `actividad` (para qué es un canal) y `agente` (quién
    existe, en qué equipo y ámbito, y cuándo se le vio por última vez).

    Sin argumentos devuelve todo (es corto). `clase` filtra; `nombre` busca uno;
    `hostname` sirve para saber qué equipo es esta máquina (`hostname` en la
    consola) antes de identificarte."""
    return _g(registro.ver, clase, nombre, hostname)


@mcp.tool
def registro_crear(clase: str, nombre: str, hostname: str | None = None,
                   tipo: str | None = None, dueno: str | None = None,
                   descripcion: str | None = None) -> dict:
    """Da de alta un `equipo` (necesita `hostname` y `tipo` pc|servidor), un
    `ambito` (necesita `tipo` empresa|proyecto) o una `actividad`. Los agentes NO
    se crean aquí: se registran solos la primera vez que un nombre válido entra a
    un canal. Solo con el usuario diciéndolo: un catálogo no se llena por
    iniciativa propia. No hay editar ni borrar."""
    return _g(registro.crear, clase, nombre, auth.cuenta_actual(), hostname, tipo, dueno,
              descripcion)


@mcp.tool
def registro_anotar(agente: str, descripcion: str) -> dict:
    """Escribe la FICHA de un agente (hasta 600 caracteres): qué hace, en qué va,
    qué espera. Es lo único del catálogo que se edita: es estado, no catálogo. La
    mantiene quien coordina (el CEO sobre sus workers) o el propio agente. Se lee
    con `registro_ver(clase='agente')`."""
    return _g(registro.anotar, agente, descripcion)


# --- Canales entre agentes ---
#
# Un canal es una SALA de agentes (sin tope), que pueden estar en máquinas y
# cuentas distintas. Un mensaje puede ir dirigido (`para`) a un miembro: solo a
# ese se le empuja y solo él acusa; sin `para` va a todos. A diferencia de las memorias, los canales NO están aislados por
# cuenta: de eso se trata. El aislamiento lo da la membresía.
#
# El hub guarda y entrega. Quien DESPIERTA a un agente que está esperando es el
# puente local (`canal/menx-canal.mjs`), que empuja lo que llega a la sesión de
# Claude Code como evento de canal.

@mcp.tool
def crear_canal(nombre: str, descripcion: str | None = None,
                agente: str | None = None, tags: list[str] | None = None) -> dict:
    """Crea un canal. El nombre sigue la nomenclatura del catálogo:
    `canal-<equipo1>-<equipo2>-<actividad>` (dos equipos, en orden alfabético) o
    `canal-<ambito>-<actividad>` (sala de un ámbito, para varios agentes). Los
    equipos, ámbitos y actividades tienen que existir (`registro_ver`); si no, se
    rechaza. La actividad y el ámbito se agregan solos como tags.

    **Pasa `agente` con tu nombre**: crear el canal no te mete en él, y sin eso tu
    primer `enviar_mensaje` falla.

    `tags` (opcional) dice QUÉ ES el canal; viajan con cada mensaje para que quien
    lo reciba sepa cómo tratarlo. Vocabulario recomendado: `proyecto:<nombre>`,
    `tipo:<voz|pantalla|avisos|devops|worker>`, `efimero`, `sin-acuse`."""
    return _g(canales.crear_canal, nombre, descripcion, agente, auth.cuenta_actual(), tags)


@mcp.tool
def editar_canal(canal: str, descripcion: str | None = None,
                 tags: list[str] | None = None) -> dict:
    """Cambia la descripción y/o los tags de un canal existente. Lo que no pases no
    se toca. Los `tags` REEMPLAZAN a los anteriores (`[]` los quita todos).

    Solo puedes editar un canal que creaste o en el que estás."""
    return _g(canales.editar_canal, canal, descripcion, tags, auth.cuenta_actual())


@mcp.tool
def listar_canales(tags: list[str] | None = None) -> list[dict]:
    """**Tus** canales —los que creaste y en los que estás—, con la ficha de cada
    miembro (cuánto tiene sin leer, cuándo escribió y leyó por última vez), sus
    tags y el total de mensajes. Empieza por aquí antes de crear.

    `tags` filtra: solo los que tengan TODOS los pedidos. Un tag terminado en `:`
    casa por prefijo (`["proyecto:"]` = los que tengan algún proyecto). Úsalo para
    no traerte los canales de otros proyectos: `listar_canales(tags=["proyecto:x"])`.

    No lista los de otras cuentas. Si te dieron el nombre de uno, `unirse_canal`
    entra igual aunque no salga en esta lista.

    "Tuyos" es **por cuenta, no por agente**: si otro agente comparte tu apikey,
    sus canales te salen aquí aunque no hayas entrado. Normal cuando los dos son
    del mismo dueño; tenlo en cuenta antes de suponer que un canal es tuyo."""
    return _g(canales.listar_canales, auth.cuenta_actual(), tags)


@mcp.tool
def borrar_canal(canal: str) -> dict:
    """Borra un canal y todos sus mensajes. **Esto sí destruye**: no se archiva ni
    se puede restaurar, a diferencia de las memorias. Confírmalo con el usuario.

    Solo puedes borrar un canal que creaste o en el que estás."""
    return _g(canales.borrar_canal, canal, auth.cuenta_actual())


@mcp.tool
def unirse_canal(canal: str, agente: str) -> dict:
    """Entra a un canal con tu nombre de agente, que tiene que seguir la
    nomenclatura `agt-<equipo>-<ambito>-<rol>` con equipo y ámbito del catálogo
    (si no, se rechaza y te dice por qué). Un canal no tiene tope de miembros;
    **puedes estar en varios a la vez**. Volver a entrar no es error: retomas
    donde ibas."""
    return _g(canales.unirse_canal, canal, agente, auth.cuenta_actual())


@mcp.tool
def salir_canal(canal: str, agente: str) -> dict:
    """Deja el canal y libera el cupo."""
    return _g(canales.salir_canal, canal, agente)


@mcp.tool
def enviar_mensaje(canal: str, agente: str, texto: str, acuse: bool = False,
                   para: str | None = None) -> dict:
    """Escribe en el canal. `agente` eres tú. `para` es el destinatario (un miembro
    del canal): todos lo pueden leer, pero solo a él se le empuja al terminal y
    solo él acusa. Sin `para`, va a todos los miembros (un aviso, un "empiezo").

    Si el otro tiene el puente local corriendo, esto **le interrumpe la espera** y
    lo pone a trabajar. Escribe el mensaje completo: el otro no ve tu conversación
    ni tus archivos, solo este texto.

    `acuse=True` lo marca como acuse de recibo, para que el otro lado no conteste
    un acuse con otro acuse. Normalmente no lo pones tú: lo manda el puente solo."""
    return _g(canales.enviar_mensaje, canal, agente, texto, acuse, para)


@mcp.tool
async def recibir_mensajes(canal: str, agente: str, espera: int = 0) -> dict:
    """Lo que te hayan escrito y no hayas leído. `espera` en segundos deja la
    llamada colgada hasta que llegue algo (máximo 110; Claude Code corta a los 120).

    Úsala para esperar la respuesta después de preguntar algo. Si vuelve vacía, el
    otro no ha contestado: puedes reintentar o seguir con lo tuyo."""
    return await _ga(canales.recibir_async, canal, agente, espera)


@mcp.tool
def mis_canales(agente: str, tags: list[str] | None = None) -> list[dict]:
    """En qué canales estás con ese nombre de agente, con sus tags. `tags` filtra
    igual que en `listar_canales`."""
    return _g(canales.mis_canales, agente, tags)


@mcp.tool
async def recibir_de_todos(agente: str, espera: int = 0, marcar: bool = True) -> dict:
    """Lo pendiente en **todos** tus canales de una vez. Es lo que usa el puente
    local; a mano sirve para "¿me escribió alguien?" sin ir canal por canal.

    `marcar=False` no da nada por leído — solo para quien vaya a confirmar
    después con `confirmar_entrega`."""
    return await _ga(canales.recibir_todo_async, agente, espera, marcar)


@mcp.tool
def confirmar_entrega(canal: str, agente: str, hasta: int) -> dict:
    """Da por leído hasta ese `seq`. La usa el puente cuando el mensaje ya entró
    de verdad en la sesión; a mano no hace falta."""
    return _g(canales.confirmar_entrega, canal, agente, hasta)


# --- Archivos publicados ---
#
# Dos rutas HTTP normales además de las tools, porque los bytes no pueden viajar
# por una tool: el modelo tendría que escribir el archivo entero en base64 y cada
# byte le cuesta. Quien sube es un proceso local (`publicar_archivo` del MCP del
# selector) que lee la ruta del disco y hace el POST.
#
# La subida cuelga de /mcp/archivos a propósito: el nginx de producción ya manda
# todo /<prefijo>/api/* a /mcp/*, así que no hace falta abrir otra ruta ni inventarle al
# cliente una URL aparte — es MEMORY_BASE_URL + "/archivos".

@mcp.custom_route("/mcp/archivos", methods=["POST"])
async def subir_archivo(request: Request) -> JSONResponse:
    """POST con el archivo como cuerpo crudo. Query: `nombre` (obligatorio),
    `expira_dias`, `descripcion`. Content-Type = mime del archivo."""
    try:
        cta = await asyncio.to_thread(auth.cuenta_de, auth.apikey_de_headers(request.headers))
    except MemoriaError as e:
        return JSONResponse({"error": str(e)}, status_code=401)

    # Quien sube desde un <input type=file> arma un FormData por reflejo, y sin este
    # rechazo se guardaba el cuerpo del form entero con un 201: archivo corrupto y
    # ningún error. Lo reportó el primer cliente Node que lo usó.
    if (request.headers.get("content-type") or "").lower().startswith("multipart/"):
        return JSONResponse({"error": "el cuerpo va con los bytes crudos del archivo, "
                                      "no multipart/form-data; Content-Type = mime del "
                                      "archivo y el nombre en la query (?nombre=...)"},
                            status_code=415)

    maximo = settings.archivos_max_mb * archivos.MB
    declarado = request.headers.get("content-length")
    if declarado and declarado.isdigit() and int(declarado) > maximo:
        return JSONResponse({"error": f"el máximo es {settings.archivos_max_mb} MB"},
                            status_code=413)
    # Se cuenta mientras llega y no solo por Content-Length, que lo manda el cliente.
    trozos, total = [], 0
    async for trozo in request.stream():
        total += len(trozo)
        if total > maximo:
            return JSONResponse({"error": f"el máximo es {settings.archivos_max_mb} MB"},
                                status_code=413)
        trozos.append(trozo)

    q = request.query_params
    try:
        expira = float(q["expira_dias"]) if q.get("expira_dias") else None
    except ValueError:
        return JSONResponse({"error": "`expira_dias` tiene que ser un número"},
                            status_code=400)
    if not q.get("nombre"):
        return JSONResponse({"error": "falta `nombre` en la query"}, status_code=400)
    try:
        out = await asyncio.to_thread(
            archivos.publicar, cta, q["nombre"], b"".join(trozos),
            request.headers.get("content-type"), expira, q.get("descripcion"))
    except MemoriaError as e:
        return JSONResponse({"error": str(e)}, status_code=400)
    return JSONResponse(out, status_code=201)


@mcp.custom_route("/f/{token}", methods=["GET"])
@mcp.custom_route("/f/{token}/{nombre}", methods=["GET"])
async def ver_archivo(request: Request):
    """El link público. Sin apikey: el token es el permiso."""
    hallado = await asyncio.to_thread(archivos.para_servir, request.path_params["token"])
    if hallado is None:
        # Igual para inexistente, borrado y vencido: no se confirma que existió.
        return PlainTextResponse("no existe o ya no está disponible", status_code=404)
    a, ruta = hallado
    cabeceras = {
        "Content-Disposition": f"inline; filename*=UTF-8''{quote(a['nombre'])}",
        "X-Content-Type-Options": "nosniff",
        # El token va en la URL: que no se filtre por Referer a donde enlace el archivo.
        "Referrer-Policy": "no-referrer",
        "X-Robots-Tag": "noindex, nofollow",
        "Cache-Control": "private, max-age=60",
    }
    if a["mime"] in archivos.ACTIVOS:
        # Un HTML publicado corre en un origen opaco, no en el del hub: sus scripts
        # funcionan pero no pueden leer ni llamar nada de menximple.mdtools.io. No
        # se aplica a todo porque el visor de PDF de Chrome se niega a abrir con
        # `sandbox`.
        cabeceras["Content-Security-Policy"] = "sandbox allow-scripts allow-popups"
    return FileResponse(ruta, media_type=a["mime"], headers=cabeceras)


@mcp.tool
def listar_archivos() -> list[dict]:
    """Los archivos que ha publicado tu cuenta, con su URL, tamaño y si ya vencieron.

    Para **publicar** uno no es esta: los bytes no pueden viajar por una tool del hub.
    Usa `publicar_archivo` del servidor local `menximple-selector`, que lee la ruta
    del disco y lo sube."""
    return _g(archivos.listar, auth.cuenta_actual())


@mcp.tool
def borrar_archivo(archivo: str) -> dict:
    """Borra un archivo publicado por su `id` o por su URL. **Esto sí destruye**: el
    link deja de abrir para todos a quien se lo mandaron y no se puede restaurar.
    Confírmalo con el usuario."""
    return _g(archivos.borrar, auth.cuenta_actual(), archivo)


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
    # El MCP se sirve en /mcp; la ofuscación del path público (ej. /<prefijo>/api) la hace el
    # reverse proxy (nginx) mapeando /<prefijo>/api -> /mcp.
    registro.sembrar()          # las actividades base, si el catálogo está vacío
    mcp.run(transport="http", host=settings.mcp_host, port=settings.mcp_port)


if __name__ == "__main__":
    main()
