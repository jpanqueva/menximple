// Hub aislado con sesiones y SSE reales. No usa red externa ni apikey de trabajo.
import assert from 'node:assert/strict'
import { test } from 'node:test'
import http from 'node:http'
import { randomUUID, createHash } from 'node:crypto'
import { mkdtempSync, readFileSync, writeFileSync, existsSync, rmSync } from 'node:fs'
import { tmpdir } from 'node:os'
import { join, resolve, dirname, basename } from 'node:path'
import { fileURLToPath } from 'node:url'
import { setTimeout as pausa } from 'node:timers/promises'
import { Client } from '@modelcontextprotocol/sdk/client/index.js'
import { StdioClientTransport } from '@modelcontextprotocol/sdk/client/stdio.js'

const PUENTE = fileURLToPath(new URL('../menx-canal.mjs', import.meta.url))
const CODEX = fileURLToPath(new URL('../../codex/menx-canal.mjs', import.meta.url))
const AGENTE = 'agt-prueba-menx-codex'

async function hasta(condicion, timeout = 7000) {
  const fin = Date.now() + timeout
  while (!condicion()) {
    if (Date.now() > fin) assert.fail('no se cumplió la condición antes del timeout')
    await pausa(40)
  }
}

async function entorno(t) {
  const dir = mkdtempSync(join(tmpdir(), 'menx-codex-test-'))
  const sesiones = new Map(), abiertas = [], cerradas = [], confirmadas = [], acuses = []
  const pendientes = [], sockets = new Set()
  let maxVivas = 0, gets = 0, polls = 0, fallo503 = false, deleteColgado = false
  const responder = (res, id, result) => {
    if (!res.destroyed && !res.writableEnded) {
      res.setHeader('content-type', 'application/json')
      res.end(JSON.stringify({ jsonrpc: '2.0', id, result }))
    }
  }
  const server = http.createServer(async (req, res) => {
    const sid = req.headers['mcp-session-id']
    if (req.method === 'DELETE') {
      if (deleteColgado) return // simular nginx que no contesta; el cliente debe cerrar igual
      const s = sesiones.get(sid)
      for (const stream of s?.streams ?? []) stream.end()
      for (const p of s?.polls ?? []) { clearTimeout(p.timer); p.res.end() }
      sesiones.delete(sid); cerradas.push(sid)
      res.writeHead(200); res.end(); return
    }
    if (req.method === 'GET') {
      const s = sesiones.get(sid)
      if (!s) { res.writeHead(404); res.end(); return }
      gets++
      res.writeHead(200, { 'content-type': 'text/event-stream' }); res.flushHeaders()
      s.streams.add(res)
      res.on('close', () => s.streams.delete(res))
      return
    }
    let raw = ''
    for await (const chunk of req) raw += chunk
    const body = JSON.parse(raw)
    if (body.method === 'initialize') {
      const id = randomUUID()
      sesiones.set(id, { streams: new Set(), polls: new Set() }); abiertas.push(id)
      maxVivas = Math.max(maxVivas, sesiones.size)
      res.setHeader('mcp-session-id', id)
      responder(res, body.id, { protocolVersion: body.params.protocolVersion,
        serverInfo: { name: 'menx-test', version: '1.0' }, capabilities: { tools: {} } })
      return
    }
    if (body.method?.startsWith('notifications/')) { res.writeHead(202); res.end(); return }
    if (!sesiones.has(sid)) { res.writeHead(404); res.end(); return }
    const tool = body.params?.name, a = body.params?.arguments ?? {}
    if (tool === 'registro_ver' && fallo503) {
      fallo503 = false; res.writeHead(503); res.end('Service Temporarily Unavailable'); return
    }
    const ok = (data) => responder(res, body.id, { content: [{ type: 'text', text: JSON.stringify(data) }] })
    if (tool === 'registro_ver') return ok([{ nombre: 'prueba', hostname: 'prueba', tipo: 'pc' }])
    if (tool === 'mis_canales') return ok([{ nombre: 'canal-menx-trabajo' }])
    if (tool === 'unirse_canal') return responder(res, body.id, {
      isError: true, content: [{ type: 'text', text: 'no existe el canal' }],
    })
    if (tool === 'confirmar_entrega') {
      confirmadas.push(a)
      while (pendientes[0]?.seq <= a.hasta) pendientes.shift()
      return ok({ ok: true })
    }
    if (tool === 'enviar_mensaje') { acuses.push(a); return ok({ seq: 90 }) }
    if (tool === 'recibir_de_todos') {
      polls++
      assert.equal(a.marcar, false, 'no dar por leído al consultar')
      const s = sesiones.get(sid)
      const p = { res, timer: null, enviar: () => {
        clearTimeout(p.timer); s.polls.delete(p)
        ok({ canales: pendientes.length ? [{ canal: 'canal-menx-trabajo', tags: ['tipo:worker'],
          miembros: 2, hasta: pendientes.at(-1).seq, mensajes: [...pendientes] }] : [] })
      } }
      s.polls.add(p)
      p.timer = setTimeout(p.enviar, pendientes.length ? 10 : a.espera * 1000)
      res.on('close', () => { clearTimeout(p.timer); s.polls.delete(p) })
      return
    }
    ok({})
  })
  server.on('connection', (s) => { sockets.add(s); s.on('close', () => sockets.delete(s)) })
  await new Promise((resolve) => server.listen(0, '127.0.0.1', resolve))
  const fakeCli = join(dir, 'cola.mjs'), registro = join(dir, 'cola.jsonl')
  writeFileSync(fakeCli, `
    import {appendFileSync, existsSync} from 'node:fs';
    const args=process.argv.slice(2);
    const texto=args[args.indexOf('--message')+1];
    const fallo=existsSync(process.env.FALLO_COLA) && texto.includes('segundo');
    appendFileSync(process.env.REGISTRO_COLA, JSON.stringify({args, fallo, pid:process.pid})+'\\n');
    if(fallo) process.exit(3);
    if(existsSync(process.env.COLA_COLGADA)) await new Promise(()=>setInterval(()=>{},1000));
  `)
  const clientes = []
  async function abrir(codex = true, session = randomUUID()) {
    const env = { ...process.env, MEMORY_BASE_URL: `http://127.0.0.1:${server.address().port}/mcp`,
      MEMORY_APIKEY: 'test-only', MENX_CANAL_DIR: dir, MENX_CODEX_CLI: fakeCli,
      REGISTRO_COLA: registro, FALLO_COLA: join(dir, 'fallar'), COLA_COLGADA: join(dir, 'colgar') }
    for (const key of ['CODEX_THREAD_ID', 'CODEX_SESSION_ID', 'CLAUDE_CODE_SESSION_ID', 'CANAL_AGENTE', 'MENX_CLIENT']) delete env[key]
    if (session) env[codex ? 'CODEX_THREAD_ID' : 'CLAUDE_CODE_SESSION_ID'] = session
    const client = new Client({ name: 'test', version: '1' })
    const transport = new StdioClientTransport({ command: process.execPath, args: [codex ? CODEX : PUENTE], env, stderr: 'pipe' })
    let stderr = ''
    transport.stderr.on('data', (data) => { stderr += data })
    await client.connect(transport)
    const c = { client, transport, session, eventos: [], log: () => stderr,
      call: async (name, args = {}) => {
        const r = await client.callTool({ name, arguments: args })
        return { error: !!r.isError, data: r.isError ? r.content[0].text : JSON.parse(r.content[0].text) }
      } }
    client.fallbackNotificationHandler = async (n) => c.eventos.push(n)
    clientes.push(c)
    return c
  }
  t.after(async () => {
    for (const c of clientes) await c.client.close()
    server.closeAllConnections()
    await new Promise((resolve) => server.close(resolve))
    assert.equal(dirname(resolve(dir)), resolve(tmpdir()))
    assert.ok(basename(dir).startsWith('menx-codex-test-'))
    rmSync(dir, { recursive: true, force: true })
  })
  return { dir, abrir, sesiones, abiertas, cerradas, confirmadas, acuses,
    cola: () => existsSync(registro) ? readFileSync(registro, 'utf8').trim().split('\n').filter(Boolean).map(JSON.parse) : [],
    stats: () => ({ maxVivas, gets, polls, sockets: sockets.size }),
    fallo503: () => { fallo503 = true }, deleteColgado: () => { deleteColgado = true },
    poner: (...mensajes) => {
      pendientes.push(...mensajes)
      for (const s of sesiones.values()) for (const p of [...s.polls]) p.enviar()
    },
  }
}

