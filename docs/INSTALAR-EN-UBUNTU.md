# Instalar menximple en Ubuntu (Claude Code)

Esta guía es para **usar** el sistema, no para montarlo. Al terminar, Claude Code
tendrá memoria a largo plazo en **todas** tus sesiones, se abra el proyecto que se abra.

> **Si eres un agente de IA y te dijeron "lee esto e instálalo":** sigue los pasos
> 1 a 6 **en orden y comprobando la salida de cada uno** — si `which` no imprime
> nada o `claude mcp list` no dice *Connected*, para y arregla eso antes de
> seguir; encadenar comandos sobre un paso fallido deja al usuario con una
> instalación a medias que parece buena.
>
> El paso 4 (CLI) sí puedes saltarlo. **El paso 6 (canales) no**: son dos mitades,
> memoria y hablar con otros agentes, y sin él, cuando alguien te escriba no te vas
> a enterar.
>
> Lo único que no está aquí — y que **no puede estar**, porque el repositorio es
> público — son la **URL base** y la **apikey**. Si el usuario no te las dio,
> pídeselas antes de empezar. Se usan **solo en el paso 3**, dentro del comando
> `claude mcp add`, que las guarda en `~/.claude.json`. No las escribas en ningún
> otro archivo, y menos en uno del repositorio.
>
> Al terminar, dile al usuario que **reinicie Claude Code**.

---

## Antes de empezar: qué es distinto en Ubuntu

El **selector visual no está disponible en Linux**. En Windows la ventana se abre
en una consola aparte; en Linux no hay equivalente y el proceso hijo no tendría
terminal donde dibujar. En su lugar se usa el **modo chat**, que hace lo mismo sin
ventana: el agente te enseña el árbol y tú pides las memorias por su número.

Por eso aquí **basta con instalar el hub**. Si además vas a usar los comandos de
consola, el paso 4 instala el cliente.

```
> ¿qué memorias tengo?

jhon
└── administrativa/
    └── clientes/
        ├── #3   Facturacion electronica en la DIAN  [skill]
        └── #4   Cliente Grupo del Llano  [general]

> cárgame la 3 y la 4
```

---

## 0. Lo que tienes que pedir

| dato | pinta que tiene | dónde se usa |
|---|---|---|
| **URL base** del hub | `https://algo.tu-dominio.com/xxxx/api` | paso 3 |
| **apikey de tu cuenta** | una cadena larga, tuya y personal | paso 3 |

- **Tu apikey es tu cuenta.** Quien la tenga ve todas tus memorias. No la pegues
  en un chat de grupo ni en un `.mcp.json` de proyecto (ese archivo se commitea).
- **Se entrega una sola vez.** Si la pierdes hay que generar una cuenta nueva.

---

## 1. Requisitos

**Para tener memoria en Claude Code solo hace falta Claude Code.** El hub corre en
el servidor: aquí no se instala nada más.

```bash
claude --version     # lo único imprescindible
python3 --version    # cualquier versión sirve, es solo para el paso 3
```

- **El hub no usa Python.** Da igual qué versión tengas, o si no tienes.
- El bloque de permisos del paso 3 usa `python3`, pero le vale **cualquier
  versión** (3.6 en adelante). Si no hay `python3`, ahí mismo tienes la
  alternativa: editar el archivo a mano.
- **Python 3.10+ solo hace falta para el paso 4**, el cliente de consola, que es
  opcional. Ubuntu 20.04 trae 3.8 y eso **no impide** completar los pasos 2 y 3:
  no instales nada para saltar ese requisito salvo que el usuario quiera el CLI.

---

## 2. Registrar el hub

`--scope user` es lo que hace que valga para **todas** tus sesiones y no solo para
un proyecto. Reemplaza `<URL>` y `<APIKEY>`, **sin** los símbolos `<` y `>`:

```bash
claude mcp add --scope user --transport http menximple <URL> --header "X-API-Key: <APIKEY>"
```

Así se ve ya relleno (valores de ejemplo, **no** sirven):

```bash
claude mcp add --scope user --transport http menximple https://memoria.ejemplo.com/abcd/api --header "X-API-Key: Kj7xQ2mNp4RtYw9sZbVc1EhGf6UaLdOi3nTyMr8PxWk"
```

Comprobar:

```bash
claude mcp list
```

Debe salir **✓ Connected**. Queda guardado en `~/.claude.json`.

> Si te equivocaste escribiendo la URL o la apikey, repetir el comando **no** vale:
> falla con *"already exists in user config"*. Primero
> `claude mcp remove --scope user menximple`.
>
> Si ya lo tenías en el `.mcp.json` de algún proyecto, quita esa entrada: la
> configuración del proyecto tiene prioridad y te seguirá pidiendo aprobación.

---

## 3. Quitar las confirmaciones de permisos

Sin esto Claude Code pregunta cada vez que usa una tool de memoria. Las reglas van
en `~/.claude/settings.json`. Este bloque respeta lo que ya tengas y **sirve con
cualquier `python3`**, no hace falta 3.10:

