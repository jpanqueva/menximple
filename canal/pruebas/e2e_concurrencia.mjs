/**
 * El bucle de escucha corre colgado mientras el agente llama tools. Antes eso
 * compartia una sola variable `hub` y reventaba con
 * "Cannot read properties of null (reading 'callTool')".
 */
import { fileURLToPath } from 'node:url'
import { Client } from '@modelcontextprotocol/sdk/client/index.js'
import { StdioClientTransport } from '@modelcontextprotocol/sdk/client/stdio.js'

const URL_HUB = process.env.MEMORY_BASE_URL
const APIKEY = process.env.MEMORY_APIKEY
// fileURLToPath y no .pathname: en Windows .pathname devuelve /C:/... con
// barra inicial, que no es una ruta valida y el proceso hijo no arranca.
const PUENTE = fileURLToPath(new URL('../menx-canal.mjs', import.meta.url))

const fallos = []
const chk = (c, m) => { console.log((c ? '  OK   ' : '  FALLO') + '  ' + m); if (!c) fallos.push(m) }

const c = new Client({ name: 'test', version: '1' }, { capabilities: {} })
await c.connect(new StdioClientTransport({
  command: 'node', args: [PUENTE],
  env: { ...process.env, MEMORY_BASE_URL: URL_HUB, MEMORY_APIKEY: APIKEY },
  stderr: 'pipe',
}))

const call = async (tool, args = {}) => {
  const r = await c.callTool({ name: tool, arguments: args })
  const t = r?.content?.find((x) => x.type === 'text')?.text
  return { error: !!r?.isError, texto: t, dato: (() => { try { return JSON.parse(t) } catch { return null } })() }
}

console.log('== identificarse mientras el bucle ya esta corriendo ==')
let r = await call('canal_identificarse', { agente: 'concurrencia-1' })
chk(!r.error && r.dato?.agente === 'concurrencia-1', `identifico -> ${r.texto?.slice(0, 80)}`)

// A partir de aqui el bucle esta colgado 100 s en recibir_de_todos. Toda llamada
// que se haga ahora convive con esa espera: es justo el escenario que rompia.
console.log('== 8 llamadas en paralelo con el bucle colgado ==')
await new Promise((x) => setTimeout(x, 2500))
const rs = await Promise.all(Array.from({ length: 8 }, () => call('canal_estado')))
const malas = rs.filter((x) => x.error)
chk(malas.length === 0, `ninguna reventó (${malas.map((m) => m.texto).slice(0, 2)})`)
chk(rs.every((x) => x.dato?.agente === 'concurrencia-1'), 'todas ven la identidad correcta')

console.log('== y sigue funcionando despues ==')
r = await call('canal_estado')
chk(!r.error, `la conexión sigue sana -> ${r.texto?.slice(0, 60)}`)

await c.close()
console.log()
console.log(fallos.length ? `${fallos.length} FALLOS: ${fallos}` : 'TODO OK')
process.exit(fallos.length ? 1 : 0)
