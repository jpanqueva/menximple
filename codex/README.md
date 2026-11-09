# MENX en Codex

El mismo hub, las mismas memorias y archivos que en Claude Code. La configuración
de Claude no se modifica. No hace falta otro servidor ni otro repositorio.

## Primera etapa: memorias y archivos

Requisitos: Codex CLI y Python 3.11+. Desde este repositorio:

```powershell
python -m pip install -e .
python codex/instalar.py --solo-memorias --from-claude
```

`--from-claude` copia la URL y la apikey de `menximple` en `~/.claude.json`.
Sin instalación previa de Claude:

```powershell
python codex/instalar.py --solo-memorias --url "https://TU-HUB/api"
```

La clave se pide oculta; también se acepta `MEMORY_APIKEY` del entorno. Nunca la
pongas en un archivo del repositorio. El instalador escribe únicamente en
`$CODEX_HOME/config.toml` (por defecto `~/.codex/config.toml`), hace una copia antes
de cambiarlo y preserva las demás opciones y MCP. La configuración personal y sus
copias contienen la clave. Repetir la instalación no duplica los servidores.

Se registran:

| MCP | Función |
| --- | --- |
| `menximple` | Memorias remotas, búsqueda, carpetas y contexto por HTTP |
| `menximple-selector` | Selector visual local, cargar memorias y publicar archivos |

Comprueba con `codex.cmd mcp list` (Windows) o `codex mcp list` (Linux/macOS).
Después **cierra y reanuda Codex** para cargar los nuevos MCP:

```powershell
codex.cmd resume --last
```

En la conversación, prueba en este orden:

1. «Muéstrame el árbol de mis memorias, solo carpetas». Debe llamar a `arbol`.
2. «Busca las memorias de menx». Debe llamar a `buscar` y citar números.
3. «Carga la memoria #N». El hub usa `cargar_contexto(entry_ids=["N"])`;
   el selector local ofrece `cargar_memorias(ids=["N"])`.
4. «Abre el selector de memorias». Debe abrir una ventana y esperar tu selección.

`publicar_archivo(ruta)` entrega un enlace público. Pruébalo solo con un archivo
que quieras compartir; no es necesario publicar nada para verificar las memorias.

## Canales: segunda etapa

La adaptación incluida está en desarrollo; **no se instala** con
`--solo-memorias`. Se validará por separado antes de usarla en una conversación
real. El puente de Claude conserva sus notificaciones `claude/channel`; la entrada
`codex/menx-canal.mjs` usa `codex queue --thread ... --message ... --resume`.
Requiere una versión de Codex con ese comando y Node 18+.

La identidad se liga a `CODEX_THREAD_ID` (o `CODEX_SESSION_ID`), nunca a la máquina
completa. No se confirma un mensaje en el hub hasta que Codex lo haya guardado en
su cola. Eso no demuestra que el modelo ya lo haya leído. Si no se puede reanudar
la sesión, Codex puede guardar el mensaje con un aviso; se procesa al reanudar.

## Verificación del instalador

```powershell
python -m unittest discover -s codex -p "test_*.py"
```

Documentación oficial: [MCP](https://learn.chatgpt.com/docs/extend/mcp) y
[codex queue](https://learn.chatgpt.com/docs/developer-commands#codex-queue).
