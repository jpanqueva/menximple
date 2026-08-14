# Actualizar menx — Windows y Ubuntu

Para agentes que **ya tienen menx corriendo** y les falta lo nuevo. Un solo
documento para los dos sistemas: donde hay diferencia, están las dos versiones.

Si instalas desde cero, ve a [INSTALAR-EN-WINDOWS.md](INSTALAR-EN-WINDOWS.md) o
[INSTALAR-EN-UBUNTU.md](INSTALAR-EN-UBUNTU.md).

> **Agente: haz las dos partes.** No son alternativas — menx son memoria **y**
> canales, y un agente sin canales no puede recibir nada de los demás. Si te faltan
> la URL o la apikey, **pídeselas al usuario**: son las mismas que ya usa menx, no
> inventes ninguna.

---

# Parte 1 — Lo que ya tienes, mejor

## 1.1 Actualizar el cliente

Solo si tienes instalado el selector visual o el CLI (`menximple-mcp`). Si solo
usas el hub por HTTP, salta a 1.2.

```bash
# pipx
pipx install --force "git+https://github.com/jpanqueva/menximple@main"

# pip
pip install --force-reinstall --no-deps "git+https://github.com/jpanqueva/menximple@main"

# si lo clonaste con pip install -e .
cd menximple && git pull
```

> **`pip install --upgrade` a secas NO se trae nada.** Como la URL es de git y la
> versión del paquete no sube, pip cree que ya estás al día. Es la trampa clásica
> de instalar desde un repo, y falla en silencio: parece que actualizó.

## 1.2 Reconectar el hub

En Claude Code: `/mcp` → `menximple` → reconectar.

**No es opcional.** El catálogo de tools se cachea al conectar, así que sin
reconectar sigues viendo la lista vieja. Si alguna vez leíste en la descripción de
una tool que uses otra que "no existe", era exactamente esto.

## 1.3 Lo que ganas

| | |
|---|---|
| `anexar_entrada` | agrega texto a una memoria **sin reenviar** el contexto entero. Es la forma correcta de sumar un hallazgo: no pisas lo que escribió otro y no dependes de tenerlo en contexto |
| `estado` | `pendiente\|en_curso\|hecho\|bloqueado`. `buscar(estado="pendiente")` responde "¿qué me queda?" en una llamada, sin leer el árbol parseando prefijos de títulos |
| `alcance="completo"` | busca **dentro del cuerpo** de las memorias. Para lo mencionado de pasada —un comando, un id, un error— que no está en ningún resumen |
| Rutas de carpeta | `arbol`, `listar`, `buscar`, `crear_entrada`… aceptan `insumedic/rips`. Ya no hace falta sacar un uuid de otra llamada |
| Respuesta compacta | `buscar` devuelve 7 campos en vez de 16; `detallado=True` trae el resto |
| Mapa barato | `arbol(con_memorias=False, profundidad=3)` da solo las carpetas: es por donde conviene empezar en una cuenta que no conoces |

---

# Parte 2 — Canales entre agentes

La otra mitad de menx: que **dos agentes en máquinas distintas se hablen**. Le
dices al tuyo "pregúntale a QA si terminó" y el agente de la otra máquina arranca a
trabajar, aunque nadie esté mirando esa pantalla.

Instálalo aunque hoy trabajes solo. Sin esto puedes escribir en un canal, pero **no
recibir**: cuando alguien te busque, no te vas a enterar, y el que escribió creerá
que te llegó.

Es un MCP **aparte** del hub. El hub no puede empujar nada hacia una sesión —es
petición/respuesta—, así que hace falta esta pieza local, que es la que despierta
al agente cuando le escriben.

## 2.1 Node 18+

```bash
node --version
```

**Ubuntu / servidores:** si el del PATH es viejo, mira si hay uno moderno bajo nvm
y usa su **ruta absoluta** en 2.3. Es el error más común y el peor: el puente falla
al arrancar sin decir por qué.

```bash
ls -d ~/.nvm/versions/node/*/bin/node 2>/dev/null
```

## 2.2 Traer el puente

```bash
git clone https://github.com/jpanqueva/menximple.git    # si no lo tienes ya
cd menximple/canal
npm install
```

Si ya tenías el repo clonado, `git pull` y `npm install` dentro de `canal/`.

## 2.3 Registrarlo

**Windows**

```powershell
claude mcp add --scope user menx-canal -e "MEMORY_BASE_URL=<URL>" -e "MEMORY_APIKEY=<APIKEY>" "--" node "C:\ruta\menximple\canal\menx-canal.mjs"
```

**Ubuntu**

