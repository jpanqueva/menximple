"""Canales de conversación entre agentes.

Un canal es una **sala** (como en IRC) de agentes que pueden estar en máquinas,
cuentas y países distintos. Sin tope de miembros. Un mensaje puede ir **dirigido**
(`para`) a un miembro: todos pueden leerlo, pero solo a ese se le empuja al
terminal y solo él acusa recibo; sin `para`, va a todos.

Los nombres son estrictos y salen del catálogo (`registro.py`): agentes
`agt-<equipo>-<ambito>-<rol>` y canales `canal-<equipo1>-<equipo2>-<actividad>` o
`canal-<ambito>-<actividad>`. Lo que no cumpla el formato se rechaza. Fue una
decisión del usuario tras una semana de agentes con nombres inventados y máquinas
que fallaban sin que se supiera cuáles eran. El hub solo guarda y entrega; quien despierta a un agente que
está esperando es el puente local (`canal/menx-canal.mjs`), que empuja el mensaje
a la sesión de Claude Code como evento de canal.

Dos decisiones que conviene entender antes de tocar esto:

- **Un canal cruza cuentas, pero el catálogo no.** El sentido es que el agente de
  una cuenta le hable al de otra, así que la **membresía** manda: solo los dos que
  están dentro leen y escriben, sin importar de qué cuenta sean. Pero `listar_canales`
  sí filtra —los que creaste y en los que estás—, porque sin eso cualquiera con una
  apikey enumeraba los canales ajenos con su nombre y su descripción. Entrar a uno
  de otra cuenta sigue siendo posible por el nombre exacto: se comparte como un
  enlace de reunión, te lo pasan, no lo encuentras.
- **La unidad de aislamiento es la CUENTA, no el agente.** Dos agentes que comparten
  apikey se ven los canales del otro sin haber entrado, porque para `_mia` basta con
  que coincida la cuenta del creador. Es lo correcto cuando los dos agentes son del
  mismo dueño —el caso normal— pero significa que correr agentes de clientes
  distintos bajo una sola apikey los deja enumerarse entre sí. Si hiciera falta
  separarlos, la cuenta es la línea: una apikey por cliente.
- **Sin tope de miembros, mensajes dirigidos.** Antes eran salas de dos, para que
  "el otro" no fuera ambiguo. Con varios miembros, `para` dice a quién va; un
  mensaje sin `para` es para todos (un aviso, un "empiezo").
"""
import functools
import threading

from . import registro, store
from .models import MemoriaError

ESPERA_MAX = 110      # Claude Code corta las tools a los 120 s; ver `recibir`.
RETROCESO = 20        # cuánto historial ve quien entra; ver `unirse_canal`.
TAGS_MAX = 8          # por canal
TAG_LARGO = 40


# --- Tags ------------------------------------------------------------------ #
# Un canal puede llevar tags: texto corto que dice QUÉ ES el canal, para que el
# agente que recibe un mensaje sepa cómo tratarlo sin tener la regla escrita en
# otro lado. NO sirven para descubrir canales (eso ya lo hace la membresía:
# `mis_canales` y `recibir_todo` van por agente), sino para darles significado y
# para filtrar el catálogo por proyecto.
#
# Son texto libre, pero conviene un vocabulario corto y compartido:
#   proyecto:<nombre>   a qué proyecto pertenece        (proyecto:sagente)
#   tipo:<clase>        qué clase de canal es           (tipo:voz, tipo:pantalla,
#                                                        tipo:avisos, tipo:devops,
#                                                        tipo:worker)
#   efimero             se puede borrar al terminar
#   sin-acuse           el puente NO manda acuse automático (al otro lado hay un
#                       proceso que no los lee, o el acuse solo hace ruido)

