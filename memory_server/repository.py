"""Repositorio sobre Qdrant (único almacén): cuentas, árbol, entradas, historial, búsqueda.

Multi-cuenta con aislamiento fail-closed: `cta` (slug ya autenticado por apikey)
entra en TODO filtro y se verifica al recuperar por id — nunca se cruza data entre
cuentas. Validación estricta y fail-fast: lo inválido lanza MemoriaError con mensaje
accionable; los errores inesperados se propagan sin capturar."""
import re
import secrets
import unicodedata

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


def _carpeta_viva(cta: str, folder_id: str, papel: str) -> dict:
    """Carpeta que existe, es de la cuenta y no está archivada. Guardar dentro de
    algo archivado dejaría la memoria invisible desde el minuto uno."""
    f = store.get(store.CARPETAS, folder_id)
    if not f or f.get("cuenta") != cta:
        raise MemoriaError(f"carpeta {papel} {folder_id} no existe en la cuenta '{cta}'")
    if f.get("archivada"):
        raise MemoriaError(f"la carpeta '{f['nombre']}' está archivada; "
                           "restáurala antes de guardar ahí")
    return f


def _valida_tipo(tipo: str) -> str:
    if tipo not in TIPOS:
        raise MemoriaError(f"tipo inválido: {tipo!r}. Debe ser uno de {list(TIPOS)}")
    return tipo


def _vector(resumen: str) -> list[float]:
    if settings.embeddings_enabled:
        from . import embeddings
        return embeddings.embed(resumen, kind="passage")
    return store.ceros()


def _tokens(texto: str) -> int:
    """Tamaño del contexto en tokens, **aproximado** (~4 caracteres por token).

    Sirve para que el usuario sepa cuánto le cuesta cargar una memoria antes de
    hacerlo; no pretende igualar al tokenizador del modelo."""
    return (len(texto or "") + 3) // 4


def _accion_out(p: dict) -> dict | None:
    a = p.get("ultima_accion")
    if isinstance(a, dict) and a.get("tipo"):
        return {"tipo": a["tipo"], "fecha": store.iso(a.get("ts")), "detalle": a.get("detalle")}

    # Lo guardado antes de que existiera el campo: se deduce de las marcas de tiempo.
    usada, editada, creada = p.get("last_used"), p.get("updated_at"), p.get("created_at")
    if usada and (not editada or usada >= editada):
        return {"tipo": "cargada", "fecha": store.iso(usada), "detalle": None}
    if editada and creada and editada > creada:
        return {"tipo": "editada", "fecha": store.iso(editada), "detalle": None}
    if creada:
        return {"tipo": "creada", "fecha": store.iso(creada), "detalle": None}
    return None


def _archivo_out(p: dict) -> dict:
    """Lo archivado se marca siempre en la respuesta: nada debe parecer vivo si no lo está."""
    if not p.get("archivada"):
        return {}
    return {"archivada": True, "archivada_at": store.iso(p.get("archivada_ts")),
            "archivada_motivo": p.get("archivada_motivo")}


def _carpeta_out(p: dict) -> dict:
    return {
        "id": p["_id"], "cuenta": p["cuenta"], "nombre": p["nombre"],
        "parent_id": p.get("parent_id") or None,
        "path": p.get("path", []), "descripcion": p.get("descripcion"),
        "created_at": store.iso(p.get("created_at")), "updated_at": store.iso(p.get("updated_at")),
        "ultima_accion": _accion_out(p),
        **_archivo_out(p),
    }


def _siguiente_numero(cta: str) -> int:
    """Consecutivo por cuenta: un nombre corto que el usuario pueda decir en voz alta
    ("la 12") en vez del uuid.

    Sale del mayor que exista, **incluidas las archivadas**: un número no se
    reutiliza nunca, o dos memorias distintas acabarían llamándose igual."""
    ultimas = store.scroll(store.ENTRADAS, must=[store.cond("cuenta", cta)],
                           order_key="numero", limit=1)
    return int(ultimas[0].get("numero") or 0) + 1 if ultimas else 1


