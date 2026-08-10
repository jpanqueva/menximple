"""Repositorio sobre Qdrant (único almacén): cuentas, árbol, entradas, historial, búsqueda.

Multi-cuenta con aislamiento fail-closed: `cta` (slug ya autenticado por apikey)
entra en TODO filtro y se verifica al recuperar por id — nunca se cruza data entre
cuentas. Validación estricta y fail-fast: lo inválido lanza MemoriaError con mensaje
accionable; los errores inesperados se propagan sin capturar."""
import secrets

from . import store
from .config import settings
from .models import TIPOS, MemoriaError

# --------------------------------------------------------------------------- #
# Helpers
# --------------------------------------------------------------------------- #

def _req(valor, campo: str) -> str:
    if valor is None or not str(valor).strip():
        raise MemoriaError(f"campo requerido: {campo}")
    return str(valor).strip()


def _valida_tipo(tipo: str) -> str:
    if tipo not in TIPOS:
        raise MemoriaError(f"tipo inválido: {tipo!r}. Debe ser uno de {list(TIPOS)}")
    return tipo


def _vector(resumen: str) -> list[float]:
    if settings.embeddings_enabled:
        from . import embeddings
        return embeddings.embed(resumen, kind="passage")
    return store.ceros()


def _carpeta_out(p: dict) -> dict:
    return {
        "id": p["_id"], "cuenta": p["cuenta"], "nombre": p["nombre"],
        "parent_id": p.get("parent_id") or None,
        "path": p.get("path", []), "descripcion": p.get("descripcion"),
        "created_at": store.iso(p.get("created_at")), "updated_at": store.iso(p.get("updated_at")),
    }


def _entrada_out(p: dict, con_contexto: bool = False) -> dict:
    out = {
        "id": p["_id"], "cuenta": p["cuenta"], "folder_id": p.get("folder_id"),
        "titulo": p["titulo"], "resumen": p["resumen"], "tipo": p["tipo"],
        "tags": p.get("tags", []), "path": p.get("path", []),
        "version": p.get("version", 1), "use_count": p.get("use_count", 0),
        "created_at": store.iso(p.get("created_at")), "updated_at": store.iso(p.get("updated_at")),
        "last_used": store.iso(p.get("last_used")),
    }
    if con_contexto:
        out["contexto"] = p.get("contexto", "")
    return out


# --------------------------------------------------------------------------- #
# Cuentas (cada una con su apikey y sus memorias privadas)
# --------------------------------------------------------------------------- #

def crear_cuenta(slug: str, nombre: str | None = None) -> dict:
    slug = _req(slug, "slug").lower().replace(" ", "-")
    pid = store.id_desde(slug)
    if store.get(store.CUENTAS, pid):
        raise MemoriaError(f"la cuenta '{slug}' ya existe")
    apikey = secrets.token_urlsafe(32)
    payload = {"_id": pid, "slug": slug, "nombre": (nombre or slug).strip(),
               "apikey": apikey, "created_at": store.now_ts()}
    store.upsert(store.CUENTAS, pid, payload)
    # La apikey se devuelve UNA sola vez: guárdala, no se puede volver a mostrar.
    return {"cuenta": slug, "nombre": payload["nombre"], "apikey": apikey,
            "created_at": store.iso(payload["created_at"])}


def listar_cuentas() -> list[dict]:
    pts = store.scroll(store.CUENTAS, limit=1000)
    pts.sort(key=lambda p: p.get("slug", ""))
    return [{"cuenta": p["slug"], "nombre": p.get("nombre", p["slug"]),
             "created_at": store.iso(p.get("created_at"))} for p in pts]


# --------------------------------------------------------------------------- #
# Carpetas (organización libre: proyectos / subproyectos / lo que el usuario quiera)
# --------------------------------------------------------------------------- #