def _norm_tags(tags) -> list[str]:
    """Normaliza: minúsculas, sin espacios alrededor, sin repetidos, con tope."""
    if tags is None:
        return []
    if isinstance(tags, str):                    # "a, b" también vale
        tags = tags.split(",")
    salida: list[str] = []
    for t in tags:
        t = " ".join(str(t or "").strip().lower().split())
        if not t or t in salida:
            continue
        if len(t) > TAG_LARGO:
            raise MemoriaError(f"el tag '{t[:20]}…' pasa de {TAG_LARGO} caracteres")
        if "," in t:
            raise MemoriaError(f"un tag no puede llevar coma: '{t}'")
        salida.append(t)
    if len(salida) > TAGS_MAX:
        raise MemoriaError(f"un canal admite máximo {TAGS_MAX} tags")
    return salida


def _con_tags(c: dict, tags: list[str]) -> bool:
    """¿El canal tiene TODOS los tags pedidos? Un tag que acaba en ':' o en '*'
    casa por prefijo: `proyecto:` encuentra cualquier proyecto."""
    suyos = c.get("tags") or []
    for t in tags:
        if t.endswith(":") or t.endswith("*"):
            pref = t.rstrip("*")
            if not any(s.startswith(pref) for s in suyos):
                return False
        elif t not in suyos:
            return False
    return True


# --- Un canal se escribe de a uno ------------------------------------------ #
# El canal es UN documento (descripción, tags, `seq`, y el `visto` de cada
# miembro) y todo lo que lo toca hace leer-modificar-guardar del documento
# ENTERO. Dos operaciones a la vez sobre el mismo canal se pisaban: la segunda en
# guardar devolvía `seq` a su valor viejo, el siguiente mensaje REPETÍA número, y
# quien lo esperaba —que pide "lo que tenga seq mayor que el último que vi"— no
# lo veía nunca. Se perdía en silencio, con el hub diciendo "entregado".
#
# Pasó el 2026-09-19, tres veces en una hora: un RESULTADO de un worker y un
# mensaje de voz al usuario. Los pares que chocaron: `editar_canal` con
# `enviar_mensaje`, y —el más frecuente, porque ocurre justo al llegar cada
# mensaje— el long-poll de quien recibe marcando `visto` mientras el que envía
# todavía no había guardado el `seq` nuevo.
#
# El hub es un solo proceso (las tools síncronas van al threadpool), así que un
# cerrojo en memoria por canal basta. Todo el que escribe el canal lo toma y
# RELEE el documento ya dentro. Si algún día hay varios procesos, esto no alcanza:
# haría falta que `seq` y `visto` dejen de vivir en el mismo documento.
_CERROJOS: dict[str, threading.Lock] = {}
_CERROJOS_G = threading.Lock()


def _cerrojo(canal: str) -> threading.Lock:
    clave = (canal or "").strip().lower()
    with _CERROJOS_G:
        return _CERROJOS.setdefault(clave, threading.Lock())


def _de_a_uno(f):
    """La función entera corre con el cerrojo del canal (su primer argumento)."""
    @functools.wraps(f)
    def envuelta(canal, *a, **k):
        with _cerrojo(canal):
            return f(canal, *a, **k)
    return envuelta


def _marcar_visto(canal: str, agente: str, hasta: int) -> None:
    """Avanza el `visto` de un miembro, releyendo el canal dentro del cerrojo."""
    with _cerrojo(canal):
        c = _canal(canal)
        cambio = False
        for x in c.get("miembros", []):
            if x["agente"] == agente and hasta > x.get("visto", 0):
                x["visto"] = hasta
                x["leyo"] = store.now_ts()
                cambio = True
        if cambio:
            store.upsert(store.CANALES, c["_id"], c)


def _canal(nombre: str) -> dict:
    nombre = (nombre or "").strip().lower()
    if not nombre:
        raise MemoriaError("falta el nombre del canal")
    hallados = store.scroll(store.CANALES, must=[store.cond("nombre", nombre)], limit=1)
    if not hallados:
        raise MemoriaError(f"no existe el canal '{nombre}'; míralos con `listar_canales` "
                           "o créalo con `crear_canal`")
    return hallados[0]


def _agente(nombre: str, cta: str | None = None) -> str:
    """Nombre válido según el catálogo (`agt-<equipo>-<ambito>-<rol>`), ya
    registrado y con su `visto` al día. Lo que no cumpla el formato, o cuyo equipo
    o ámbito no existan, se rechaza con el motivo."""
    a = (nombre or "").strip()
    if not a:
        raise MemoriaError("falta el nombre del agente (agt-<equipo>-<ambito>-<rol>)")
    return registro.tocar_agente(a, cta)


