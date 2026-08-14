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
import { readFileSync } from 'node:fs'
import { homedir } from 'node:os'
import { join } from 'node:path'

const ARCHIVO = join(process.env.MENX_CANAL_DIR || join(homedir(), '.menx-canal'),
                     'identidades.json')

let entrada = ''
process.stdin.on('data', (d) => { entrada += d })
process.stdin.on('end', () => {
  let sesion = ''
  let modelo = ''
  let dir = ''
  try {
    const j = JSON.parse(entrada || '{}')
    sesion = j.session_id ?? ''
    modelo = j.model?.display_name ?? ''
    dir = (j.workspace?.current_dir ?? j.cwd ?? '').split(/[\\/]/).pop() ?? ''
  } catch { /* sin json utilizable: se pinta lo que se pueda */ }

  let menx = 'menx: sin identidad'
  try {
    const d = JSON.parse(readFileSync(ARCHIVO, 'utf8'))[sesion]
    if (d?.agente) {
      const n = d.canales?.length ?? 0
      menx = `menx: ${d.agente}` +
             (n ? ` · ${n} canal${n > 1 ? 'es' : ''}: ${d.canales.join(', ')}` : ' · sin canales')
    }
  } catch { /* sin archivo todavía: queda "sin identidad", que es la verdad */ }

  process.stdout.write([dir, modelo, menx].filter(Boolean).join('  |  '))
})
