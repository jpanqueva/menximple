# menximple

Hub de **memoria a largo plazo** para agentes de IA, servido por **MCP sobre HTTP**.
Almacén único **Qdrant** (documentos en payload + vectores del `resumen`).
Multi-cuenta con **apikey por cuenta** (memorias privadas y aisladas).

> **¿Te lo compartieron para usarlo?** Deja Claude Code con memoria en todas tus
> sesiones; solo tienes que pedir la URL y tu apikey:
> **[Windows](docs/INSTALAR-EN-WINDOWS.md)** · **[Ubuntu](docs/INSTALAR-EN-UBUNTU.md)**.
> Luego **[USO.md](USO.md)** para saber cómo se usa.
>
> Un agente al que le digan *"lee este repo e instala"* tiene ahí todo lo que
> necesita salvo la URL y la apikey, que **no están en el repo a propósito**.
>

> Diseño y decisiones: `ARQUITECTURA.md` · Investigación previa: `investigacion/INFORME-ESTADO-DEL-ARTE.md`

## Modelo
- **Carpetas**: organización libre (proyectos/subproyectos/como se quiera).
- **Entradas** (la memoria): `titulo`, `resumen` (lo que se busca), `contexto`,
  `tipo` = `credencial|skill|general|historical`, `tags`, y un **consecutivo**
  (`#4`) para pedirla por número. Editables y versionadas; borrar archiva.
- **Cuentas**: cada una con su apikey; sus memorias son privadas (aislamiento fail-closed).

## Dos servidores MCP
- **`menximple`** — el hub, por HTTP, en el servidor.
- **`menximple-selector`** — local, en la máquina del usuario: es el único que
  puede abrir el selector visual en su escritorio. El hub corre en un contenedor
  y no tiene pantalla donde dibujar.

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
Hub: `arbol`, `listar`, `buscar`, `buscar_relacionadas`, `listar_recientes`,
`obtener_entrada`, `cargar_contexto`, `ver_historial`, `crear_carpeta`,
`editar_carpeta`, `crear_entrada`, `editar_entrada`, `borrar_entrada`,
`borrar_carpeta`, `restaurar_entrada`, `restaurar_carpeta`, y (admin)
`crear_cuenta`, `listar_cuentas`.

Selector local: `abrir_selector`, `recoger_seleccion`, `cerrar_selector`,
`cargar_memorias`.

Qué hace cada una y cuándo usarla: **[USO.md](USO.md)**.

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
- **No cifra en reposo.** Las memorias de tipo `credencial` deberían guardar la
  referencia, no el secreto. Endurecimiento (cifrado, auditoría) diferido.
- Embeddings apagados a propósito: encenderlos hoy rompería la búsqueda por
  número y por prefijo, porque el camino vectorial sustituye al léxico en vez de
  sumarse. Tendría que ser híbrido, con mínimo de parecido.
- El selector es de solo lectura: renombrar, mover y borrar solo por tools.
