"""Catálogo de equipos, ámbitos, actividades y agentes.

Existe porque durante una semana nadie supo quién era quién: cada máquina tenía
su copia del puente con su versión, los agentes se llamaban como cada uno quiso
("jhon-pc", "sagente-claude", "agente-pc-jhon") y una máquina mal configurada
podía pasar días fallando sin que se le viera la cara. El usuario decidió que la
nomenclatura fuera **estricta y pre-clasificada**, y que lo que no la cumpla
falle de frente.

Cuatro clases de registro, todas con `nombre` en minúsculas y solo [a-z0-9]:

- **equipo**    una máquina: `pciajhon`, `imp1`, `azure`. Lleva `hostname` (lo lee
                el puente al arrancar para saber en qué equipo está), `tipo`
                (pc|servidor) y `dueno`.
- **ambito**    una empresa o un proyecto: `sagente`, `transfiriendo`, `forja`.
- **actividad** para qué es un canal: `comunicacion`, `soporte`, `ayuda`,
                `trabajo`, `avisos`, `devops`, `voz`, `pantalla`. Vocabulario
                cerrado; se amplía solo creando una actividad nueva aquí.
- **agente**    `agt-<equipo>-<ambito>-<rol>`. Se registra solo la primera vez que
                un nombre válido entra a un canal o escribe (no hace falta darlo
                de alta a mano), y guarda `visto`: la última vez que hizo algo.

Nombres de canal (los valida `canales.py` con esto):

- `canal-<equipo1>-<equipo2>-<actividad>`   entre dos equipos, en orden alfabético
- `canal-<ambito>-<actividad>`               sala de un ámbito, sin tope de miembros

Solo hay consultar y crear. Ni editar ni borrar desde las tools: un catálogo que
se edita a la ligera deja de ser un catálogo.
"""
import re

from . import store
from .models import MemoriaError

CLASES = ("equipo", "ambito", "actividad", "agente")
SLUG = re.compile(r"^[a-z0-9]{2,24}$")
RE_AGENTE = re.compile(r"^agt-([a-z0-9]{2,24})-([a-z0-9]{2,24})-([a-z0-9]{2,24})$")
RE_CANAL = re.compile(r"^canal-([a-z0-9]{2,24})-([a-z0-9]{2,24})(?:-([a-z0-9]{2,24}))?$")
TIPOS_EQUIPO = ("pc", "servidor")
TIPOS_AMBITO = ("empresa", "proyecto")
TIPOS_AGENTE = ("ia", "proceso")

# Las actividades con las que nace el catálogo. Se crean si no existen al
# arrancar el hub (ver `sembrar`), para que un canal se pueda crear desde el
# primer minuto sin registrar nada a mano.
ACTIVIDADES_BASE = {
    "comunicacion": "conversación de trabajo entre agentes",
    "soporte": "mantenimiento del sistema: cambios, instrucciones, validaciones",
    "ayuda": "un agente le pide ayuda puntual a otro",
    "trabajo": "sala de un ámbito: quien coordina y quienes ejecutan",
    "avisos": "procesos automáticos avisan; no se contesta",
    "devops": "órdenes exactas a un proceso que levanta y cierra agentes",
    "voz": "lo que se escribe se le lee en voz alta a una persona",
    "pantalla": "lo que se escribe se le muestra a una persona (Markdown)",
}


def _slug(nombre: str, que: str) -> str:
    n = (nombre or "").strip().lower()
    if not SLUG.match(n):
        raise MemoriaError(f"{que} inválido: '{nombre}'. Solo minúsculas y dígitos, "
                           "de 2 a 24 caracteres, sin guiones ni espacios")
    return n


# Caché de lecturas positivas. Esto lo consulta CADA operación de canal, incluido
# el long-poll de cada agente una vez por segundo: tres consultas a Qdrant por
# vuelta (equipo, ámbito, agente) eran ~40 ms y con 60 agentes esperando se
# comían el pool de hilos. Lo que existe no deja de existir (no hay borrar), así
# que cachear los aciertos es seguro; `crear` invalida por si acaso.
import time as _time
_CACHE: dict[tuple[str, str], tuple[float, dict]] = {}
_CACHE_TTL = 60.0


