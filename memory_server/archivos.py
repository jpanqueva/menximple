"""Archivos publicados: se suben y quedan en un link público.

Existe para lo que las memorias no resuelven: un PDF, un informe HTML o una imagen
que hay que **pasarle a alguien**. Se publica y lo que vuelve es una URL; compartir
por un canal es mandar esa URL como texto, sin nada especial en los canales.

Tres decisiones que conviene entender antes de tocar esto:

- **Los bytes van a disco, no a Qdrant.** Qdrant es el almacén de las memorias y
  guarda aquí solo la ficha (nombre, tamaño, dueño, token). Meter 20 MB en un
  payload lo haría viajar entero en cada `scroll` de la colección.
- **El link es el permiso.** Quien tiene la URL abre el archivo, sin apikey: es
  para eso. Por eso el token es largo y aleatorio (no sale del id ni del nombre) y
  el nombre del final de la URL es decorativo — cambiarlo no abre otro archivo.
- **Borrar sí destruye**, a diferencia de las memorias. Un archivo publicado es
  algo que se entrega, no conocimiento que haya que poder recuperar; y lo que de
  verdad hace falta al borrar es que el link muera y el disco se libere, que el
  servidor es compartido.
"""
import hashlib
import os
import re
import secrets
import unicodedata
from pathlib import Path
from urllib.parse import quote

from . import store
from .config import settings
from .models import MemoriaError

MB = 1024 * 1024

# Lo que el navegador ejecutaría si se abre en el dominio del hub. Se sirve con CSP
# `sandbox` (ver server.py) para que un HTML publicado no corra con el origen del hub.
ACTIVOS = ("text/html", "application/xhtml+xml", "image/svg+xml", "text/xml",
           "application/xml")


def _dir() -> Path:
    d = Path(settings.archivos_dir)
    d.mkdir(parents=True, exist_ok=True)
    return d


def _ruta(a: dict) -> Path:
    # Se guarda por id, nunca por el nombre que mandó el cliente: así un nombre
    # como `../../.env` no puede escribir fuera de la carpeta.
    return _dir() / a["_id"]


def nombre_limpio(nombre: str | None) -> str:
    """El nombre que se muestra y va al final de la URL.

    Se queda con la última parte de una ruta (Windows o Unix), quita tildes y deja
    letras, números, punto, guion y guion bajo. Lo demás pasa a guion."""
    n = re.split(r"[\\/]", (nombre or "").strip())[-1]
    n = unicodedata.normalize("NFKD", n).encode("ascii", "ignore").decode()
    n = re.sub(r"[^A-Za-z0-9._-]+", "-", n).strip(".-")
    return n[:120] or "archivo"


def _mime(nombre: str, mime: str | None) -> str:
    import mimetypes
    if mime and "/" in mime:
        return mime.split(";")[0].strip().lower()
    return mimetypes.guess_type(nombre)[0] or "application/octet-stream"


def url(a: dict) -> str:
    ruta = f"/f/{a['token']}/{quote(a['nombre'])}"
    return settings.public_base_url.rstrip("/") + ruta


def _out(a: dict) -> dict:
    return {
        "id": a["_id"], "nombre": a["nombre"], "url": url(a),
        "mime": a["mime"], "tamano": a["tamano"], "sha256": a["sha256"],
        "descripcion": a.get("descripcion"),
        "creado": store.iso(a.get("created_at")),
        "expira": store.iso(a.get("expira_at")),
    }


def _vencido(a: dict) -> bool:
    return bool(a.get("expira_at")) and a["expira_at"] <= store.now_ts()


def _de_cuenta(cta: str) -> list[dict]:
    return store.scroll(store.ARCHIVOS, must=[store.cond("cuenta", cta)], limit=5000)


