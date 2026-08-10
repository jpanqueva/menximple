# MCP Memory Server — Estado del arte y decisión de arquitectura

> Investigación previa al desarrollo · 2026-08-10 · Soluciones Estratégicas de Datos SAS
> Objetivo: decidir **construir vs. adoptar**, y **si vale la pena búsqueda vectorial** o basta metadatos en Mongo.

---

## 0. Resumen ejecutivo (la decisión, en una página)

1. **No existe un "ganador" único.** El default pragmático de producción en 2026 es **mem0** (adoptar); la alternativa SQL/DB-nativa sin vector DB es **Memori** (ya soporta MongoDB); el MCP oficial de memoria es solo demo.
2. **Tu especificación describe un servidor a la medida** (gatekeeping estricto `company_id`+`project_tag`, fail-fast, secret references). Eso **ningún producto lo trae exactamente** → recomendación: **construir un servidor MCP delgado propio**, tomando `coleam00/mcp-mem0` y las tools de mem0/OpenMemory como referencia de forma.
3. **NO empezar con búsqueda vectorial.** Para unas pocas miles de memorias, un query filtrado por `company_id + project_tag` sobre un índice compuesto da **100% de recall y suele ser más rápido que un índice ANN**. Lo vectorial se agrega **después** como bolt-on, y solo si aparece un problema real de recuperación semántica.
4. **NO basar producción en el `$vectorSearch` nativo de Mongo self-hosted:** existe (sept-2025) pero está en **public preview, "no para producción", solo Linux, requiere replica set + binario `mongot`, y SSPL al llegar a GA**.
5. **Stack recomendado:** Python + **FastMCP 3.x** + transporte **Streamable HTTP** + **MongoDB** (async PyMongo) + Docker detrás de reverse proxy. Esquema **"vector-ready"** desde el día uno para que agregar vectores sea aditivo, no un rewrite.

**Camino sugerido:** construir el servidor propio, **Fase 0 = solo metadatos + full-text de Mongo**; **Fase 1 (opcional, disparada por necesidad) = Qdrant en Docker + embeddings locales (BGE-M3 para español)**.

---

## 1. Landscape open-source (construir vs. adoptar)

| Proyecto | Estrellas | Licencia | Lenguaje | Backend | Recuperación | Tools MCP | Multi-tenant | Madurez |
|---|---|---|---|---|---|---|---|---|
| MCP `server-memory` (oficial) | (monorepo) | MIT | TS | archivo JSONL | solo keyword | 9 (entidades/relaciones) | ❌ No | Demo |
| **mem0** | ~63k | Apache-2.0 | Py/TS | Qdrant+Postgres (pluggable) | híbrida vec+BM25+entidad | 4 (add/search/list/delete) | ✅ Fuerte (user/agent/run) | Alta |
| Letta (ex-MemGPT) | ~24k | Apache-2.0 | Py | Postgres+pgvector | memoria por niveles (core+archival) | consume MCP; API REST | multi-agente | Alta (pesada) |
| Graphiti/Zep | ~30k | Apache-2.0 | Py | Neo4j/FalkorDB/Neptune | **grafo temporal**+vec+BM25 | episodios/entidad/search/group | group_id | Alta (ops pesada) |
| basic-memory | ~3.6k | **AGPL-3.0** | Py | Markdown+SQLite (opt Milvus) | híbrida FT+vec | ~18 (notes/search/projects) | ✅ por-proyecto | Media-Alta |
| Qdrant MCP | ~1.5k | Apache-2.0 | Py | Qdrant | vectorial | 2 (store/find) | por-colección | Media |
| Chroma MCP | ~256 | Apache-2.0 | Py | ChromaDB | vec+FT+metadatos | colección/query | colección+meta | Media |
| **coleam00/mcp-mem0** | (template) | — | Py | Postgres/pgvector (mem0) | semántica | 3 (save/get_all/search) | vía ids de mem0 | Plantilla |
| **Memori** (GibsonAI) | ~16k | Apache-2.0 | Py/TS | **SQL: SQLite/PG/MySQL/Mongo** | estructurada+híbrida | 2 (recall/summary) | entity/process/session | Media-Alta |
| cognee | ~30k | Apache-2.0 | Py | grafo+vector+relacional | grafo+vector (pipeline ECL) | cognify/search/codify | user/tenant | Media-Alta |