def _get(clase: str, nombre: str) -> dict | None:
    k = (clase, nombre)
    hit = _CACHE.get(k)
    if hit and _time.monotonic() - hit[0] < _CACHE_TTL:
        return dict(hit[1])
    r = store.scroll(store.REGISTRO, must=[store.cond("clase", clase),
                                           store.cond("nombre", nombre)], limit=1)
    if r:
        _CACHE[k] = (_time.monotonic(), dict(r[0]))
        return r[0]
    return None


def _out(r: dict) -> dict:
    o = {k: v for k, v in r.items() if k not in ("_id", "created_at", "visto")}
    o["creado"] = store.iso(r.get("created_at"))
    if r.get("clase") == "agente":
        o["visto"] = store.iso(r.get("visto"))
    return o


def ver(clase: str | None = None, nombre: str | None = None,
        hostname: str | None = None) -> list[dict]:
    """El catálogo, o una parte. Sin argumentos lo devuelve entero (es corto)."""
    must = []
    if clase:
        if clase not in CLASES:
            raise MemoriaError(f"clase desconocida: '{clase}'. Son: {', '.join(CLASES)}")
        must.append(store.cond("clase", clase))
    if nombre:
        must.append(store.cond("nombre", (nombre or "").strip().lower()))
    if hostname:
        must.append(store.cond("hostname", (hostname or "").strip().lower()))
    rs = store.scroll(store.REGISTRO, must=must or None, limit=1000)
    rs.sort(key=lambda r: (CLASES.index(r.get("clase", "agente")), r.get("nombre", "")))
    return [_out(r) for r in rs]


def crear(clase: str, nombre: str, cta: str | None = None, hostname: str | None = None,
          tipo: str | None = None, dueno: str | None = None,
          descripcion: str | None = None) -> dict:
    """Da de alta un equipo, un ámbito o una actividad. Los agentes no se crean
    aquí: se registran solos al usar un nombre válido (ver `tocar_agente`)."""
    if clase not in ("equipo", "ambito", "actividad"):
        raise MemoriaError("solo se crean a mano equipo, ambito o actividad; los agentes "
                           "se registran solos al entrar a un canal con un nombre válido")
    n = _slug(nombre, f"nombre de {clase}")
    if _get(clase, n):
        raise MemoriaError(f"ya existe {clase} '{n}'")
    r = {"_id": store.nuevo_id(), "clase": clase, "nombre": n, "cuenta": cta,
         "descripcion": (descripcion or "").strip() or None, "created_at": store.now_ts()}
    if clase == "equipo":
        if tipo not in TIPOS_EQUIPO:
            raise MemoriaError(f"un equipo necesita tipo: {' | '.join(TIPOS_EQUIPO)}")
        h = (hostname or "").strip().lower()
        if not h:
            raise MemoriaError("un equipo necesita hostname (lo que devuelve `hostname` en "
                               "esa máquina); el puente lo usa para saber dónde corre")
        choque = store.scroll(store.REGISTRO, must=[store.cond("clase", "equipo"),
                                                    store.cond("hostname", h)], limit=1)
        if choque:
            raise MemoriaError(f"ese hostname ya es del equipo '{choque[0]['nombre']}'")
        r.update({"hostname": h, "tipo": tipo, "dueno": (dueno or "").strip() or None})
    elif clase == "ambito":
        if tipo not in TIPOS_AMBITO:
            raise MemoriaError(f"un ámbito necesita tipo: {' | '.join(TIPOS_AMBITO)}")
        r["tipo"] = tipo
    store.upsert(store.REGISTRO, r["_id"], r)
    _CACHE.pop((clase, n), None)
    return _out(r)


def sembrar() -> None:
    """Las actividades base, si faltan. Se llama al arrancar el hub."""
    try:
        for n, d in ACTIVIDADES_BASE.items():
            if not _get("actividad", n):
                store.upsert(store.REGISTRO, store.nuevo_id(),
                             {"_id": store.nuevo_id(), "clase": "actividad", "nombre": n,
                              "descripcion": d, "cuenta": None, "created_at": store.now_ts()})
    except Exception:  # noqa: BLE001 — sin Qdrant aún; se reintenta en la próxima llamada
        pass


# --- validación de nombres ------------------------------------------------- #