# --- Texto de búsqueda: lo que de verdad se indexa para encontrar una memoria --- #

_PALABRAS = re.compile(r"[a-z0-9]{2,}")


def _normaliza(texto: str) -> str:
    """Minúsculas y sin tildes.

    El índice de Qdrant baja a minúsculas pero **no** ignora los acentos, así que
    sin esto 'facturación' no encuentra 'Facturacion'. Hay que aplicarlo a lo que
    se guarda Y a lo que se busca; si solo se hace en un lado, no sirve de nada."""
    t = unicodedata.normalize("NFD", texto or "").lower()
    return "".join(c for c in t if unicodedata.category(c) != "Mn")


def _texto_busqueda(titulo: str, resumen: str, tags: list[str] | None) -> str:
    """Campo aparte con título + resumen + tags ya normalizados. Se indexa este y
    no los originales: así el acento deja de importar sin tocar lo que ve el usuario."""
    return _normaliza(" ".join([titulo or "", resumen or "", " ".join(tags or [])]))


# Palabras que no dicen nada de lo que se busca. Sin esta lista, "receta de arroz
# con pollo" devuelve memorias de facturación: "con" es prefijo de "contactos".
_VACIAS = {
    "al", "algo", "alguna", "algunas", "alguno", "algunos", "ante", "aqui", "asi",
    "cada", "como", "con", "contra", "cual", "cuales", "cuando", "cuanta", "cuanto",
    "de", "del", "desde", "donde", "dos", "el", "ella", "ellos", "en", "entre", "era",
    "eres", "es", "esa", "ese", "eso", "esta", "estan", "estas", "este", "esto",
    "estos", "estoy", "fue", "ha", "hay", "hacer", "hago", "la", "las", "le", "les",
    "lo", "los", "mas", "me", "mi", "mis", "mucho", "muy", "necesito", "ni", "no",
    "nos", "o", "otra", "otro", "para", "pero", "poder", "por", "porque", "puede",
    "puedo", "que", "quien", "quiero", "se", "ser", "si", "sin", "sobre", "solo",
    "son", "su", "sus", "tambien", "tengo", "tiene", "todo", "toda", "todos", "tu",
    "un", "una", "uno", "unos", "y", "ya",
}


def _palabras(query: str) -> list[str]:
    """Palabras con las que vale la pena buscar. Si el usuario solo escribió palabras
    vacías, se usan tal cual: peor es no buscar nada."""
    todas = _PALABRAS.findall(_normaliza(query))
    return [w for w in todas if w not in _VACIAS] or todas


def _puntaje(p: dict, palabras: list[str]) -> int:
    """Cuánto pega el query con esta memoria.

    Casar en el título vale más que en el resumen, y este más que en un tag: un
    acierto en el nombre es de lo que va la memoria, y un tag lo comparte media
    cuenta. Sin este peso, empatan todas y el desempate acaba siendo la fecha."""
    campos = ((4, p.get("titulo", "")), (2, p.get("resumen", "")),
              (1, " ".join(p.get("tags") or [])))
    total = 0
    for peso, texto in campos:
        tokens = _PALABRAS.findall(_normaliza(texto))
        total += peso * sum(1 for w in palabras if any(tk.startswith(w) for tk in tokens))
    return total


def _como_numero(query: str) -> int | None:
    """`12` o `#12` = buscar por consecutivo. El índice de texto no sirve para esto:
    un número corto no llega al mínimo de caracteres que se indexa."""
    q = query.strip().lstrip("#").strip()
    return int(q) if q.isdigit() else None


