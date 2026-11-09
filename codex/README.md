# MENX en Codex

El mismo hub, las mismas memorias y archivos que en Claude Code. La configuración
de Claude no se modifica. No hace falta otro servidor ni otro repositorio.

## Primera etapa: memorias y archivos

Requisitos: Codex CLI, Python 3.11+ y Node 20+ para los canales. Desde este repositorio:

```powershell
python -m pip install -e .
npm --prefix canal ci
python codex/instalar.py --from-claude
```

`--from-claude` copia la URL y la apikey de `menximple` en `~/.claude.json`.
Sin instalación previa de Claude (se pide la apikey oculta):

```powershell
python codex/instalar.py --url "https://TU-HUB/api"
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
| `menx-canal` | Identidad de conversación, operaciones de canal y entrega a Codex |

Para instalar solamente memorias y archivos, añade `--solo-memorias`. No necesita
Node. Esta opción reemplaza el bloque administrado completo, por lo que también
quita los canales de ese bloque si estaban instalados.

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

## Canales en Codex

El puente de Claude conserva sus notificaciones `claude/channel`. La entrada
`codex/menx-canal.mjs` usa `codex queue --thread ... --message ... --resume` para
guardar los mensajes en la conversación de destino. Se probó con Codex 0.167.0;
el instalador comprueba que tu CLI ofrece ese comando. No hacen falta flags de
canales de Claude ni un segundo servidor de sockets.

La identidad se liga a `CODEX_THREAD_ID` (o `CODEX_SESSION_ID`), nunca a la máquina
completa. Si el cliente no pasa esas variables al MCP, este arranca sin consumidor.
El agente consulta `CODEX_THREAD_ID` en su entorno de ejecución y lo pasa como
`sesion_codex` al llamar a `canal_identificarse`. El UUID se liga al proceso; no
puede cambiarse a otra conversación. No lo fijes en la configuración global.

No se confirma un mensaje en el hub hasta que Codex lo haya guardado en
su cola. Eso no demuestra que el modelo ya lo haya leído. Si no se puede reanudar
la sesión, Codex puede guardar el mensaje con un aviso; se procesa al reanudar.
Para recibir automáticamente, usa una sesión local con el daemon de Codex; no
arranques con `--no-daemon`. El acuse distingue «en cola» de «procesado».

Prueba después de reabrir Codex:

1. «Identifícate en MENX con ámbito menx y rol codex». `canal_estado` debe mostrar
   el equipo, el agente y el UUID de esta conversación.
2. «Entra al canal ...» indicando una sala existente acordada con el otro agente.
3. Haz que el otro agente envíe un mensaje dirigido al nombre mostrado. Debe
   entrar como un mensaje externo de MENX y permitir contestar con `canal_enviar`.

La sesión HTTP del hub se reutiliza entre herramientas y escucha. La espera de
100 segundos tiene timeout de 115; un error de negocio no recicla la conexión.
Al reconectar se espera el cierre de la anterior. Al cerrar stdin se cancela la
entrega pendiente a Codex, se envía DELETE al hub y se cierra el transporte local.
Si DELETE no responde, el cierre local tiene un límite; la sesión remota dependerá
de la caducidad del hub. En Windows el instalador prefiere el binario nativo para
evitar dejar un proceso hijo detrás del shim Node.

Los mensajes largos viajan como referencia a JSON local en
`~/.menx-canal/mensajes-codex/`, con SHA-256, para no exceder el límite de argumentos
de Windows. El mensaje en cola indica qué archivo leer. Esos archivos se conservan
para que una sesión reanudada pueda leerlos. Esta integración está destinada a
Codex local, con acceso a ese disco y a su daemon.

La entrega favorece recuperar mensajes: si el proceso cae después de guardarlos
en Codex y antes de confirmarlos en MENX, pueden reaparecer. Usa `canal` y `seq`
para reconocerlos. Un fallo de cola no se confirma ni genera acuse de éxito.

## Archivos

`publicar_archivo` sigue en `menximple-selector`, como en Claude; no se duplica
en otro proceso. La subida usa bytes crudos y una conexión HTTP de duración
limitada. Para compartir con otro agente, publica el archivo y envía su URL por
`canal_enviar`. Las funciones `listar_archivos` y `borrar_archivo` están en el hub.

## Barra de Codex y monitor de MENX

La barra nativa se configura escribiendo `/statusline` en Codex: permite elegir
modelo, contexto, límites, rama y otros campos predefinidos. El script de barra
de Claude no se conecta a esa barra.

Para ver MENX, abre otro panel de terminal en este repositorio:

```powershell
node codex/estado-menx.mjs --watch
```

Muestra las identidades de Codex registradas, sus canales, equipo, versión y la
última respuesta del hub. Distingue `PUENTE ACTIVO`, `SIN PUENTE` y `OTRA INSTANCIA`:
una identidad guardada no demuestra que siga escuchando. Consulta tanto el PID
como el cerrojo del consumidor. No abre sockets ni llama al hub; lee lo que el
puente ya escribe en `~/.menx-canal/`.

`--sesion UUID` filtra una conversación; también usa `CODEX_THREAD_ID` si está en
el entorno. Sin `--watch` hace una consulta única; `--json` permite consumir el
estado desde otras herramientas. `Ctrl+C` cierra solo el monitor.

## Verificación del instalador

```powershell
python -m unittest discover -s codex -p "test_*.py"
node --test canal/pruebas/codex.test.mjs
```

Las pruebas son locales: no necesitan la apikey de trabajo. Cubren la subida de
bytes y errores HTTP; compatibilidad con Claude; reintentos de cola; informes
largos; recuperación y separación de identidades; consumidor único; cierre de
SSE; reconexión tras un 503; DELETE y queue colgados. La prueba de silencio tarda
65 segundos para superar el antiguo corte de 60 del SDK.

Documentación oficial: [MCP](https://learn.chatgpt.com/docs/extend/mcp) y
[codex queue](https://learn.chatgpt.com/docs/developer-commands#codex-queue).
