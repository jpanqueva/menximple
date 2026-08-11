"""Almacén único: Qdrant. Documentos en payload + vectores del resumen.

Tres colecciones: `cuentas`, `carpetas`, `entradas`. Las dos primeras usan un
vector dummy (size 1) porque solo se usan como store documental con filtros de
payload; `entradas` usa el vector del resumen (o ceros si los embeddings están off).
Cada punto lleva su propio id en payload['_id'] para exponerlo sin depender del record."""
import time
import uuid
from datetime import datetime, timezone

from qdrant_client import QdrantClient
from qdrant_client.models import (
    Direction, Distance, FieldCondition, Filter, MatchAny, MatchText, MatchValue,
    OrderBy, PayloadSchemaType, PointStruct, TextIndexParams, TextIndexType,
    TokenizerType, VectorParams,
)

from .config import settings

CUENTAS = "cuentas"
CARPETAS = "carpetas"
ENTRADAS = "entradas"
_DUMMY = [0.0]

_client: QdrantClient | None = None


def client() -> QdrantClient:
    global _client
    if _client is None:
        _client = QdrantClient(
            url=settings.qdrant_url,
            api_key=settings.qdrant_api_key or None,
        )
    return _client


# --- tiempo ---------------------------------------------------------------- #

def now_ts() -> float:
    return time.time()


def iso(ts) -> str | None:
    if not ts:
        return None
    return datetime.fromtimestamp(ts, tz=timezone.utc).isoformat()


# --- ids ------------------------------------------------------------------- #

def nuevo_id() -> str:
    return str(uuid.uuid4())


def id_desde(texto: str) -> str:
    return str(uuid.uuid5(uuid.NAMESPACE_OID, texto))


def ceros() -> list[float]:
    return [0.0] * settings.embedding_dims


# --- condiciones de filtro ------------------------------------------------- #

def cond(key: str, value) -> FieldCondition:
    return FieldCondition(key=key, match=MatchValue(value=value))


def cond_any(key: str, values: list) -> FieldCondition:
    return FieldCondition(key=key, match=MatchAny(any=values))


def cond_text(key: str, text: str) -> FieldCondition:
    return FieldCondition(key=key, match=MatchText(text=text))


def _flt(must) -> Filter | None:
    return Filter(must=must) if must else None


# --- esquema --------------------------------------------------------------- #

# Prefijos de 2 letras en adelante: con 1 el índice crece muchísimo y una sola
# letra no discrimina nada.
PREFIJO = TextIndexParams(type=TextIndexType.TEXT, tokenizer=TokenizerType.PREFIX,
                          min_token_len=2, max_token_len=30, lowercase=True)


def ensure_collections() -> None:
    c = client()
    existentes = {x.name for x in c.get_collections().collections}
    if CUENTAS not in existentes:
        c.create_collection(CUENTAS, vectors_config=VectorParams(size=1, distance=Distance.COSINE))
    if CARPETAS not in existentes:
        c.create_collection(CARPETAS, vectors_config=VectorParams(size=1, distance=Distance.COSINE))
    if ENTRADAS not in existentes:
        c.create_collection(
            ENTRADAS,
            vectors_config=VectorParams(size=settings.embedding_dims, distance=Distance.COSINE),
        )

    kw, flt, txt = PayloadSchemaType.KEYWORD, PayloadSchemaType.FLOAT, PayloadSchemaType.TEXT
    _idx(CUENTAS, {"apikey": kw, "slug": kw})
    _idx(CARPETAS, {"cuenta": kw, "parent_id": kw, "ancestros": kw, "updated_at": flt})
    _idx(ENTRADAS, {
        "cuenta": kw, "folder_id": kw, "ancestros": kw, "tipo": kw, "tags": kw,
        "updated_at": flt, "last_used": flt,
        # Título y resumen se buscan escribiendo a medias ("corr" -> "Correlativo"),
        # así que van indexados por prefijo. El contexto no: indexar cada prefijo de
        # cada palabra de un texto largo multiplica el índice sin ganar nada, porque
        # lo que el usuario busca a tientas es el nombre, no el cuerpo.
        "titulo": PREFIJO, "resumen": PREFIJO, "contexto": txt,
    })


def _mismo_indice(info, deseado) -> bool:
    """¿El índice que ya existe es el que queremos? Cambiar el esquema en el código
    no reindexa nada: un índice creado con otro tokenizador hay que rehacerlo."""
    tok = getattr(deseado, "tokenizer", None)
    if tok is None:                      # keyword/float: no tienen variantes
        return True
    return getattr(getattr(info, "params", None), "tokenizer", None) == tok


def _idx(coll: str, campos: dict) -> None:
    esquema = client().get_collection(coll).payload_schema or {}
    for campo, tipo in campos.items():
        actual = esquema.get(campo)
        if actual is not None:
            if _mismo_indice(actual, tipo):
                continue
            client().delete_payload_index(coll, field_name=campo)
        client().create_payload_index(coll, field_name=campo, field_schema=tipo)


# --- operaciones sobre puntos --------------------------------------------- #

def upsert(coll: str, pid: str, payload: dict, vector: list[float] | None = None) -> None:
    client().upsert(coll, points=[PointStruct(id=pid, vector=vector or _DUMMY, payload=payload)])


def es_id_valido(pid) -> bool:
    try:
        uuid.UUID(str(pid))
        return True
    except (ValueError, TypeError, AttributeError):
        return False


def get(coll: str, pid: str, con_vector: bool = False) -> dict | None:
    if not es_id_valido(pid):  # id con formato inválido = no encontrado
        return None
    r = client().retrieve(coll, ids=[pid], with_payload=True, with_vectors=con_vector)
    if not r:
        return None
    p = r[0]
    payload = dict(p.payload or {})
    if con_vector:
        payload["__vector__"] = p.vector
    return payload


def set_payload(coll: str, pid: str, payload: dict) -> None:
    client().set_payload(coll, payload=payload, points=[pid])


def delete(coll: str, pid: str) -> None:
    client().delete(coll, points_selector=[pid])


def scroll(coll: str, must=None, order_key: str | None = None,
           desc: bool = True, limit: int = 1000) -> list[dict]:
    order_by = None
    if order_key:
        order_by = OrderBy(key=order_key, direction=Direction.DESC if desc else Direction.ASC)
    pts, _ = client().scroll(
        coll, scroll_filter=_flt(must), order_by=order_by, limit=limit, with_payload=True
    )
    return [dict(p.payload or {}) for p in pts]


def search(coll: str, vector: list[float], must=None, limit: int = 10) -> list[dict]:
    res = client().search(coll, query_vector=vector, query_filter=_flt(must), limit=limit, with_payload=True)
    return [dict(p.payload or {}) for p in res]