def _entrada_out(p: dict, con_contexto: bool = False) -> dict:
    out = {
        "id": p["_id"], "numero": p.get("numero"),
        "cuenta": p["cuenta"], "folder_id": p.get("folder_id"),
        "titulo": p["titulo"], "resumen": p["resumen"], "tipo": p["tipo"],
        "tags": p.get("tags", []), "path": p.get("path", []),
        "version": p.get("version", 1), "use_count": p.get("use_count", 0),
        "tokens": _tokens(p.get("contexto", "")),
        "created_at": store.iso(p.get("created_at")), "updated_at": store.iso(p.get("updated_at")),
        "last_used": store.iso(p.get("last_used")),
        "ultima_accion": _accion_out(p),
        **_archivo_out(p),
    }
    if con_contexto:
        out["contexto"] = p.get("contexto", "")
    return out


# --- Última acción: qué le pasó de último a una memoria (y a sus carpetas) --- #

def _accion(tipo: str, ts: float, detalle: str | None = None) -> dict:
    return {"tipo": tipo, "ts": ts, "detalle": detalle}


def _propagar_accion(cta: str, folder_id: str | None, accion: dict) -> None:
    """Marca la carpeta de la entrada y sus ancestros con la misma acción.

    Sin esto una carpeta padre se vería inactiva aunque sus memorias se usen a diario."""
    if not folder_id:
        return
    f = store.get(store.CARPETAS, folder_id)
    if not f or f.get("cuenta") != cta:
        return
    for fid in [folder_id] + list(f.get("ancestros", [])):
        store.set_payload(store.CARPETAS, fid, {"ultima_accion": accion})


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
        p = _carpeta_viva(cta, parent_id, "padre")
        ancestros = p.get("ancestros", []) + [p["_id"]]
        path = p.get("path", []) + [p["nombre"]]
        parent_ref = parent_id
    else:
        ancestros, path, parent_ref = [], [], ""  # "" = raíz

    ts = store.now_ts()
    pid = store.nuevo_id()
    payload = {"_id": pid, "cuenta": cta, "nombre": nombre, "parent_id": parent_ref,
               "ancestros": ancestros, "path": path, "descripcion": descripcion,
               "created_at": ts, "updated_at": ts,
               "ultima_accion": _accion("creada", ts)}
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
            destino = _carpeta_viva(cta, mover_a, "destino")
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

    ts = store.now_ts()
    cambios["updated_at"] = ts
    cambios["ultima_accion"] = _accion("movida" if mover_a is not None else "editada", ts)
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

    f = _carpeta_viva(cta, folder_id, "")

    ts = store.now_ts()
    pid = store.nuevo_id()
    payload = {
        "_id": pid, "numero": _siguiente_numero(cta),
        "cuenta": cta, "folder_id": folder_id,
        "ancestros": f.get("ancestros", []) + [f["_id"]],
        "path": f.get("path", []) + [f["nombre"]],
        "titulo": titulo, "resumen": resumen, "contexto": contexto,
        "tipo": tipo, "tags": tags or [],
        "busqueda": _texto_busqueda(titulo, resumen, tags),
        "created_at": ts, "updated_at": ts, "use_count": 0,
        "version": 1, "historial": [],
        "ultima_accion": _accion("creada", ts),
        "embedding_model": settings.embedding_model if settings.embeddings_enabled else None,
    }
    store.upsert(store.ENTRADAS, pid, payload, vector=_vector(resumen))
    _propagar_accion(cta, folder_id, payload["ultima_accion"])
    return _entrada_out(payload)