def _miembro(c: dict, agente: str) -> dict:
    for m in c.get("miembros", []):
        if m["agente"] == agente:
            return m
    raise MemoriaError(f"'{agente}' no está en el canal '{c['nombre']}'; "
                       "entra primero con `unirse_canal`")


def _out(c: dict) -> dict:
    seq = c.get("seq", 0)
    return {
        "nombre": c["nombre"], "descripcion": c.get("descripcion"),
        "actividad": c.get("actividad"),
        **({"ambito": c["ambito"]} if c.get("ambito") else {}),
        **({"equipos": c["equipos"]} if c.get("equipos") else {}),
        "tags": c.get("tags") or [],
        "agentes": [m["agente"] for m in c.get("miembros", [])],
        # La ficha de cada miembro: con esto se ve, antes de escribirle a alguien,
        # si está vivo, cuándo habló por última vez y cuánto tiene sin leer.
        "miembros": [{"agente": m["agente"],
                      "pendientes": max(0, seq - m.get("visto", 0)),
                      "ultimo_escribio": store.iso(m.get("escribio")),
                      "ultimo_leyo": store.iso(m.get("leyo")),
                      "desde": store.iso(m.get("desde"))} for m in c.get("miembros", [])],
        "mensajes": seq,
        "ultimo_mensaje": store.iso(c.get("ultimo_ts")),
        "creado": store.iso(c.get("created_at")),
    }


def _mia(c: dict, cta: str | None) -> bool:
    """¿Este canal es de mi cuenta — lo creé o estoy dentro?"""
    if not cta:
        return True
    if c.get("cuenta") == cta:
        return True
    return any(m.get("cuenta") == cta for m in c.get("miembros", []))


def crear_canal(nombre: str, descripcion: str | None = None,
                agente: str | None = None, cta: str | None = None,
                tags=None) -> dict:
    """Crea el canal y, si le pasas `agente`, te mete dentro.

    Lo segundo no es un atajo: quien crea un canal es porque va a hablar en él, y
    obligarlo a un `unirse_canal` aparte solo servía para que su primer mensaje
    fallara con "no estás en el canal". Pasó la primera vez que alguien lo usó."""
    nombre = (nombre or "").strip().lower()
    if not nombre:
        raise MemoriaError("falta el nombre del canal")
    partes = registro.validar_canal(nombre)      # rechaza lo que no siga la nomenclatura
    tags = _norm_tags(tags)                      # antes de crear nada: si están mal, no se crea
    # La actividad y el ámbito viajan también como tags, que es lo que el puente
    # pone en cada mensaje entregado (tipo:voz, proyecto:sagente...).
    for t in ([f"tipo:{partes['actividad']}"] +
              ([f"proyecto:{partes['ambito']}"] if partes.get("ambito") else [])):
        if t not in tags:
            tags.append(t)
    if store.scroll(store.CANALES, must=[store.cond("nombre", nombre)], limit=1):
        raise MemoriaError(f"ya existe un canal '{nombre}'")
    ts = store.now_ts()
    payload = {"_id": store.nuevo_id(), "nombre": nombre, "descripcion": descripcion,
               "cuenta": cta, "miembros": [], "seq": 0, "tags": tags,
               "actividad": partes["actividad"], "ambito": partes.get("ambito"),
               "equipos": partes.get("equipos"),
               "created_at": ts, "updated_at": ts}
    store.upsert(store.CANALES, payload["_id"], payload)
    if agente:
        return unirse_canal(nombre, agente, cta)
    return _out(payload)