def crear_carpeta(cta: str, nombre: str, parent_id: str | None = None,
                  descripcion: str | None = None) -> dict:
    nombre = _req(nombre, "nombre")
    if parent_id:
        p = store.get(store.CARPETAS, parent_id)
        if not p or p.get("cuenta") != cta:
            raise MemoriaError(f"carpeta padre {parent_id} no existe en la cuenta '{cta}'")
        ancestros = p.get("ancestros", []) + [p["_id"]]
        path = p.get("path", []) + [p["nombre"]]
        parent_ref = parent_id
    else:
        ancestros, path, parent_ref = [], [], ""  # "" = raíz

    ts = store.now_ts()
    pid = store.nuevo_id()
    payload = {"_id": pid, "cuenta": cta, "nombre": nombre, "parent_id": parent_ref,
               "ancestros": ancestros, "path": path, "descripcion": descripcion,
               "created_at": ts, "updated_at": ts}
    store.upsert(store.CARPETAS, pid, payload)
    return _carpeta_out(payload)


def editar_carpeta(cta: str, folder_id: str, nombre: str | None = None,
                   descripcion: str | None = None, mover_a: str | None = None) -> dict:
    f = store.get(store.CARPETAS, folder_id)
    if not f or f.get("cuenta") != cta:
        raise MemoriaError(f"carpeta {folder_id} no existe en la cuenta '{cta}'")

    cambios: dict = {}
    if nombre is not None:
        cambios["nombre"] = _req(nombre, "nombre")
    if descripcion is not None:
        cambios["descripcion"] = descripcion

    if mover_a is not None:
        if mover_a == folder_id:
            raise MemoriaError("una carpeta no puede ser su propio padre")
        if mover_a:
            destino = store.get(store.CARPETAS, mover_a)
            if not destino or destino.get("cuenta") != cta:
                raise MemoriaError(f"carpeta destino {mover_a} no existe en la cuenta '{cta}'")
            if folder_id in destino.get("ancestros", []):
                raise MemoriaError("no se puede mover una carpeta dentro de su propio subárbol")
            cambios["parent_id"] = mover_a
            cambios["ancestros"] = destino.get("ancestros", []) + [mover_a]
            cambios["path"] = destino.get("path", []) + [destino["nombre"]]
        else:
            cambios["parent_id"] = ""
            cambios["ancestros"] = []
            cambios["path"] = []

    if not cambios:
        raise MemoriaError("no se enviaron campos para editar")

    cambios["updated_at"] = store.now_ts()
    store.set_payload(store.CARPETAS, folder_id, cambios)
    if mover_a is not None or "nombre" in cambios:
        _recalcular_subarbol(cta, folder_id)
    return _carpeta_out(store.get(store.CARPETAS, folder_id))


def _recalcular_subarbol(cta: str, folder_id: str) -> None:
    """Tras renombrar/mover, recalcula ancestros/path de subcarpetas y entradas."""
    f = store.get(store.CARPETAS, folder_id)
    base_anc = f.get("ancestros", []) + [f["_id"]]
    base_path = f.get("path", []) + [f["nombre"]]

    for sub in store.scroll(store.CARPETAS, must=[store.cond("cuenta", cta), store.cond("parent_id", folder_id)]):
        store.set_payload(store.CARPETAS, sub["_id"], {"ancestros": base_anc, "path": base_path})
        _recalcular_subarbol(cta, sub["_id"])

    for e in store.scroll(store.ENTRADAS, must=[store.cond("cuenta", cta), store.cond("folder_id", folder_id)]):
        store.set_payload(store.ENTRADAS, e["_id"], {"ancestros": base_anc, "path": base_path})


# --------------------------------------------------------------------------- #
# Entradas (la memoria en sí)
# --------------------------------------------------------------------------- #

