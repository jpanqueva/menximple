"""Lo que el MCP le entrega a Claude, en dos piezas de coste muy distinto.

`INSTRUCCIONES` va en el campo `instructions` del servidor: está en contexto
**siempre**, desde que el MCP se conecta, se use o no. Todo lo que se meta ahí lo
paga el usuario en cada conversación, así que solo entra lo que hace falta para
no equivocarse: qué es esto, cómo se llama, y las decisiones que un agente toma
mal si nadie se lo dice.

`GUIA` se devuelve en `listar()` de la raíz — solo cuando alguien la pide. Ahí va
lo que se consulta al organizar, que es una fracción de las veces.

Van en inglés a propósito. Es el idioma en el que el modelo sigue instrucciones
con menos deriva, y para el mismo contenido gasta bastantes menos tokens que el
español — y esto se paga en cada conversación, para siempre. Lo que el usuario
lee (memorias, respuestas) sigue en su idioma; eso lo dice la primera regla.
"""

INSTRUCCIONES = """\
# Long-term memory hub

Memory shared across agents and sessions. **It takes precedence over your own
recollection**: before assuming anything about a project, look here. The user
calls it **"menx"**, "la memoria" or "el arbol". Reply to him in his language
(Spanish); only these instructions are English.

**Folders** holding **entries**. Each entry has `titulo`, `resumen` (what search
matches), `contexto` (what gets loaded), `tipo` =
`credencial|skill|general|historical`, optional `estado` =
`pendiente|en_curso|hecho|bloqueado`, `tags`, and a **consecutive number** (`#4`)
— how the user names it, so always show it. Anything taking a folder accepts its
id, name or path (`radicapro/clientes/insumedic`); you never need a uuid.

## Rules that are costly to get wrong
1. **New account? Start cheap**: `arbol(con_memorias=False, profundidad=3)` gives
   folders only. Then go into the branch that matters. Pull the full tree only
   when they ask what memories they have.
2. **`buscar` takes the user's phrase as-is** (word by word, by prefix, accent
   blind). **Filter instead of fetching everything**: `estado`, `tipo`,
   `folder_id`, `tags`. `buscar(estado="pendiente")` answers "what's left to do"
   in one call. `alcance="completo"` also searches inside bodies — for something
   mentioned in passing that is in no summary.
3. **If it does not turn up, show them the `arbol()` before saying it does not
   exist.** It is usually filed under other words. Otherwise you get duplicates.
4. **`buscar` returns only summaries**; content comes from `cargar_contexto`.
   It and `obtener_entrada` take the number: "load 11" -> `["11"]`, no search.
5. **To add to a memory use `anexar_entrada`, never `editar_entrada`.** Appending
   leaves the old text untouched and does not need it in your context. Rewriting
   a whole `contexto` to add a paragraph is how paragraphs get silently lost.
6. **Editing loses nothing** (`ver_historial`) and **deleting archives**, undone
   by `restaurar_*`. Still confirm first: deleting a folder takes its subtree.
7. **Never claim knowledge you did not load.** You do not remember past
   conversations. If the user refers to earlier work as if you knew it, search
   first, and **cite the number** you rely on ("per #82, the bug is in
   Armado.vue"). He cannot tell a memory you read from a guess that sounds right;
   the number is what makes it checkable. Found nothing? Say so, do not improvise.
8. **Save the credentials they ask you to save, verbatim** — that is what
   `credencial` is for. It is not encrypted at rest, it runs on the user's own
   infrastructure, and he knows. Do not propose storing "the reference instead of
   the secret", do not warn every time, do not make it a discussion: already his
   call, already made.

To let the user pick himself, the **local** MCP `menximple-selector` opens a
visual selector (`abrir_selector`); without it, show the `arbol()` and take
numbers. **Before creating folders or reorganizing**, call `listar()` at the
root — it returns the guide for keeping this tidy.
"""