```bash
cp ~/.claude/settings.json ~/.claude/settings.json.bak 2>/dev/null   # por si acaso

python3 - <<'PY'
import json, os
f = os.path.expanduser("~/.claude/settings.json")
os.makedirs(os.path.dirname(f), exist_ok=True)
try:
    with open(f) as fh: s = json.load(fh)
except (OSError, ValueError):
    s = {}
p = s.setdefault("permissions", {})
allow = p.setdefault("allow", [])
for regla in ("mcp__menximple", "mcp__menximple-selector"):
    if regla not in allow: allow.append(regla)
with open(f, "w") as fh: json.dump(s, fh, indent=2)
print(json.dumps(s, indent=2))
PY
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

Si no hay `python3`, edita `~/.claude/settings.json` a mano y añade las dos reglas
dentro de `permissions.allow`. Comprueba después que sigue siendo JSON válido.

**Con esto ya tienes memoria en Claude Code.** El paso 4 es opcional y no aporta
nada dentro del agente; el **paso 6 (canales) sí hay que hacerlo**.

---

## 4. (Opcional) El cliente de consola

Solo si quieres usar menximple **fuera** de Claude Code — en un script, un cron o
una sesión SSH. Dentro de Claude Code no hace falta.

**Este paso sí necesita Python 3.10+.** Compruébalo antes:

```bash
python3 --version
```

Si es menor (Ubuntu 20.04 trae 3.8), **no instales nada por tu cuenta**: pregúntale
al usuario si quiere el CLI. Si dice que sí, hace falta un intérprete más nuevo:

```bash
sudo add-apt-repository -y ppa:deadsnakes/ppa && sudo apt update
sudo apt install -y python3.11 python3.11-venv
python3.11 -m pip install --user pipx
python3.11 -m pipx install "git+https://github.com/jpanqueva/menximple@main"
```

Con Python 3.10+ ya presente:

```bash
sudo apt install -y pipx        # en 22.04+; si no existe: python3 -m pip install --user pipx
pipx ensurepath                 # y reabre la terminal
pipx install "git+https://github.com/jpanqueva/menximple@main"
which menximple                 # debe imprimir ~/.local/bin/menximple
```

Configúralo en tu shell (`~/.bashrc` o `~/.zshrc`):

```bash
export MEMORY_BASE_URL="<URL>"
export MEMORY_APIKEY="<APIKEY>"
```

Uso:

```bash
menximple select --query "facturacion"    # lista candidatos en JSON, con su número
menximple load   --ids 3,4                # trae el contexto de esas memorias
```

`select` devuelve JSON con `numero`, `titulo` y `resumen` de cada candidato; `load`
acepta el consecutivo o el uuid. Es la salida pensada para que la consuma un
programa: para leer tú, es más cómodo pedirle el árbol al agente.

> El paquete también trae `menximple-mcp`, el servidor MCP del selector visual.
> En Linux no aporta nada porque la ventana no se puede abrir; instálalo solo si
> también trabajas en Windows.

---

## 5. Comprobar que quedó

Reinicia Claude Code y pide, en cualquier sesión:

> muéstrame el árbol de mis memorias

Debe responder con la estructura de tu cuenta (vacía si acabas de empezar, es
normal). Después pídele cargar alguna por su número.

---

## Si algo falla

| síntoma | causa y arreglo |
|---|---|
| `already exists in user config` | Ya estaba registrado. `claude mcp remove --scope user menximple` y repite. |
| **Pending approval** | Lo registraste en un proyecto en vez de con `--scope user`. Repite el paso 2 con esa opción. |
| Error de autenticación | Apikey mal copiada o URL incompleta. Revisa `~/.claude.json` → `mcpServers.menximple`. |
| Sigue pidiendo permiso | El `settings.json` quedó mal formado: `python3 -m json.tool ~/.claude/settings.json`. |
| `menximple: command not found` | Falta `pipx ensurepath` y reabrir la terminal, o `~/.local/bin` no está en el PATH. |
| No abre ninguna ventana | Es lo esperado: en Linux se usa el modo chat. Pide el árbol y elige por número. |

---

## Actualizar y desinstalar

```bash
pipx install --force "git+https://github.com/jpanqueva/menximple@main"   # cliente

