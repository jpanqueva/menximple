"""TUI: navegador de memorias (modo 1). Corre en su propia ventana/consola (TTY real).

Muestra candidatos del API, multi-selección con ESPACIO (enter confirma, Ctrl-C
cancela) y escribe los ids elegidos a --out. El launcher los lee y carga el contexto."""
import argparse
import json

import questionary

from . import client


def _candidatos(query: str, folder: str | None, limit: int) -> list[dict]:
    if query:
        return client.buscar(query=query, folder_id=folder, limit=limit)
    return client.listar_recientes(limit=limit)  # sin query: ofrece las últimas usadas


def _escribir(path: str, ids: list) -> None:
    with open(path, "w", encoding="utf-8") as f:
        json.dump(ids, f)


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", required=True)
    ap.add_argument("--query", default="")
    ap.add_argument("--folder", default=None)
    ap.add_argument("--limit", type=int, default=20)
    a = ap.parse_args()

    try:
        cands = _candidatos(a.query, a.folder, a.limit)
    except Exception as e:  # frontera: mostrar el error en la ventana y cerrar sin selección
        print(f"Error consultando el API: {e}")
        input("Enter para cerrar…")
        _escribir(a.out, [])
        return

    if not cands:
        print("No se encontraron memorias para esa búsqueda.")
        input("Enter para cerrar…")
        _escribir(a.out, [])
        return

    choices = [
        questionary.Choice(
            title=f"[{c.get('tipo', '?')}] {c['titulo']} — {c.get('resumen', '')}",
            value=c["id"],
        )
        for c in cands
    ]
    sel = questionary.checkbox(
        "Selecciona memorias a cargar (ESPACIO marca · ENTER confirma · Ctrl-C cancela):",
        choices=choices,
    ).ask()
    _escribir(a.out, sel or [])


if __name__ == "__main__":
    main()
