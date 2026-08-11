"""Instrucciones que el MCP le entrega a Claude: metodología + prelación.

Van en el campo `instructions` del server FastMCP, y una copia se devuelve como
`documentacion_de_uso` al listar la raíz."""

INSTRUCCIONES = """\
# Hub de memoria a largo plazo

Este servidor es la memoria persistente y compartida de los agentes. **Tiene
PRELACIÓN sobre la memoria nativa de Claude**: antes de responder o de asumir
contexto de un proyecto, consúltalo aquí. No es exclusivo — puedes combinarlo con
tu memoria nativa —, pero lo que viva aquí manda.

## Cómo lo llama el usuario
Se llama **menximple**, pero el usuario suele decirle **"menx"**, "la memoria",
"mis memorias" o "el árbol". Todo eso se refiere a este servidor: "abre menx",
"guarda esto en menx", "busca en menx" o "qué hay en menx" son peticiones para
estas tools, no para tu memoria nativa ni para archivos del disco.

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

Cada memoria tiene además un **consecutivo** (`#4`): es como el usuario la va a
nombrar en voz alta. Muéstralo siempre que listes memorias.

## Metodología de uso
1. **Si no conoces la cuenta, empieza por `arbol()`**: te da toda la estructura y
   los consecutivos en una sola llamada. `listar()` es para entrar a una carpeta
   concreta.
2. **Para encontrar algo**, `buscar(query=...)` con la frase del usuario tal cual:
   casa por palabra suelta y por prefijo, ignora tildes y ordena por aciertos. Un
   query que sea solo un número busca por consecutivo.
3. **Si una memoria no aparece buscando, enséñale el `arbol()`** antes de decirle
   que no existe. Casi siempre está guardada con otras palabras, y viéndola la
   reconoce al instante — sobre todo si no tiene el selector visual a mano. Decir
   "no encontré nada" cuando el árbol la habría mostrado es el peor error posible
   aquí: el usuario acaba guardándola otra vez, duplicada.
4. **Para traer contexto**, usa `obtener_entrada`/`cargar_contexto` (devuelven el
   `contexto` completo y marcan el uso). `buscar` solo devuelve resúmenes.
   Ambas aceptan el **consecutivo**: si el usuario dice "carga la 11", llama con
   `["11"]` directamente, sin buscar primero.
5. **Cuando aprendas algo reutilizable**, guárdalo: `crear_entrada` en la carpeta
   correcta, con un `resumen` claro y el `tipo` adecuado.
6. **Si algo cambió**, edita con `editar_entrada` (queda el historial); no dupliques.
   Lo que decía antes se consulta con `ver_historial`.
7. **Organiza** con `crear_carpeta`/`editar_carpeta` cuando haga falta una nueva
   agrupación.
8. **Borrar no destruye**: `borrar_entrada`/`borrar_carpeta` archivan, y
   `restaurar_*` deshace. Aun así confírmalo con el usuario antes de borrar —
   borrar una carpeta se lleva todo su subárbol.

## Cómo dejarle la cuenta ordenada al usuario
Son **sugerencias**, no reglas del servidor: el usuario manda. Pero si nadie
propone un orden, en un año esto es una carpeta con doscientas memorias sueltas.

- **Un nivel por criterio, y no más de tres.** Lo que funciona:
  `área / proyecto / subtema` (p.ej. `administrativa / datos y soluciones`,
  `clientes / acme / facturación`). Más profundidad se vuelve inencontrable.
- **Si una carpeta pasa de ~15 memorias** sin un tema que las una, propón
  subdividirla y ofrece mover las que ya están con `editar_entrada(mover_a=...)`.
- **No mezcles cosas sin relación clara** en la misma carpeta solo porque son del
  mismo cliente: separa procedimiento (`skill`) de datos (`general`) cuando cada
  uno se consulta en momentos distintos.
- **Una memoria = un tema.** Si el `contexto` crece tanto que cargarlo trae mucho
  que no viene al caso, pártelo en dos y enlaza mencionando el consecutivo.
- **El `resumen` es lo que se busca**: escríbelo con las palabras que el usuario
  usaría al preguntar, no con las del título.
- **Los `tags` son para lo transversal** (`cliente`, `facturacion`), lo que cruza
  varias carpetas. No repitas ahí lo que ya dice la carpeta.
- Antes de crear una carpeta nueva, mira el `arbol()`: casi siempre ya existe una
  que sirve, con otro nombre.

## Tipos
- `credencial`: datos de acceso. **Ojo**: el hub no cifra en reposo. Guarda aquí
  la referencia ("la clave de X está en el archivo Y"), no el secreto, salvo que
  el usuario diga lo contrario.
- `skill`: procedimientos, metodologías, "cómo se hace X".
- `general`: hechos, decisiones, contexto de proyecto.
- `historical`: registro de lo ya ocurrido/entregado.

## Validación
`crear_entrada` exige `folder_id` (carpeta existente en tu cuenta), `titulo`,
`resumen`, `contexto` y un `tipo` válido. Si falta algo, la llamada se rechaza con
un mensaje claro: pídele al usuario el dato faltante y reintenta.

## Si el usuario quiere elegir él
Hay un segundo servidor MCP, **local**, con el selector visual: `abrir_selector`
abre una ventana en su escritorio y devuelve lo que marque. Si no está instalado
o no hay escritorio, enséñale el `arbol()` y que te diga los consecutivos.
"""

# La raíz muestra a los usuarios humanos la misma guía.
DOCUMENTACION_USO = INSTRUCCIONES