claude mcp remove --scope user menximple                                 # quitar
pipx uninstall menximple
```

Y quita las entradas de `permissions.allow` en `~/.claude/settings.json`.

---

## 6. Canales entre agentes

Hasta aquí tienes **memoria**. Esta es la otra mitad: que **dos agentes en máquinas
distintas se hablen**. Le dices al tuyo "pregúntale a QA si terminó" y el agente de
la otra máquina arranca a trabajar, aunque nadie esté mirando esa pantalla.

En un servidor es justo lo que lo vuelve útil: el agente de aquí recibe encargos
sin que nadie tenga una terminal abierta mirándolo. Instálalo aunque hoy trabajes
solo — sin esto puedes escribir en un canal pero **no recibir**, y el que te
escriba creerá que te llegó.

### 6.1 Node: la trampa número uno en servidores

Necesita **Node 18+**, y en un servidor el `node` del PATH suele ser el viejo del
sistema aunque haya uno moderno instalado:

```bash
node --version                      # el del PATH
ls ~/.nvm/versions/node 2>/dev/null # los de nvm, si hay
```

Si el del PATH no llega a 18, **no basta con tener otro instalado**: hay que usar
su **ruta absoluta** en el paso 6.3. Nos pasó en un Ubuntu 20.04 con `node` v10 en
`/usr/bin` y un v22 bajo nvm; con `node` a secas el puente falla al arrancar y no
dice por qué.

```bash
ls -d ~/.nvm/versions/node/*/bin/node    # esta es la ruta que vas a usar
```

### 6.2 Traer el puente

El puente es un MCP local que corre en esta máquina. El hub no puede empujar nada
hacia una sesión — es petición/respuesta —, así que esta pieza es la que despierta
al agente cuando le escriben.

```bash
git clone https://github.com/jpanqueva/menximple.git ~/menximple
cd ~/menximple/canal
PATH=~/.nvm/versions/node/v22.19.0/bin:$PATH npm install   # ajusta la versión
```

### 6.3 Registrarlo

**La misma URL y la misma apikey del paso 2.** Con Node moderno en el PATH:

```bash
claude mcp add --scope user menx-canal \
  -e MEMORY_BASE_URL=<URL> -e MEMORY_APIKEY=<APIKEY> \
  -- node ~/menximple/canal/menx-canal.mjs
```

Si el `node` del PATH es viejo, **ruta absoluta**:

```bash
claude mcp add --scope user menx-canal \
  -e MEMORY_BASE_URL=<URL> -e MEMORY_APIKEY=<APIKEY> \
  -- /home/TU-USUARIO/.nvm/versions/node/v22.19.0/bin/node /home/TU-USUARIO/menximple/canal/menx-canal.mjs
```

> Aquí **no** se pone ningún nombre de agente. La identidad se pide por
> conversación (6.5): en una misma máquina puedes tener varios agentes abiertos y
> cada uno es uno distinto.

### 6.4 Arrancar con el flag

**Los canales no se activan con `/mcp`.** Hay que arrancar Claude Code así:

```bash
claude --dangerously-load-development-channels server:menx-canal
```

Sale una advertencia → **"I am using this for local development"**. Es
"dangerously" solo porque los canales propios no están en la lista aprobada de
Anthropic mientras la función es research preview.

> **El fallo más confuso de todo esto:** sin el flag el MCP se registra igual y
> **verás** las tools `canal_*`, pero no llegará ningún mensaje. Parece instalado y
> está mudo.

### 6.5 Identificarte

> Identifícate en los canales de menx como `qa-ubuntu`.

Algo reconocible para el otro lado. Sobrevive a los `/mcp`; con `/resume` o al
reiniciar, Claude Code abre sesión nueva y te la vuelve a pedir — sugiriéndote la
que usaste antes en esa carpeta.

### 6.6 Hablar

```
¿Qué canales hay?                     →  listar_canales
Crea un canal "qa" y entra.           →  canal_crear
Dile a jhon-windows que ya terminé.   →  canal_enviar
```

Un canal admite **2 agentes**; puedes estar en varios a la vez. Lo que pasa solo:
el mensaje **entra en tu sesión** y arranca un turno si estabas ocioso, tu puente
**acusa recibo** automáticamente, y nada se da por leído hasta que entra de verdad
—si el puente se cae antes, se reentrega—.

Con el puente corriendo **no esperes mensajes a mano** con `recibir_mensajes`:
llegan empujados y esa tool casi siempre devolverá vacío.

### 6.7 Barra de estado

La identidad del canal es invisible, y un agente que se cree identificado y no lo
está deja de recibir sin que nada lo diga. En `~/.claude/settings.json`:

```json
"statusLine": {
  "type": "command",
  "command": "/home/TU-USUARIO/.nvm/versions/node/v22.19.0/bin/node /home/TU-USUARIO/menximple/canal/statusline-menx.mjs",
  "padding": 1
}
```

Queda algo así:

```
insumedic  |  Opus 5  |  menx: qa-ubuntu · 1 canal: qa
```

Se lee **al arrancar**: hay que cerrar y abrir Claude Code, con `/mcp` no aparece.

### 6.8 Comprobar

```
¿En qué canales estoy?   →  canal_estado
```

| Síntoma | Causa |
|---|---|
| No existen las tools `canal_*` | El MCP no quedó registrado (6.3) |
| Existen pero no llega nada | Arrancaste sin el flag (6.4) |
| "sin identidad" | Falta 6.5, o abriste sesión nueva |
| El puente no arranca y no dice por qué | El `node` viejo del PATH (6.1) |

---

Cómo se usa una vez instalado: **[../USO.md](../USO.md)**
Si ya lo tenías de antes y quieres lo nuevo: **[ACTUALIZAR.md](ACTUALIZAR.md)**
