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
| `test_canales_pool.py` | 60 esperas colgadas (más que los 40 hilos del pool) no bloquean una llamada trivial, y siguen entregando. Levanta el hub de verdad: tarda ~2 min |
| `test_archivos.py` | subir con el cliente real y abrir el link, cabeceras (sandbox, referrer), límites y cuota, nombres con ruta, aislamiento y borrado, vencimiento |

### Con las dependencias de producción

`correr.sh` usa el Python de tu máquina, que puede tener otra versión de FastMCP.
Para probar con exactamente la de la imagen (`requirements.txt`, fijada):

```bash
docker build -f pruebas/Dockerfile.pruebas -t menx-pruebas .
docker network create menx-pruebas-red
docker run -d --name menx-pruebas-qdrant --network menx-pruebas-red qdrant/qdrant:latest
docker run --rm --network menx-pruebas-red -v "$PWD:/app" -w /app -e PYTHONPATH=/app   -e QDRANT_URL=http://menx-pruebas-qdrant:6333 menx-pruebas python pruebas/test_canales_pool.py
```

## De punta a punta — necesitan un hub real

```bash
export MEMORY_BASE_URL="https://tu-hub/xxxx/api"
export MEMORY_APIKEY="<una apikey de pruebas, NO la de trabajo>"
cd canal && npm install && cd ..
node pruebas/e2e_identidad.mjs
node pruebas/e2e_acuse.mjs
node pruebas/e2e_concurrencia.mjs
node pruebas/e2e_sesiones.mjs
```

Levantan puentes de verdad como procesos aparte —igual que haría Claude Code— y
hablan con un hub real. Crean canales `e2e-*` y los dejan; bórralos con
`borrar_canal` si molestan.

**Usa una apikey de pruebas.** Escriben en el hub al que apuntes.

| archivo | qué cubre |
|---|---|
| `e2e_identidad.mjs` | dos agentes en la misma máquina con identidades distintas, y que ninguno reciba lo suyo propio |
| `e2e_acuse.mjs` | acuse automático, y que un acuse no se acuse (si no, dos agentes se saludan para siempre) |
| `e2e_sesiones.mjs` | que el puente no deje sesiones vivas en el hub: ni por errores de tool, ni por esperar en silencio más de 60 s, ni al salir. Pone un proxy que cuenta sesiones abiertas/cerradas. Tarda ~90 s |
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
