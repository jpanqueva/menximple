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
    key = _apikey()
    if not key:
        raise MemoriaError("falta apikey: envía el header 'X-API-Key' de la cuenta")
    pts = store.scroll(store.CUENTAS, must=[store.cond("apikey", key)], limit=1)
    if not pts:
        raise MemoriaError("apikey inválida")
    return pts[0]["slug"]


def exigir_admin() -> None:
    """Protege la gestión de cuentas. Si no hay admin_token configurado, queda abierto (dev)."""
    if not settings.admin_token:
        return
    headers = get_http_headers() or {}
    if headers.get("x-admin-token") != settings.admin_token:
        raise MemoriaError("token de administración inválido o ausente (header 'X-Admin-Token')")
