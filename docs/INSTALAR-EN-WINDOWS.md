# Instalar menximple en tu Windows (Claude Code)

Esta guía es para **usar** el sistema, no para montarlo. Al terminar, Claude Code
tendrá memoria a largo plazo en **todas** tus sesiones, se abra el proyecto que se abra.

> **Si eres un agente de IA y te dijeron "lee esto e instálalo":** sigue los pasos
> 1 a 6 **en orden y comprobando la salida de cada uno** — si `where.exe` no
> imprime nada o `claude mcp list` no dice *Connected*, para y arregla eso antes
> de seguir; encadenar comandos sobre un paso fallido deja al usuario con una
> instalación a medias que parece buena.
>
> **El paso 6 (canales) va también.** Son dos mitades: memoria y hablar con otros
> agentes. Sin él, cuando alguien te escriba no te vas a enterar.
>
> Lo único que no está aquí — y que **no puede estar**, porque el repositorio es
> público — son la **URL base** y la **apikey**. Si el usuario no te las dio,
> pídeselas antes de empezar. Se usan **solo en el paso 3**, dentro de los dos
> comandos `claude mcp add`, que las guardan en `%USERPROFILE%\.claude.json`. No
> las escribas en ningún otro archivo, y menos en uno del repositorio.
>
> Al terminar, dile al usuario que **reinicie Claude Code**: hasta entonces las
> tools nuevas no existen para ti ni para él.

---

## 0. Lo que tienes que pedir antes de empezar

Pídele a quien administra el servidor:

| dato | pinta que tiene | dónde se usa |
|---|---|---|
| **URL base** del hub | `https://algo.tu-dominio.com/xxxx/api` | paso 3 |
| **apikey de tu cuenta** | una cadena larga, tuya y personal | paso 3 |

Los dos se escriben **una sola vez**, en los comandos del paso 3, y quedan
guardados en `%USERPROFILE%\.claude.json`. No hay que editar ningún archivo a mano.

Dos cosas importantes:

- **Tu apikey es tu cuenta.** Quien la tenga ve todas tus memorias. No la pegues
  en un chat de grupo, ni en un repositorio, ni en el `.mcp.json` de un proyecto
  (ese archivo se commitea). En esta guía terminan en tu perfil de Windows, que no
  se sube a ningún lado.
- **Se entrega una sola vez.** Si la pierdes hay que generar una cuenta nueva.

---

## 1. Requisitos

Abre PowerShell y comprueba:

```powershell
claude --version    # lo único imprescindible
python --version    # 3.10 o superior — solo para el selector visual
git --version       # solo para instalar el paquete
```

Qué necesita cada cosa:

| | qué hace falta |
|---|---|
| **Memoria en Claude Code** (el hub) | nada más que Claude Code. No usa Python. |
| **Selector visual** (la ventana) | Python 3.10+ y git, para instalar el paquete |

