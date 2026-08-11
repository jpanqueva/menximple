"""TUI: navegador de memorias (modo 1). Corre en su propia ventana/consola (TTY real).

Dos paneles: a la izquierda el árbol de carpetas y memorias de la cuenta, a la
derecha la ficha de lo que esté bajo el cursor (metadatos + contexto completo).
Se marcan varias con ESPACIO y F2 las carga: escribe los ids elegidos a `--out`,
que es lo que el launcher lee para traer el contexto.

Previsualizar NO cuenta como cargar: el detalle se pide con `marcar_uso=False`."""
import argparse
import json
import os
import sys
import tempfile
import traceback
from datetime import datetime, timezone

from rich.text import Text
from textual import work
from textual.app import App, ComposeResult
from textual.binding import Binding
from textual.containers import Horizontal, Vertical, VerticalScroll
from textual.widgets import Footer, Header, Input, Markdown, Static, Tree

from . import client

# Se ejecuta en una ventana aparte: si algo revienta ahí, no lo ve nadie.
LOG = os.path.join(tempfile.gettempdir(), "menximple-tui.log")


def _log(msg: str) -> None:
    try:
        with open(LOG, "a", encoding="utf-8") as f:
            f.write(f"{datetime.now():%Y-%m-%d %H:%M:%S}  {msg}\n")
    except OSError:
        pass


class Arbol(Tree):
    """Tree normal, salvo ESPACIO: aquí marca la memoria en vez de plegar el nodo.

    Los BINDINGS se heredan por MRO, así que no basta con filtrar el del padre:
    hay que redefinir la misma tecla para que gane la de esta clase."""

    BINDINGS = [
        Binding("space", "marcar_memoria", "Marcar", show=True),
        Binding("right", "abrir", "Abrir", show=False),
        Binding("left", "cerrar", "Cerrar", show=False),
        Binding("escape", "volver_a_busqueda", "Volver a buscar", show=False),
    ]

    def action_marcar_memoria(self) -> None:
        self.app.action_marcar()

    def action_volver_a_busqueda(self) -> None:
        """ESC desde la lista NO cierra: sube a la caja de búsqueda. Cerrar cuesta
        dos ESC a propósito, porque perder lo marcado por un tecleo es caro."""
        self.app.action_enfocar_busqueda()

    def action_abrir(self) -> None:
        n = self.cursor_node
        if n is not None and n.allow_expand and not n.is_expanded:
            n.expand()

    def action_cerrar(self) -> None:
        """Cierra la carpeta; si ya está cerrada, sube a la carpeta que la contiene."""
        n = self.cursor_node
        if n is None:
            return
        if n.allow_expand and n.is_expanded:
            n.collapse()
        elif n.parent is not None and n.parent is not self.root:
            self.select_node(n.parent)
            self.scroll_to_node(n.parent)


class Detalle(VerticalScroll):
    """Panel derecho. No toma el foco: si lo tomara, las flechas dejarían de mover
    el árbol y la interfaz parecería congelada. Se desplaza con AvPág/RePág."""

    can_focus = False


class Buscador(Input):
    """Caja de búsqueda de la que se puede salir: ABAJO y ENTER bajan a la lista,
    para no quedar atrapado escribiendo.

    Aquí ESC sí cierra: es el segundo paso del ESC de la lista."""

    BINDINGS = [
        Binding("down", "ir_a_lista", "Ir a la lista", show=False),
        Binding("escape", "salir", "Salir", show=False),
    ]

    def action_ir_a_lista(self) -> None:
        self.app.query_one("#arbol", Arbol).focus()
        # Al salir del buscador el panel derecho está vacío y no hay evento de
        # cursor que lo repueble: hay que repintarlo a mano.
        self.app.repintar_ficha_actual()

    def action_salir(self) -> None:
        self.app.action_cancelar()


# Color por tipo de memoria: el mismo criterio en el árbol y en la ficha.
COLOR_TIPO = {"credencial": "red", "skill": "cyan",
              "general": "green", "historical": "yellow"}


def _fecha(iso: str | None) -> str:
    """Fecha en relativo ('hace 5 min'), que es lo que el usuario lee de un vistazo."""
    if not iso:
        return "—"
    try:
        t = datetime.fromisoformat(iso)
    except ValueError:
        return iso
    if t.tzinfo is None:
        t = t.replace(tzinfo=timezone.utc)
    seg = (datetime.now(timezone.utc) - t).total_seconds()
    if seg < 60:
        return "hace un momento"
    if seg < 3600:
        return f"hace {int(seg // 60)} min"
    if seg < 86400:
        return f"hace {int(seg // 3600)} h"
    if seg < 86400 * 30:
        return f"hace {int(seg // 86400)} d"
    return t.astimezone().strftime("%d/%m/%Y")


