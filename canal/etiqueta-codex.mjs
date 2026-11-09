// Texto para el campo thread-name de la barra nativa de Codex.
export function etiquetaCodex(agente, canales) {
  const nombres = canales.map((c) => typeof c === 'string' ? c : c.nombre)
  const lista = nombres.length
    ? `${nombres.length} canal${nombres.length === 1 ? '' : 'es'}: ${nombres.join(', ')}`
    : 'sin canales'
  return `MENX: ${agente} | ${lista}`
}