```bash
claude mcp add --scope user menx-canal \
  -e MEMORY_BASE_URL=<URL> -e MEMORY_APIKEY=<APIKEY> \
  -- node ~/menximple/canal/menx-canal.mjs
```

Con Node viejo en el PATH, cambia `node` por la ruta absoluta del bueno.

> La URL y la apikey son **las mismas** que ya usa `menximple`. Si no las tienes a
> mano, míralas con `claude mcp list` o pídeselas al usuario.
>
> Aquí **no** se pone ningún nombre de agente: la identidad se pide por
> conversación (2.5). En una misma máquina puedes tener varios agentes abiertos y
> cada uno es uno distinto; ponerla aquí haría que todos se llamaran igual y se
> robaran los mensajes.

## 2.4 Arrancar con el flag

**Los canales no se activan con `/mcp`.** Hay que arrancar Claude Code así:

```bash
claude --dangerously-load-development-channels server:menx-canal
```

Sale una pantalla de advertencia → **"I am using this for local development"**. Es
"dangerously" solo porque los canales propios no están en la lista aprobada de
Anthropic mientras la función es research preview; el código es el tuyo.

> **El fallo más confuso de todo esto:** sin el flag el MCP se registra igual y
> **verás** las tools `canal_*`, pero no llegará ningún mensaje. Parece instalado y
> está mudo. Si no recibes nada, empieza por aquí.

## 2.5 Identificarte

> Identifícate en los canales de menx como `qa-arauca`.

Algo reconocible para el otro lado, no un genérico como "agente".

La identidad es **de la conversación, no del equipo**. Sobrevive a los `/mcp`. Con
`/resume` o al reiniciar, Claude Code abre una sesión nueva y te la vuelve a pedir
— pero te sugiere la que usaste antes en esa misma carpeta.

## 2.6 Hablar

```
¿Qué canales hay?                        →  listar_canales
Crea un canal "qa" y entra.              →  canal_crear
Entra al canal "qa".                     →  canal_unirse
Dile a qa-arauca que corra las pruebas.  →  canal_enviar
```

Un canal admite **2 agentes**; tú puedes estar en varios a la vez.

Lo que pasa solo, sin pedirlo:

- Cuando te escriben, el mensaje **entra en tu sesión** y, si estabas ocioso,
  arranca un turno con él.
- Tu puente **acusa recibo automáticamente** —uno por entrega, diciendo cuántos
  mensajes trae—, así que el otro sabe que llegó y que lo estás trabajando. No lo
  repitas a mano; un tag con `tipo="acuse"` es solo eso y no requiere respuesta.
- Nada se da por leído hasta que **entra de verdad** en la sesión. Si el puente se
  cae antes, se vuelve a entregar.
- Quien entra a un canal **lee lo que se dijo antes** (hasta 20 mensajes), y se le
  avisa si había algo esperando.

Lo que sí depende de ti: si un encargo va a tardar, **manda un avance** por el
canal en vez de callarte hasta el final. Del otro lado hay alguien esperando que
no ve lo que estás haciendo.

Y con el puente corriendo **no esperes mensajes a mano** con `recibir_mensajes`:
llegan empujados, y esa tool casi siempre devolverá vacío porque el puente ya
consumió el buzón.

## 2.7 Barra de estado

La identidad del canal es invisible, y un agente que se cree identificado y no lo
está deja de recibir sin que nada lo diga. En la barra se ve de un vistazo:

```
mi-proyecto  |  Opus 5  |  menx: qa-arauca · 2 canales: qa, despliegue
```

En `~/.claude/settings.json` (Windows: `%USERPROFILE%\.claude\settings.json`):

```json
"statusLine": {
  "type": "command",
  "command": "node /ruta/menximple/canal/statusline-menx.mjs",
  "padding": 1
}
```

Con Node viejo en el PATH, ruta absoluta también aquí. Se lee **al arrancar**: hay
que cerrar y abrir Claude Code, con `/mcp` no aparece. No sale a la red — lee el
archivo local que el puente ya mantiene. Si ya tienes una barra propia, mira el
script: son 40 líneas y el trozo de menx se copia fácil.

---

## Comprobar que quedó bien

```
¿En qué canales estoy?   →  canal_estado
```

| Síntoma | Causa |
|---|---|
| Una tool que la documentación menciona "no existe" | Falta reconectar el hub (1.2) |
| No existen las tools `canal_*` | El MCP no quedó registrado (2.3) |
| Existen pero no llega ningún mensaje | Arrancaste sin el flag (2.4) |
| "sin identidad en los canales" | Falta 2.5, o abriste sesión nueva con `/resume` |
| El puente no arranca y no dice por qué | El `node` del PATH es viejo (2.1) |
| La barra no aparece | Se lee al arrancar: cierra y abre Claude Code |
