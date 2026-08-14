#!/usr/bin/env bash
# Corre las pruebas herméticas contra un Qdrant desechable.
#
# No tocan producción ni necesitan apikey: levantan su propio Qdrant en un puerto
# aparte, lo usan y lo tiran. Se pueden correr cuantas veces haga falta.
#
#   ./pruebas/correr.sh
#
# Las de punta a punta (e2e_*.mjs) van aparte porque sí necesitan un hub real:
# ver README.md.
set -u

PUERTO="${QDRANT_PUERTO:-6399}"
NOMBRE="menx-pruebas-qdrant"
AQUI="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$AQUI/.."

echo "levantando Qdrant desechable en :$PUERTO"
docker rm -f "$NOMBRE" >/dev/null 2>&1
docker run -d --name "$NOMBRE" -p "$PUERTO:6333" qdrant/qdrant:latest >/dev/null
trap 'docker rm -f "$NOMBRE" >/dev/null 2>&1' EXIT

# Esperar a que responda en vez de dormir a ojo: en una máquina lenta 5 s no bastan
# y la primera prueba falla por un motivo que no tiene nada que ver con el código.
for _ in $(seq 30); do
  curl -sf "http://127.0.0.1:$PUERTO/healthz" >/dev/null 2>&1 && break
  sleep 1
done

export QDRANT_URL="http://127.0.0.1:$PUERTO"
export EMBEDDINGS_ENABLED=false

fallos=0
for f in pruebas/test_*.py; do
  printf '%-34s ' "$(basename "$f")"
  if salida="$(python "$f" 2>&1)"; then
    echo "OK"
  else
    echo "FALLA"
    echo "$salida" | sed 's/^/    /'
    fallos=$((fallos + 1))
  fi
done

echo
if [ "$fallos" -eq 0 ]; then
  echo "todo en verde"
else
  echo "$fallos archivo(s) con fallos"
fi
exit "$fallos"
