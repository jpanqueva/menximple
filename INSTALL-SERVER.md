# Instalar el SERVIDOR de `menximple`

El servidor es el hub de memoria (MCP sobre HTTP) con Qdrant como único almacén.
Guarda las cuentas, carpetas y entradas. Los clientes se conectan por `MEMORY_BASE_URL`.

## Opción A — Docker (recomendada)

Requisitos: Docker + Docker Compose.

```bash
git clone https://github.com/jpanqueva/menximple.git
cd menximple
cp .env.example .env          # edita ADMIN_TOKEN (y embeddings si quieres)
docker compose up -d --build  # levanta qdrant (con volumen) + api en :8000
```
El MCP queda en `http://TU-SERVIDOR:8000/mcp`. Qdrant persiste en el volumen `qdrant_data`.
Detrás de un reverse proxy (Nginx/Caddy) para TLS en producción — ver abajo.

### Reverse proxy (Nginx)

El transporte del MCP es Streamable HTTP: las respuestas son `text/event-stream`
sin `Content-Length`. Eso tiene dos consecuencias que hay que atender o el cliente
va lento sin que se note por qué.

```nginx
location /mcp {
    proxy_pass http://127.0.0.1:8000/mcp;

    proxy_http_version 1.1;
    proxy_set_header Connection "";
    proxy_set_header Host $host;
    proxy_set_header X-Real-IP $remote_addr;
    proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
    proxy_set_header X-Forwarded-Proto $scheme;

    proxy_buffering off;          # SSE: no acumular la respuesta
    proxy_cache off;
    proxy_read_timeout 3600s;
    proxy_send_timeout 3600s;

    # El gzip_types global no incluye text/event-stream, así que hay que pedirlo aquí.
    gzip on;
    gzip_types text/event-stream application/json;
    gzip_min_length 1000;
}
```

**No pongas `chunked_transfer_encoding off;`.** Parece razonable para SSE y es la
trampa: sin `Content-Length` y sin chunked, nginx solo puede delimitar el cuerpo
**cerrando la conexión**, así que devuelve `Connection: close` aunque uvicorn haya
respondido `keep-alive`. El cliente paga handshake TCP+TLS completo en cada llamada
(~220 ms medidos contra un servidor a 110 ms de RTT).

Para comprobar que quedó bien, dos requests seguidos deben reutilizar la conexión
y traer `Content-Encoding: gzip`:

```bash
curl -s -o /dev/null -w 'tcp=%{time_connect} tls=%{time_appconnect}\n' ... \
     --next -s -o /dev/null -w 'tcp=%{time_connect} tls=%{time_appconnect}\n' ...
# el segundo debe marcar tcp=0.000 tls=0.000
```

### Actualizar
```bash
cd menximple && git pull && docker compose up -d --build
```

### Activar embeddings (opcional)
En `.env`: `EMBEDDINGS_ENABLED=true`. En `docker-compose.yml`: `WITH_EMBEDDINGS: "true"`.
Reconstruye: `docker compose up -d --build` (el modelo se cachea en el volumen `hf_cache`).

## Opción B — pip (sin Docker)

Requisitos: Python 3.10+ y un Qdrant accesible.
```bash
# Qdrant:
docker run -d -p 6333:6333 -v qdrant_data:/qdrant/storage qdrant/qdrant

# Servidor:
pip install "menximple[server] @ git+https://github.com/jpanqueva/menximple@main"
export QDRANT_URL=http://localhost:6333
export MCP_HOST=0.0.0.0 MCP_PORT=8000
export ADMIN_TOKEN="<token secreto para crear cuentas>"
menximple-server
```
Con embeddings: instala `menximple[server,embeddings]` y pon `EMBEDDINGS_ENABLED=true`.

### Actualizar
```bash
pip install --upgrade "menximple[server] @ git+https://github.com/jpanqueva/menximple@main"
# y reinicia el proceso menximple-server
```

## Crear cuentas (obtener apikeys)
Las cuentas se crean con la tool admin `crear_cuenta` (requiere el header `X-Admin-Token`
= `ADMIN_TOKEN`). Devuelve la **apikey una sola vez** — guárdala. Cada consola usa esa
apikey en `MEMORY_APIKEY`. Ver `INSTALL-CLIENTE.md`.

## Variables de entorno
| Variable | Default | Para qué |
|---|---|---|
| `MCP_HOST` / `MCP_PORT` | `0.0.0.0` / `8000` | dónde escucha el server |
| `QDRANT_URL` | `http://localhost:6333` | Qdrant (en compose: `http://qdrant:6333`) |
| `ADMIN_TOKEN` | (vacío = abierto) | protege crear/listar cuentas |
| `EMBEDDINGS_ENABLED` | `false` | activa vectores del resumen |
| `EMBEDDING_MODEL` / `EMBEDDING_DIMS` | e5-small / 384 | modelo de embeddings |
