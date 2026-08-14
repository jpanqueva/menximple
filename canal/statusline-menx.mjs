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

  process.stdout.write([dir, modelo, menx].filter(Boolean).join('  |  '))
})
