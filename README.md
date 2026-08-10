# menximple

Hub de **memoria a largo plazo** para agentes de IA, servido por **MCP sobre HTTP**.
Almacén único **Qdrant** (documentos en payload + vectores del `resumen`).
Multi-cuenta con **apikey por cuenta** (memorias privadas y aisladas).

> Diseño y decisiones: `ARQUITECTURA.md` · Investigación previa: `investigacion/INFORME-ESTADO-DEL-ARTE.md`

## Modelo
- **Carpetas**: organización libre (proyectos/subproyectos/como se quiera).
- **Entradas** (la memoria): `titulo`, `resumen` (se indexa/embebe), `contexto`,
  `tipo` = `credencial|skill|general|historical`, `tags`. Editables y versionadas.
- **Cuentas**: cada una con su apikey; sus memorias son privadas (aislamiento fail-closed).

## Correr con Docker (todo containerizado)
```bash
cp .env.example .env          # ajusta ADMIN_TOKEN, etc.
docker compose up -d --build  # levanta qdrant (con volumen) + api
```
El MCP queda en `http://localhost:8000/mcp`. Qdrant persiste en el volumen `qdrant_data`.

### Con embeddings (opcional)
En `.env`: `EMBEDDINGS_ENABLED=true`. En `docker-compose.yml`: `WITH_EMBEDDINGS: "true"`.
Reconstruye: `docker compose up -d --build`. El modelo se cachea en el volumen `hf_cache`.

## Autenticación
- **Cuentas** (admin): `crear_cuenta` / `listar_cuentas`. Protegidas por el header
  `X-Admin-Token` (= `ADMIN_TOKEN`). `crear_cuenta` devuelve la **apikey una sola vez**.
- **Uso normal**: cada llamada envía el header `X-API-Key: <apikey de la cuenta>`.
  La cuenta se deriva de la apikey; no se pasa como argumento.

## Tools MCP
`listar`, `crear_carpeta`, `editar_carpeta`, `crear_entrada`, `editar_entrada`,
`obtener_entrada`, `cargar_contexto`, `buscar`, `buscar_relacionadas`,
`listar_recientes`, y (admin) `crear_cuenta`, `listar_cuentas`.

## Instalación
- **Cliente (en tus consolas):** ver **[INSTALL-CLIENTE.md](INSTALL-CLIENTE.md)**
  → `pipx install "git+https://github.com/jpanqueva/menximple@main"` (comando `menximple`).
- **Servidor:** ver **[INSTALL-SERVER.md](INSTALL-SERVER.md)**
  → Docker (`docker compose up -d --build`) o pip (`menximple[server]`).

Actualizar: cliente `pipx install --force "git+https://github.com/jpanqueva/menximple@main"`;
servidor `git pull && docker compose up -d --build`.

## Sacar una versión nueva
Edita `version` en `pyproject.toml`, commit, `git tag vX.Y.Z && git push --tags`.
En las consolas: `pipx install --force "git+https://github.com/jpanqueva/menximple@main"`.

## Pendientes
- Endurecimiento de seguridad (cifrado en reposo, TLS, auditoría) — diferido.
- (Opcional) exponer el selector como MCP local además del CLI.
