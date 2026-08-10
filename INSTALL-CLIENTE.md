# Instalar el CLIENTE de `menximple` (en tus consolas)

El cliente da los comandos `menximple select` / `menximple load` para buscar y cargar
memorias desde cualquier consola. Habla con el servidor por HTTP.

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
