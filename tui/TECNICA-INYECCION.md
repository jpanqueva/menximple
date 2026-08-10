# Técnica de inyección TUI/chat  (probada 2026-08-10)

Cómo el selector de contexto mete lo elegido **dentro de la conversación** de Claude.

## Canal de inyección
En Claude Code, lo único que "entra a la conversación" de forma controlada es el
**resultado de una tool** (o de un comando de shell que Claude ejecuta). Por eso el
selector se invoca como **una llamada que BLOQUEA hasta que el programa muere**, y su
**stdout / valor de retorno** = el contexto seleccionado → queda inyectado.

```
Claude ejecuta el lanzador  ──▶  abre ventana (TTY propio)  ──▶  usuario marca/cancela
        ▲                                                              │
        └────────── stdout = contexto elegido (inyectado) ◀── lee archivo de selección
```

## Bloqueo + cancelación (probado)
- **Éxito:** `Start-Process -Wait` (o `-PassThru` + `WaitForExit`) bloquea hasta que la
  ventana cierra; luego se lee el archivo de selección. Verificado: bloqueó 3 s y
  devolvió el JSON.
- **Timeout / se bloquea:** `WaitForExit($ms)` → si vence, `Kill()` y se devuelve
  "cancelado por timeout". Verificado: mató la ventana a los 5 s y liberó el chat.
- **Cancela el usuario:** cierra la ventana / no selecciona → exit ≠ 0 o archivo vacío
  → se devuelve "cancelado" (sin inyectar nada).
- Leer siempre con **UTF-8** (`Get-Content -Encoding utf8` / `open(..., encoding="utf-8")`).

## Servidor ciego (sin escritorio)
Antes de intentar abrir ventana, detectar entorno interactivo:
- Windows: `[Environment]::UserInteractive`.
- Linux: `os.environ.get("DISPLAY")` / `WAYLAND_DISPLAY`; en tmux normalmente no hay.
- Override manual: variable `MEMORY_TUI=off`.

Si NO hay escritorio → **no se abre ventana**: se cae al **modo chat** (el lanzador
devuelve los candidatos como JSON y Claude guía la selección por número en el chat,
llamando luego a `cargar_contexto`).

## Arquitectura del lanzador
- `launcher`: lo ejecuta Claude. Detecta entorno → abre TUI en consola nueva
  (Windows `CREATE_NEW_CONSOLE`) con timeout, o cae a modo chat. Imprime el contexto
  elegido (JSON) a stdout.
- `browser` (TUI): corre en la ventana; habla con el API por `MEMORY_BASE_URL` +
  `X-API-Key` (mismo API, única fuente de verdad); multi-selección con espacio; escribe
  la selección a un archivo temporal.
- `client`: envuelve el cliente MCP (`fastmcp.Client`) para llamar `buscar`, `listar`,
  `cargar_contexto`.