@_de_a_uno
def editar_canal(canal: str, descripcion: str | None = None, tags=None,
                 cta: str | None = None) -> dict:
    """Cambia la descripción y/o los tags de un canal que ya existe. Lo que venga
    en `None` no se toca; `tags=[]` los quita todos. Los tags REEMPLAZAN a los que
    había (no se suman): así lo que queda es exactamente lo que se pasó.

    Solo puede quien lo creó o quien está dentro, igual que borrarlo."""
    c = _canal(canal)
    if not _mia(c, cta):
        raise MemoriaError(f"'{c['nombre']}' no es un canal tuyo; solo puede editarlo "
                           "quien lo creó o quien está dentro")
    if descripcion is None and tags is None:
        raise MemoriaError("no hay nada que cambiar: pasa `descripcion`, `tags` o ambos")
    if descripcion is not None:
        c["descripcion"] = descripcion
    if tags is not None:
        c["tags"] = _norm_tags(tags)
    c["updated_at"] = store.now_ts()
    store.upsert(store.CANALES, c["_id"], c)
    return _out(c)


def listar_canales(cta: str | None = None, tags=None) -> list[dict]:
    """Los canales de esta cuenta: los que creó y en los que está.

    NO los lista todos. Los canales cruzan cuentas a propósito —ese es el sentido—
    pero eso vale para la MEMBRESÍA, no para el catálogo: sin este filtro, cualquiera
    con una apikey enumeraba los canales de los demás con su nombre y su descripción,
    que suele explicar justo lo que uno no quiere que se lea de rebote.

    Entrar a un canal de otra cuenta sigue siendo posible: `unirse_canal` acepta el
    nombre exacto aunque no salga aquí. Se comparte como un enlace de reunión — te lo
    pasan, no lo encuentras.

    `tags` filtra: solo los canales que tengan TODOS los pedidos (ver `_con_tags`)."""
    pedidos = _norm_tags(tags)
    cs = [c for c in store.scroll(store.CANALES, limit=500)
          if _mia(c, cta) and _con_tags(c, pedidos)]
    cs.sort(key=lambda c: c.get("nombre", ""))
    return [_out(c) for c in cs]


@_de_a_uno
def borrar_canal(canal: str, cta: str | None = None) -> dict:
    """Borra el canal y sus mensajes. **Esto sí destruye**, a diferencia del resto
    de menx: un canal es tráfico, no conocimiento, y lo que hace falta de verdad es
    poder limpiar los de prueba. Solo puede quien lo creó o quien está dentro."""
    c = _canal(canal)
    if not _mia(c, cta):
        raise MemoriaError(f"'{c['nombre']}' no es un canal tuyo; solo puede borrarlo "
                           "quien lo creó o quien está dentro")
    msgs = store.scroll(store.MENSAJES, must=[store.cond("canal_id", c["_id"])], limit=5000)
    for m in msgs:
        store.delete(store.MENSAJES, m["_id"])
    store.delete(store.CANALES, c["_id"])
    return {"borrado": c["nombre"], "mensajes_borrados": len(msgs),
            "agentes_que_estaban": [m["agente"] for m in c.get("miembros", [])]}


@_de_a_uno
def unirse_canal(canal: str, agente: str, cta: str | None = None) -> dict:
    c = _canal(canal)
    agente = _agente(agente, cta)
    miembros = c.get("miembros", [])

    ya = [m for m in miembros if m["agente"] == agente]
    if ya:
        # Reentrar no es un error: un agente que se reinicia vuelve al mismo sitio
        # y debe seguir leyendo desde donde iba, no perder su marca. Se aprovecha
        # para sellar la cuenta si el registro venía de antes de que existiera.
        if cta and not ya[0].get("cuenta"):
            ya[0]["cuenta"] = cta
            store.upsert(store.CANALES, c["_id"], c)
        return {**_out(c), "reentro": True, "leidos_hasta": ya[0].get("visto", 0)}

    # Quien llega SÍ lee lo que se dijo antes. La primera versión ponía la marca
    # en el último mensaje ("lo dicho antes de llegar no es suyo") y eso perdía en
    # silencio justo el mensaje que más importa: el que uno deja esperando a que
    # el otro entre. Se comprobó en el primer uso real — el que escribió creyó que
    # el otro lo vería al llegar, y no lo vio.
    #
    # Se limita a los últimos RETROCESO porque esto se inyecta en el contexto del
    # agente que entra, y volcarle un canal de doscientos mensajes lo paga el
    # usuario. Si se recortó, se dice.
    atras = max(0, c.get("seq", 0) - RETROCESO)
    miembros.append({"agente": agente, "visto": atras, "cuenta": cta,
                     "desde": store.now_ts(), "escribio": None, "leyo": None})
    c["miembros"] = miembros
    c["updated_at"] = store.now_ts()
    store.upsert(store.CANALES, c["_id"], c)
    out = _out(c)
    pendientes = c.get("seq", 0) - atras
    if pendientes:
        out["te_esperan"] = (f"{pendientes} mensaje(s) escritos antes de que entraras; "
                             "léelos con `recibir_mensajes`")
    if atras:
        out["recortado"] = f"no verás los {atras} primeros (tope de {RETROCESO})"
    return out


