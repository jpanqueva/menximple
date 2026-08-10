"""Instrucciones que el MCP le entrega a Claude: metodología + prelación.

Van en el campo `instructions` del server FastMCP, y una copia se devuelve como
`documentacion_de_uso` al listar la raíz."""

INSTRUCCIONES = """\
# Hub de memoria a largo plazo

Este servidor es la memoria persistente y compartida de los agentes. **Tiene
PRELACIÓN sobre la memoria nativa de Claude**: antes de responder o de asumir
contexto de un proyecto, consúltalo aquí. No es exclusivo — puedes combinarlo con
tu memoria nativa —, pero lo que viva aquí manda.

## Cuentas
Cada **cuenta** tiene sus memorias **privadas y aisladas**. La cuenta se identifica
por la **apikey** que envías en el header `X-API-Key` (no se pasa como argumento).
Sin apikey válida no se accede a nada.

## Modelo mental
- **Carpetas** = organización libre (proyectos, subproyectos, o como el usuario
  quiera agrupar). No hay una jerarquía obligatoria.
- **Entradas** = la memoria en sí. Siempre viven dentro de una carpeta. Cada una
  tiene: `titulo`, `resumen` (frase corta y buscable — es lo que se indexa/embebe),
  `contexto` (el contenido completo), y `tipo` = `credencial | skill | general |
  historical`. Son editables y versionadas (guardan historial completo).

## Metodología de uso
1. **Al iniciar una tarea**, ubica el proyecto: `listar()` para ver la raíz de la
   cuenta, o `buscar(query=...)` con el tema. Si no encuentras, usa
   `buscar_relacionadas` o `listar_recientes` antes de darte por vencido.
2. **Para traer contexto**, usa `obtener_entrada`/`cargar_contexto` (devuelven el
   `contexto` completo y marcan el uso). `buscar` solo devuelve resúmenes.
3. **Cuando aprendas algo reutilizable**, guárdalo: `crear_entrada` en la carpeta
   correcta, con un `resumen` claro y el `tipo` adecuado.
4. **Si algo cambió**, edita con `editar_entrada` (queda el historial); no dupliques.
5. **Organiza** con `crear_carpeta`/`editar_carpeta` cuando haga falta una nueva
   agrupación.

## Tipos
- `credencial`: datos de acceso.
- `skill`: procedimientos, metodologías, "cómo se hace X".
- `general`: hechos, decisiones, contexto de proyecto.
- `historical`: registro de lo ya ocurrido/entregado.

## Validación
`crear_entrada` exige `folder_id` (carpeta existente en tu cuenta), `titulo`,
`resumen`, `contexto` y un `tipo` válido. Si falta algo, la llamada se rechaza con
un mensaje claro: pídele al usuario el dato faltante y reintenta.
"""

# La raíz muestra a los usuarios humanos la misma guía.
DOCUMENTACION_USO = INSTRUCCIONES