def publicar(cta: str, nombre: str | None, datos: bytes, mime: str | None = None,
             expira_dias: float | None = None, descripcion: str | None = None) -> dict:
    """Guarda el archivo y devuelve su ficha con la URL pública."""
    if not datos:
        raise MemoriaError("el archivo está vacío")
    maximo = settings.archivos_max_mb * MB
    if len(datos) > maximo:
        raise MemoriaError(f"el archivo pesa {len(datos) / MB:.1f} MB y el máximo es "
                           f"{settings.archivos_max_mb} MB")
    # La cuota cuenta también los vencidos: siguen ocupando disco hasta que se borren.
    usado = sum(a.get("tamano", 0) for a in _de_cuenta(cta))
    cuota = settings.archivos_cuota_mb * MB
    if usado + len(datos) > cuota:
        raise MemoriaError(f"no cabe: la cuenta usa {usado / MB:.1f} MB de "
                           f"{settings.archivos_cuota_mb} MB. Borra alguno con "
                           "`borrar_archivo` (míralos con `listar_archivos`)")
    if expira_dias is not None and expira_dias <= 0:
        raise MemoriaError("`expira_dias` tiene que ser mayor que 0 (u omitirse)")

    nombre = nombre_limpio(nombre)
    ts = store.now_ts()
    a = {
        "_id": store.nuevo_id(), "cuenta": cta, "nombre": nombre,
        "mime": _mime(nombre, mime), "tamano": len(datos),
        "sha256": hashlib.sha256(datos).hexdigest(),
        "token": secrets.token_urlsafe(24), "descripcion": descripcion,
        "created_at": ts,
        "expira_at": ts + expira_dias * 86400 if expira_dias else None,
    }
    # Primero el disco y después la ficha: si falla la escritura no queda un link
    # que apunta a nada. Se escribe a un temporal y se renombra para que nadie
    # sirva un archivo a medio escribir.
    destino = _ruta(a)
    tmp = destino.with_suffix(".parcial")
    tmp.write_bytes(datos)
    os.replace(tmp, destino)
    try:
        store.upsert(store.ARCHIVOS, a["_id"], a)
    except Exception:
        destino.unlink(missing_ok=True)
        raise
    return _out(a)


def listar(cta: str) -> list[dict]:
    """Los archivos de la cuenta, del más nuevo al más viejo, con lo que ocupan."""
    xs = sorted(_de_cuenta(cta), key=lambda a: a.get("created_at", 0), reverse=True)
    return [{**_out(a), "vencido": _vencido(a)} for a in xs]


def _token_de(ref: str) -> str | None:
    m = re.search(r"/f/([A-Za-z0-9_-]+)", ref)
    return m.group(1) if m else None


def _buscar(cta: str, ref: str) -> dict:
    ref = (ref or "").strip()
    if not ref:
        raise MemoriaError("falta el archivo: pasa su `id` o su URL")
    a = store.get(store.ARCHIVOS, ref) if store.es_id_valido(ref) else None
    if a is None:
        token = _token_de(ref) or ref
        hallados = store.scroll(store.ARCHIVOS, must=[store.cond("token", token)], limit=1)
        a = hallados[0] if hallados else None
    # Lo de otra cuenta responde igual que lo inexistente: decir "es de otro" ya
    # confirma que el link existe.
    if a is None or a.get("cuenta") != cta:
        raise MemoriaError("no hay ningún archivo tuyo con ese id o URL; míralos con "
                           "`listar_archivos`")
    return a


def borrar(cta: str, ref: str) -> dict:
    """Borra de verdad: el link deja de abrir y el disco se libera."""
    a = _buscar(cta, ref)
    store.delete(store.ARCHIVOS, a["_id"])
    _ruta(a).unlink(missing_ok=True)
    return {"borrado": a["nombre"], "url_que_ya_no_abre": url(a),
            "liberado": a.get("tamano", 0)}


def para_servir(token: str) -> tuple[dict, Path] | None:
    """La ficha y la ruta en disco de un link público, o None si no debe abrir."""
    if not token or not re.fullmatch(r"[A-Za-z0-9_-]{16,64}", token):
        return None
    hallados = store.scroll(store.ARCHIVOS, must=[store.cond("token", token)], limit=1)
    if not hallados or _vencido(hallados[0]):
        return None
    a = hallados[0]
    ruta = _ruta(a)
    return (a, ruta) if ruta.is_file() else None
