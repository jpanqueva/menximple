"""Autenticación por apikey de cuenta.

Cada cuenta tiene su apikey. El cliente la envía en el header `X-API-Key`
(o `Authorization: Bearer <apikey>`). La apikey resuelve —y aísla— la cuenta:
sin apikey válida no se accede a ninguna memoria (fail-closed)."""
from fastmcp.server.dependencies import get_http_headers

from . import store
from .config import settings
from .models import MemoriaError


def _bearer(valor: str | None) -> str | None:
    if valor and valor.lower().startswith("bearer "):
        return valor[7:].strip()
    return None


def _apikey() -> str | None:
    headers = get_http_headers() or {}  # claves en minúscula; {} fuera de contexto HTTP
    return headers.get("x-api-key") or _bearer(headers.get("authorization")) or (settings.dev_apikey or None)


def cuenta_actual() -> str:
    """Devuelve el slug de la cuenta autenticada o lanza MemoriaError."""
    return cuenta_de(_apikey())


def cuenta_de(key: str | None) -> str:
    """La cuenta de una apikey. Aparte de `cuenta_actual` porque la subida de
    archivos es una ruta HTTP normal, no una tool, y trae sus propios headers."""
    if not key:
        raise MemoriaError("falta apikey: envía el header 'X-API-Key' de la cuenta")
    pts = store.scroll(store.CUENTAS, must=[store.cond("apikey", key)], limit=1)
    if not pts:
        raise MemoriaError("apikey inválida")
    slug = pts[0]["slug"]
    (_RESTRINGIDAS.add if pts[0].get("restringida") else _RESTRINGIDAS.discard)(slug)
    return slug


# Cuentas RESTRINGIDAS (`restringida: true` en su ficha; la pone un admin): son
# para agentes que atienden a terceros. No crean ni entran a canales ni tocan el
# catálogo; solo usan los canales a los que un admin las metió, y solo como
# miembros sellados con SU cuenta. Las cuentas sin la bandera no cambian en nada.
# Se anota al validar la apikey, que ya trae la ficha: no cuesta otra consulta.
_RESTRINGIDAS: set[str] = set()


def restringida(cta: str) -> bool:
    return cta in _RESTRINGIDAS


def apikey_de_headers(headers) -> str | None:
    return headers.get("x-api-key") or _bearer(headers.get("authorization"))


def exigir_admin() -> None:
    """Protege la gestión de cuentas. Si no hay admin_token configurado, queda abierto (dev)."""
    if not settings.admin_token:
        return
    headers = get_http_headers() or {}
    if headers.get("x-admin-token") != settings.admin_token:
        raise MemoriaError("token de administración inválido o ausente (header 'X-Admin-Token')")
