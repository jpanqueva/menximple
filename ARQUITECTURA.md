# Arquitectura — MCP Memory Server

> Decisión tomada tras la investigación (`investigacion/INFORME-ESTADO-DEL-ARTE.md`).
> **Construir propio**, Python + FastMCP + MongoDB, con vectores **opcionales** (Qdrant + embedding ligero) solo sobre el `resumen`.

---

## 1. Concepto

Hub central de **memoria a largo plazo** para agentes de IA (Claude y otros), desplegable en un servidor, consumible por MCP sobre HTTP. Es la **única fuente de verdad** vía una API; tanto el navegador TUI como el modo chat consumen esa misma API con una `base_url` configurable.

El MCP trae **instrucciones propias** que le enseñan a Claude la metodología de uso y que **este sistema tiene prelación** sobre la memoria nativa de Claude (sin ser exclusivo).

---

## 2. Modelo de datos

Un **árbol**. Dos tipos de cosa, y son distintas:

- **Carpeta** (`carpetas`): organización libre — proyectos, subproyectos o como el usuario quiera. **No es una regla rígida.** Una carpeta puede contener subcarpetas y/o entradas.
- **Entrada de memoria** (`entradas`): **el nodo/memoria real**. Siempre vive dentro de una carpeta. Es editable y versionada.

### Colección `carpetas`
| Campo | Tipo | Nota |
|---|---|---|
| `_id` | ObjectId | |
| `nombre` | str | requerido |
| `parent_id` | ObjectId \| null | null = raíz |
| `ancestros` | [ObjectId] | cadena de carpetas padre (para consultas de subárbol) |
| `path` | [str] | nombres de ancestros, para mostrar |
| `descripcion` | str \| null | opcional |
| `created_at`, `updated_at` | datetime | |

### Colección `entradas`
| Campo | Tipo | Nota |
|---|---|---|
| `_id` | ObjectId | |
| `folder_id` | ObjectId | carpeta padre (requerido) |
| `ancestros` | [ObjectId] | padre + sus padres (metadato) |
| `path` | [str] | ruta legible |
| `titulo` | str | requerido |
| `resumen` | str | requerido — **lo único que se embebe** |
| `contexto` | str | contenido completo (requerido) |
| `tipo` | enum | `credencial \| skill \| general \| historical` (requerido) |
| `tags` | [str] | opcional |
| `created_at`, `updated_at` | datetime | |
| `last_used` | datetime \| null | tracking de uso |
| `use_count` | int | tracking de uso |
| `version` | int | arranca en 1 |
| `historial` | [snapshot] | **snapshot completo** de cada versión previa |
| `embedding_model`, `embedding_dims` | str/int \| null | registrados si hay vector |

El vector (si está activo) vive en **Qdrant**, no en Mongo; la entrada guarda el modelo/dims para no mezclar embeddings de modelos distintos.

### Índices Mongo
- `carpetas`: `parent_id`, `ancestros`
- `entradas`: `folder_id`, `ancestros`, `tipo`, `last_used desc`, y **text index** sobre `titulo,resumen,contexto,tags`

---

## 3. Recuperación (vectores opcionales)

- **`EMBEDDINGS_ENABLED=false` por defecto.** Sin vectores → búsqueda por **text index de Mongo** + filtros de metadatos + recencia. A escala modesta esto da recall completo y cero infra extra.
- **`EMBEDDINGS_ENABLED=true`** → se embebe el `resumen` con un modelo ligero (default `intfloat/multilingual-e5-small`, 384d, bueno en español, corre en CPU) y se guarda en Qdrant. `buscar` usa el vector; el filtro de metadatos (tipo/carpeta/tags) sigue aplicando.
- El uso de embeddings **no es fijo**: se puede prender/apagar por config sin cambiar el esquema (los campos ya están reservados).