const mensaje = (seq, texto = 'hola') => ({ seq, texto, de: 'agt-prueba-menx-otro', para: AGENTE, acuse: false })

test('Claude conserva push, errores de negocio reutilizan sesión y cerrar termina SSE', async (t) => {
  const h = await entorno(t), c = await h.abrir(false)
  assert.ok(c.client.getServerCapabilities().experimental['claude/channel'])
  assert.equal((await c.call('canal_identificarse', { agente: AGENTE })).error, false)
  await hasta(() => h.stats().polls > 0)
  for (let i = 0; i < 3; i++) {
    const r = await c.call('canal_unirse', { canal: 'inexistente' })
    assert.ok(r.error); assert.match(r.data, /no existe/)
  }
  assert.equal(h.abiertas.length, 1)
  h.poner(mensaje(1))
  await hasta(() => h.confirmadas.length && h.acuses.length)
  assert.equal(c.eventos[0].method, 'notifications/claude/channel')
  assert.equal(c.eventos[0].params.content, 'hola')
  assert.equal(h.acuses.length, 1)
  assert.match(h.acuses[0].texto, /lo estoy procesando/)
  await c.client.close()
  await hasta(() => h.cerradas.length === 1)
  assert.equal(h.sesiones.size, 0)
})

test('Codex: sesión explícita, cola fallida no confirma, reintenta sin duplicar el primer mensaje', async (t) => {
  const h = await entorno(t), c = await h.abrir(true, null)
  assert.equal(c.client.getServerCapabilities().experimental, undefined)
  assert.equal((await c.call('canal_estado')).data.sesion, null)
  assert.ok((await c.call('canal_identificarse', { agente: AGENTE })).error)
  await pausa(1100)
  assert.equal(h.stats().polls, 0)
  const sesion = randomUUID()
  assert.equal((await c.call('canal_identificarse', { agente: AGENTE, sesion_codex: sesion })).error, false)
  assert.ok((await c.call('canal_identificarse', { agente: AGENTE, sesion_codex: randomUUID() })).error)
  await hasta(() => h.stats().polls > 0)
  writeFileSync(join(h.dir, 'fallar'), '')
  h.poner(mensaje(1, 'primero: " & $(nunca-ejecutar) `dato`'), mensaje(2, 'segundo'))
  await hasta(() => h.cola().some((x) => x.fallo))
  assert.equal(h.confirmadas.length, 0)
  assert.equal(h.acuses.length, 0)
  rmSync(join(h.dir, 'fallar'))
  await hasta(() => h.confirmadas.length && h.acuses.length)
  const cola = h.cola()
  assert.equal(cola.filter((x) => x.args.join(' ').includes('primero')).length, 1)
  assert.equal(cola.filter((x) => !x.fallo).length, 2)
  assert.equal(cola[0].args[cola[0].args.indexOf('--thread') + 1], sesion)
  assert.ok(cola[0].args.includes('--resume'))
  assert.match(h.acuses[0].texto, /en cola de Codex/)
  assert.equal(c.eventos.length, 0)
  h.poner(mensaje(3, 'informe'.repeat(5000)), { ...mensaje(4, 'acuse de otro agente'), acuse: true })
  await hasta(() => h.confirmadas.length >= 2 && h.cola().filter((x) => !x.fallo).length === 4)
  const larga = h.cola().find((x) => x.args.join(' ').includes('content_file'))
  const texto = larga.args[larga.args.indexOf('--message') + 1]
  const referencia = JSON.parse(texto.slice(texto.indexOf('\n') + 1))
  const completo = readFileSync(referencia.content_file, 'utf8')
  assert.equal(JSON.parse(completo).content, 'informe'.repeat(5000))
  assert.equal(createHash('sha256').update(completo).digest('hex'), referencia.sha256)
  await hasta(() => h.acuses.length === 2)
  assert.equal(h.acuses.length, 2, 'el acuse entrante no se acusa')
  await c.client.close()
  await hasta(() => h.cerradas.length === 1)
  // Reconectar la MISMA conversación recupera la identidad; otra sesión no.
  const otra = await h.abrir(true)
  assert.equal((await otra.call('canal_estado')).data.agente, null)
  await otra.client.close()
  const recuperada = await h.abrir(true, sesion)
  assert.equal((await recuperada.call('canal_estado')).data.agente, AGENTE)
})

