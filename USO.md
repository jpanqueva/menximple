# Cómo se usa menximple

Guía para empezar en un proyecto nuevo. Si eres un agente de IA leyendo esto: el
servidor te entrega la misma metodología en el campo `instructions` del protocolo
(está en `memory_server/instructions.py`), y `arbol()` te dice qué hay en la cuenta.

---

## 1. Qué es esto

Se llama **menximple**, pero en el día a día se le dice **menx**. "Abre menx",
"guarda esto en menx", "qué hay en menx" — el agente entiende todas.

Un sitio donde tus memorias viven **fuera** de la conversación y sobreviven a que
cierres la terminal, compactes el contexto o cambies de máquina. Cada cuenta tiene
sus memorias privadas, y se identifica por su apikey.

- **Carpetas** — organización libre. No hay jerarquía obligatoria.
- **Memorias** (entradas) — siempre dentro de una carpeta. Cada una tiene:
  - `titulo` — cómo la reconoces.
  - `resumen` — **lo que se busca**. Una frase con las palabras que usarías al preguntar.
  - `contexto` — el contenido completo. Es lo que se carga a la conversación.
  - `tipo` — `credencial` · `skill` · `general` · `historical`.
  - `tags`, y un **consecutivo** (`#4`) para poder pedirla por número.

Nada se destruye: editar deja historial y borrar archiva.

---

## 2. Los dos servidores MCP

Son dos, y hacen falta los dos para la experiencia completa:

| | qué hace | dónde corre |
|---|---|---|
| `menximple` | el hub: buscar, guardar, organizar | remoto, por HTTP |
| `menximple-selector` | abre el selector visual en tu escritorio | **local**, en tu máquina |

El hub corre en un contenedor en el servidor, así que **no puede abrir ventanas en
tu PC**. Por eso el selector es un segundo servidor, local, que sí puede.

`.mcp.json` de tu proyecto:

```jsonc
{
  "mcpServers": {
    "menximple": {
      "type": "http",
      "url": "https://TU-SERVIDOR/mcp",
      "headers": { "X-API-Key": "<tu apikey>" }
    },
    "menximple-selector": {
      "command": "menximple-mcp",
      "env": {
        "MEMORY_BASE_URL": "https://TU-SERVIDOR/mcp",
        "MEMORY_APIKEY": "<tu apikey>"
      }
    }
  }
}
```

**En Windows es mejor no usar el `.mcp.json` del proyecto**: ese archivo se
commitea y la apikey acabaría en un repositorio. Regístralos a nivel de usuario
siguiendo [docs/INSTALAR-EN-WINDOWS.md](docs/INSTALAR-EN-WINDOWS.md) — quedan en
tu perfil, valen para todas las sesiones y no piden permisos cada vez.

Instalación del cliente en Linux/macOS o para uso desde consola:
[INSTALL-CLIENTE.md](INSTALL-CLIENTE.md).

---

## 3. La forma normal de cargar memoria: el selector

Es la vía preferida — el usuario ve lo que hay y elige, en vez de que el agente
adivine.

Le pides al agente *"abre mis memorias"* y llama a `abrir_selector`. Se abre una
ventana con el árbol a la izquierda y la ficha de lo que tengas bajo el cursor a
la derecha (metadatos y contexto completo).

| tecla | qué hace |
|---|---|
| `↑ ↓` | moverse |
| `→ ←` | abrir / cerrar carpeta (cerrada, `←` sube a la carpeta padre) |
| `ESPACIO` | marcar / desmarcar la memoria |
| `F2` o `Ctrl+G` | cargar lo marcado y cerrar |
| `/` | ir al buscador |
| `Enter` (en el buscador) | buscar y bajar a la lista |
| `ESC` | desde la lista sube al buscador; **el segundo ESC cierra** |
| `Re Pág` / `Av Pág` | desplazar el panel derecho |
| `Ctrl+L` | olvidar las marcas de "ya cargada" |

Las memorias que ya cargaste en esta conversación salen con **●** azul y en gris,
para no cargarlas dos veces. Ese estado va por conversación: una terminal nueva
arranca limpia y `/resume` lo recupera.

> **Después de un `/compact`**: el contexto se vacía pero ningún servidor MCP se
> entera, así que las marcas siguen ahí. Dile al agente que las limpie
> (`olvidar_cargadas`) o pulsa `Ctrl+L` en la ventana.

La ventana **no se cierra sola**. Si tardas, la llamada devuelve un token y el
agente sigue esperando con `recoger_seleccion`. Tómate el tiempo que quieras.

---

## 4. Sin ventana: por chat

En un servidor sin escritorio, o si prefieres no abrir nada, el agente te enseña
el árbol y tú pides por número:

```
> ¿qué tengo guardado?

jhon
└── administrativa/
    └── datos y soluciones/
        ├── #1   Como generar una cotizacion  [skill]
        ├── #2   Datos fiscales de Soluciones Estrategicas  [general]
        ├── #3   Facturacion electronica en la DIAN  [skill]
        └── #4   Cliente Grupo del Llano (Llanogas)  [general]

> cárgame la 3 y la 4
```

`arbol()` acepta `folder_id` para ver una rama sola, `profundidad` para cortar
(lo que queda fuera se anuncia, no se esconde) y `con_memorias=False` para ver
solo el esqueleto de carpetas.

