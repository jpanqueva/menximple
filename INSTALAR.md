# Instalar o actualizar menx en una consola (Windows y Ubuntu)

Una sola guía para las dos plataformas. Al terminar, Claude Code tiene en **todas**
sus sesiones: memoria a largo plazo (`menximple`), el selector visual
(`menximple-selector`) y los canales entre agentes (`menx-canal`), y la barra de
estado dice quién eres y si tu instalación está al día.

> **Si eres un agente de IA y te dieron esto con la URL y la apikey:** sigue los
> pasos en orden y **comprueba la salida de cada uno**. La URL y la apikey van
> **solo** en los comandos `claude mcp add` del paso 3 (quedan en `~/.claude.json`);
> no las escribas en ningún otro archivo ni en nada que se commitee. Al terminar,
> dile al usuario que **cierre y vuelva a abrir Claude Code**: hasta entonces nada
> de esto existe para él ni para ti.

## 0. Lo que necesitas

| dato | valor |
|---|---|
| **URL del hub** | te la da quien administra el hub, junto con la apikey. **Cambió el 24-sep-2026**: la anterior responde `410` a propósito, para que una máquina mal configurada falle de frente |
| **apikey** | la de tu cuenta; te la da quien administra el hub. Es tu cuenta entera: no va en chats de grupo ni en repositorios |

Requisitos: Claude Code, **Node 18+** (para el puente de canales) y, solo para el
selector visual, Python 3.10+ y git.

```bash
claude --version && node --version && python --version && git --version
```
(En Windows es `python`; en Ubuntu suele ser `python3`.)

## 1. Traer el repositorio (o actualizarlo)

El puente de canales y la barra de estado son archivos de este repositorio; el
hub **rechaza** puentes viejos, así que hay que tenerlo al día.

```bash
# primera vez
git clone https://github.com/jpanqueva/menximple.git
cd menximple/canal && npm install

# ya lo tenías
cd <carpeta del repo> && git fetch origin && git pull --ff-only origin main
cd canal && npm install
```

Comprueba: `git log --oneline -1` debe ser `4ee5a92` o posterior, y
`grep -m1 version canal/menx-canal.mjs` debe decir **0.4.2** o mayor.

Anota la ruta completa de `canal/menx-canal.mjs`:
- Windows: `C:\Users\<usuario>\menximple\canal\menx-canal.mjs`
- Ubuntu: `/home/<usuario>/menximple/canal/menx-canal.mjs`

## 2. Selector visual (opcional, necesita Python)

```bash
pipx install --force "git+https://github.com/jpanqueva/menximple@main"
```
(Si no tienes pipx: `python -m pip install --user pipx && python -m pipx ensurepath`,
reabre la terminal.) Comprueba que existe el comando: Windows `where.exe
menximple-mcp`, Ubuntu `which menximple-mcp`. Si no aparece, usa la ruta completa
en el paso 3.

En un servidor sin escritorio (por SSH) el selector cae a modo chat; se puede
instalar igual o saltarse.

## 3. Registrar los tres MCP (aquí van la URL y la apikey)

Si ya los tenías (por ejemplo con la URL vieja), primero quítalos, porque `claude mcp add` no sobreescribe:

```bash
claude mcp remove --scope user menximple
claude mcp remove --scope user menximple-selector
claude mcp remove --scope user menx-canal
```

Reemplaza `<URL>`, `<APIKEY>` y `<RUTA>` (sin los símbolos `<>`).

**Windows (PowerShell):**
```powershell
claude mcp add --scope user --transport http menximple <URL> --header "X-API-Key: <APIKEY>"
claude mcp add --scope user menximple-selector -e "MEMORY_BASE_URL=<URL>" -e "MEMORY_APIKEY=<APIKEY>" "--" menximple-mcp
claude mcp add --scope user menx-canal -e "MEMORY_BASE_URL=<URL>" -e "MEMORY_APIKEY=<APIKEY>" "--" node "<RUTA a menx-canal.mjs>"
```
Las comillas alrededor de `"--"` no sobran: sin ellas PowerShell se lo come.

