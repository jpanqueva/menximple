#!/usr/bin/env node
/**
 * Barra de estado: quién soy en los canales de menx.
 *
 * Claude Code ejecuta esto y pinta lo que salga por stdout, pasándole el JSON de
 * la sesión por stdin. De ahí solo hace falta `session_id`, que es la misma clave
 * con la que el puente guarda la identidad.
 *
 * Existe porque la identidad del canal es invisible: si un agente se cree
 * identificado y no lo está, deja de recibir mensajes y nada se lo dice. En la
 * barra se ve de un vistazo, y de paso resuelve tener varios agentes abiertos en
 * la misma máquina sin saber cuál es cuál.
 *
 * NO sale a la red: la barra se repinta muy seguido y una llamada al hub por
 * render sería absurda. Lee solo el archivo local que el puente ya mantiene.
 *
 * Instalar en ~/.claude/settings.json:
 *   "statusLine": { "type": "command", "command": "node RUTA/statusline-menx.mjs" }
 */
import { readFileSync, readdirSync, existsSync } from 'node:fs'
import { homedir } from 'node:os'
import { join, dirname } from 'node:path'
import { fileURLToPath } from 'node:url'

// --- versiones: ¿esta consola corre lo que hay en el disco? --------------- //
//
// Cada máquina tiene su copia del puente, y una copia vieja fugaba conexiones
// durante días sin que nadie lo viera (Azure y el PC de Transfiriendo, sep-2026).
// La barra compara la versión del puente QUE CORRE (la escribe el proceso en el
// archivo de identidades) con la del archivo en disco (que `git pull` actualiza):
// si difieren, hay que reiniciar Claude Code; si no hay versión, el puente es
// anterior a esto y hay que actualizar el repo.
const AQUI = dirname(fileURLToPath(import.meta.url))
function versionEnDisco() {
  try {
    const m = /const VERSION = '([^']+)'/.exec(readFileSync(join(AQUI, 'menx-canal.mjs'), 'utf8'))
    return m?.[1] ?? null
  } catch { return null }
}
// El selector se instala con pip/pipx: la versión está en su dist-info. Se
// buscan los sitios habituales sin ejecutar nada (la barra corre a cada rato).
function versionSelector() {
  const home = homedir()
  const candidatos = [
    join(home, '.local', 'pipx', 'venvs', 'menximple', 'Lib', 'site-packages'),
    join(process.env.LOCALAPPDATA || '', 'pipx', 'venvs', 'menximple', 'Lib', 'site-packages'),
    join(process.env.LOCALAPPDATA || '', 'Programs', 'Python'),
    join(home, '.local', 'lib'),
    '/usr/local/lib', '/usr/lib',
  ]
  const vistos = new Set()
  const busca = (dir, prof) => {
    if (prof < 0 || !dir || vistos.has(dir) || !existsSync(dir)) return null
    vistos.add(dir)
    let hijos = []
    try { hijos = readdirSync(dir, { withFileTypes: true }) } catch { return null }
    for (const h of hijos) {
      if (!h.isDirectory()) continue
      const m = /^menximple-([0-9][^-]*)\.dist-info$/i.exec(h.name)
      if (m) return m[1]
    }
    for (const h of hijos) {
      if (!h.isDirectory()) continue
      if (/^(python3?\.?[0-9]*|Python[0-9]+|site-packages|Lib|lib|venvs|menximple)$/i.test(h.name)) {
        const v = busca(join(dir, h.name), prof - 1); if (v) return v
      }
    }
    return null
  }
  for (const c of candidatos) { const v = busca(c, 4); if (v) return v }
  return null
}

const DIR = process.env.MENX_CANAL_DIR || join(homedir(), '.menx-canal')
const ARCHIVO = join(DIR, 'identidades.json')
const CERROJO = join(DIR, 'consumidor.json')   // lo escribe el puente que escucha