**El número es una referencia de verdad**, no solo algo que mirar: donde una tool
pida un `entry_id` puedes pasarle `"11"` o `"#11"` igual que el uuid. Vale para
cargar, obtener, editar, borrar y ver el historial.

> **El árbol es también el rescate cuando algo no aparece buscando.** Si recuerdas
> haber guardado algo pero no con qué palabras, pide el árbol: casi siempre está,
> con otro nombre. Es mejor que guardarlo otra vez y acabar con duplicados.

---

## 5. Buscar

Puedes pasarle **la frase completa**, no hace falta acertar la palabra exacta:

- casa por **palabra suelta** — "facturador dian" encuentra la memoria de la DIAN
  aunque "facturador" no esté en ningún lado;
- casa por **prefijo** — "corr" encuentra "Correlativo";
- **ignora tildes** — "facturación" encuentra "Facturacion";
- ordena por cuántas palabras acertaron, pesando más el título que el resumen y
  el resumen más que los tags;
- un query que sea **solo un número** busca por consecutivo (`#4` es explícito;
  `4` a secas reintenta como texto si no existe la memoria 4).

Lo que **no** hace: entender sinónimos. "facturador" no encuentra "facturación"
por sí solo. Eso lo resolverían los embeddings, hoy apagados a propósito.

---

## 6. Reglas de orden (sugerencias)

El servidor no impone ninguna estructura. Estas son las que evitan que en un año
tengas doscientas memorias sueltas:

- **Un nivel por criterio, máximo tres.** `área / proyecto / subtema`:
  `administrativa / datos y soluciones`, `clientes / acme / facturación`.
  Más profundidad se vuelve inencontrable.
- **Si una carpeta pasa de ~15 memorias** sin un tema que las una, subdivídela.
  Mover no cuesta nada: `editar_entrada(mover_a=...)` y las rutas se recalculan solas.
- **No mezcles cosas sin relación clara** solo porque son del mismo cliente.
  Separa el procedimiento (`skill`) de los datos (`general`) si los consultas en
  momentos distintos.
- **Una memoria = un tema.** Si el contexto crece tanto que cargarlo trae mucho
  que no viene al caso, pártelo y enlaza mencionando el consecutivo.
- **Escribe el `resumen` como preguntarías**, no como titularías.
- **Los `tags` son para lo transversal** (`cliente`, `facturacion`): lo que cruza
  varias carpetas. No repitas ahí lo que ya dice la carpeta.
- Antes de crear una carpeta, mira el `arbol()`: casi siempre ya hay una que
  sirve, con otro nombre.

**Credenciales:** el hub **no cifra en reposo**. Guarda la referencia ("la clave
de X está en el archivo Y"), no el secreto.

---

## 7. Las tools

**Ver y buscar**

| tool | para qué |
|---|---|
| `arbol` | toda la cuenta en texto, con consecutivos. Lo primero al llegar. |
| `listar` | el contenido de una carpeta |
| `buscar` | por texto o por número; devuelve resúmenes, no el contexto |
| `buscar_relacionadas` | vecinos de un tema o de otra memoria |
| `listar_recientes` | lo último que se usó |

**Leer**

| tool | para qué |
|---|---|
| `obtener_entrada` | una memoria completa. `marcar_uso=False` para solo mirarla |
| `cargar_contexto` | varias de golpe: la tool para cargar al agente |
| `ver_historial` | qué decía antes de cada edición |

**Escribir**

| tool | para qué |
|---|---|
| `crear_carpeta` / `editar_carpeta` | crear, renombrar, describir, mover (`mover_a=''` = raíz) |
| `crear_entrada` / `editar_entrada` | guardar y actualizar (`mover_a` cambia de carpeta) |
| `borrar_entrada` / `borrar_carpeta` | **archivan**, no destruyen |
| `restaurar_entrada` / `restaurar_carpeta` | deshacen el borrado |

**Selector (servidor local)**

| tool | para qué |
|---|---|
| `abrir_selector` | abre la ventana y espera |
| `recoger_seleccion` | sigue esperando si devolvió `pendiente` |
| `cerrar_selector` | la cierra a la fuerza |
| `cargar_memorias` | carga por id (segundo paso del modo chat) |
| `olvidar_cargadas` | borra las marcas ● (tras un compact) |

**Admin** (header `X-Admin-Token`): `crear_cuenta`, `listar_cuentas`.
`crear_cuenta` devuelve la apikey **una sola vez**.

---

## 8. Detalles que sorprenden

- **Borrar una carpeta se lleva todo su subárbol.** Te dice cuántas cosas arrastró.
  Al restaurarla no revive lo que ya estaba borrado aparte.
- **Los consecutivos no se reutilizan.** Si borras la última, la siguiente sigue
  contando; dos memorias distintas nunca comparten número.
- **No se puede guardar dentro de una carpeta borrada**: la memoria nacería invisible.
- **Un `/compact` no es observable** desde ningún MCP. Las marcas ● hay que
  limpiarlas a mano.
- **Claude Code corta las llamadas a tools a los 120 s.** Por eso el selector
  devuelve un token en vez de morirse.

---

Diseño y decisiones: [ARQUITECTURA.md](ARQUITECTURA.md) ·
Instalación: [INSTALL-CLIENTE.md](INSTALL-CLIENTE.md) · [INSTALL-SERVER.md](INSTALL-SERVER.md)
