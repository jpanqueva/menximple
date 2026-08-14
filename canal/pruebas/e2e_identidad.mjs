/**
 * Dos puentes en la MISMA maquina, identificandose distinto, hablandose entre si.
 * Es el caso que el diseno anterior rompia: con CANAL_AGENTE en la config del PC
 * ambos se habrian llamado igual y se habrian robado los mensajes.
 */
import { fileURLToPath } from 'node:url'
import { tmpdir } from 'node:os'
import { join } from 'node:path'
import { Client } from '@modelcontextprotocol/sdk/client/index.js'
import { StdioClientTransport } from '@modelcontextprotocol/sdk/client/stdio.js'

const URL_HUB = process.env.MEMORY_BASE_URL
const APIKEY = process.env.MEMORY_APIKEY
// fileURLToPath y no .pathname: en Windows .pathname devuelve /C:/... con
// barra inicial, que no es una ruta valida y el proceso hijo no arranca.
const PUENTE = fileURLToPath(new URL('../menx-canal.mjs', import.meta.url))
const CANAL = 'e2e-ident-' + Date.now().toString().slice(-6)

const AISLADO = join(tmpdir(), 'menx-pruebas-' + process.pid)

// Los puentes que levanta una prueba TIENEN que quedar aislados del agente que
// esté corriendo en esta máquina. Heredar el entorno tal cual les pasa el
// CLAUDE_CODE_SESSION_ID de la sesión real: recuperan SU identidad del archivo
// compartido, le quitan el turno del buzón y lo dejan sordo. Pasó de verdad —
// el puente real disparó su aviso de "otra instancia tomó el buzón" a mitad de
// una prueba. De ahí el directorio propio y la sesión propia.
function entorno(extra = {}) {
  const e = { ...process.env, MEMORY_BASE_URL: URL_HUB, MEMORY_APIKEY: APIKEY,
              MENX_CANAL_DIR: AISLADO, ...extra }
  delete e.CLAUDE_CODE_SESSION_ID
  delete e.CANAL_AGENTE
  return e
}

const fallos = []
const chk = (c, m) => { console.log((c ? '  OK   ' : '  FALLO') + '  ' + m); if (!c) fallos.push(m) }

// Cada puente es un proceso aparte, como lo seria cada sesion de Claude Code.
const recibido = { a: [], b: [] }

async function abrir(etiqueta) {
  const c = new Client({ name: 'test', version: '1' }, { capabilities: {} })
  await c.connect(new StdioClientTransport({
    command: 'node', args: [PUENTE],
    env: entorno(),
    stderr: 'pipe',
  }))
  // Los eventos de canal salen como notificacion: es lo que Claude Code inyecta.
  c.fallbackNotificationHandler = async (n) => {
    if (n.method === 'notifications/claude/channel') {
      // Los acuses se descartan: son tráfico del puente, no del agente. Esta
      // prueba se escribió antes de que existieran y los contaba como mensajes.
      if (n.params.meta.tipo === 'acuse') return
      recibido[etiqueta].push({ de: n.params.meta.de, canal: n.params.meta.canal,
                                texto: n.params.content })
    }
  }
  return c
}

const call = async (c, tool, args = {}) => {
  const r = await c.callTool({ name: tool, arguments: args })
  const t = r?.content?.find((x) => x.type === 'text')?.text
  return { error: !!r?.isError, texto: t, dato: (() => { try { return JSON.parse(t) } catch { return null } })() }
}

const A = await abrir('a')
const B = await abrir('b')

console.log('== sin identidad, el puente NO deja usar canales ==')
let r = await call(A, 'canal_unirse', { canal: CANAL })
chk(r.error && /identidad/i.test(r.texto), `pide identificarse -> ${r.texto?.slice(0, 60)}`)
r = await call(A, 'canal_estado')
chk(r.dato?.agente === null, 'canal_estado dice que no hay identidad')

console.log('== dos identidades distintas en la MISMA maquina ==')
await call(A, 'canal_identificarse', { agente: 'qa-arauca' })
await call(B, 'canal_identificarse', { agente: 'jhon-insumedic' })
const ea = (await call(A, 'canal_estado')).dato
const eb = (await call(B, 'canal_estado')).dato
chk(ea.agente === 'qa-arauca' && eb.agente === 'jhon-insumedic',
    `cada puente tiene la suya -> ${ea.agente} / ${eb.agente}`)

console.log('== se hablan ==')
// El canal se crea desde el hub (crear_canal no necesita identidad).
const hub = new Client({ name: 't', version: '1' }, { capabilities: {} })
const { StreamableHTTPClientTransport } = await import('@modelcontextprotocol/sdk/client/streamableHttp.js')
await hub.connect(new StreamableHTTPClientTransport(new URL(URL_HUB), {
  requestInit: { headers: { 'X-API-Key': APIKEY } },
}))
await hub.callTool({ name: 'crear_canal', arguments: { nombre: CANAL } })

await call(A, 'canal_unirse', { canal: CANAL })
await call(B, 'canal_unirse', { canal: CANAL })
await call(B, 'canal_enviar', { canal: CANAL, texto: 'corre las pruebas del armado' })
await new Promise((r) => setTimeout(r, 6000))

chk(recibido.a.length === 1 && recibido.a[0].texto === 'corre las pruebas del armado',
    `A recibio el mensaje -> ${JSON.stringify(recibido.a)}`)
chk(recibido.a[0]?.de === 'jhon-insumedic', `y sabe quien lo mando -> ${recibido.a[0]?.de}`)
chk(recibido.b.length === 0, `B NO recibio el suyo propio -> ${JSON.stringify(recibido.b)}`)

console.log('== contesta el otro lado ==')
await call(A, 'canal_enviar', { canal: CANAL, texto: '12 pruebas OK' })
await new Promise((r) => setTimeout(r, 6000))
chk(recibido.b.length === 1 && recibido.b[0].de === 'qa-arauca',
    `B recibio la respuesta de A -> ${JSON.stringify(recibido.b)}`)

// limpieza
await call(A, 'canal_salir', { canal: CANAL })
await call(B, 'canal_salir', { canal: CANAL })
await A.close(); await B.close(); await hub.close()

console.log()
console.log(fallos.length ? `${fallos.length} FALLOS: ${fallos}` : 'TODO OK')
process.exit(fallos.length ? 1 : 0)