Si `python` no responde, instálalo desde [python.org](https://www.python.org/downloads/)
marcando **"Add python.exe to PATH"**, y reabre la terminal. Si el usuario no
quiere instalar Python, **no te bloquees**: salta el paso 2, registra solo el hub
en el paso 3 (el primero de los dos comandos) y usa el modo chat — el agente
enseña el árbol y el usuario elige por número. Dile que el selector visual queda
pendiente de instalar Python.

---

## 2. Instalar el cliente (para el selector visual)

Esto instala `menximple-mcp`, el servidor local que abre la ventana. **Si no hay
Python y el usuario no quiere instalarlo, sáltate este paso**: el hub del paso 3
funciona igual sin él.

No hace falta clonar el repositorio: pip lo descarga solo. Con **pipx**
(recomendado, aísla el paquete y no toca tu Python):

```powershell
python -m pip install --user pipx
python -m pipx ensurepath
# cierra y reabre PowerShell para que el PATH se refresque
pipx install "git+https://github.com/jpanqueva/menximple@main"
```

Sin pipx funciona igual:

```powershell
pip install "git+https://github.com/jpanqueva/menximple@main"
```

Comprueba que quedó y **anota la ruta** que imprima:

```powershell
where.exe menximple-mcp
```

Debe salir algo como `C:\Users\TU-USUARIO\.local\bin\menximple-mcp.exe` (pipx) o
`...\Python313\Scripts\menximple-mcp.exe` (pip). Si no imprime nada, el directorio
de scripts no está en el PATH: usa la ruta completa en el paso 3 y arregla el PATH
después.

> **Clonar el repo solo hace falta si vas a tocar el código.** En ese caso:
> `git clone https://github.com/jpanqueva/menximple.git` y dentro,
> `pip install -e .` en lugar de lo de arriba.

---

## 3. Registrar los dos servidores MCP

Son dos:

| | qué hace | dónde corre | |
|---|---|---|---|
| `menximple` | el hub: buscar, guardar, organizar | en el servidor | imprescindible |
| `menximple-selector` | abre el selector visual en tu escritorio | **en tu PC** | necesita el paso 2 |

El hub vive en un contenedor y no tiene pantalla donde dibujar: por eso el
selector tiene que correr aquí.

### Aquí es donde van la URL y la apikey

**Este paso es el único sitio donde se escriben.** No hay que crear ni editar
ningún archivo a mano: los dos comandos de abajo las guardan solos en
`%USERPROFILE%\.claude.json`, que es la configuración del usuario de Windows.

- Cada `<URL>` se reemplaza por la URL base que te dieron — las **dos** veces.
- Cada `<APIKEY>` se reemplaza por tu apikey — las **dos** veces.
- Se dejan **sin** los símbolos `<` y `>`.

`--scope user` es lo que hace que valga para **todas** tus sesiones y no solo para
un proyecto:

```powershell
claude mcp add --scope user --transport http menximple <URL> --header "X-API-Key: <APIKEY>"

claude mcp add --scope user menximple-selector -e "MEMORY_BASE_URL=<URL>" -e "MEMORY_APIKEY=<APIKEY>" "--" menximple-mcp
```

Así se ven ya rellenos (valores de ejemplo, **no** sirven):

```powershell
claude mcp add --scope user --transport http menximple https://memoria.ejemplo.com/abcd/api --header "X-API-Key: Kj7xQ2mNp4RtYw9sZbVc1EhGf6UaLdOi3nTyMr8PxWk"

claude mcp add --scope user menximple-selector -e "MEMORY_BASE_URL=https://memoria.ejemplo.com/abcd/api" -e "MEMORY_APIKEY=Kj7xQ2mNp4RtYw9sZbVc1EhGf6UaLdOi3nTyMr8PxWk" "--" menximple-mcp
```

> **Agente:** si el usuario no te dio los dos datos, **para y pídeselos**. No
> inventes una URL, no dejes el placeholder puesto y no escribas la apikey en un
> `.mcp.json` de proyecto ni en ningún archivo del repositorio — solo con estos
> dos comandos.

> Las comillas alrededor de `"--"` no sobran: sin ellas PowerShell se lo come y el
> comando falla con `missing required argument 'commandOrUrl'`.

Comprobar:

```powershell
claude mcp list
```

Los dos deben salir **√ Connected**. Quedan guardados en
`%USERPROFILE%\.claude.json`, fuera de cualquier repositorio.

> **Si te equivocaste al escribir la URL o la apikey**, no vale con repetir el
> comando: `claude mcp add` falla con *"MCP server ... already exists in user
> config"*. Hay que quitarlo primero:
>
> ```powershell
> claude mcp remove --scope user menximple
> claude mcp remove --scope user menximple-selector
> ```
>
> **Si ya lo tenías configurado en el `.mcp.json` de algún proyecto**, quita esas
> dos entradas de ese archivo: la configuración del proyecto tiene prioridad sobre
> la del usuario y te seguirá pidiendo aprobación cada vez.

---

## 4. Quitar las confirmaciones de permisos

Sin esto Claude Code te pregunta cada vez que usa una tool de memoria. Pega este
bloque en PowerShell — respeta lo que ya tengas configurado:

```powershell
Copy-Item "$env:USERPROFILE\.claude\settings.json" "$env:USERPROFILE\.claude\settings.json.bak" -ErrorAction SilentlyContinue

$f = "$env:USERPROFILE\.claude\settings.json"
if (Test-Path $f) { $s = Get-Content $f -Raw | ConvertFrom-Json } else { $s = [pscustomobject]@{} }
if (-not $s.permissions) {
  $s | Add-Member -NotePropertyName permissions -NotePropertyValue ([pscustomobject]@{ allow=@(); deny=@(); ask=@() }) -Force
}
if (-not $s.permissions.allow) {
  $s.permissions | Add-Member -NotePropertyName allow -NotePropertyValue @() -Force
}
$s.permissions.allow = @($s.permissions.allow + @("mcp__menximple","mcp__menximple-selector") | Select-Object -Unique)
[IO.File]::WriteAllText($f, ($s | ConvertTo-Json -Depth 20))
Get-Content $f
```

Queda así:

```json
{
  "permissions": {
    "allow": ["mcp__menximple", "mcp__menximple-selector"],
    "deny": [],
    "ask": []
  }
}
```

`mcp__menximple` autoriza **todas** las tools de ese servidor. Si prefieres que te
siga preguntando antes de borrar, no pongas esa línea: lista una por una las que
sí autorizas (`mcp__menximple__buscar`, `mcp__menximple__arbol`, …) y deja fuera
`mcp__menximple__borrar_entrada` y `mcp__menximple__borrar_carpeta`.

> Se usa `[IO.File]::WriteAllText` y no `Out-File` porque en PowerShell 5.1
> `Out-File -Encoding utf8` escribe BOM, y un JSON con BOM puede no parsearse.

---

## 5. Comprobar que quedó

Reinicia Claude Code y pide, en cualquier sesión:

> muéstrame el árbol de mis memorias

Debe responder con la estructura de tu cuenta. Después:

> abre mis memorias

Debe abrirse una ventana en el escritorio con el selector. Si el árbol salió pero
la ventana no, el hub está bien y el problema es el servidor local del paso 3.

---

## Si algo falla

| síntoma | causa y arreglo |
|---|---|
| `missing required argument 'commandOrUrl'` | Faltaron las comillas en `"--"` (paso 3). |
| `already exists in user config` | Ya estaba registrado. `claude mcp remove --scope user <nombre>` y repite. |
| `claude` no se reconoce como comando | Claude Code no está instalado o no quedó en el PATH. Reabre PowerShell; si sigue, reinstálalo. |
| No hay Python, o es menor que 3.10 | Solo afecta al selector visual. Registra únicamente el hub (paso 3, primer comando) y usa el modo chat. |
| `menximple-selector` no aparece en la lista | La carpeta de scripts no está en el PATH. Regístralo otra vez con la ruta completa que dio `where.exe`. |
| Aparece pero sale **failed** | Ejecuta `menximple-mcp` a mano: debe quedarse esperando sin imprimir nada (habla por stdin/stdout). Si revienta, falta una dependencia: reinstala con pipx. |
| **Pending approval** | Lo registraste en un proyecto en vez de con `--scope user`. Repite el paso 3 con esa opción. |
| Error de autenticación | Apikey mal copiada o URL incompleta. Revisa `%USERPROFILE%\.claude.json` → `mcpServers.menximple`. |
| El selector no abre ventana | Solo abre donde hay escritorio. Por SSH o en un servidor, el agente cae a modo chat: te enseña el árbol y eliges por número. |
| Sigue pidiendo permiso | El `settings.json` quedó mal formado. Ábrelo y valida que sea JSON legal. |

---

## Actualizar

**Cierra Claude Code antes.** Con una sesión abierta, su selector tiene
`menximple-mcp.exe` en uso y el comando revienta con `PermissionError [WinError 32]`
— al final, después de reinstalar el entorno, así que queda a medias. El error es un
stack de `pathlib` que no menciona a Claude Code por ningún lado.

```powershell
pipx install --force "git+https://github.com/jpanqueva/menximple@main"
```

Si falla igual, quedaron procesos de sesiones anteriores:

```powershell
Get-Process menximple-mcp -ErrorAction SilentlyContinue | Stop-Process -Force
```

y repite el comando.

Reinicia Claude Code después: el servidor local arranca con la sesión, así que el
código nuevo no aplica hasta reiniciar.

---

## Desinstalar

```powershell
claude mcp remove --scope user menximple
claude mcp remove --scope user menximple-selector
pipx uninstall menximple
```

Y quita las dos entradas de `permissions.allow` en
`%USERPROFILE%\.claude\settings.json`.

---

## 6. Canales entre agentes

Hasta aquí tienes **memoria**. Esta es la otra mitad: que **dos agentes en máquinas
distintas se hablen**. Le dices al tuyo "pregúntale a QA si terminó" y el agente de
la otra máquina arranca a trabajar, aunque nadie esté mirando esa pantalla.

Instálalo aunque hoy trabajes solo. Sin esto puedes escribir en un canal, pero **no
recibir**: cuando alguien te busque no te vas a enterar, y el que escribió creerá
que te llegó.

Necesita **Node 18+**:

```powershell
node --version
```

### 6.1 Traer el puente

El puente es un MCP local que corre en tu PC. El hub no puede empujar nada hacia
una sesión — es petición/respuesta —, así que esta pieza es la que despierta al
agente cuando le escriben.

```powershell
git clone https://github.com/jpanqueva/menximple.git
cd menximple\canal
npm install
```

Anota la ruta completa de `menx-canal.mjs`. Con el clon en `C:\dev` sería
`C:\dev\menximple\canal\menx-canal.mjs`.

### 6.2 Registrarlo

**La misma URL y la misma apikey del paso 3.** Reemplaza `<URL>`, `<APIKEY>` y la
ruta, sin los símbolos `<` y `>`:

```powershell
claude mcp add --scope user menx-canal -e "MEMORY_BASE_URL=<URL>" -e "MEMORY_APIKEY=<APIKEY>" "--" node "C:\dev\menximple\canal\menx-canal.mjs"
```

> Aquí **no** se pone ningún nombre de agente. La identidad se pide por
> conversación (6.4): en una misma máquina puedes tener varios agentes abiertos y
> cada uno es uno distinto. Ponerla aquí haría que todos se llamaran igual y se
> robaran los mensajes.

### 6.3 Arrancar con el flag

**Los canales no se activan con `/mcp`.** Hay que arrancar Claude Code así:

```powershell
claude --dangerously-load-development-channels server:menx-canal
```

Sale una pantalla de advertencia → elige **"I am using this for local
development"**. Es "dangerously" solo porque los canales propios no están en la
lista aprobada de Anthropic mientras la función es research preview; el código es
el tuyo.

> **El fallo más confuso de todo esto:** si arrancas sin el flag, el MCP se
> registra igual y **verás** las tools `canal_*`, pero no te llegará ningún
> mensaje. Parece instalado y está mudo. Si no recibes nada, empieza por aquí.

### 6.4 Identificarte

> Identifícate en los canales de menx como `jhon-windows`.

Elige algo reconocible para el otro lado, no un genérico como "agente". La
identidad sobrevive a los `/mcp`; con `/resume` o al reiniciar, Claude Code abre
una sesión nueva y te la vuelve a pedir — pero te sugiere la que usaste antes en
esa misma carpeta.

### 6.5 Hablar

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
- Tu puente **acusa recibo automáticamente**: el otro sabe que llegó y que lo estás
  trabajando.
- Nada se da por leído hasta que **entra de verdad** en la sesión. Si el puente se
  cae antes, se vuelve a entregar.

Con el puente corriendo **no esperes mensajes a mano** con `recibir_mensajes`:
llegan empujados, y esa tool casi siempre devolverá vacío porque el puente ya
consumió el buzón.

### 6.6 Barra de estado

La identidad del canal es invisible, y un agente que se cree identificado y no lo
está deja de recibir sin que nada lo diga. En la barra se ve de un vistazo:

```
mi-proyecto  |  Opus 5  |  menx: jhon-windows · 1 canal: qa
```

En `%USERPROFILE%\.claude\settings.json`:

```json
"statusLine": {
  "type": "command",
  "command": "node C:/dev/menximple/canal/statusline-menx.mjs",
  "padding": 1
}
```

> **Barras normales, no backslashes** — `C:/dev/...`, no `C:\dev\...`. Claude Code
> corre este comando a través de Git Bash, y ahí `\U`, `\c` y compañía se comen como
> escapes: la ruta llega rota, Node muere con `MODULE_NOT_FOUND` y la barra
> simplemente no aparece, sin decir por qué.
>
> Y no lo pruebes desde PowerShell: ahí los backslashes **sí funcionan**, así que te
> da un falso positivo y concluyes que está bien cuando no lo está.

Se lee **al arrancar**, así que hay que cerrar y abrir Claude Code — con `/mcp` no
aparece. No sale a la red: lee el archivo local que el puente ya mantiene.

### 6.7 Comprobar

```
¿En qué canales estoy?   →  canal_estado
```

| Síntoma | Causa |
|---|---|
| No existen las tools `canal_*` | El MCP no quedó registrado (6.2) |
| Existen pero no llega nada | Arrancaste sin el flag (6.3) |
| "sin identidad" | Falta 6.4, o abriste sesión nueva |
| El puente no arranca | `node` del PATH viejo: usa la ruta absoluta al de 18+ |

---

Ya instalado, cómo se usa: **[../USO.md](../USO.md)**
Si ya lo tenías de antes y quieres lo nuevo: **[ACTUALIZAR.md](ACTUALIZAR.md)**