def editar_entrada(cta: str, entry_id: str, titulo: str | None = None,
                   resumen: str | None = None, contexto: str | None = None,
                   tipo: str | None = None, tags: list[str] | None = None,
                   mover_a: str | None = None) -> dict:
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

    origen = e.get("folder_id")
    if mover_a is not None:
        destino = _carpeta_viva(cta, _req(mover_a, "mover_a"), "destino")
        cambios["folder_id"] = mover_a
        cambios["ancestros"] = destino.get("ancestros", []) + [destino["_id"]]
        cambios["path"] = destino.get("path", []) + [destino["nombre"]]

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
    ts = store.now_ts()
    if {"titulo", "resumen", "tags"} & cambios.keys():   # si no, quedaría buscándose por lo viejo
        nuevo["busqueda"] = _texto_busqueda(nuevo["titulo"], nuevo["resumen"],
                                            nuevo.get("tags"))
    nuevo["updated_at"] = ts
    nuevo["version"] = e.get("version", 1) + 1
    nuevo["historial"] = e.get("historial", []) + [snapshot]
    nuevo["ultima_accion"] = _accion("movida" if mover_a is not None else "editada", ts)

    vector = _vector(nuevo["resumen"]) if "resumen" in cambios else vector_actual
    store.upsert(store.ENTRADAS, entry_id, nuevo, vector=vector)
    _propagar_accion(cta, nuevo.get("folder_id"), nuevo["ultima_accion"])
    if mover_a is not None and origen and origen != mover_a:
        _propagar_accion(cta, origen, _accion("movida", ts, detalle=nuevo["titulo"]))
    return _entrada_out(nuevo)


def obtener_entrada(cta: str, entry_id: str, marcar_uso: bool = True) -> dict:
    e = store.get(store.ENTRADAS, entry_id)
    if not e or e.get("cuenta") != cta:
        raise MemoriaError(f"entrada {entry_id} no existe en la cuenta '{cta}'")
    if marcar_uso:  # previsualizar en el navegador no debe contar como cargarla
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
    e["ultima_accion"] = _accion("cargada", e["last_used"])
    store.set_payload(store.ENTRADAS, e["_id"],
                      {"last_used": e["last_used"], "use_count": e["use_count"],
                       "ultima_accion": e["ultima_accion"]})
    _propagar_accion(e["cuenta"], e.get("folder_id"), e["ultima_accion"])


# --------------------------------------------------------------------------- #
# Borrar = archivar. Nada se destruye: se saca del árbol y se puede restaurar.
#
# El almacén guarda memoria de trabajo de meses; un borrado real es un error que
# no se puede deshacer y del que no queda ni rastro para saber qué faltaba. Lo
# archivado desaparece de listar/buscar, pero sigue accesible por id.
# --------------------------------------------------------------------------- #

def _marca_archivo(archivar: bool, ts: float, motivo: str | None,
                   por: str) -> dict:
    if not archivar:
        # Se dejan los campos en falso/vacío en vez de quitarlos: así una entrada
        # restaurada se distingue de una que nunca se tocó, y el filtro sigue igual.
        return {"archivada": False, "archivada_ts": None, "archivada_motivo": None,
                "archivada_por": None,
                "ultima_accion": _accion("restaurada", ts, motivo)}
    return {"archivada": True, "archivada_ts": ts, "archivada_motivo": motivo,
            "archivada_por": por,
            "ultima_accion": _accion("archivada", ts, motivo)}


def archivar_entrada(cta: str, entry_id: str, archivar: bool = True,
                     motivo: str | None = None) -> dict:
    e = store.get(store.ENTRADAS, entry_id)
    if not e or e.get("cuenta") != cta:
        raise MemoriaError(f"entrada {entry_id} no existe en la cuenta '{cta}'")
    if bool(e.get("archivada")) == archivar:
        estado = "archivada" if archivar else "activa"
        raise MemoriaError(f"la entrada '{e['titulo']}' ya está {estado}")

    ts = store.now_ts()
    cambios = _marca_archivo(archivar, ts, motivo, "directa")
    cambios["updated_at"] = ts
    store.set_payload(store.ENTRADAS, entry_id, cambios)
    _propagar_accion(cta, e.get("folder_id"),
                     _accion(cambios["ultima_accion"]["tipo"], ts, e["titulo"]))
    return _entrada_out({**e, **cambios})


def _subarbol(cta: str, folder_id: str) -> tuple[list[dict], list[dict]]:
    """Carpetas descendientes y entradas que cuelgan de ahí (a cualquier profundidad).

    Se resuelve con `ancestros`, que ya lleva la rama completa: no hace falta
    recorrer nivel por nivel."""
    bajo = [store.cond("cuenta", cta), store.cond_any("ancestros", [folder_id])]
    return (store.scroll(store.CARPETAS, must=bajo, limit=10000),
            store.scroll(store.ENTRADAS, must=bajo, limit=10000))


