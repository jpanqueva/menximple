"""Prototipo mínimo para PROBAR el canal de inyección TUI -> chat.

Se ejecuta en una ventana propia (TTY real). Muestra unas opciones, el usuario
marca por número, y escribe la selección a un archivo que el proceso lanzador
(que espera) lee y devuelve al chat. Con --auto no pide input (prueba de plumbing).

NO es la TUI final (esa usará curses/textual y hablará con el API por base_url).
"""
import json
import sys
import time

SALIDA = sys.argv[1]
AUTO = len(sys.argv) > 2 and sys.argv[2] == "--auto"

# En la versión real esto vendrá del API (buscar/listar). Aquí es fijo para la prueba.
OPCIONES = [
    {"id": "1", "titulo": "Deploy API", "resumen": "cómo se despliega el api con docker compose"},
    {"id": "2", "titulo": "Credenciales SOP", "resumen": "acceso SSH al servidor de producción"},
    {"id": "3", "titulo": "Regla facturación Llano", "resumen": "radicar antes del 20 de cada mes"},
]


def render():
    print("=" * 56)
    print("  SELECTOR DE CONTEXTO  (prueba de inyección al chat)")
    print("=" * 56)
    for i, o in enumerate(OPCIONES, 1):
        print(f"   [{i}] {o['titulo']} — {o['resumen']}")
    print()


def main():
    render()
    if AUTO:
        elegidas = [OPCIONES[0], OPCIONES[2]]
        print("(modo --auto) seleccionando [1] y [3]…")
        time.sleep(1)
    else:
        print("Escribe los números a cargar separados por espacio (ej: 1 3) y Enter:")
        try:
            crudo = input("> ").split()
        except EOFError:
            crudo = []
        elegidas = [OPCIONES[int(s) - 1] for s in crudo
                    if s.isdigit() and 1 <= int(s) <= len(OPCIONES)]

    with open(SALIDA, "w", encoding="utf-8") as f:
        json.dump(elegidas, f, ensure_ascii=False, indent=2)

    print(f"\nSeleccionaste {len(elegidas)} memoria(s). Enviando al chat…")
    time.sleep(1)


if __name__ == "__main__":
    main()
