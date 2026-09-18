/**
 * Que el puente no deje sesiones huérfanas en el hub.
 *
 * La caída del 17/09/2026: nginx se quedó sin conexiones para todos los sitios del
 * servidor, y el 94% eran flujos de menx — ~480 sesiones abiertas con ~20 agentes.
 * El puente reciclaba la conexión soltando la referencia sin cerrarla, y lo hacía
 * (1) en cada error de tool, aunque fuera un "no existe el canal", y (2) cada minuto
 * en silencio, porque el SDK corta a los 60 s y la espera pedía 100.
 *
 * Se pone un proxy delante del hub que CUENTA sesiones: cuántas abre el puente (las
 * `mcp-session-id` distintas que devuelve el hub) y cuántas cierra (DELETE). Así se
 * mide lo que de verdad importa, lo que queda vivo del otro lado.
 *
 * Tarda ~90 s: el caso (2) solo aparece pasado el minuto.
 */
import http from 'node:http'
import { fileURLToPath } from 'node:url'
import { tmpdir } from 'node:os'
import { join } from 'node:path'
import { Client } from '@modelcontextprotocol/sdk/client/index.js'
import { StdioClientTransport } from '@modelcontextprotocol/sdk/client/stdio.js'

const HUB = new URL(process.env.MEMORY_BASE_URL)
const APIKEY = process.env.MEMORY_APIKEY
const PUENTE = fileURLToPath(new URL('../menx-canal.mjs', import.meta.url))
const AISLADO = join(tmpdir(), 'menx-pruebas-sesiones-' + process.pid)

const fallos = []
const chk = (c, m) => { console.log((c ? '  OK   ' : '  FALLO') + '  ' + m); if (!c) fallos.push(m) }
const dormir = (s) => new Promise((r) => setTimeout(r, s * 1000))

// --- proxy que cuenta sesiones -------------------------------------------- //
const abiertas = new Set()
const cerradas = new Set()
const proxy = http.createServer((req, res) => {
  const sid = req.headers['mcp-session-id']
  const up = http.request({ host: HUB.hostname, port: HUB.port, path: HUB.pathname,
                            method: req.method, headers: { ...req.headers, host: HUB.host } },
    (r) => {
      const nuevo = r.headers['mcp-session-id']
      if (nuevo) abiertas.add(nuevo)
      if (req.method === 'DELETE' && sid && r.statusCode < 300) cerradas.add(sid)
      res.writeHead(r.statusCode, r.headers)
      r.pipe(res)
    })
  up.on('error', () => { res.writeHead(502); res.end() })
  req.pipe(up)
})
await new Promise((r) => proxy.listen(0, '127.0.0.1', r))
const URL_PROXY = `http://127.0.0.1:${proxy.address().port}${HUB.pathname}`
const vivas = () => [...abiertas].filter((s) => !cerradas.has(s)).length

// --- un puente, como lo arrancaría Claude Code ------------------------------ //
const env = { ...process.env, MEMORY_BASE_URL: URL_PROXY, MEMORY_APIKEY: APIKEY,
              MENX_CANAL_DIR: AISLADO }
delete env.CLAUDE_CODE_SESSION_ID
delete env.CANAL_AGENTE
const c = new Client({ name: 'test', version: '1' }, { capabilities: {} })
await c.connect(new StdioClientTransport({ command: 'node', args: [PUENTE], env,
                                          stderr: 'pipe' }))
const tool = (name, args = {}) => c.callTool({ name, arguments: args })

console.log('== errores de tool no reciclan la sesión ==')
await tool('canal_identificarse', { agente: 'e2e-sesiones-' + process.pid })
await dormir(2)
const antes = abiertas.size
let errores = 0
for (let i = 0; i < 3; i++) {
  const r = await tool('canal_unirse', { canal: 'no-existe-' + Date.now() })
  if (r.isError || /no existe/.test(JSON.stringify(r.content))) errores++
}
chk(errores === 3, `las 3 llamadas fallaron de verdad (si no, no prueba nada) -> ${errores}`)
chk(abiertas.size === antes, `y no abrieron sesiones nuevas -> ${abiertas.size - antes} nuevas`)
chk(abiertas.size >= 1, `el puente sí tiene su sesión -> ${abiertas.size}`)

console.log('== escuchar en silencio más de un minuto no fuga ==')
const antesSilencio = abiertas.size
await dormir(75)          // pasa el corte de 60 s del SDK
chk(abiertas.size === antesSilencio,
    `75 s escuchando sin mensajes: ${abiertas.size - antesSilencio} sesiones nuevas (debe ser 0)`)

console.log('== al cerrar, el puente cierra su sesión en el hub ==')
await c.close()           // cierra el stdin del puente, como Claude Code al salir
for (let i = 0; i < 10 && vivas() > 0; i++) await dormir(0.5)
chk(vivas() === 0, `sesiones vivas en el hub tras cerrar: ${vivas()} de ${abiertas.size}`)

proxy.close()
console.log(`\nabiertas ${abiertas.size}, cerradas ${cerradas.size}`)
console.log('FALLOS:', fallos.length)
process.exit(fallos.length ? 1 : 0)