**Lectura para nuestro caso (multi-empresa/multi-proyecto, self-hosted, escala modesta, datos sensibles):**

- **Adoptar mem0 (OpenMemory self-hosted)** → lo más seguro y soportado; multi-tenant real; backend Postgres+Qdrant. Costo: tokens de LLM para "extracción" de memorias + correr Qdrant. Su "magia" de extracción automática es menos predecible que un guardado explícito.
- **Adoptar Memori** → memoria como filas SQL en una DB que ya operamos (¡soporta Mongo!), sin vector DB, transparente y portable. Recall semántico difuso más débil.
- **Construir wrapper MCP propio** (forma de `coleam00/mcp-mem0`: `save_context`/`search_context` con columnas `company_id`/`project_tag`) → control total, sin paywall, sin servicio externo, y **cumple exactamente el gatekeeping estricto que pediste**. Son unos cientos de líneas.
- **Solo ir a Graphiti/Zep, Letta o cognee** si necesitáramos razonamiento temporal, agentes que auto-editan su contexto, o ingesta de un grafo de conocimiento de toda la organización. Traen mucho más peso operativo (grafo DB, runtime de agente, pipelines de extracción). **No es nuestro caso hoy.**

> **Por qué construir y no adoptar:** tu especificación exige rechazo explícito si falta `company_id`/`project_tag`, fail-fast sin try/catch que silencie, y jamás guardar secretos en texto plano. Ningún producto trae ese gatekeeping tal cual; adaptarlos cuesta casi lo mismo que un servidor delgado propio — y el propio queda sin dependencias de terceros ni "magia" impredecible.

---

## 2. ¿Vectorial o metadatos? (el punto crítico)

**La búsqueda vectorial resuelve UN solo problema:** recuperar por *significado* cuando las palabras de la consulta no coinciden con las del texto guardado (sinónimos, paráfrasis, cross-lingual). Todo lo demás —scoping, recencia, tags exactos, keywords conocidas— lo hacen mejor los índices normales.

**Señal fuerte de la industria:** en mayo-2025 **Anthropic quitó la búsqueda vectorial de Claude Code**, reemplazando el pipeline de embeddings/chunking/vector-DB por herramientas tipo grep/filesystem que el agente maneja. La tendencia 2026 es *darle al agente herramientas de recuperación + contexto "just-in-time"* en vez de embeber todo por defecto. Los vectores son una herramienta especializada, no una base obligatoria.

**Usar solo metadatos/keyword (SIN vectores) cuando —criterios de decisión:**
- La recuperación es **navegacional/estructurada**: "dame memorias de `company_id=X, project_tag=Y, tag=deploy`, más recientes primero". Trabajo de índice B-tree.
- **Corpus por-tenant pequeño** (miles, incluso decenas de miles). Índice compuesto `(company_id, project_tag)` + scan filtrado = **100% recall, sin aproximación**, y a menudo más rápido que recorrer un grafo HNSW. Montar ANN aquí es el error clásico de sobre-ingeniería.
- Las consultas traen **keywords/identificadores conocidos** (números de orden, nombres de cliente, strings de error) → **índice de texto de Mongo** (BM25) lo resuelve nativo.
- El agente **ya sabe qué busca** (puede construir un filtro) en vez de hacer recall abierto.

**Los vectores SÍ se justifican cuando:**
- Importa la **generalización semántica** (consulta y memoria usan palabras distintas para la misma idea y no puedes enumerar sinónimos).
- **Corpus grande y estable por tenant** (~10k–100k+ ítems/tenant) donde escanear todo es lento.
- **Recall abierto** ("¿qué sé que sea relevante a esta situación?") con latencia sub-segundo.
- **Cross-lingual** (guardar en español, consultar en inglés) — relevante para nosotros.

> **Regla práctica:** si no puedes señalar una consulta concreta donde las palabras del usuario NO van a coincidir con el texto guardado, **todavía no necesitas vectores.**

