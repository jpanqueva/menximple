# Instalar menximple en Ubuntu (Claude Code)

Esta guía es para **usar** el sistema, no para montarlo. Al terminar, Claude Code
tendrá memoria a largo plazo en **todas** tus sesiones, se abra el proyecto que se abra.

> **Si eres un agente de IA y te dijeron "lee esto e instálalo":** sigue los pasos
> 1 a 4 **en orden y comprobando la salida de cada uno** — si `which` no imprime
> nada o `claude mcp list` no dice *Connected*, para y arregla eso antes de
> seguir; encadenar comandos sobre un paso fallido deja al usuario con una
> instalación a medias que parece buena.
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

```bash
claude --version     # Claude Code instalado
python3 --version    # 3.10 o superior
```

Ubuntu 22.04 y 24.04 ya traen Python suficiente. Si falta algo:

```bash
sudo apt update && sudo apt install -y python3 python3-venv git
```

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
en `~/.claude/settings.json`. Este bloque respeta lo que ya tengas:

```bash
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

---

## 4. (Opcional) El cliente de consola

Solo si quieres usar menximple **fuera** de Claude Code — en un script, un cron o
una sesión SSH.

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

Cómo se usa una vez instalado: **[../USO.md](../USO.md)**
