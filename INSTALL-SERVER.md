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
Detrás de un reverse proxy (Nginx/Caddy) para TLS en producción.

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