Nota de refuerzo (Anthropic Contextual Retrieval): el keyword/BM25 no es un fallback legacy, hace **la mitad del trabajo**; embeddings contextuales bajan fallos ~35%, sumar BM25 léxico lo lleva a ~49%, y el reranking a ~67%.

### 2.1. El `$vectorSearch` nativo de Mongo self-hosted (verificado)

**Existe fuera de Atlas — pero con salvedades que lo descartan para producción HOY:**
- Anunciado **17-sep-2025**: `$search`/`$vectorSearch` llegaron a **Community y Enterprise Server**, antes exclusivos de Atlas. Corre sobre un binario aparte **`mongot`** que sincroniza índices vía Change Streams (operar un segundo proceso junto a `mongod`).
- **Estado = PUBLIC PREVIEW, "solo para desarrollo/evaluación, no producción"** (palabras de MongoDB). Sin GA self-managed confirmado.
- Requiere **MongoDB 8.2+**, es **solo Linux** (NO macOS/Windows), y exige **replica set** (aunque sea de un nodo).
- **Licencia SSPL** al llegar a GA. Bien para self-host interno; problema si algún día se ofrece "como servicio" a terceros.

**Veredicto:** atractivo (un solo store, sin sync tax), pero **no basar producción en un preview.** El Atlas cloud Vector Search sí es GA — pero es cloud, no el Docker self-host que queremos.

### 2.2. Si algún día se necesitan vectores — comparativa self-hosted

| Opción | ¿Docker self-host gratis? | Filtrado-con-vectores | Complejidad ops | Notas |
|---|---|---|---|---|
| Atlas Vector Search | ❌ Solo cloud | Excelente | Baja (managed) | GA/producción, pero no es Docker self-host; costo Atlas |
| Mongo `$vectorSearch` (mongot) | ⚠️ Sí pero **preview/no-prod**, Linux, replica set | Bueno (paridad Atlas) | Media-Alta | El sueño "un solo store" — **aún no** |
| **Qdrant** | ✅ `docker run`, Apache-2.0 | **El mejor** — filtros dentro del HNSW | Media (servicio aparte) | Ideal para búsqueda filtrada/multi-tenant |
| **pgvector** | ✅ `CREATE EXTENSION` | Bueno (0.8+ iterative scans) | **La más baja si ya corres Postgres** | La opción "tecnología aburrida"; RLS para tenancy |
| Redis (RediSearch) | ✅ Docker | Bueno | Baja latencia; RAM a escala | Si ya usas Redis |
| Milvus | ✅ standalone | Fuerte, billion-scale | **Alta** (K8s/etcd/MinIO) | Overkill para nuestro tamaño |
| Weaviate | ✅ Docker | Híbrido nativo + tenancy | Media | Híbrido+tenancy out-of-the-box |

**Para nuestro perfil:** si Mongo sigue siendo el store documental → **Qdrant**. Si nos abrimos a consolidar → **pgvector** (un solo store, transaccional). Milvus/Weaviate/Redis: situacionales, no indicados a nuestra escala.

### 2.3. Embeddings (si se llega a esa fase)

- Volumen minúsculo: unas pocas miles de memorias < 1M tokens → embeber todo con **OpenAI `text-embedding-3-small` cuesta centavos**.
- **Pero por sensibilidad de datos (PII de clientes, datos médicos de Salud Renal), inclinarse a LOCAL:** `nomic-embed-text` (768d, corre en CPU vía Ollama) para general, **`BGE-M3` (1024d, 100+ idiomas) para español/multilingüe.**
- Dimensiones: **512–1024 es el punto dulce.** **Guardar siempre `embedding_model` + `embedding_dims` con cada vector** — no se pueden mezclar embeddings de modelos distintos; re-embeber por cambio de modelo es el principal costo de migración futuro.

---

## 3. Cómo construir el servidor MCP (para el primer commit)

**Stack:** Python + **FastMCP 3.x** (fijar el major), transporte **Streamable HTTP**, MongoDB async, Docker detrás de Nginx/Traefik/Caddy.