@_de_a_uno
def salir_canal(canal: str, agente: str) -> dict:
    c = _canal(canal)
    agente = _agente(agente)
    _miembro(c, agente)
    c["miembros"] = [m for m in c.get("miembros", []) if m["agente"] != agente]
    c["updated_at"] = store.now_ts()
    store.upsert(store.CANALES, c["_id"], c)
    return _out(c)


@_de_a_uno
def enviar_mensaje(canal: str, agente: str, texto: str, acuse: bool = False,
                   para: str | None = None) -> dict:
    """Escribe en el canal. `para` lo dirige a un miembro: todos lo pueden leer,
    pero solo a ese se le empuja y solo él acusa. Sin `para`, es para todos.
    `acuse=True` marca el mensaje como acuse de recibo.

    El acuse existe porque un encargo puede tardar mucho y, sin él, quien preguntó
    no distingue "todavía no lo ha leído" de "lo está trabajando". Va marcado para
    que el puente del otro lado no conteste un acuse con otro acuse: así es como
    dos agentes educados se saludan para siempre."""
    texto = (texto or "").strip()
    if not texto:
        raise MemoriaError("el mensaje está vacío")
    c = _canal(canal)
    agente = _agente(agente)
    yo = _miembro(c, agente)
    destino = None
    if para:
        destino = (para or "").strip().lower()
        if destino == agente:
            raise MemoriaError("`para` no puede ser tú mismo")
        _miembro(c, destino)             # tiene que estar en el canal
    yo["escribio"] = store.now_ts()

    # El contador del canal manda, pero se comprueba contra los mensajes que ya
    # existen: si alguna vez quedó atrasado (ver `_cerrojo`), no se repite número y
    # de paso se corrige solo. La consulta trae "los de seq mayor", que es ninguno.
    seq = c.get("seq", 0)
    adelantados = store.scroll(store.MENSAJES,
                               must=[store.cond("canal_id", c["_id"]),
                                     store.cond_mayor("seq", seq)], limit=500)
    seq = max([seq] + [m.get("seq", 0) for m in adelantados]) + 1
    ts = store.now_ts()
    # Un solo id: el del punto y el del payload TIENEN que ser el mismo. Estaban
    # saliendo de dos llamadas distintas, así que `_id` no apuntaba a nada y borrar
    # por él no borraba. Pasó desapercibido hasta que hubo algo que borrara.
    mid = store.nuevo_id()
    store.upsert(store.MENSAJES, mid,
                 {"_id": mid, "canal_id": c["_id"], "seq": seq,
                  "de": agente, "para": destino, "texto": texto, "ts": ts,
                  "acuse": bool(acuse)})
    c["seq"] = seq
    c["updated_at"] = ts
    c["ultimo_ts"] = ts
    store.upsert(store.CANALES, c["_id"], c)

    otros = [destino] if destino else \
            [m["agente"] for m in c.get("miembros", []) if m["agente"] != agente]
    return {"canal": c["nombre"], "seq": seq, "para": otros or None,
            "aviso": None if otros else
            "no hay nadie más en el canal todavía; el mensaje queda esperando"}