def archivar_carpeta(cta: str, folder_id: str, archivar: bool = True,
                     motivo: str | None = None) -> dict:
    """Archiva la carpeta con todo lo que cuelga de ella, y la restaura igual.

    Al restaurar solo vuelve lo que se archivó *con* esta carpeta: lo que ya
    estaba archivado por su cuenta se queda como estaba, que es lo que el usuario
    dejó dicho la última vez."""
    f = store.get(store.CARPETAS, folder_id)
    if not f or f.get("cuenta") != cta:
        raise MemoriaError(f"carpeta {folder_id} no existe en la cuenta '{cta}'")
    if bool(f.get("archivada")) == archivar:
        estado = "archivada" if archivar else "activa"
        raise MemoriaError(f"la carpeta '{f['nombre']}' ya está {estado}")

    ts = store.now_ts()
    subcarpetas, entradas = _subarbol(cta, folder_id)
    propia = _marca_archivo(archivar, ts, motivo, "directa")
    propia["updated_at"] = ts
    heredada = _marca_archivo(archivar, ts, motivo, folder_id)

    tocadas = 0
    for coll, puntos in ((store.CARPETAS, subcarpetas), (store.ENTRADAS, entradas)):
        for p in puntos:
            if archivar:
                if p.get("archivada"):
                    continue                       # ya estaba: no lo toco
            elif p.get("archivada_por") != folder_id:
                continue                           # no se archivó con esta carpeta
            store.set_payload(coll, p["_id"], heredada)
            tocadas += 1

    store.set_payload(store.CARPETAS, folder_id, propia)
    if f.get("parent_id"):
        _propagar_accion(cta, f["parent_id"],
                         _accion(propia["ultima_accion"]["tipo"], ts, f["nombre"]))
    return {**_carpeta_out({**f, **propia}), "arrastradas": tocadas}


def ver_historial(cta: str, entry_id: str) -> dict:
    """Las versiones anteriores de una memoria, de la más nueva a la más vieja.

    Cada edición guarda la versión que había antes, así que la versión N tiene
    N-1 registros. Va aparte de `obtener_entrada` porque el historial completo
    puede ser mucho más grande que la memoria y casi nunca se necesita."""
    e = store.get(store.ENTRADAS, entry_id)
    if not e or e.get("cuenta") != cta:
        raise MemoriaError(f"entrada {entry_id} no existe en la cuenta '{cta}'")
    hist = list(e.get("historial", []))
    hist.reverse()
    return {
        "id": entry_id, "titulo": e["titulo"], "version_actual": e.get("version", 1),
        "versiones": [{
            "version": h.get("version"), "fecha": store.iso(h.get("ts")),
            "titulo": h.get("titulo"), "resumen": h.get("resumen"),
            "tipo": h.get("tipo"), "tags": h.get("tags", []),
            "contexto": h.get("contexto", ""),
            "tokens": _tokens(h.get("contexto", "")),
        } for h in hist],
    }


# --------------------------------------------------------------------------- #
# Navegación y búsqueda (siempre scoped a la cuenta)
# --------------------------------------------------------------------------- #

def listar(cta: str, folder_id: str | None = None,
           incluir_archivadas: bool = False) -> dict:
    from .instructions import DOCUMENTACION_USO
    parent = folder_id or ""  # "" = raíz
    vivas = [] if incluir_archivadas else [store.cond_viva()]

    carpetas = store.scroll(store.CARPETAS,
                            must=[store.cond("cuenta", cta),
                                  store.cond("parent_id", parent)] + vivas)
    carpetas.sort(key=lambda p: p.get("nombre", ""))
    out = {"cuenta": cta, "folder_id": folder_id,
           "carpetas": [_carpeta_out(c) for c in carpetas], "entradas": []}

    if folder_id:  # las entradas viven dentro de una carpeta
        entradas = store.scroll(store.ENTRADAS,
                                must=[store.cond("cuenta", cta),
                                      store.cond("folder_id", folder_id)] + vivas,
                                order_key="updated_at")
        out["entradas"] = [_entrada_out(e) for e in entradas]
    else:
        out["documentacion_de_uso"] = DOCUMENTACION_USO
    return out


