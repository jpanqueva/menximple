/**
 * Acuse de recibo automatico entre dos puentes reales.
 * Lo critico: que NO se acuse un acuse (seria un bucle infinito de cortesia).
 */
import { fileURLToPath } from 'node:url'
import { tmpdir } from 'node:os'
import { join } from 'node:path'
import { Client } from '@modelcontextprotocol/sdk/client/index.js'
import { StdioClientTransport } from '@modelcontextprotocol/sdk/client/stdio.js'
import { StreamableHTTPClientTransport } from '@modelcontextprotocol/sdk/client/streamableHttp.js'

const URL_HUB = process.env.MEMORY_BASE_URL
const APIKEY = process.env.MEMORY_APIKEY
// fileURLToPath y no .pathname: en Windows .pathname devuelve /C:/... con
// barra inicial, que no es una ruta valida y el proceso hijo no arranca.
const PUENTE = fileURLToPath(new URL('../menx-canal.mjs', import.meta.url))
const CANAL = 'e2e-acuse-' + Date.now().toString().slice(-6)

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
const recibido = { a: [], b: [] }

async function abrir(et) {
  const c = new Client({ name: 'test', version: '1' }, { capabilities: {} })
  await c.connect(new StdioClientTransport({
    command: 'node', args: [PUENTE],
    env: entorno(),
    stderr: 'pipe',
  }))
  c.fallbackNotificationHandler = async (n) => {
    if (n.method === 'notifications/claude/channel') {
      recibido[et].push({ de: n.params.meta.de, tipo: n.params.meta.tipo ?? 'mensaje',
                          texto: n.params.content })
    }
  }
  return c
}
const call = async (c, tool, args = {}) => {
  const r = await c.callTool({ name: tool, arguments: args })
  const t = r?.content?.find((x) => x.type === 'text')?.text
  return { error: !!r?.isError, texto: t }
}

const A = await abrir('a')   // el que recibe el encargo
const B = await abrir('b')   // el que lo manda y espera
await call(A, 'canal_identificarse', { agente: 'quien-trabaja' })
await call(B, 'canal_identificarse', { agente: 'quien-espera' })
await call(B, 'canal_crear', { canal: CANAL, descripcion: 'acuse' })
await call(A, 'canal_unirse', { canal: CANAL })

console.log('== canal_crear ya deja dentro al creador ==')
const r = await call(B, 'canal_enviar', { canal: CANAL, texto: 'corre las pruebas' })
chk(!r.error, `B escribe sin unirse aparte -> ${r.texto?.slice(0, 50)}`)

console.log('== el acuse vuelve solo a quien espera ==')
await new Promise((x) => setTimeout(x, 9000))
const acuses = recibido.b.filter((m) => m.tipo === 'acuse')
chk(acuses.length === 1, `B recibio exactamente 1 acuse -> ${acuses.length}`)
chk(acuses[0]?.de === 'quien-trabaja' && /procesando/.test(acuses[0]?.texto ?? ''),
    `y dice quien lo procesa -> ${acuses[0]?.texto?.slice(0, 60)}`)
chk(recibido.a.filter((m) => m.tipo === 'acuse').length === 0,
    'A NO recibio acuse de su propio acuse (sin bucle)')

console.log('== y no se dispara una cascada ==')
await new Promise((x) => setTimeout(x, 8000))
const total = recibido.a.length + recibido.b.length
chk(total === 2, `en total 2 eventos: el encargo y su acuse -> ${total}`)

console.log('== el encargo real si llego, y sin marca de acuse ==')
const enc = recibido.a.find((m) => m.tipo === 'mensaje')
chk(enc?.texto === 'corre las pruebas', `A recibio el encargo -> ${enc?.texto}`)

// limpieza
await call(A, 'canal_salir', { canal: CANAL })
await call(B, 'canal_salir', { canal: CANAL })
await A.close(); await B.close()
console.log()
console.log(fallos.length ? `${fallos.length} FALLOS: ${fallos}` : 'TODO OK')
process.exit(fallos.length ? 1 : 0)