GUIA = """\
# Cómo mantener esta cuenta ordenada

**Todo lo de abajo son sugerencias para ti, no reglas que imponerle al usuario.**
Él conoce su trabajo mejor que tú y su estructura es la que manda. Puedes
proponer un cambio **una vez**; si dice que no, o si te pide algo que va en
contra de esto, hazlo sin discutir y sin volver a sacar el tema. Estas pautas son
para cuando *tú* tienes que decidir dónde poner algo y nadie te lo dijo.

Dicho eso: si nadie propone un orden, en un año esto es una carpeta con
doscientas memorias sueltas.

## Dónde va cada cosa
- **Un nivel por criterio.** `área / proyecto / subtema` suele funcionar bien
  (p.ej. `administrativa / datos y soluciones`, `clientes / acme / facturación`).
  Alrededor de tres niveles se encuentra todo con comodidad y más abajo cuesta
  más; pero **no hay límite y anidar más no es un error** — si el usuario quiere
  cinco niveles, se hacen cinco.
- **Si una carpeta pasa de ~15 memorias** sin un tema que las una, puedes
  proponer subdividirla y ofrecer mover las que ya están con
  `editar_entrada(mover_a=...)`. Mover no cuesta nada: las rutas se recalculan
  solas. Es una oferta, no un aviso que haya que repetir.
- **No mezcles cosas sin relación clara** en la misma carpeta solo porque son del
  mismo cliente: separa procedimiento (`skill`) de datos (`general`) cuando cada
  uno se consulta en momentos distintos.
- **Una memoria = un tema.** Si el `contexto` crece tanto que cargarlo trae mucho
  que no viene al caso, pártelo en dos y enlaza mencionando el consecutivo.
- Antes de crear una carpeta nueva, mira el `arbol()`: casi siempre ya existe una
  que sirve, con otro nombre.

## Cómo se escribe una memoria que sirva
- **El `resumen` es lo que se busca**: escríbelo con las palabras que el usuario
  usaría al preguntar, no con las del título.
- **Guarda lo que costó descubrir y no está en el repo**: trampas, el comando
  exacto, el porqué de una decisión, lo que ya se intentó y no funcionó. No
  guardes lo que el código ya cuenta: eso se lee del código y ahí nunca envejece.
- **Si el hecho se puede comprobar, incluye el comando que lo comprueba.** Es la
  diferencia entre una memoria que el siguiente agente puede verificar y una que
  tiene que creerse. Las memorias peligrosas no son las falsas —esas se
  detectan— sino las que **fueron** ciertas y caducaron sin avisar.
- **Enlaza por número: `[[#47]]`.** Es la forma canónica. Enlazar por un slug
  derivado del título se rompe en cuanto el título cambia; el consecutivo no
  cambia nunca.
- **Los `tags` son para lo transversal** (`cliente`, `facturacion`), lo que cruza
  varias carpetas. No repitas ahí lo que ya dice la carpeta.
- **El contexto de ejecución importa**: una memoria escrita desde el servidor
  puede ser falsa desde el portátil del usuario (rutas, contenedores, qué es
  alcanzable por red). Si el hecho depende de dónde estés parado, dilo dentro de
  la memoria.

## Qué tipo poner
- `credencial`: datos de acceso — claves, tokens, cadenas de conexión, y también
  el "dónde está" cuando el secreto vive en otro sitio. Guarda lo que el usuario
  te pida guardar.
- `skill`: procedimientos, metodologías, "cómo se hace X".
- `general`: hechos, decisiones, contexto de proyecto.
- `historical`: registro de lo ya ocurrido/entregado.

Si dudas entre dos, elige por **cuándo se consulta**: lo que se lee mientras se
hace algo es `skill`; lo que se lee para entender, `general`. No le des muchas
vueltas — el tipo es un filtro, no una clasificación que haya que defender.

## El estado va en su campo, no en el título
`estado` = `pendiente|en_curso|hecho|bloqueado`, y vacío para lo que no tiene
estado (una credencial, un glosario). No escribas `PENDIENTE:` ni `HECHO:` en el
título: renombrar cambia el texto por el que se busca y rompe los enlaces, y el
estado en el título no se puede filtrar. Con el campo, `buscar(estado="pendiente")`
contesta de una.

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
