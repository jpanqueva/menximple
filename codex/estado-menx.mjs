#!/usr/bin/env node
// Monitor local: no abre sesiones MCP, sockets, ni conexiones HTTP.
import { readFileSync } from 'node:fs'
import { homedir } from 'node:os'
import { join, resolve } from 'node:path'
import { fileURLToPath } from 'node:url'

function leer(ruta) {
  try {
    const datos = JSON.parse(readFileSync(ruta, 'utf8'))
    if (!datos || typeof datos !== 'object' || Array.isArray(datos)) throw new Error('estado invalido')
    return { datos }
  }
  catch (e) { return { datos: {}, error: e.code === 'ENOENT' ? null : 'estado local ilegible; reintentando' } }
}
const limpio = (s) => String(s ?? '').replace(/[\x00-\x1f\x7f]/g, ' ')
const vivo = (pid) => {
  if (!Number.isInteger(pid) || pid <= 0) return false
  try { process.kill(pid, 0); return true } catch { return false }
}

export function resumir(sesion, d, cerrojos, version, ahora = Date.now()) {
  const activo = vivo(d.pid)
  const consumidor = cerrojos[d.agente] === d.pid
  const hub = d.hub ?? {}
  const minutos = hub.ok ? Math.max(0, Math.floor((ahora - hub.ok) / 60000)) : null
  return {
    sesion, agente: limpio(d.agente), equipo: limpio(d.equipo || d.hostname || '?'),
    estado: !activo ? 'SIN PUENTE' : !consumidor ? 'OTRA INSTANCIA' : 'PUENTE ACTIVO',
    canales: Array.isArray(d.canales) ? d.canales.map(limpio) : null,
    version: limpio(d.version || '?'),
    reiniciar: !!version && version !== d.version,
    hub: hub.error ? `ERROR: ${limpio(hub.error)}` : minutos === null ? 'sin comprobar'
      : minutos > 6 ? `sin respuesta reciente (${minutos} min)` : `ultima respuesta hace ${minutos} min`,
  }
}

export function estado({ dir = process.env.MENX_CANAL_DIR || join(homedir(), '.menx-canal'), sesion } = {}) {
  const identidades = leer(join(dir, 'identidades-codex.json'))
  const cerrojos = leer(join(dir, 'consumidor.json'))
  let version = null
  try {
    version = /const VERSION = '([^']+)'/.exec(readFileSync(
      fileURLToPath(new URL('../canal/menx-canal.mjs', import.meta.url)), 'utf8'))?.[1]
  } catch { /* se puede ejecutar el monitor aunque el puente no esté en disco */ }
  const filas = Object.entries(identidades.datos)
    .filter(([id, d]) => (!sesion || id === sesion) && d?.agente)
    .sort(([, a], [, b]) => (b.ts ?? 0) - (a.ts ?? 0))
    .map(([id, d]) => resumir(id, d, cerrojos.datos, version))
  return { sesion: sesion || null, error: identidades.error || cerrojos.error || null, filas }
}

export function dibujar(s) {
  const lineas = ['MENX / Codex (estado local; Ctrl+C para salir del monitor)']
  if (s.error) lineas.push(s.error)
  if (!s.filas.length) lineas.push(s.sesion
    ? `Sin identidad registrada para la sesion ${limpio(s.sesion)}. Usa canal_identificarse en Codex.`
    : 'Sin identidades de Codex registradas. Usa canal_identificarse en tu conversacion.')
  for (const f of s.filas) {
    lineas.push('', `${f.estado} | ${f.agente} | equipo ${f.equipo}`,
      `Sesion: ${limpio(f.sesion)}`,
      `Canales: ${f.canales === null ? 'sin comprobar' : f.canales.length ? f.canales.join(', ') : 'ninguno'}`,
      `Hub: ${f.hub} | puente ${f.version}${f.reiniciar ? ' | REINICIAR (version en disco diferente)' : ''}`)
  }
  return lineas.join('\n')
}

if (process.argv[1] && resolve(process.argv[1]) === fileURLToPath(import.meta.url)) {
  const args = process.argv.slice(2)
  const sesionIndex = args.indexOf('--sesion')
  if (sesionIndex >= 0 && (!args[sesionIndex + 1] || args[sesionIndex + 1].startsWith('--'))) {
    process.stderr.write('Uso: node codex/estado-menx.mjs [--sesion UUID] [--watch] [--json]\n')
    process.exit(1)
  }
  const sesion = sesionIndex >= 0 ? args[sesionIndex + 1]
    : process.env.CODEX_THREAD_ID || process.env.CODEX_SESSION_ID
  let anterior
  const pintar = () => {
    const s = estado({ sesion })
    const texto = args.includes('--json') ? JSON.stringify(s, null, 2) : dibujar(s)
    if (texto !== anterior) {
      if (args.includes('--watch') && process.stdout.isTTY) process.stdout.write('\x1b[2J\x1b[H')
      process.stdout.write(texto + '\n')
      anterior = texto
    }
  }
  pintar()
  if (args.includes('--watch')) setInterval(pintar, 2000)
}