def _tokens(n: int | None) -> str:
    if not n:
        return "—"
    return f"~{n / 1000:.1f}K" if n >= 1000 else f"~{n}"


def _accion(a: dict | None) -> str:
    if not a:
        return "—"
    return f"{a.get('tipo', '?')} · {_fecha(a.get('fecha'))}"


class Navegador(App):
    """Selector de memorias en dos paneles."""

    CSS = """
    #izq { width: 48%; border-right: solid $accent; }
    #buscador { border: round $accent; background: $surface; margin: 1 1 0 1; }
    #buscador:focus { border: round $success; }
    #arbol { padding: 0 1; height: 1fr; }
    #der { width: 1fr; padding: 1 2; }
    #ficha { height: auto; }
    #contexto { height: auto; background: transparent; margin: 0; padding: 0; }
    """

    BINDINGS = [  # ESPACIO lo declara el árbol, para poder ganarle al Tree de Textual
        Binding("f2,ctrl+g", "confirmar", "Cargar selección"),
        Binding("escape", "cancelar", "Atrás · salir"),  # dos ESC desde la lista
        ("slash", "enfocar_busqueda", "Buscar"),
        Binding("pagedown", "desplazar(1)", "Bajar detalle", show=False),
        Binding("pageup", "desplazar(-1)", "Subir detalle", show=False),
    ]

    def __init__(self, out: str, query: str = "", folder: str | None = None,
                 limit: int = 20):
        super().__init__()
        self.out = out
        self.query_inicial = query
        self.folder = folder
        self.limit = limit
        self.marcadas: dict[str, dict] = {}   # id -> entrada (orden = orden de marcado)
        # carpeta -> ids que marcó ella. Guarda los ids y no un contador porque al
        # desmarcarla hay que quitar exactamente esos, y una entrada no sabe de qué
        # carpetas cuelga: `_entrada_out` no devuelve `ancestros`.
        self.marcadas_de: dict[str, list[str]] = {}
        self.confirmado = False
        self.cuenta = "…"
        self._gen = 0                 # descarta contextos que llegan tarde
        self._gen_busq = 0            # ídem para resultados de búsqueda
        self._temporizador = None     # rebote al mover el cursor
        self._buscando = False        # la lista muestra resultados, no carpetas

    # --- Layout --- #

    def compose(self) -> ComposeResult:
        yield Header(show_clock=False)
        with Horizontal():
            with Vertical(id="izq"):
                yield Buscador(placeholder="tema o #nº y Enter · vacío = todo",
                               id="buscador")
                yield Arbol("memorias", id="arbol")
            with Detalle(id="der"):
                yield Static(id="ficha")
                yield Markdown(id="contexto")
        yield Footer()

    def on_mount(self) -> None:
        self.query_one("#buscador", Buscador).border_title = "Buscar"
        arbol = self.query_one("#arbol", Arbol)
        arbol.show_root = False
        arbol.focus()
        self._pintar_estado()
        if self.query_inicial:
            self.query_one("#buscador", Input).value = self.query_inicial
            self._lanzar_busqueda(self.query_inicial)
        else:
            self._restaurar_carpetas()

    # --- Carga de datos (en hilos: la red no puede congelar la interfaz) --- #

    @work(thread=True)
    def _cargar_carpeta(self, node, folder_id: str | None) -> None:
        data = client.listar(folder_id=folder_id)
        self.call_from_thread(self._pintar_hijos, node, data)

    @work(thread=True)
    def _buscar(self, query: str, gen: int) -> None:
        res = client.buscar(query=query, limit=self.limit)
        self.call_from_thread(self._pintar_busqueda, query, res, gen)

    @work(thread=True)
    def _cargar_contexto(self, entry_id: str, gen: int) -> None:
        """Sin `exclusive`: un worker de hilo no se puede cancelar de verdad, así que
        en vez de cancelarlo se descarta su respuesta si el cursor ya se movió."""
        try:
            full = client.obtener_entrada(entry_id, marcar_uso=False)
        except Exception as e:
            _log(f"obtener_entrada({entry_id}): {traceback.format_exc()}")
            self.call_from_thread(self.query_one("#contexto", Markdown).update,
                                  f"*no se pudo cargar el contexto: {e}*")
            return
        if gen != self._gen:
            return
        self.call_from_thread(self.query_one("#contexto", Markdown).update,
                              full.get("contexto", "") or "*(sin contexto)*")

    # --- Pintado --- #

    def _marcadas_de(self, folder_id: str) -> int:
        """Cuántas de las que marcó esta carpeta siguen marcadas: el usuario puede
        haber quitado alguna a mano después."""
        return sum(1 for i in self.marcadas_de.get(folder_id, []) if i in self.marcadas)

    def _etiqueta_carpeta(self, c: dict) -> Text:
        marcadas = self._marcadas_de(c["id"])
        t = Text("✓ ", style="bold green") if marcadas else Text("▸ ", style="dim")
        t.append(c["nombre"], style="bold")
        if marcadas:
            t.append(f"  ({marcadas} marcada{'s' if marcadas > 1 else ''})",
                     style="green")
        t.append(f"   {_accion(c.get('ultima_accion'))}", style="dim italic")
        return t

    def _etiqueta_entrada(self, e: dict) -> Text:
        marcada = e["id"] in self.marcadas
        t = Text("✓ ", style="bold green") if marcada else Text("  ")
        # El consecutivo va delante: es como el usuario puede pedir esta memoria
        # sin leer un uuid, y se escribe tal cual en el buscador.
        if e.get("numero"):
            t.append(f"#{e['numero']:<3} ", style="dim")
        t.append(e["titulo"], style="bold" if marcada else "")
        t.append(f"  {e.get('tipo', '')}", style=COLOR_TIPO.get(e.get("tipo"), "white"))
        t.append(f" · {_tokens(e.get('tokens'))}", style="dim")
        return t

    def _pintar_hijos(self, node, data: dict) -> None:
        if data.get("cuenta"):     # la cuenta la resuelve el servidor a partir de la apikey
            self.cuenta = data["cuenta"]
            self._pintar_estado()
        node.remove_children()
        for c in data.get("carpetas", []):
            hijo = node.add(self._etiqueta_carpeta(c), data={"kind": "carpeta", "obj": c})
            hijo.add("cargando…", data={"kind": "placeholder"})  # se llena al expandir
        for e in data.get("entradas", []):
            node.add_leaf(self._etiqueta_entrada(e), data={"kind": "entrada", "obj": e})
        if not node.children:
            node.add_leaf(Text("(vacío)", style="dim italic"), data={"kind": "vacio"})
        node.expand()

    def _pintar_busqueda(self, query: str, res: list[dict], gen: int) -> None:
        if gen != self._gen_busq:   # llegó tarde: el usuario ya buscó otra cosa
            return
        arbol = self.query_one("#arbol", Arbol)
        arbol.root.remove_children()
        if not res:
            arbol.root.add_leaf(Text(f"sin resultados para «{query}»", style="dim italic"),
                                data={"kind": "vacio"})
            return
        for e in res:
            arbol.root.add_leaf(self._etiqueta_entrada(e), data={"kind": "entrada", "obj": e})

    def _pintar_ficha(self, node) -> None:
        ficha = self.query_one("#ficha", Static)
        ctx = self.query_one("#contexto", Markdown)
        info = node.data or {}
        obj = info.get("obj")

        if info.get("kind") == "entrada":
            t = Text()
            if obj.get("numero"):
                t.append(f"#{obj['numero']}  ", style="dim")
            t.append(f"{obj['titulo']}\n", style="bold")
            t.append(f"{obj.get('resumen', '')}\n\n", style="italic dim")
            for k, v in (
                ("nº", f"#{obj['numero']}" if obj.get("numero") else "—"),
                ("tipo", obj.get("tipo", "—")),
                ("carpeta", " / ".join(obj.get("path") or []) or "—"),
                ("creada", _fecha(obj.get("created_at"))),
                ("última acción", _accion(obj.get("ultima_accion"))),
                ("tamaño", f"{_tokens(obj.get('tokens'))} tokens"),
                ("versión", f"v{obj.get('version', 1)} · {obj.get('use_count', 0)} cargas"),
                ("tags", ", ".join(obj.get("tags") or []) or "—"),
                ("id", obj["id"]),
            ):
                t.append(f"{k:>14}  ", style="dim")
                t.append(f"{v}\n")
            ficha.update(t)
            ctx.update("*cargando contexto…*")
            # Rebote: al bajar rápido por la lista, sólo se pide el contexto de la
            # memoria donde el cursor se detiene, no el de cada una que pasa.
            self._gen += 1
            gen = self._gen
            if self._temporizador is not None:
                self._temporizador.stop()
            self._temporizador = self.set_timer(
                0.25, lambda: self._cargar_contexto(obj["id"], gen))

        elif info.get("kind") == "carpeta":
            t = Text()
            t.append(f"▸ {obj['nombre']}\n", style="bold")
            t.append(f"{obj.get('descripcion') or ''}\n\n", style="italic dim")
            for k, v in (
                ("ruta", " / ".join(obj.get("path") or []) or "(raíz)"),
                ("creada", _fecha(obj.get("created_at"))),
                ("última acción", _accion(obj.get("ultima_accion"))),
                ("id", obj["id"]),
            ):
                t.append(f"{k:>14}  ", style="dim")
                t.append(f"{v}\n")
            ficha.update(t)
            ctx.update("")
        else:
            ficha.update("")
            ctx.update("")

    def _pintar_estado(self) -> None:
        """Cuenta y selección viven en el título: el Footer ya ocupa la línea de abajo."""
        self.title = f"menximple · cuenta {self.cuenta}"
        n = len(self.marcadas)
        if not n:
            self.sub_title = "ninguna marcada"
            return
        tot = sum(e.get("tokens") or 0 for e in self.marcadas.values())
        self.sub_title = f"{n} marcada(s) · {_tokens(tot)} tokens a cargar"

    # --- Eventos --- #

    def on_tree_node_highlighted(self, ev) -> None:
        try:
            self._pintar_ficha(ev.node)
        except Exception:  # un fallo pintando no puede dejar la lista sin responder
            _log(f"_pintar_ficha: {traceback.format_exc()}")

    def on_tree_node_expanded(self, ev) -> None:
        info = ev.node.data or {}
        if info.get("kind") != "carpeta":
            return
        hijos = ev.node.children
        if len(hijos) == 1 and (hijos[0].data or {}).get("kind") == "placeholder":
            self._cargar_carpeta(ev.node, info["obj"]["id"])

    def on_input_submitted(self, ev: Input.Submitted) -> None:
        self.query_one("#arbol", Arbol).focus()
        q = ev.value.strip()
        if q:
            self._lanzar_busqueda(q)
        else:
            self._restaurar_carpetas()

    def on_input_changed(self, ev: Input.Changed) -> None:
        """Vaciar la caja devuelve las carpetas sin tener que dar Enter."""
        if not ev.value.strip() and self._buscando:
            self._restaurar_carpetas()

    # --- Acciones --- #

    def _esperando(self, aviso: str) -> None:
        """Deja la lista con un solo aviso y el panel derecho en blanco: mientras
        se consulta no puede quedar a la vista nada de lo anterior, que ya no
        corresponde a lo que se está pidiendo."""
        arbol = self.query_one("#arbol", Arbol)
        arbol.root.remove_children()
        arbol.root.add_leaf(Text(aviso, style="dim italic"), data={"kind": "vacio"})
        self.limpiar_detalle()

    def _lanzar_busqueda(self, query: str) -> None:
        self._buscando = True
        self._gen_busq += 1
        self._esperando(f"buscando «{query}»…")
        self._buscar(query, self._gen_busq)

    def _restaurar_carpetas(self) -> None:
        self._buscando = False
        self._gen_busq += 1          # invalida una búsqueda que siga en vuelo
        self._esperando("cargando…")
        self._cargar_carpeta(self.query_one("#arbol", Arbol).root, self.folder)

    def limpiar_detalle(self) -> None:
        """Vacía el panel derecho y descarta el contexto que venga en camino."""
        self._gen += 1
        if self._temporizador is not None:
            self._temporizador.stop()
        self.query_one("#ficha", Static).update("")
        self.query_one("#contexto", Markdown).update("")

    def repintar_ficha_actual(self) -> None:
        node = self.query_one("#arbol", Arbol).cursor_node
        if node is not None:
            self._pintar_ficha(node)

    def action_enfocar_busqueda(self) -> None:
        self.query_one("#buscador", Input).focus()
        self.limpiar_detalle()   # la ficha es de la lista, no de lo que se escribe

    def action_desplazar(self, paso: int) -> None:
        """El panel derecho no toma el foco, así que se desplaza desde aquí."""
        self.query_one("#der", Detalle).scroll_page_down() if paso > 0 \
            else self.query_one("#der", Detalle).scroll_page_up()

    def on_worker_state_changed(self, ev) -> None:
        if ev.worker.state.name == "ERROR":   # si no, la ventana muere sin explicación
            _log(f"worker {ev.worker.name}: {ev.worker.error!r}")

    def action_marcar(self) -> None:
        arbol = self.query_one("#arbol", Arbol)
        node = arbol.cursor_node
        info = (node.data or {}) if node else {}
        if info.get("kind") == "carpeta":
            self._marcar_carpeta(node, info["obj"])
            return
        if info.get("kind") != "entrada":
            return
        e = info["obj"]
        if e["id"] in self.marcadas:
            del self.marcadas[e["id"]]
        else:
            self.marcadas[e["id"]] = e
        node.set_label(self._etiqueta_entrada(e))
        self._pintar_estado()

    def _marcar_carpeta(self, node, carpeta: dict) -> None:
        """ESPACIO sobre una carpeta marca todo lo que cuelga de ella.

        Las memorias se piden al servidor en vez de leer el árbol: una carpeta sin
        abrir no tiene hijos cargados, y obligar a expandirla rama por rama para
        poder marcarla entera vaciaría de sentido el atajo."""
        if self._marcadas_de(carpeta["id"]):
            self._aplicar_marcas_carpeta(node, carpeta, [], quitar=True)
            return
        node.set_label(Text(f"▸ {carpeta['nombre']}   buscando…", style="dim italic"))
        self._traer_para_marcar(node, carpeta)

    @work(thread=True)
    def _traer_para_marcar(self, node, carpeta: dict) -> None:
        try:
            memorias = client.buscar(query="", folder_id=carpeta["id"], limit=500)
        except Exception:
            _log(f"marcar carpeta {carpeta['id']}: {traceback.format_exc()}")
            memorias = []
        self.call_from_thread(self._aplicar_marcas_carpeta, node, carpeta, memorias)

    def _aplicar_marcas_carpeta(self, node, carpeta: dict, memorias: list[dict],
                                quitar: bool = False) -> None:
        if quitar:
            for eid in self.marcadas_de.pop(carpeta["id"], []):
                self.marcadas.pop(eid, None)
        else:
            for e in memorias:
                self.marcadas.setdefault(e["id"], e)
            self.marcadas_de[carpeta["id"]] = [e["id"] for e in memorias]
            if not memorias:
                self.notify(f"«{carpeta['nombre']}» no tiene memorias")
        node.set_label(self._etiqueta_carpeta(carpeta))
        self._repintar_entradas()
        self._pintar_estado()

    def _repintar_entradas(self) -> None:
        """Marcar una carpeta cambia el ✓ de memorias que ya están a la vista."""
        pendientes = [self.query_one("#arbol", Arbol).root]
        while pendientes:
            n = pendientes.pop()
            info = n.data or {}
            if info.get("kind") == "entrada":
                n.set_label(self._etiqueta_entrada(info["obj"]))
            pendientes.extend(n.children)

    def action_confirmar(self) -> None:
        self.confirmado = True
        self.exit()

    def action_cancelar(self) -> None:
        self.marcadas.clear()
        self.exit()