def _pendientes(c: dict, desde: int, agente: str) -> tuple[list[dict], int]:
    """Lo que le falta leer a `agente`, y hasta qué `seq` se puede dar por visto.

    Devuelve los dos valores porque no coinciden: los mensajes **propios** no se
    entregan (nadie necesita que le lean lo que acaba de escribir) pero sí cuentan
    como vistos. Si solo se avanzara la marca hasta el último mensaje entregado,
    los propios se volverían a examinar en cada vuelta del long-poll."""
    # El `seq > desde` va en la CONSULTA, no en Python: esto lo llama el long-poll
    # una vez por segundo y por canal, y filtrando aquí el servidor leía y
    # serializaba el historial entero cada vuelta —47 ms con 60 mensajes, y crece
    # con el historial— para tirar casi todo.
    msgs = store.scroll(store.MENSAJES,
                        must=[store.cond("canal_id", c["_id"]),
                              store.cond_mayor("seq", desde)],
                        limit=500)
    msgs = sorted(msgs, key=lambda m: m.get("seq", 0))
    if not msgs:
        return [], desde
    # Lo propio y lo dirigido a otro no se entrega, pero sí cuenta como visto: el
    # canal es una sala, uno se entera de todo, pero solo lo suyo le interrumpe.
    return ([m for m in msgs if m.get("de") != agente and m.get("para") in (None, agente)],
            msgs[-1]["seq"])


def _canales_de(agente: str) -> list[dict]:
    return [c for c in store.scroll(store.CANALES, limit=500)
            if any(m["agente"] == agente for m in c.get("miembros", []))]


def mis_canales(agente: str, tags=None) -> list[dict]:
    """En qué canales está este agente. `tags` filtra igual que en `listar_canales`."""
    pedidos = _norm_tags(tags)
    return [_out(c) for c in _canales_de(_agente(agente)) if _con_tags(c, pedidos)]


@_de_a_uno
def confirmar_entrega(canal: str, agente: str, hasta: int) -> dict:
    """Marca como leído hasta `hasta`. Va aparte de `recibir_todo` a propósito.

    Antes se marcaba al ENTREGARLO al puente, no al llegar a la sesión, y en ese
    hueco se perdía: si el puente moría —o el usuario reconectaba el MCP justo
    ahí— el mensaje quedaba consumido y no se entregaba nunca. Pasó, y en silencio.

    Separarlo cambia el riesgo por el opuesto: si la confirmación se pierde, el
    mensaje se vuelve a entregar. Repetido es molesto; perdido es un fallo."""
    c = _canal(canal)
    agente = _agente(agente)
    m = _miembro(c, agente)
    hasta = max(int(hasta or 0), m.get("visto", 0))   # nunca retroceder
    for x in c["miembros"]:
        if x["agente"] == agente:
            x["visto"] = min(hasta, c.get("seq", 0))
            x["leyo"] = store.now_ts()
    store.upsert(store.CANALES, c["_id"], c)
    return {"canal": c["nombre"], "agente": agente, "leido_hasta": hasta}


def recibir_todo(agente: str, espera: int = 0, marcar: bool = True) -> dict:
    """Lo pendiente en **todos** los canales del agente, en una sola espera.

    Es lo que usa el puente local: un agente suele estar en varios canales y abrir
    una espera por cada uno sería una llamada colgada por canal. Devuelve en cuanto
    entra algo en cualquiera de ellos.

    `marcar=False` NO da nada por leído: quien llama se compromete a confirmar con
    `confirmar_entrega` cuando el mensaje esté de verdad en la sesión. Es lo que
    usa el puente; ver por qué en `confirmar_entrega`."""
    import time

    agente = _agente(agente)
    espera = max(0, min(int(espera or 0), ESPERA_MAX))
    limite = time.time() + espera

    while True:
        salida = []
        for c in _canales_de(agente):
            visto = next(m.get("visto", 0) for m in c["miembros"] if m["agente"] == agente)
            msgs, hasta = _pendientes(c, visto, agente)
            if marcar and hasta > visto:
                _marcar_visto(c["nombre"], agente, hasta)
            if msgs:
                salida.append({
                    # Los tags viajan con la entrega para que el puente los ponga
                    # en el evento sin tener que preguntar por cada canal.
                    "canal": c["nombre"], "tags": c.get("tags") or [], "hasta": hasta,
                    "mensajes": [{"seq": x["seq"], "de": x["de"], "para": x.get("para"),
                                  "texto": x["texto"], "acuse": bool(x.get("acuse")),
                                  "cuando": store.iso(x["ts"])} for x in msgs],
                })
        if salida or time.time() >= limite:
            return {"agente": agente, "canales": salida}
        time.sleep(1.0)