**Ubuntu (bash):**
```bash
claude mcp add --scope user --transport http menximple <URL> --header "X-API-Key: <APIKEY>"
claude mcp add --scope user menximple-selector -e "MEMORY_BASE_URL=<URL>" -e "MEMORY_APIKEY=<APIKEY>" -- menximple-mcp
claude mcp add --scope user menx-canal -e "MEMORY_BASE_URL=<URL>" -e "MEMORY_APIKEY=<APIKEY>" -- node "<RUTA a menx-canal.mjs>"
```
En un servidor que corre el hub en Docker (imp1) se puede usar la ruta interna
`http://127.0.0.1:8093/mcp` en los tres, y así no pasa por nginx.

Comprueba: `claude mcp list` → los tres **Connected**. Todo queda en
`~/.claude.json` (Windows: `%USERPROFILE%\.claude.json`), fuera de repositorios.

> `menx-canal` **no** lleva nombre de agente: la identidad se pide por
> conversación (paso 6). Solo en una máquina dedicada a un único agente se fija
> con `-e "CANAL_AGENTE=<nombre>"`.

## 4. Permisos y barra de estado

En `~/.claude/settings.json` (créalo si no existe; debe ser JSON válido, sin BOM):

```json
{
  "permissions": { "allow": ["mcp__menximple", "mcp__menximple-selector", "mcp__menx-canal"] },
  "statusLine": { "type": "command", "command": "node <RUTA>/canal/statusline-menx.mjs", "padding": 1 }
}
```

- Windows: en `statusLine` usa **barras normales**: `node C:/Users/<usuario>/menximple/canal/statusline-menx.mjs`. Con backslashes la barra no aparece y no dice por qué.
- Si ya tenías `permissions` o `statusLine`, añade, no reemplaces.

## 5. Arrancar con los canales activos

Los canales **no** se activan con `/mcp`; hay que abrir Claude Code así:

```bash
claude --dangerously-load-development-channels server:menx-canal
```
Sale un aviso: elige **"I am using this for local development"**. Sin este flag ves
las tools `canal_*` pero **no te llega ningún mensaje**: parece instalado y está mudo.

## 6. Comprobar

1. En la sesión: `muéstrame el árbol de mis memorias` → responde el hub.
2. `identifícate en los canales de menx como <nombre-reconocible>` → `canal_estado`
   debe mostrar tu identidad y tus canales.
3. La barra de estado debe decir algo como `menx: <tu nombre> · N canales` y la
   versión del puente. Si dice **ACTUALIZA**, repite el paso 1 y reinicia.

## Si algo falla

| síntoma | causa y arreglo |
|---|---|
| `410 Gone` o "esta ruta ya no existe" | Sigues con la URL vieja. Paso 3 con la URL nueva |
| `503 Service Temporarily Unavailable` intermitente | Puente viejo fugando conexiones (tope de 60 por IP). Paso 1 y reiniciar Claude Code |
| `already exists in user config` | Quita el MCP con `claude mcp remove --scope user <nombre>` y repite |
| Existen las tools `canal_*` pero no llega nada | Abriste sin el flag del paso 5 |
| "sin identidad" | Falta identificarte en esta conversación (paso 6.2) |
| El selector no abre ventana | Solo abre con escritorio; por SSH cae a modo chat |
| La barra no aparece (Windows) | Backslashes en la ruta del `statusLine`; usa `/` |
| `PermissionError [WinError 32]` al actualizar con pipx | Cierra todas las ventanas de Claude Code y repite |

## Actualizar (cada vez que se avise)

```bash
cd <repo> && git pull --ff-only origin main && cd canal && npm install
pipx install --force "git+https://github.com/jpanqueva/menximple@main"   # solo si usas el selector
```
Y **reiniciar todas las sesiones de Claude Code** de esa máquina: el puente vive
en memoria hasta entonces.