test('solo la instancia que tomó el buzón entrega al volver de un long-poll', async (t) => {
  const h = await entorno(t), a = await h.abrir(), b = await h.abrir()
  await a.call('canal_identificarse', { agente: AGENTE })
  await hasta(() => h.stats().polls === 1)
  await b.call('canal_identificarse', { agente: AGENTE })
  await hasta(() => h.stats().polls === 2)
  h.poner(mensaje(1, 'destino único'))
  await hasta(() => h.confirmadas.length > 0)
  const entregas = h.cola().filter((x) => x.args.join(' ').includes('destino único'))
  assert.equal(entregas.length, 1)
  assert.equal(entregas[0].args[entregas[0].args.indexOf('--thread') + 1], b.session)
})

test('red 503 cierra la sesión anterior antes de abrir otra', async (t) => {
  const h = await entorno(t), c = await h.abrir()
  await c.call('canal_estado')
  h.fallo503()
  const r = await c.call('canal_registro_ver', { clase: 'equipo' })
  assert.equal(r.error, false)
  assert.equal(h.abiertas.length, 2)
  assert.equal(h.cerradas.length, 1)
  assert.equal(h.stats().maxVivas, 1)
  await c.client.close()
  await hasta(() => h.cerradas.length === 2)
})

test('DELETE colgado no deja al proceso ni su socket SSE vivos', async (t) => {
  const h = await entorno(t), c = await h.abrir()
  await c.call('canal_estado')
  await hasta(() => h.stats().gets === 1)
  h.deleteColgado()
  await c.client.close()
  await hasta(() => h.stats().sockets === 0)
})