def _escribir(path: str, ids: list) -> None:
    with open(path, "w", encoding="utf-8") as f:
        json.dump(ids, f)


def _pausa() -> None:
    """Espera al usuario. Si la consola no tiene stdin (EOFError), no bloquea."""
    try:
        input("Enter para cerrar…")
    except EOFError:
        pass


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", required=True)
    ap.add_argument("--query", default="")
    ap.add_argument("--folder", default=None)
    ap.add_argument("--limit", type=int, default=20)
    # Tolerante con argumentos que no conoce, a propósito. Quien nos lanza es el
    # launcher, que vive en el proceso MCP: ese proceso arranca con la sesión de
    # Claude Code y sigue con el código viejo hasta que el usuario la reinicia,
    # mientras que este archivo se relee en cada ventana. Si al quitar una opción
    # `argparse` abortara, la ventana se abriría y moriría al instante, sin log ni
    # explicación, hasta el siguiente reinicio.
    a, sobran = ap.parse_known_args()
    if sobran:
        _log(f"argumentos ignorados (launcher desactualizado): {sobran}")

    # La consola nueva de Windows no arranca en UTF-8 y la interfaz usa ▸ ✓ ─.
    for flujo in (sys.stdout, sys.stderr):
        try:
            flujo.reconfigure(encoding="utf-8")
        except (AttributeError, OSError):
            pass

    app = Navegador(a.out, a.query, a.folder, a.limit)
    try:
        app.run()
    except Exception as e:  # frontera: el launcher no puede quedarse esperando a ciegas
        _escribir(a.out, [])
        print(f"Error abriendo el navegador de memorias: {e}")
        _pausa()
        return
    _escribir(a.out, list(app.marcadas) if app.confirmado else [])


if __name__ == "__main__":
    main()
