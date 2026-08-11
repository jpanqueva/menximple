"""TUI: navegador de memorias (modo 1). Corre en su propia ventana/consola (TTY real).

Dos paneles: a la izquierda el árbol de carpetas y memorias de la cuenta, a la
derecha la ficha de lo que esté bajo el cursor (metadatos + contexto completo).
Se marcan varias con ESPACIO y F2 las carga: escribe los ids elegidos a `--out`,
que es lo que el launcher lee para traer el contexto.

Previsualizar NO cuenta como cargar: el detalle se pide con `marcar_uso=False`."""
import argparse
import json
import sys
from datetime import datetime, timezone

from rich.text import Text
from textual import work
from textual.app import App, ComposeResult
from textual.binding import Binding
from textual.containers import Horizontal, Vertical, VerticalScroll
from textual.widgets import Footer, Header, Input, Markdown, Static, Tree

from . import client


class Arbol(Tree):
    """Tree normal, salvo ESPACIO: aquí marca la memoria en vez de plegar el nodo.

    Los BINDINGS se heredan por MRO, así que no basta con filtrar el del padre:
    hay que redefinir la misma tecla para que gane la de esta clase."""

    BINDINGS = [Binding("space", "marcar_memoria", "Marcar", show=True)]

    def action_marcar_memoria(self) -> None:
        self.app.action_marcar()


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
    #buscador { border: none; background: $boost; margin: 0; }
    #arbol { padding: 0 1; height: 1fr; }
    #der { width: 1fr; padding: 1 2; }
    #ficha { height: auto; }
    #contexto { height: auto; background: transparent; margin: 0; padding: 0; }
    """

    BINDINGS = [  # ESPACIO lo declara el árbol, para poder ganarle al Tree de Textual
        ("f2", "confirmar", "Cargar selección"),
        ("escape", "cancelar", "Cancelar"),
        ("slash", "enfocar_busqueda", "Buscar"),
    ]

    def __init__(self, out: str, query: str = "", folder: str | None = None, limit: int = 20):
        super().__init__()
        self.out = out
        self.query_inicial = query
        self.folder = folder
        self.limit = limit
        self.marcadas: dict[str, dict] = {}   # id -> entrada (orden = orden de marcado)
        self.confirmado = False

    # --- Layout --- #

    def compose(self) -> ComposeResult:
        yield Header(show_clock=False)
        with Horizontal():
            with Vertical(id="izq"):
                yield Input(placeholder="Buscar y Enter (vacío = todo)", id="buscador")
                yield Arbol("memorias", id="arbol")
            with VerticalScroll(id="der"):
                yield Static(id="ficha")
                yield Markdown(id="contexto")
        yield Footer()

    def on_mount(self) -> None:
        self.title = "menximple"
        arbol = self.query_one("#arbol", Arbol)
        arbol.show_root = False
        arbol.focus()
        self._pintar_estado()
        if self.query_inicial:
            self.query_one("#buscador", Input).value = self.query_inicial
            self._buscar(self.query_inicial)
        else:
            self._cargar_carpeta(arbol.root, self.folder)

    # --- Carga de datos (en hilos: la red no puede congelar la interfaz) --- #

    @work(thread=True)
    def _cargar_carpeta(self, node, folder_id: str | None) -> None:
        data = client.listar(folder_id=folder_id)
        self.call_from_thread(self._pintar_hijos, node, data)

    @work(thread=True)
    def _buscar(self, query: str) -> None:
        res = client.buscar(query=query, limit=self.limit)
        self.call_from_thread(self._pintar_busqueda, query, res)

    @work(thread=True, exclusive=True, group="ficha")
    def _cargar_contexto(self, entrada: dict) -> None:
        full = client.obtener_entrada(entrada["id"], marcar_uso=False)
        self.call_from_thread(self.query_one("#contexto", Markdown).update,
                              full.get("contexto", "") or "*(sin contexto)*")

    # --- Pintado --- #

    def _etiqueta_carpeta(self, c: dict) -> Text:
        t = Text("▸ ", style="dim")
        t.append(c["nombre"], style="bold")
        t.append(f"   {_accion(c.get('ultima_accion'))}", style="dim italic")
        return t

    def _etiqueta_entrada(self, e: dict) -> Text:
        marcada = e["id"] in self.marcadas
        t = Text("✓ " if marcada else "  ", style="bold green" if marcada else "")
        t.append(e["titulo"], style="bold" if marcada else "")
        t.append(f"  {e.get('tipo', '')}", style=COLOR_TIPO.get(e.get("tipo"), "white"))
        t.append(f" · {_tokens(e.get('tokens'))}", style="dim")
        return t

    def _pintar_hijos(self, node, data: dict) -> None:
        node.remove_children()
        for c in data.get("carpetas", []):
            hijo = node.add(self._etiqueta_carpeta(c), data={"kind": "carpeta", "obj": c})
            hijo.add("cargando…", data={"kind": "placeholder"})  # se llena al expandir
        for e in data.get("entradas", []):
            node.add_leaf(self._etiqueta_entrada(e), data={"kind": "entrada", "obj": e})
        if not node.children:
            node.add_leaf(Text("(vacío)", style="dim italic"), data={"kind": "vacio"})
        node.expand()

    def _pintar_busqueda(self, query: str, res: list[dict]) -> None:
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
            t.append(f"{obj['titulo']}\n", style="bold")
            t.append(f"{obj.get('resumen', '')}\n\n", style="italic dim")
            for k, v in (
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
            self._cargar_contexto(obj)

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
        """El contador vive en el subtítulo: el Footer ya ocupa la línea de abajo."""
        n = len(self.marcadas)
        if not n:
            self.sub_title = "ninguna marcada"
            return
        tot = sum(e.get("tokens") or 0 for e in self.marcadas.values())
        self.sub_title = f"{n} marcada(s) · {_tokens(tot)} tokens a cargar"

    # --- Eventos --- #

    def on_tree_node_highlighted(self, ev) -> None:
        self._pintar_ficha(ev.node)

    def on_tree_node_expanded(self, ev) -> None:
        info = ev.node.data or {}
        if info.get("kind") != "carpeta":
            return
        hijos = ev.node.children
        if len(hijos) == 1 and (hijos[0].data or {}).get("kind") == "placeholder":
            self._cargar_carpeta(ev.node, info["obj"]["id"])

    def on_input_submitted(self, ev: Input.Submitted) -> None:
        q = ev.value.strip()
        arbol = self.query_one("#arbol", Arbol)
        arbol.focus()
        if q:
            self._buscar(q)
        else:
            arbol.root.remove_children()
            self._cargar_carpeta(arbol.root, self.folder)

    # --- Acciones --- #

    def action_enfocar_busqueda(self) -> None:
        self.query_one("#buscador", Input).focus()

    def action_marcar(self) -> None:
        arbol = self.query_one("#arbol", Arbol)
        node = arbol.cursor_node
        info = (node.data or {}) if node else {}
        if info.get("kind") != "entrada":
            return
        e = info["obj"]
        if e["id"] in self.marcadas:
            del self.marcadas[e["id"]]
        else:
            self.marcadas[e["id"]] = e
        node.set_label(self._etiqueta_entrada(e))
        self._pintar_estado()

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
    a = ap.parse_args()

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