def crear_entrada(cta: str, folder_id: str, titulo: str, resumen: str,
                  contexto: str, tipo: str, tags: list[str] | None = None) -> dict:
    folder_id = _req(folder_id, "folder_id")
    titulo = _req(titulo, "titulo")
    resumen = _req(resumen, "resumen")
    contexto = _req(contexto, "contexto")
    tipo = _valida_tipo(_req(tipo, "tipo"))

    f = store.get(store.CARPETAS, folder_id)
    if not f or f.get("cuenta") != cta:
        raise MemoriaError(
            f"carpeta {folder_id} no existe en la cuenta '{cta}'; "
            "crea o elige una carpeta antes de guardar la memoria"
        )

    ts = store.now_ts()
    pid = store.nuevo_id()
    payload = {
        "_id": pid, "cuenta": cta, "folder_id": folder_id,
        "ancestros": f.get("ancestros", []) + [f["_id"]],
        "path": f.get("path", []) + [f["nombre"]],
        "titulo": titulo, "resumen": resumen, "contexto": contexto,
        "tipo": tipo, "tags": tags or [],
        "created_at": ts, "updated_at": ts, "use_count": 0,
        "version": 1, "historial": [],
        "embedding_model": settings.embedding_model if settings.embeddings_enabled else None,
    }
    store.upsert(store.ENTRADAS, pid, payload, vector=_vector(resumen))
    return _entrada_out(payload)


def editar_entrada(cta: str, entry_id: str, titulo: str | None = None,
                   resumen: str | None = None, contexto: str | None = None,
                   tipo: str | None = None, tags: list[str] | None = None) -> dict:
    e = store.get(store.ENTRADAS, entry_id, con_vector=True)
    if not e or e.get("cuenta") != cta:
        raise MemoriaError(f"entrada {entry_id} no existe en la cuenta '{cta}'")

    cambios: dict = {}
    if titulo is not None:
        cambios["titulo"] = _req(titulo, "titulo")
    if resumen is not None:
        cambios["resumen"] = _req(resumen, "resumen")
    if contexto is not None:
        cambios["contexto"] = _req(contexto, "contexto")
    if tipo is not None:
        cambios["tipo"] = _valida_tipo(tipo)
    if tags is not None:
        cambios["tags"] = tags
    if not cambios:
        raise MemoriaError("no se enviaron campos para editar")

    snapshot = {
        "version": e.get("version", 1), "titulo": e["titulo"], "resumen": e["resumen"],
        "contexto": e["contexto"], "tipo": e["tipo"], "tags": e.get("tags", []),
        "ts": e.get("updated_at"),
    }
    vector_actual = e.pop("__vector__", None) or store.ceros()
    nuevo = {k: v for k, v in e.items() if k != "__vector__"}
    nuevo.update(cambios)
    nuevo["updated_at"] = store.now_ts()
    nuevo["version"] = e.get("version", 1) + 1
    nuevo["historial"] = e.get("historial", []) + [snapshot]

    vector = _vector(nuevo["resumen"]) if "resumen" in cambios else vector_actual
    store.upsert(store.ENTRADAS, entry_id, nuevo, vector=vector)
    return _entrada_out(nuevo)


def obtener_entrada(cta: str, entry_id: str) -> dict:
    e = store.get(store.ENTRADAS, entry_id)
    if not e or e.get("cuenta") != cta:
        raise MemoriaError(f"entrada {entry_id} no existe en la cuenta '{cta}'")
    _marcar_uso(e)
    return _entrada_out(e, con_contexto=True)


def cargar_contexto(cta: str, entry_ids: list[str]) -> list[dict]:
    if not entry_ids:
        raise MemoriaError("entry_ids vacío: indica al menos una entrada a cargar")
    salida = []
    for eid in entry_ids:
        e = store.get(store.ENTRADAS, eid)
        if not e or e.get("cuenta") != cta:
            raise MemoriaError(f"entrada {eid} no existe en la cuenta '{cta}'")
        _marcar_uso(e)
        salida.append(_entrada_out(e, con_contexto=True))
    return salida


