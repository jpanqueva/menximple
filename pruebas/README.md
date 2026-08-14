# Pruebas

Dos grupos, con costes muy distintos.

## Herméticas — corren solas

```bash
./pruebas/correr.sh
```

Levantan un **Qdrant desechable** en un puerto aparte, lo usan y lo tiran. No tocan
producción, no necesitan apikey, se pueden correr cuantas veces haga falta. Es lo
que hay que pasar antes de tocar `memory_server/`.

| archivo | qué cubre |
|---|---|
| `test_memorias.py` | carpetas por ruta, `estado`, `anexar_entrada`, alcance de búsqueda, respuesta compacta |
| `test_canales.py` | crear, dos por canal, varios canales por agente, enviar/recibir, long-poll |
| `test_canales_entrega.py` | que el creador entre solo, y que quien llega lea lo anterior |
| `test_canales_cuentas.py` | aislamiento del catálogo, borrado real, filtro de rango |

## De punta a punta — necesitan un hub real

```bash
export MEMORY_BASE_URL="https://tu-hub/xxxx/api"
export MEMORY_APIKEY="<una apikey de pruebas, NO la de trabajo>"
cd canal && npm install && cd ..
node pruebas/e2e_identidad.mjs
node pruebas/e2e_acuse.mjs
node pruebas/e2e_concurrencia.mjs
```

Levantan puentes de verdad como procesos aparte —igual que haría Claude Code— y
hablan con un hub real. Crean canales `e2e-*` y los dejan; bórralos con
`borrar_canal` si molestan.

**Usa una apikey de pruebas.** Escriben en el hub al que apuntes.

| archivo | qué cubre |
|---|---|
| `e2e_identidad.mjs` | dos agentes en la misma máquina con identidades distintas, y que ninguno reciba lo suyo propio |
| `e2e_acuse.mjs` | acuse automático, y que un acuse no se acuse (si no, dos agentes se saludan para siempre) |
| `e2e_concurrencia.mjs` | llamadas del agente mientras el bucle de escucha está colgado, que es lo que rompía la conexión al hub |

## Por qué están aquí

De los once defectos que se corrigieron el 14/08/2026, **dos los encontró una prueba
y ninguno salió de leer el código buscando defectos**:

- `enviar_mensaje` llamaba a `nuevo_id()` dos veces, así que el id del punto y el
  `_id` del payload eran distintos y **borrar por `_id` no borraba nada**. Llevaba
  ahí desde el primer día, invisible porque no existía nada que borrara. Lo cazó una
  comprobación de "no quedan mensajes huérfanos" que casi no se escribe.
- El cerrojo del consumidor comprobaba el turno solo **antes** de pedir. La espera
  dura 100 s, de sobra para que arranque otra instancia mientras está colgada, y esa
  es justo la ventana por la que entra el mensaje. La primera versión falló la prueba
  por eso.

Y dos de las que pasaron ese día **pasaban por el motivo equivocado**: una "veía solo
sus canales" cuando no había ninguno ajeno que rechazar, y otra mandaba mensajes
"seguidos" que en realidad salían con segundos entre ellos. Ninguna falló. Ninguna
probaba lo que decía.

De ahí las dos reglas al escribir una aquí: **comprobar el porqué, no solo el
resultado** —si esperas un error, mira *cuál*—, y **que la prueba no pueda pasar
vacíamente**: si el escenario no se dio (nada que rechazar, nada que agrupar), eso
es un fallo de la prueba, no un aprobado.
