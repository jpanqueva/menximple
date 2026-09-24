"""Catálogo mínimo para las pruebas de canales: con la nomenclatura estricta, ni
un agente ni un canal existen si su equipo, ámbito y actividad no están dados
de alta. Se importa después de `store.ensure_collections()`."""
from memory_server import registro
from memory_server.models import MemoriaError

registro.sembrar()
for eq in ("eqa", "eqb", "eqc", "eqz") + tuple(f"eq{i}" for i in range(10)):
    try:
        registro.crear("equipo", eq, cta="x", hostname=f"host-{eq}", tipo="pc")
    except MemoriaError:
        pass
for amb in ("prueba", "otro"):
    try:
        registro.crear("ambito", amb, cta="x", tipo="proyecto")
    except MemoriaError:
        pass