def _must(cta: str, tipo: str | None, folder_id: str | None, tags: list[str] | None,
          incluir_archivadas: bool = False) -> list:
    must = [store.cond("cuenta", cta)]
    if not incluir_archivadas:
        must.append(store.cond_viva())
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
           limit: int = 15, incluir_archivadas: bool = False) -> list[dict]:
    must = _must(cta, tipo, folder_id, tags, incluir_archivadas)

    # Camino vectorial (embeddings activos + hay query).
    if settings.embeddings_enabled and query.strip():
        from . import embeddings
        vec = embeddings.embed(query, kind="query")
        return [_entrada_out(p) for p in store.search(store.ENTRADAS, vec, must=must, limit=limit)]

    # Camino texto/metadatos (full-text de payload de Qdrant).
    if not query.strip():
        return [_entrada_out(p) for p in
                store.scroll(store.ENTRADAS, must=must, order_key="updated_at", limit=limit)]

    def busca(opciones, tope: int) -> list[dict]:
        from qdrant_client.models import Filter
        return store.scroll(store.ENTRADAS, must=must + [Filter(should=opciones)],
                            order_key="updated_at", limit=tope)

    # Un query que es solo un número se lee como el consecutivo, y NO como texto:
    # el contexto va indexado por palabras, así que "3" traería toda memoria que
    # mencione un 3 por ahí. Si no existe esa memoria se reintenta como texto,
    # porque entonces lo más probable es que buscara algo tipo "2026". Con "#" no
    # se reintenta: ahí el usuario ya dijo explícitamente que iba por número.
    numero = _como_numero(query)
    if numero is not None:
        res = busca([store.cond("numero", numero)], limit)
        if res or query.strip().startswith("#"):
            return [_entrada_out(p) for p in res]

    # El usuario pide con una frase ("crear una factura con el facturador de la
    # DIAN"), no con la palabra exacta que quedó guardada. Qdrant exige que estén
    # TODAS las palabras del texto que se le pase, así que una sola que no case
    # deja fuera la memoria correcta: se busca palabra por palabra, con OR, y se
    # ordena aquí por cuántas casaron. El contexto va con la frase completa, para
    # que sume solo cuando de verdad habla del tema.
    palabras = _palabras(query)
    if not palabras:
        return []
    opciones = [store.cond_text("busqueda", w) for w in palabras]
    opciones.append(store.cond_text("contexto", query))

    candidatos = busca(opciones, max(limit * 5, 50))
    candidatos.sort(key=lambda p: (-_puntaje(p, palabras), -(p.get("updated_at") or 0)))
    return [_entrada_out(p) for p in candidatos[:limit]]


def buscar_relacionadas(cta: str, texto: str | None = None,
                        entry_id: str | None = None, limit: int = 15) -> list[dict]:
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
    """Las últimas usadas primero y, si sobra cupo, las creadas/editadas más nuevas.

    Una entrada nunca usada no tiene `last_used`, y Qdrant excluye del `order_by`
    los puntos sin ese campo: sin el relleno, una cuenta recién poblada se vería
    vacía."""
    must = [store.cond("cuenta", cta), store.cond_viva()]
    salida = store.scroll(store.ENTRADAS, must=must, order_key="last_used", limit=limit)
    if len(salida) < limit:
        vistos = {p["_id"] for p in salida}
        nuevas = store.scroll(store.ENTRADAS, must=must, order_key="updated_at",
                              limit=limit + len(vistos))
        for p in nuevas:
            if p["_id"] in vistos:
                continue
            salida.append(p)
            if len(salida) >= limit:
                break
    return [_entrada_out(p) for p in salida]