let entrada = ''
process.stdin.on('data', (d) => { entrada += d })
process.stdin.on('end', () => {
  let sesion = ''
  let modelo = ''
  let dir = ''
  let dirCompleto = ''
  try {
    const j = JSON.parse(entrada || '{}')
    sesion = j.session_id ?? ''
    modelo = j.model?.display_name ?? ''
    dirCompleto = j.workspace?.current_dir ?? j.cwd ?? ''
    dir = dirCompleto.split(/[\\/]/).filter(Boolean).pop() ?? ''
  } catch { /* sin json utilizable: se pinta lo que se pueda */ }

  let menx = 'menx: sin identidad'
  let versiones = ''
  try {
    const todas = JSON.parse(readFileSync(ARCHIVO, 'utf8'))
    // Primero por sesión; si no, la más reciente de ESTA carpeta.
    //
    // El puente guarda contra el CLAUDE_CODE_SESSION_ID que recibe al arrancar, y
    // la barra recibe el `session_id` del JSON de Claude Code. Se dio por hecho que
    // eran el mismo y no siempre lo son —tras un /resume la barra decía "sin
    // identidad" con el puente perfectamente identificado—, así que la carpeta
    // sirve de respaldo.
    const d = todas[sesion] ?? Object.values(todas)
      .filter((v) => v?.cwd && v.cwd === dirCompleto && v?.agente)
      .sort((a, b) => (b.ts ?? 0) - (a.ts ?? 0))[0]

    // Pero el respaldo NO prueba que haya un puente escuchando ahora: puede ser el
    // rastro de una sesión anterior. Y una barra que dice "identificado" cuando el
    // puente no lo está es peor que no tenerla — es justo el fallo callado que esta
    // barra existe para delatar; paso una vez y costo una tanda de mensajes.
    // El cerrojo del consumidor sí lo prueba: lo escribe el puente al quedarse con
    // el turno, y su pid tiene que seguir vivo.
    let escuchando = false
    if (d?.agente) {
      try {
        const pid = JSON.parse(readFileSync(CERROJO, 'utf8'))[d.agente]
        process.kill(pid, 0)          // lanza si el proceso ya no existe
        escuchando = true
      } catch { /* sin cerrojo o con pid muerto: no hay nadie oyendo */ }
    }
    if (d?.agente && !escuchando) {
      process.stdout.write([dir, modelo,
        `menx: SIN ESCUCHAR (identifícate como ${d.agente})`].filter(Boolean).join('  |  '))
      return
    }
    if (d) {
      // Los tres MCP, con su versión, y si el puente que corre es el del disco.
      const disco = versionEnDisco()
      let puente
      // Sin versión en el registro: el puente que corre es anterior a esto. Si el
      // disco ya tiene la nueva, solo falta reiniciar; si tampoco, actualizar el repo.
      let hub = null
      if (!d.version) puente = disco ? `canal ✗ REINICIA Claude Code (en disco ${disco})` : 'canal ✗ ACTUALIZA el repo'
      else if (disco && disco !== d.version) puente = `canal ${d.version} ✗ REINICIA Claude Code (en disco ${disco})`
      else puente = `canal ${d.version} ✓`
      if (d.version) {
        const h = d.hub ?? {}
        const hace = h.ok ? (Date.now() - h.ok) / 60000 : Infinity
        hub = h.error ? `hub ✗ ${h.error.slice(0, 40)}`
            : hace < 6 ? `hub ${h.version ?? ''} ✓`.replace('  ', ' ')
            : h.ok ? `hub ✗ sin respuesta hace ${Math.round(hace)} min` : 'hub ?'
      }
      const sel = versionSelector()
      versiones = [puente, hub, sel ? `selector ${sel}` : 'selector ✗ no instalado'].filter(Boolean).join(' · ')
    }
    if (d?.agente) {
      menx = `menx: ${d.agente}`
      // Distinguir "sé que no tiene canales" de "no lo sé todavía": un registro
      // viejo no trae la lista, y decir "sin canales" ahí sería mentir.
      if (Array.isArray(d.canales)) {
        const cs = d.canales
        if (!cs.length) {
          menx += ' · sin canales'
        } else {
          // Con muchos canales la barra se come la línea: se nombran los 3
          // primeros y el resto se cuenta.
          const muestra = cs.slice(0, 3).join(', ')
          const resto = cs.length - 3
          menx += ` · ${cs.length} canal${cs.length > 1 ? 'es' : ''}: ` +
                  muestra + (resto > 0 ? ` +${resto}` : '')
        }
      }
    }
  } catch { /* sin archivo todavía: queda "sin identidad", que es la verdad */ }

  process.stdout.write([dir, modelo, menx, versiones].filter(Boolean).join('  |  '))
})
