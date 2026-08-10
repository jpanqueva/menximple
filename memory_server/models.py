"""Tipos del dominio."""
from enum import Enum


class TipoEntrada(str, Enum):
    credencial = "credencial"
    skill = "skill"
    general = "general"
    historical = "historical"


TIPOS = tuple(t.value for t in TipoEntrada)


class MemoriaError(Exception):
    """Error de dominio con mensaje accionable para el agente cliente.

    El server lo traduce a ToolError (nunca se silencia). Los errores
    inesperados se dejan propagar tal cual (fail-fast)."""