- FastMCP genera el **JSON Schema automáticamente** desde type hints + Pydantic → cero boilerplate y "reject on missing metadata" nativo.
- **stdio** = un cliente local por proceso; **Streamable HTTP** = servidor siempre-encendido para múltiples agentes → **usar HTTP** (SSE-only está deprecado). MCP **no tiene sesión a nivel de protocolo**: el scope viene en los argumentos de cada llamada (`company_id`/`project_tag`), no del estado de conexión.

### 3.1. Validación estricta que RECHAZA (dos capas)

- **Capa de esquema (rechazo automático):** `company_id`/`project_tag` requeridos sin default → el framework rechaza el `tools/call` antes del handler (error `-32602 Invalid params`).
  - ⚠️ **Watch-item:** bug conocido [fastmcp#1606](https://github.com/jlowin/fastmcp/issues/1606) — el `ValidationError` de Pydantic caía a `-32603 Internal error`. Verificar el mapeo en la versión que fijemos.
- **Capa semántica (rechazo accionable):** lanzar `ToolError` con mensaje que el agente pueda convertir en pregunta al usuario. La spec dice que los clientes **SHOULD** pasar los errores de ejecución de tools al LLM para auto-corrección.
- **Upgrade idiomático 2026:** en vez de rechazo duro, usar **elicitation (`InputRequiredResult`/MRTR)** → el tool pide al cliente que le pregunte al usuario los datos faltantes y reintenta. Solo si los agentes-cliente soportan elicitation.
- **Fail-fast:** nunca envolver la lógica real en try/except que silencie; `mask_error_details=True` oculta internos pero **los `ToolError` explícitos siempre se reenvían**.

### 3.2. Diseño de tools (superficie pequeña, prior art mem0/OpenMemory)

OpenMemory expone: `add_memories`, `search_memory`, `list_memories`, `delete_all_memories`. Convención: pocas tools, `verbo_sustantivo`, snake_case, ≤128 chars.

Superficie sugerida:
- `save_context(company_id, project_tag, content, tags?)` — **idempotente** vía `idempotency_key` del cliente (los agentes reintentan → sin duplicados).
- `search_context(company_id, project_tag, query, limit?)` — recuperación scoped.
- `list_projects(company_id)` — descubrimiento para que el agente pueble `project_tag`.
- `delete_context(company_id, project_tag, id)` — borrado id-scoped y estrecho (evitar `delete_all`).

Una tool = una intención. No hacer un mega `memory(action=...)`. Usar `outputSchema` + `structuredContent` para parseo confiable.

### 3.3. Aislamiento multi-tenant en Mongo (fail-closed)

**Colección única compartida + filtro obligatorio `(company_id, project_tag)` + índice compuesto** (guía oficial de Mongo: colecciones separadas por tenant NO dan aislamiento; DB-per-tenant agrega costo sin ganancia de seguridad real salvo pocos tenants grandes/regulados).

```javascript
db.memories.createIndex({ company_id: 1, project_tag: 1, created_at: -1 })
db.memories.createIndex({ company_id: 1, project_tag: 1, idempotency_key: 1 }, { unique: true })
```

Enrutar **toda** operación por un repositorio scoped que **inyecta mecánicamente** el predicado de tenant y se **niega a correr si falta scope**. El scope se hace spread **al final** para que el caller no lo pueda sobrescribir; borrados/updates siempre AND con el predicado de tenant (un match por `_id` solo nunca debe borrar cross-tenant).

### 3.4. Secret references, no texto plano (dos preocupaciones)

- **(a) Credenciales del propio servidor** nunca en la imagen/código: inyectar en runtime desde Secret Manager/Vault; la config guarda una **referencia** (`secret_ref: "projects/x/secrets/mongo-uri/versions/latest"`) que se resuelve al arrancar. Vault puede emitir usuarios Mongo efímeros por sesión.
- **(b) Evitar que un agente escriba secretos en las memorias:** guard de **redacción/validación en cada write** que rechace (fail-fast) contenido con forma de credencial (API keys, AWS `AKIA…`, tokens GitHub `ghp_…`, private keys, JWT). Guardar en su lugar `{"kind":"secret_ref","ref":"…"}`.

### 3.5. Contenedorización

- Servidor compartido siempre-encendido → **Streamable HTTP en puerto publicado**, `host="0.0.0.0"` dentro del contenedor. stdio-in-Docker solo para dev local de un cliente.
- Imagen mínima non-root (python:3.12-slim), healthcheck, detrás de reverse proxy para TLS/auth/logs. Mongo con volumen persistente y credenciales por docker secrets, nunca horneadas en la imagen.

---

## 4. Plan de implementación por fases

**Fase 0 — construir ahora (metadatos + full-text, vector-ready):**
- Índice compuesto `(company_id, project_tag, created_at)`; multikey en `tags`; **text index** en cuerpo/título.
- Recuperación = filtrar por scope → `$text` opcional → ordenar por recencia/score. Barato, exacto, portable (corre en Windows dev y cualquier server Linux).
- **A prueba de futuro:** reservar campos nullable `embedding: [float]`, `embedding_model: string`, `embedding_dims: int`, y enrutar todos los writes por una capa repositorio única → un solo lugar donde luego "también indexar el vector".
- Tools: `save_context`, `search_context`, `list_projects`, `delete_context`. Validación estricta + fail-closed + guard de secretos.

**Fase 1 — vectores solo cuando aparezca un disparador real** (un tenant cruza decenas de miles de memorias; usuarios se quejan de que "no encuentra si no uso las palabras exactas"; se necesita cross-lingual):
- Backfill: embeber los textos existentes (batch de minutos y centavos).
- Levantar **Qdrant en Docker** (o `CREATE EXTENSION vector` si migramos a Postgres). Upsert `{id, vector, company_id, project_tag, tags}`.
- Recuperación **híbrida**: filtro de metadatos (obligatorio) + ANN vectorial + BM25/rerank opcional, hidratar docs desde Mongo por id.

**Costo de migración de "simple" a "vectorial" = BAJO si se planifica el esquema ahora.** Lo caro a prever: (a) job de backfill; (b) dual-write + reconciliación y su manejo de fallos (sync tax); (c) comprometerse con un modelo/dimensión de embedding (cambiarlo = re-embeber todo → registrar por-fila). Nada de esto re-modela los documentos ni la tenancy → la migración es **aditiva**, no un rewrite.

---

## 5. Decisión de arquitectura (bottom-line)

- **Construir**, no adoptar (por el gatekeeping estricto a medida). Referencia de forma: `coleam00/mcp-mem0` + tools de mem0/OpenMemory.
- **Stack:** Python + FastMCP 3.x + Streamable HTTP + MongoDB (async PyMongo) + Docker tras reverse proxy.
- **Recuperación:** **metadatos-only desde el día uno**, esquema vector-ready. Vectores como bolt-on futuro (Qdrant + embeddings locales BGE-M3/nomic) solo bajo disparador real.
- **Validación:** `company_id`/`project_tag` requeridos (rechazo `-32602`) **+** `ToolError` accionable; evaluar elicitation.
- **Aislamiento:** colección única, índice `(company_id, project_tag, created_at)`, todo por un `ScopedRepo` fail-closed.
- **Secretos:** referencias resueltas en runtime + guard de redacción en writes; nunca credenciales crudas.

**Watch-items del primer commit:** verificar mapeo `ValidationError`→`-32602` (fastmcp#1606); no dejar que `mask_error_details` oculte texto accionable; confirmar soporte de elicitation en los clientes antes de depender de ella.

---

## 6. Fuentes principales

- MongoDB — Public Preview: Community Edition native full-text & vector search
- MCP spec — Tools (rev 2026-07-28); FastMCP docs; fastmcp#1606 / #1316
- mem0 / OpenMemory; Letta; Graphiti/Zep; basic-memory; Qdrant MCP; Chroma MCP; coleam00/mcp-mem0; Memori (GibsonAI); cognee
- Anthropic — Contextual Retrieval; Claude Code retiro de vector search (may-2025)
- Comparativas pgvector vs Qdrant (Tiger Data, Markaicode); embeddings 2026 (BentoML, PreMai)
