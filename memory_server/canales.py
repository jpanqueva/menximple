"""Canales de conversación entre agentes.

Un canal es una sala de **dos** agentes que pueden estar en máquinas, cuentas y
países distintos. El hub solo guarda y entrega; quien despierta a un agente que
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
- **Dos y no más.** No es una limitación técnica, es la que pidió el usuario: una
  conversación entre dos tiene un "el otro" sin ambigüedad, así que un mensaje no
  necesita destinatario y "responder" no necesita elegir a quién.
"""
from . import store
from .models import MemoriaError

CUPOS = 2
ESPERA_MAX = 110      # Claude Code corta las tools a los 120 s; ver `recibir`.
RETROCESO = 20        # cuánto historial ve quien entra; ver `unirse_canal`.


def _canal(nombre: str) -> dict:
    nombre = (nombre or "").strip().lower()
    if not nombre:
        raise MemoriaError("falta el nombre del canal")
    hallados = store.scroll(store.CANALES, must=[store.cond("nombre", nombre)], limit=1)
    if not hallados:
        raise MemoriaError(f"no existe el canal '{nombre}'; míralos con `listar_canales` "
                           "o créalo con `crear_canal`")
    return hallados[0]


def _agente(nombre: str) -> str:
    a = (nombre or "").strip()
    if not a:
        raise MemoriaError("falta el nombre del agente (con quién habla el otro lado)")
    return a


def _miembro(c: dict, agente: str) -> dict:
    for m in c.get("miembros", []):
        if m["agente"] == agente:
            return m
    raise MemoriaError(f"'{agente}' no está en el canal '{c['nombre']}'; "
                       "entra primero con `unirse_canal`")


def _out(c: dict) -> dict:
    return {
        "nombre": c["nombre"], "descripcion": c.get("descripcion"),
        "agentes": [m["agente"] for m in c.get("miembros", [])],
        "cupos_libres": CUPOS - len(c.get("miembros", [])),
        "mensajes": c.get("seq", 0),
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
                agente: str | None = None, cta: str | None = None) -> dict:
    """Crea el canal y, si le pasas `agente`, te mete dentro.

    Lo segundo no es un atajo: quien crea un canal es porque va a hablar en él, y
    obligarlo a un `unirse_canal` aparte solo servía para que su primer mensaje
    fallara con "no estás en el canal". Pasó la primera vez que alguien lo usó."""
    nombre = (nombre or "").strip().lower()
    if not nombre:
        raise MemoriaError("falta el nombre del canal")
    if store.scroll(store.CANALES, must=[store.cond("nombre", nombre)], limit=1):
        raise MemoriaError(f"ya existe un canal '{nombre}'")
    ts = store.now_ts()
    payload = {"_id": store.nuevo_id(), "nombre": nombre, "descripcion": descripcion,
               "cuenta": cta, "miembros": [], "seq": 0,
               "created_at": ts, "updated_at": ts}
    store.upsert(store.CANALES, payload["_id"], payload)
    if agente:
        return unirse_canal(nombre, agente, cta)
    return _out(payload)


def listar_canales(cta: str | None = None) -> list[dict]:
    """Los canales de esta cuenta: los que creó y en los que está.

    NO los lista todos. Los canales cruzan cuentas a propósito —ese es el sentido—
    pero eso vale para la MEMBRESÍA, no para el catálogo: sin este filtro, cualquiera
    con una apikey enumeraba los canales de los demás con su nombre y su descripción,
    que suele explicar justo lo que uno no quiere que se lea de rebote.

    Entrar a un canal de otra cuenta sigue siendo posible: `unirse_canal` acepta el
    nombre exacto aunque no salga aquí. Se comparte como un enlace de reunión — te lo
    pasan, no lo encuentras."""
    cs = [c for c in store.scroll(store.CANALES, limit=500) if _mia(c, cta)]
    cs.sort(key=lambda c: c.get("nombre", ""))
    return [_out(c) for c in cs]


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


def unirse_canal(canal: str, agente: str, cta: str | None = None) -> dict:
    c = _canal(canal)
    agente = _agente(agente)
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
    if len(miembros) >= CUPOS:
        otros = ", ".join(m["agente"] for m in miembros)
        raise MemoriaError(f"el canal '{c['nombre']}' ya tiene sus {CUPOS} agentes "
                           f"({otros}); usa otro canal o que alguno salga")

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
                     "desde": store.now_ts()})
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


def salir_canal(canal: str, agente: str) -> dict:
    c = _canal(canal)
    agente = _agente(agente)
    _miembro(c, agente)
    c["miembros"] = [m for m in c.get("miembros", []) if m["agente"] != agente]
    c["updated_at"] = store.now_ts()
    store.upsert(store.CANALES, c["_id"], c)
    return _out(c)


def enviar_mensaje(canal: str, agente: str, texto: str, acuse: bool = False) -> dict:
    """Escribe en el canal. `acuse=True` marca el mensaje como acuse de recibo.

    El acuse existe porque un encargo puede tardar mucho y, sin él, quien preguntó
    no distingue "todavía no lo ha leído" de "lo está trabajando". Va marcado para
    que el puente del otro lado no conteste un acuse con otro acuse: así es como
    dos agentes educados se saludan para siempre."""
    texto = (texto or "").strip()
    if not texto:
        raise MemoriaError("el mensaje está vacío")
    c = _canal(canal)
    agente = _agente(agente)
    _miembro(c, agente)

    seq = c.get("seq", 0) + 1
    ts = store.now_ts()
    # Un solo id: el del punto y el del payload TIENEN que ser el mismo. Estaban
    # saliendo de dos llamadas distintas, así que `_id` no apuntaba a nada y borrar
    # por él no borraba. Pasó desapercibido hasta que hubo algo que borrara.
    mid = store.nuevo_id()
    store.upsert(store.MENSAJES, mid,
                 {"_id": mid, "canal_id": c["_id"], "seq": seq,
                  "de": agente, "texto": texto, "ts": ts, "acuse": bool(acuse)})
    c["seq"] = seq
    c["updated_at"] = ts
    store.upsert(store.CANALES, c["_id"], c)

    otros = [m["agente"] for m in c.get("miembros", []) if m["agente"] != agente]
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
    return [m for m in msgs if m.get("de") != agente], msgs[-1]["seq"]


def _canales_de(agente: str) -> list[dict]:
    return [c for c in store.scroll(store.CANALES, limit=500)
            if any(m["agente"] == agente for m in c.get("miembros", []))]


def mis_canales(agente: str) -> list[dict]:
    """En qué canales está este agente. Puede estar en varios a la vez: el límite
    de dos es por canal, no por agente."""
    return [_out(c) for c in _canales_de(_agente(agente))]


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
                for x in c["miembros"]:
                    if x["agente"] == agente:
                        x["visto"] = hasta
                store.upsert(store.CANALES, c["_id"], c)
            if msgs:
                salida.append({
                    "canal": c["nombre"], "hasta": hasta,
                    "mensajes": [{"seq": x["seq"], "de": x["de"], "texto": x["texto"],
                                  "acuse": bool(x.get("acuse")),
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
        for x in c.get("miembros", []):
            if x["agente"] == agente:
                x["visto"] = hasta
        store.upsert(store.CANALES, c["_id"], c)

    return {
        "canal": c["nombre"],
        "mensajes": [{"seq": x["seq"], "de": x["de"], "texto": x["texto"],
                      "acuse": bool(x.get("acuse")),
                      "cuando": store.iso(x["ts"])} for x in msgs],
        "esperando": [a["agente"] for a in c.get("miembros", [])
                      if a["agente"] != agente] or None,
    }
