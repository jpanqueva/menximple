"""Lo que el MCP le entrega a Claude, en dos piezas de coste muy distinto.

`INSTRUCCIONES` va en el campo `instructions` del servidor: está en contexto
**siempre**, desde que el MCP se conecta, se use o no. Todo lo que se meta ahí lo
paga el usuario en cada conversación, así que solo entra lo que hace falta para
no equivocarse: qué es esto, cómo se llama, y las decisiones que un agente toma
mal si nadie se lo dice.

`GUIA` se devuelve en `listar()` de la raíz — solo cuando alguien la pide. Ahí va
lo que se consulta al organizar, que es una fracción de las veces.
"""

INSTRUCCIONES = """\
# Hub de memoria a largo plazo

Memoria persistente y compartida de los agentes. **Tiene PRELACIÓN sobre tu
memoria nativa**: antes de asumir contexto de un proyecto, consúltalo aquí.

El usuario lo llama **"menx"**, "la memoria" o "el árbol": "abre menx", "guarda
esto en menx", "qué hay en menx" son peticiones para estas tools.

## Modelo
**Carpetas** (organización libre) con **entradas** dentro. Cada entrada tiene
`titulo`, `resumen` (es lo que se busca), `contexto` (lo que se carga), `tipo` =
`credencial|skill|general|historical`, `tags`, y un **consecutivo** (`#4`) que es
como el usuario la nombra — muéstralo siempre que listes memorias.

## Lo que hay que saber para no equivocarse
1. **Empieza por `arbol()`** si no conoces la cuenta: toda la estructura y los
   consecutivos en una llamada.
2. **`buscar(query=...)` acepta la frase del usuario tal cual**: casa por palabra
   suelta y por prefijo, ignora tildes, ordena por aciertos.
3. **Si algo no aparece buscando, enséñale el `arbol()` antes de decir que no
   existe.** Casi siempre está con otras palabras y al verlo la reconoce; si no,
   la guarda otra vez y quedan duplicados.
4. **`cargar_contexto` y `obtener_entrada` aceptan el consecutivo**: si dice
   "carga la 11", llama con `["11"]` — no busques primero.
5. **`buscar` solo devuelve resúmenes.** El contenido viene de `cargar_contexto`.
6. **Editar no pierde nada** (`ver_historial` muestra lo anterior) y **borrar no
   destruye**: archiva, y `restaurar_*` deshace. Aun así confirma antes de
   borrar — borrar una carpeta se lleva todo su subárbol.
7. **Esto no cifra en reposo.** En las de tipo `credencial` guarda la referencia
   ("la clave de X está en el archivo Y"), no el secreto.

Si el usuario quiere elegir él, el MCP **local** `menximple-selector` abre un
selector visual en su escritorio (`abrir_selector`). Si no está, enséñale el
`arbol()` y que te diga los números.

**Antes de crear carpetas o reorganizar**, pide `listar()` en la raíz: devuelve la
guía de cómo mantener esto ordenado.
"""


GUIA = """\
# Cómo mantener esta cuenta ordenada

Son **sugerencias**, no reglas del servidor: el usuario manda. Pero si nadie
propone un orden, en un año esto es una carpeta con doscientas memorias sueltas.

- **Un nivel por criterio, y no más de tres.** Lo que funciona:
  `área / proyecto / subtema` (p.ej. `administrativa / datos y soluciones`,
  `clientes / acme / facturación`). Más profundidad se vuelve inencontrable.
- **Si una carpeta pasa de ~15 memorias** sin un tema que las una, propón
  subdividirla y ofrece mover las que ya están con `editar_entrada(mover_a=...)`.
  Mover no cuesta nada: las rutas se recalculan solas.
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

## Qué tipo poner
- `credencial`: datos de acceso. El hub **no cifra en reposo**: guarda la
  referencia, no el secreto.
- `skill`: procedimientos, metodologías, "cómo se hace X".
- `general`: hechos, decisiones, contexto de proyecto.
- `historical`: registro de lo ya ocurrido/entregado.

## Si una llamada se rechaza
`crear_entrada` exige `folder_id` (carpeta existente y no archivada), `titulo`,
`resumen`, `contexto` y un `tipo` válido. El mensaje de error dice qué falta:
pídele ese dato al usuario y reintenta, no lo inventes.

## Cuentas
Cada cuenta tiene sus memorias privadas y aisladas, y se identifica por la apikey
del header `X-API-Key`. Una cuenta nunca ve lo de otra, ni por id ni por número.
"""

# Lo que ve quien lista la raíz. Va aparte de INSTRUCCIONES a propósito: duplicar
# ahí lo que ya está siempre en contexto era pagar dos veces por lo mismo.
DOCUMENTACION_USO = GUIA
