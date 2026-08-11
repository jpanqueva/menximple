# Instalar el CLIENTE de `menximple` (en tus consolas)

El cliente trae dos cosas que hablan con el hub por HTTP:

- **`menximple-mcp`** — servidor MCP **local** que le da al agente el selector
  visual. Es la forma normal de usarlo; va en el `.mcp.json` de tu proyecto.
- **`menximple select` / `menximple load`** — los mismos comandos desde una
  consola, sin agente.

El hub corre en un contenedor en el servidor y no puede abrir ventanas en tu PC:
por eso el selector tiene que vivir aquí.

> **En Windows con Claude Code, usa [docs/INSTALAR-EN-WINDOWS.md](docs/INSTALAR-EN-WINDOWS.md)**:
> deja los dos MCP configurados para todas tus sesiones y sin pedir permisos cada
> vez. Esta página es el equivalente genérico (Linux/macOS, o uso desde consola).

## Requisitos
- Python 3.10+
- [pipx](https://pipx.pypa.io) (recomendado). Instalarlo: `python -m pip install --user pipx && python -m pipx ensurepath`

## Instalar
```bash
pipx install "git+https://github.com/jpanqueva/menximple@main"
```

## Actualizar a la última versión
```bash
pipx install --force "git+https://github.com/jpanqueva/menximple@main"
```

## Configurar (una sola vez por consola)
Agrega a tu perfil de shell (`~/.bashrc`, `~/.zshrc`, o el `$PROFILE` de PowerShell):
```bash
export MEMORY_BASE_URL="https://TU-SERVIDOR/mcp"   # o http://localhost:8000/mcp en local
export MEMORY_APIKEY="<apikey de tu cuenta>"
```
En PowerShell:
```powershell
setx MEMORY_BASE_URL "https://TU-SERVIDOR/mcp"
setx MEMORY_APIKEY   "<apikey de tu cuenta>"
```

## Uso
```bash
menximple select --query "tema"     # abre la TUI (marca con ESPACIO, ENTER confirma);
                                    # si no hay ventana (servidor/tmux) cae a modo chat
menximple load   --ids id1,id2      # carga el contexto de esas memorias
```
La salida es JSON: es lo que se inyecta en la conversación del agente.

## Desinstalar
```bash
pipx uninstall menximple
```