def _marcar_uso(e: dict) -> None:
    e["use_count"] = e.get("use_count", 0) + 1  # refleja el incremento en el objeto devuelto
    e["last_used"] = store.now_ts()
    store.set_payload(store.ENTRADAS, e["_id"],
                      {"last_used": e["last_used"], "use_count": e["use_count"]})


# --------------------------------------------------------------------------- #
# Navegación y búsqueda (siempre scoped a la cuenta)
# --------------------------------------------------------------------------- #

def listar(cta: str, folder_id: str | None = None) -> dict:
    from .instructions import DOCUMENTACION_USO
    parent = folder_id or ""  # "" = raíz

    carpetas = store.scroll(store.CARPETAS,
                            must=[store.cond("cuenta", cta), store.cond("parent_id", parent)])
    carpetas.sort(key=lambda p: p.get("nombre", ""))
    out = {"cuenta": cta, "folder_id": folder_id,
           "carpetas": [_carpeta_out(c) for c in carpetas], "entradas": []}

    if folder_id:  # las entradas viven dentro de una carpeta
        entradas = store.scroll(store.ENTRADAS,
                                must=[store.cond("cuenta", cta), store.cond("folder_id", folder_id)],
                                order_key="updated_at")
        out["entradas"] = [_entrada_out(e) for e in entradas]
    else:
        out["documentacion_de_uso"] = DOCUMENTACION_USO
    return out


def _must(cta: str, tipo: str | None, folder_id: str | None, tags: list[str] | None) -> list:
    must = [store.cond("cuenta", cta)]
    if tipo:
        must.append(store.cond("tipo", _valida_tipo(tipo)))
    if folder_id:
        from qdrant_client.models import Filter
        must.append(Filter(should=[store.cond("folder_id", folder_id),
                                    store.cond_any("ancestros", [folder_id])]))
    if tags:
        must.append(store.cond_any("tags", tags))
    return must


def buscar(cta: str, query: str = "", tipo: str | None = None,
           folder_id: str | None = None, tags: list[str] | None = None,
           limit: int = 10) -> list[dict]:
    must = _must(cta, tipo, folder_id, tags)

    # Camino vectorial (embeddings activos + hay query).
    if settings.embeddings_enabled and query.strip():
        from . import embeddings
        vec = embeddings.embed(query, kind="query")
        return [_entrada_out(p) for p in store.search(store.ENTRADAS, vec, must=must, limit=limit)]

    # Camino texto/metadatos (full-text de payload de Qdrant).
    if query.strip():
        from qdrant_client.models import Filter
        must = must + [Filter(should=[store.cond_text("titulo", query),
                                      store.cond_text("resumen", query),
                                      store.cond_text("contexto", query)])]
        res = store.scroll(store.ENTRADAS, must=must, order_key="updated_at", limit=limit)
    else:
        res = store.scroll(store.ENTRADAS, must=must, order_key="updated_at", limit=limit)
    return [_entrada_out(p) for p in res]


def buscar_relacionadas(cta: str, texto: str | None = None,
                        entry_id: str | None = None, limit: int = 10) -> list[dict]:
    """Fallback 'más inteligente': vecinos por significado (o por texto del resumen)."""
    if entry_id:
        e = store.get(store.ENTRADAS, entry_id)
        if not e or e.get("cuenta") != cta:
            raise MemoriaError(f"entrada {entry_id} no existe en la cuenta '{cta}'")
        texto = e["resumen"]
    if not texto or not texto.strip():
        raise MemoriaError("indica 'texto' o un 'entry_id' para buscar relacionadas")
    return buscar(cta, query=texto, limit=limit)


def listar_recientes(cta: str, limit: int = 10) -> list[dict]:
    res = store.scroll(store.ENTRADAS, must=[store.cond("cuenta", cta)],
                       order_key="last_used", limit=limit)
    return [_entrada_out(p) for p in res]