**Búsquedas más inteligentes (fallback, sobre todo en modo chat):** además de `buscar`, hay `buscar_relacionadas` (vecinos por significado / por texto del resumen) y `listar_recientes` (por `last_used`) para cuando la primera búsqueda no encuentra.

> `buscar` devuelve **resumen + metadatos** (no el `contexto` completo, para no volcar credenciales en búsquedas amplias). El `contexto` completo se entrega solo con `obtener_entrada` / `cargar_contexto`, que además marcan el uso.

---

## 4. Tools MCP

| Tool | Qué hace |
|---|---|
| `listar(folder_id?)` | Contenido de una carpeta (subcarpetas + entradas). Sin `folder_id` → raíz + **documentación de uso**. |
| `crear_carpeta(nombre, parent_id?, descripcion?)` | Nueva carpeta (proyecto/subproyecto/organización libre). |
| `editar_carpeta(folder_id, nombre?, descripcion?, mover_a?)` | Renombrar / describir / mover (recalcula subárbol). |
| `crear_entrada(folder_id, titulo, resumen, contexto, tipo, tags?)` | Nueva memoria. **Validación estricta** (rechaza si falta algo o `tipo` inválido). |
| `editar_entrada(entry_id, ...)` | Edita; guarda snapshot en `historial`, sube `version`, re-embebe si cambió el `resumen`. |
| `buscar(query, tipo?, folder_id?, tags?, limit?)` | Búsqueda vector/texto + filtros de metadatos. Devuelve resúmenes. |
| `buscar_relacionadas(texto\|entry_id, limit?)` | Fallback semántico / por texto. |
| `listar_recientes(limit?)` | Últimas usadas (para modo chat). |
| `obtener_entrada(entry_id)` | Entrada completa **con `contexto`**; marca uso. |
| `cargar_contexto(entry_ids[])` | Devuelve el `contexto` de varias entradas; marca uso. Es lo que carga el contexto al agente. |

Convención: pocas tools, `verbo_sustantivo`, una intención por tool.

---

## 5. Carga de contexto — dos modos, misma API

1. **TUI** (ventana aparte): navegador de memorias en Python; se marca con espacio/X; Claude puede **pre-completar la selección** (opcional). Al confirmar, la selección se entrega y se carga como contexto. Es un **cliente del API** (no lee Mongo/Qdrant directo).
2. **Chat interactivo** (para servidores por tmux, sin ventanas): Claude lista proyectos, el usuario responde por número, Claude muestra los contextos disponibles / recientes-probables, y carga por número. Usa `listar` / `buscar` / `listar_recientes` / `cargar_contexto`.

---

## 6. Validación estricta y fail-fast

- Campos requeridos y `tipo` válido se verifican en el repositorio; una violación lanza `MemoriaError` → el server la traduce a `ToolError` **con mensaje accionable** (para que el agente le pregunte al usuario). Nunca se silencia con try/except ciego; los errores inesperados se propagan.
- Toda entrada exige una **carpeta padre existente** → no hay memorias "flotantes" sin scope. (Las carpetas raíz cumplen el rol de empresa/proyecto.)

---

## 7. Despliegue

- **FastMCP sobre Streamable HTTP**, `host`/`port` configurables; `MEMORY_BASE_URL` para los clientes.
- Docker: imagen mínima non-root + Mongo (+ Qdrant opcional, perfil `embeddings`).
- Detrás de reverse proxy para TLS en producción (cuando entremos a endurecer).

---

## 8. Estado / pendientes

- [x] Investigación estado del arte
- [x] Arquitectura y esquema
- [ ] Esqueleto: config, modelos, db, repositorio (validación estricta), server FastMCP con tools + instrucciones **(en curso)**
- [ ] Embeddings/Qdrant (opcional, off por defecto)
- [ ] TUI cliente del API
- [ ] Modo chat (guiado por instrucciones del server)
- [ ] Endurecimiento de seguridad (cifrado en reposo, token, auditoría) — diferido