def recibir(canal: str, agente: str, espera: int = 0, marcar: bool = True) -> dict:
    """Los mensajes que el agente todavía no ha visto.

    `espera` en segundos deja la llamada colgada hasta que llegue algo (long-poll):
    es lo que hace que "pregúntale a QA y espera" se sienta una conversación y no
    un sondeo. Se topa en ESPERA_MAX porque Claude Code corta las tools a los 120 s;
    si se agota devuelve vacío y quien llama vuelve a preguntar."""
    import time

    c = _canal(canal)
    agente = _agente(agente)
    m = _miembro(c, agente)
    desde = m.get("visto", 0)

    espera = max(0, min(int(espera or 0), ESPERA_MAX))
    limite = time.time() + espera
    while True:
        msgs, hasta = _pendientes(c, desde, agente)
        if msgs or time.time() >= limite:
            break
        time.sleep(1.0)
        c = _canal(canal)          # releer: el otro pudo escribir mientras dormíamos

    if marcar and hasta > desde:
        _marcar_visto(c["nombre"], agente, hasta)

    return {
        "canal": c["nombre"], "tags": c.get("tags") or [],
        "mensajes": [{"seq": x["seq"], "de": x["de"], "para": x.get("para"),
                      "texto": x["texto"], "acuse": bool(x.get("acuse")),
                      "cuando": store.iso(x["ts"])} for x in msgs],
        "esperando": [a["agente"] for a in c.get("miembros", [])
                      if a["agente"] != agente] or None,
    }


# --- Esperas que no retienen un hilo -------------------------------------- #
# Las versiones de arriba son SÍNCRONAS y duermen con `time.sleep` hasta 110 s.
# FastMCP corre las tools síncronas en el threadpool de anyio, cuyo limitador por
# defecto son 40 hilos: cada agente esperando ocupaba uno de esos 40 durante toda
# la espera, y como ese pool es compartido con las otras 34 tools, con 40 esperas
# simultáneas el hub dejaba de atender TODO (buscar, cargar_contexto, crear...).
# Fue lo que lo tumbó el 2026-09-17.
#
# Estos envoltorios mueven la ESPERA al event loop (`asyncio.sleep`, coste: una
# corrutina) y dejan en un hilo solo la CONSULTA, que dura milisegundos. Se
# apoyan en las funciones de arriba con `espera=0`, que hacen exactamente una
# comprobación sin dormir — así no se duplica la lógica.
#
# OJO: NO convertir las funciones de arriba en `async def` sin más. `store` es
# síncrono y habla con Qdrant por red: esas llamadas dentro de una corrutina
# bloquearían el event loop, que es uno solo, y quedaría peor que antes.

async def recibir_async(canal: str, agente: str, espera: int = 0,
                        marcar: bool = True) -> dict:
    """`recibir`, pero la espera no retiene un hilo del pool."""
    import asyncio, time

    espera = max(0, min(int(espera or 0), ESPERA_MAX))
    limite = time.time() + espera
    while True:
        r = await asyncio.to_thread(recibir, canal, agente, 0, marcar)
        if r["mensajes"] or time.time() >= limite:
            return r
        await asyncio.sleep(1.0)


async def recibir_todo_async(agente: str, espera: int = 0,
                             marcar: bool = True) -> dict:
    """`recibir_todo`, pero la espera no retiene un hilo del pool."""
    import asyncio, time

    espera = max(0, min(int(espera or 0), ESPERA_MAX))
    limite = time.time() + espera
    while True:
        r = await asyncio.to_thread(recibir_todo, agente, 0, marcar)
        if r["canales"] or time.time() >= limite:
            return r
        await asyncio.sleep(1.0)
