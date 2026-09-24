/**
 * Tags de canales entre dos puentes reales.
 * Lo critico: que los tags lleguen DENTRO del evento (atributo `tags` del tag
 * <channel>), que un canal sin tags siga igual que siempre, y que `sin-acuse`
 * apague el acuse automatico SOLO en ese canal.
 */
import { fileURLToPath } from 'node:url'
import { tmpdir } from 'node:os'
import { join } from 'node:path'
import { Client } from '@modelcontextprotocol/sdk/client/index.js'
import { StdioClientTransport } from '@modelcontextprotocol/sdk/client/stdio.js'

const URL_HUB = process.env.MEMORY_BASE_URL
const APIKEY = process.env.MEMORY_APIKEY
const PUENTE = fileURLToPath(new URL('../menx-canal.mjs', import.meta.url))
const S = Date.now().toString().slice(-6)
const CON = 'canal-p' + S + '-voz', SIN = 'canal-p' + S + '-comunicacion', MUDO = 'canal-p' + S + '-avisos'
const AISLADO = join(tmpdir(), 'menx-pruebas-' + process.pid)

function entorno() {
  const e = { ...process.env, MEMORY_BASE_URL: URL_HUB, MEMORY_APIKEY: APIKEY, MENX_CANAL_DIR: AISLADO }
  delete e.CLAUDE_CODE_SESSION_ID
  delete e.CANAL_AGENTE
  return e
}

const fallos = []
const chk = (c, m) => { console.log((c ? '  OK   ' : '  FALLO') + '  ' + m); if (!c) fallos.push(m) }
const recibido = { a: [], b: [] }

async function abrir(et) {
  const c = new Client({ name: 'test', version: '1' }, { capabilities: {} })
  await c.connect(new StdioClientTransport({ command: 'node', args: [PUENTE], env: entorno(), stderr: 'pipe' }))
  c.fallbackNotificationHandler = async (n) => {
    if (n.method === 'notifications/claude/channel') {
      recibido[et].push({ canal: n.params.meta.canal, tipo: n.params.meta.tipo ?? 'mensaje',
                          tags: n.params.meta.tags, tieneTags: 'tags' in n.params.meta, texto: n.params.content })
    }
  }
  return c
}
const call = async (c, tool, args = {}) => {
  const r = await c.callTool({ name: tool, arguments: args })
  const t = r?.content?.find((x) => x.type === 'text')?.text
  return { error: !!r?.isError, texto: t, json: (() => { try { return JSON.parse(t) } catch { return null } })() }
}
const espera = (s) => new Promise((x) => setTimeout(x, s * 1000))

const A = await abrir('a')   // el que recibe
const B = await abrir('b')   // el que escribe
await call(A, 'canal_identificarse', { agente: 'agt-eqa-prueba-recibe' })
await call(B, 'canal_identificarse', { agente: 'agt-eqb-prueba-escribe' })

console.log('== crear con tags desde el puente ==')
await call(B, 'canal_registro_crear', { clase: 'ambito', nombre: 'p' + S, tipo: 'proyecto' })
let r = await call(B, 'canal_crear', { canal: CON, descripcion: 'con tags', tags: ['Proyecto:E2E', 'tipo:voz'] })
chk(!r.error && JSON.stringify(r.json?.tags) === `["proyecto:e2e","tipo:voz","proyecto:p${S}"]`, `canal_crear guarda los tags normalizados y añade el ámbito -> ${JSON.stringify(r.json?.tags)}`)
await call(B, 'canal_crear', { canal: SIN, descripcion: 'sin tags' })
await call(B, 'canal_crear', { canal: MUDO, descripcion: 'sin acuse', tags: ['tipo:avisos', 'sin-acuse'] })
for (const c of [CON, SIN, MUDO]) await call(A, 'canal_unirse', { canal: c })

console.log('== canal_estado muestra los tags ==')
r = await call(A, 'canal_estado')
const mios = Object.fromEntries((r.json?.canales ?? []).map((c) => [c.nombre, c.tags]))
chk(JSON.stringify(mios[CON]) === `["proyecto:e2e","tipo:voz","proyecto:p${S}"]` && JSON.stringify(mios[SIN]) === `["tipo:comunicacion","proyecto:p${S}"]`, `-> ${JSON.stringify(mios)}`)

console.log('== los tags llegan dentro del evento ==')
await call(B, 'canal_enviar', { canal: CON, texto: 'hola con tags' })
await call(B, 'canal_enviar', { canal: SIN, texto: 'hola sin tags' })
await call(B, 'canal_enviar', { canal: MUDO, texto: 'hola sin acuse' })
await espera(10)
const msj = (canal) => recibido.a.find((m) => m.canal === canal && m.tipo === 'mensaje')
chk(msj(CON)?.tags === `proyecto:e2e,tipo:voz,proyecto:p${S}`, `canal con tags -> tags="${msj(CON)?.tags}"`)
chk(msj(SIN)?.texto === 'hola sin tags' && msj(SIN)?.tags === `tipo:comunicacion,proyecto:p${S}`, `canal sin tags propios: lleva los del nombre -> ${msj(SIN)?.tags}`)
chk(msj(MUDO)?.tags === `tipo:avisos,sin-acuse,proyecto:p${S}`, `canal sin-acuse -> tags="${msj(MUDO)?.tags}"`)

console.log('== sin-acuse apaga el acuse SOLO en ese canal ==')
const acuses = (canal) => recibido.b.filter((m) => m.canal === canal && m.tipo === 'acuse').length
chk(acuses(CON) === 1, `canal normal con tags: 1 acuse -> ${acuses(CON)}`)
chk(acuses(SIN) === 1, `canal sin tags: 1 acuse, como antes -> ${acuses(SIN)}`)
chk(acuses(MUDO) === 0, `canal sin-acuse: 0 acuses -> ${acuses(MUDO)}`)

console.log('== canal_etiquetar cambia los tags y el siguiente mensaje ya los trae ==')
r = await call(A, 'canal_etiquetar', { canal: SIN, tags: ['tipo:pantalla'] })
chk(!r.error && JSON.stringify(r.json?.tags) === '["tipo:pantalla"]', `-> ${JSON.stringify(r.json?.tags)}`)
await call(B, 'canal_enviar', { canal: SIN, texto: 'segundo' })
await espera(8)
const seg = recibido.a.find((m) => m.canal === SIN && m.texto === 'segundo')
chk(seg?.tags === 'tipo:pantalla', `el mensaje siguiente llega con tags="${seg?.tags}"`)
r = await call(A, 'canal_etiquetar', { canal: SIN })
chk(r.error, 'canal_etiquetar sin nada que cambiar avisa en vez de no hacer nada')

// limpieza
for (const c of [CON, SIN, MUDO]) { await call(A, 'canal_salir', { canal: c }); await call(B, 'canal_salir', { canal: c }) }
await A.close(); await B.close()
console.log()
console.log(fallos.length ? `${fallos.length} FALLOS: ${fallos}` : 'TODO OK')
process.exit(fallos.length ? 1 : 0)