def partes_agente(nombre: str) -> tuple[str, str, str]:
    """`agt-<equipo>-<ambito>-<rol>` → (equipo, ambito, rol), o error que explica."""
    n = (nombre or "").strip().lower()
    m = RE_AGENTE.match(n)
    if not m:
        raise MemoriaError(
            f"nombre de agente inválido: '{nombre}'. El formato es "
            "agt-<equipo>-<ambito>-<rol>, todo en minúsculas y dígitos (p.ej. "
            "agt-pciajhon-sagente-soporte). Mira equipos y ámbitos con registro_ver")
    equipo, ambito, rol = m.groups()
    if not _get("equipo", equipo):
        raise MemoriaError(f"el equipo '{equipo}' no está en el catálogo. Míralo con "
                           "registro_ver(clase='equipo'); si esta máquina es nueva, "
                           "regístrala con registro_crear(clase='equipo', ...)")
    if not _get("ambito", ambito):
        raise MemoriaError(f"el ámbito '{ambito}' no está en el catálogo. Míralo con "
                           "registro_ver(clase='ambito'); si es una empresa o proyecto "
                           "nuevo, regístralo con registro_crear(clase='ambito', ...)")
    return equipo, ambito, rol


def tocar_agente(nombre: str, cta: str | None = None, tipo: str | None = None) -> str:
    """Valida el nombre y deja al agente registrado (o actualiza su `visto`).
    Devuelve el nombre normalizado. Es lo que llama `canales` en cada operación."""
    equipo, ambito, rol = partes_agente(nombre)
    n = f"agt-{equipo}-{ambito}-{rol}"
    r = _get("agente", n)
    if r:
        # Esto lo llama cada operación de canal, incluido el long-poll que consulta
        # cada segundo: `visto` se escribe como mucho una vez por minuto.
        cambio = tipo in TIPOS_AGENTE and r.get("tipo") != tipo
        if cambio or store.now_ts() - (r.get("visto") or 0) > 60:
            r["visto"] = store.now_ts()
            if cambio:
                r["tipo"] = tipo
            store.upsert(store.REGISTRO, r["_id"], r)
            _CACHE[("agente", n)] = (_time.monotonic(), dict(r))
    else:
        r = {"_id": store.nuevo_id(), "clase": "agente", "nombre": n, "equipo": equipo,
             "ambito": ambito, "rol": rol, "tipo": tipo if tipo in TIPOS_AGENTE else "ia",
             "cuenta": cta, "descripcion": None, "created_at": store.now_ts(),
             "visto": store.now_ts()}
        store.upsert(store.REGISTRO, r["_id"], r)
        _CACHE[("agente", n)] = (_time.monotonic(), dict(r))
    return n


def validar_canal(nombre: str) -> dict:
    """Comprueba el nombre de un canal contra el catálogo y devuelve sus partes:
    {"nombre", "actividad", "equipos": [a, b]} o {"nombre", "actividad", "ambito"}."""
    n = (nombre or "").strip().lower()
    m = RE_CANAL.match(n)
    if not m:
        raise MemoriaError(
            f"nombre de canal inválido: '{nombre}'. Formatos: canal-<equipo1>-<equipo2>-"
            "<actividad> (equipos en orden alfabético) o canal-<ambito>-<actividad>. "
            "Actividades: registro_ver(clase='actividad')")
    a, b, c = m.groups()
    if c is None:                                  # canal-<ambito>-<actividad>
        ambito, actividad = a, b
        if not _get("ambito", ambito):
            raise MemoriaError(f"'{ambito}' no es un ámbito del catálogo (registro_ver(clase='ambito'))")
        if not _get("actividad", actividad):
            raise MemoriaError(f"'{actividad}' no es una actividad del catálogo "
                               "(registro_ver(clase='actividad'))")
        return {"nombre": n, "actividad": actividad, "ambito": ambito}
    e1, e2, actividad = a, b, c
    for e in (e1, e2):
        if not _get("equipo", e):
            raise MemoriaError(f"'{e}' no es un equipo del catálogo (registro_ver(clase='equipo'))")
    if e1 == e2:
        raise MemoriaError("un canal entre dos equipos necesita dos equipos distintos; "
                           "para una sala del mismo equipo usa canal-<ambito>-<actividad>")
    if e1 > e2:
        raise MemoriaError(f"los equipos van en orden alfabético: canal-{e2}-{e1}-{actividad}")
    if not _get("actividad", actividad):
        raise MemoriaError(f"'{actividad}' no es una actividad del catálogo "
                           "(registro_ver(clase='actividad'))")
    return {"nombre": n, "actividad": actividad, "equipos": [e1, e2]}