test('cerrar el MCP cancela un proceso queue colgado sin confirmar el mensaje', async (t) => {
  const h = await entorno(t), c = await h.abrir()
  await c.call('canal_identificarse', { agente: AGENTE })
  await hasta(() => h.stats().polls === 1)
  writeFileSync(join(h.dir, 'colgar'), '')
  h.poner(mensaje(1))
  await hasta(() => h.cola().length === 1)
  const pid = h.cola()[0].pid
  const vivo = () => { try { process.kill(pid, 0); return true } catch { return false } }
  t.after(() => { if (vivo()) process.kill(pid) })
  assert.ok(vivo())
  await c.client.close()
  await hasta(() => !vivo())
  assert.equal(h.confirmadas.length, 0)
})

test('65 segundos de escucha no reciclan por el timeout de 60 del SDK', { timeout: 80000 }, async (t) => {
  const h = await entorno(t), c = await h.abrir()
  await c.call('canal_identificarse', { agente: AGENTE })
  await hasta(() => h.stats().polls === 1)
  await pausa(65000)
  assert.equal(h.abiertas.length, 1, c.log())
  assert.equal(h.stats().polls, 1, 'la misma llamada sigue esperando después de 60s')
  assert.equal(h.stats().gets, 1)
  await c.client.close()
  await hasta(() => h.cerradas.length === 1)
  assert.equal(h.sesiones.size, 0)
})
