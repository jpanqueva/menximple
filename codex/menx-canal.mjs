#!/usr/bin/env node
// Entrada separada: Claude conserva su transporte y su identidad de sesión.
process.env.MENX_CLIENT = 'codex'
await import('../canal/menx-canal.mjs')
