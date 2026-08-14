# Actualizar menx (ya lo tienes instalado)

Para quien ya usa menx y le falta lo nuevo: las tools que se agregaron al hub y
los **canales** entre agentes, que son un MCP aparte.

Si estás instalando desde cero, ve a [INSTALAR-EN-WINDOWS.md](INSTALAR-EN-WINDOWS.md)
o [INSTALAR-EN-UBUNTU.md](INSTALAR-EN-UBUNTU.md).

---

## 1. Actualizar el cliente

Según cómo lo instalaste:

```bash
# pipx
pipx install --force "git+https://github.com/jpanqueva/menximple@main"

# pip
pip install --force-reinstall --no-deps "git+https://github.com/jpanqueva/menximple@main"

# clonado con pip install -e .
cd menximple && git pull
```

> **`pip install --upgrade` a secas NO se trae nada.** Como la URL es de git y la
> versión del paquete no sube, pip cree que ya estás al día. Es la trampa clásica
> de instalar desde un repo.

## 2. Reconectar el hub

En Claude Code: `/mcp` → `menximple` → reconectar.

**Esto no es opcional.** El catálogo de tools se cachea al conectar, así que sin
reconectar vas a ver la lista vieja. Si alguna vez leíste en la descripción de una
tool que uses otra que "no existe", era esto.

Lo que ganas sin hacer nada más:

| | |
|---|---|
| `anexar_entrada` | agrega texto a una memoria **sin reenviar** el contexto entero |
| `estado` | `pendiente\|en_curso\|hecho\|bloqueado`. `buscar(estado="pendiente")` responde "¿qué me queda?" en una llamada |
| `alcance="completo"` | busca **dentro del cuerpo** de las memorias, no solo en resúmenes |
| Rutas de carpeta | `arbol`, `listar`, `buscar`, `crear_entrada`… aceptan `insumedic/rips`; ya no hace falta un uuid |
| Respuesta compacta | `buscar` devuelve 7 campos en vez de 16; `detallado=True` trae el resto |

---

## 3. Canales entre agentes (opcional)

Para que **dos agentes en máquinas distintas se hablen**. Si solo usas memoria,
sáltate esto.

Necesita **Node 18+**. Comprueba con `node --version`; si el del PATH es viejo pero
tienes otro (nvm, por ejemplo), usa su **ruta absoluta** en el paso 3.2 — es el
error más común y falla sin decir por qué.

### 3.1 Traer el puente

```bash
git clone https://github.com/jpanqueva/menximple.git   # si no lo tienes
cd menximple/canal
npm install
```

### 3.2 Registrarlo

Agrega a `~/.claude.json` (Windows: `C:\Users\TU-USUARIO\.claude.json`), dentro de
`mcpServers`, **con la misma URL y apikey que ya usas para menx**:

```json
"menx-canal": {
  "type": "stdio",
  "command": "node",
  "args": ["RUTA/ABSOLUTA/menximple/canal/menx-canal.mjs"],
  "env": {
    "MEMORY_BASE_URL": "<la misma URL de menximple>",
    "MEMORY_APIKEY": "<tu apikey>"
  }
}
```

No pongas identidad aquí: se pide por conversación (ver 3.4).

### 3.3 Arrancar con el flag

**Los canales no funcionan con un `/mcp`.** Hay que arrancar Claude Code así:

```bash
claude --dangerously-load-development-channels server:menx-canal
```

Sale una pantalla de advertencia → **"I am using this for local development"**.
Es "dangerously" solo porque los canales propios no están en la lista aprobada de
Anthropic mientras la función es research preview; el código es el tuyo.

> **El modo de fallo más confuso de todo esto:** si arrancas sin el flag, el MCP se
> registra igual y vas a **ver** las tools `canal_*`, pero no te llega ningún
> mensaje. Parece instalado y está mudo. Si no recibes nada, empieza por aquí.

### 3.4 Identificarse

Dile a tu agente con qué nombre quieres que lo conozcan:

> Identifícate en los canales de menx como `qa-arauca`.

La identidad es **de la conversación, no del equipo**: en una misma máquina puedes
tener varios agentes y cada uno es uno. Sobrevive a los `/mcp` (se guarda contra
el id de sesión), pero una conversación nueva empieza sin identidad.

### 3.5 Hablar

```
Crea un canal "despliegue" y entra.        →  canal_crear
¿Qué canales hay?                          →  listar_canales
Entra al canal "qa".                       →  canal_unirse
Dile a qa-arauca que corra las pruebas.    →  canal_enviar
```

Un canal admite **2 agentes**; tú puedes estar en varios a la vez.

Lo que pasa solo, sin que nadie lo pida:

- Cuando te escriben, el mensaje **entra en tu sesión** y, si estabas ocioso,
  arranca un turno con él. No hay que consultar nada.
- Tu puente **acusa recibo automáticamente**: el otro sabe que llegó y que lo estás
  trabajando. No lo repitas a mano.
- Un mensaje no se da por leído hasta que **entra de verdad** en la sesión. Si el
  puente se cae antes, se vuelve a entregar.

Con el puente corriendo, **no esperes mensajes a mano** con `recibir_mensajes`:
llegan empujados, y esa tool casi siempre te devolverá vacío porque el puente ya
consumió el buzón.

---

## 4. Barra de estado (opcional, recomendado)

La identidad del canal es invisible, y un agente que se cree identificado y no lo
está deja de recibir mensajes sin que nada lo diga. En la barra se ve de un vistazo:

```
Documents  |  Opus 5  |  menx: qa-arauca · 2 canales: qa, despliegue
```

En `~/.claude/settings.json`:

```json
"statusLine": {
  "type": "command",
  "command": "node RUTA/ABSOLUTA/menximple/canal/statusline-menx.mjs",
  "padding": 1
}
```

No sale a la red: lee el archivo local que el puente ya mantiene. Si ya tienes una
barra propia, mira el script — son 40 líneas y el trozo de menx se copia fácil.

---

## Comprobar que quedó bien

```
¿En qué canales estoy?     →  canal_estado
```

Debe decir tu nombre. Si dice "sin identidad", vuelve al 3.4. Si las tools
`canal_*` no existen, el MCP no está registrado (3.2). Si existen pero no llega
ningún mensaje, arrancaste sin el flag (3.3).
