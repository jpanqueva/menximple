"""Canales entre agentes, contra un Qdrant desechable."""
import os
import threading
import time

os.environ.setdefault("QDRANT_URL", "http://127.0.0.1:6399")
os.environ["EMBEDDINGS_ENABLED"] = "false"

from memory_server import canales as ch, store          # noqa: E402
from memory_server.models import MemoriaError           # noqa: E402

store.ensure_collections()
import _catalogo  # noqa: E402,F401
fallos = []


def chk(cond, msg):
    print(("  OK   " if cond else "  FALLO") + "  " + msg)
    if not cond:
        fallos.append(msg)


def falla(fn, trozo, msg):
    try:
        fn()
        chk(False, msg + " (no lanzó)")
    except MemoriaError as e:
        chk(trozo in str(e), f"{msg} -> {e}")


print("== crear y listar ==")
ch.crear_canal("canal-prueba-trabajo", "pruebas del piloto")
ch.crear_canal("canal-prueba-devops")
chk({c["nombre"] for c in ch.listar_canales()} >= {"canal-prueba-trabajo", "canal-prueba-devops"}, "los dos canales existen")
falla(lambda: ch.crear_canal("CANAL-PRUEBA-TRABAJO"), "ya existe", "el nombre se normaliza y no se duplica")

print("== nomenclatura estricta ==")
falla(lambda: ch.crear_canal("qa"), "nombre de canal inválido", "un nombre libre se rechaza")
falla(lambda: ch.crear_canal("canal-noexiste-trabajo"), "no es un ámbito", "un ámbito fuera del catálogo se rechaza")
falla(lambda: ch.crear_canal("canal-prueba-fiesta"), "no es una actividad", "una actividad fuera del catálogo se rechaza")
falla(lambda: ch.crear_canal("canal-eqb-eqa-trabajo"), "orden alfabético", "dos equipos van en orden alfabético")
falla(lambda: ch.unirse_canal("canal-prueba-trabajo", "jhon-windows"), "nombre de agente inválido", "un agente con nombre libre se rechaza")
falla(lambda: ch.unirse_canal("canal-prueba-trabajo", "agt-marte-prueba-x1"), "no está en el catálogo", "un equipo desconocido se rechaza")

print("== sala sin tope ==")
ch.unirse_canal("canal-prueba-trabajo", "agt-eqa-prueba-jhon")
ch.unirse_canal("canal-prueba-trabajo", "agt-eqb-prueba-qa")
r = ch.unirse_canal("canal-prueba-trabajo", "agt-eqc-prueba-tercero")
chk(len(r["agentes"]) == 3, f"el tercero entra -> {r['agentes']}")
ch.salir_canal("canal-prueba-trabajo", "agt-eqc-prueba-tercero")
r = ch.unirse_canal("canal-prueba-trabajo", "agt-eqa-prueba-jhon")
chk(r.get("reentro"), "reentrar con el mismo nombre no es error")

print("== un agente en VARIOS canales ==")
ch.unirse_canal("canal-prueba-devops", "agt-eqa-prueba-jhon")
ch.unirse_canal("canal-prueba-devops", "agt-eqb-prueba-sop")
mios = [c["nombre"] for c in ch.mis_canales("agt-eqa-prueba-jhon")]
chk(sorted(mios) == ["canal-prueba-devops", "canal-prueba-trabajo"], f"jhon-windows está en los dos -> {mios}")

print("== enviar y recibir ==")
falla(lambda: ch.enviar_mensaje("canal-prueba-trabajo", "agt-eqc-prueba-colado", "hola"), "no está en el canal",
      "no se puede escribir sin estar dentro")
ch.enviar_mensaje("canal-prueba-trabajo", "agt-eqa-prueba-jhon", "corré las pruebas del armado")
r = ch.recibir("canal-prueba-trabajo", "agt-eqb-prueba-qa")
chk([m["texto"] for m in r["mensajes"]] == ["corré las pruebas del armado"], "le llegó al otro")
chk(ch.recibir("canal-prueba-trabajo", "agt-eqb-prueba-qa")["mensajes"] == [], "no se repite: quedó marcado como visto")
chk(ch.recibir("canal-prueba-trabajo", "agt-eqa-prueba-jhon")["mensajes"] == [], "no te llega tu propio mensaje")

print("== quien llega después SÍ lee lo que se dijo antes ==")
# Cambiado a propósito: la primera versión ponía la marca en el último mensaje y
# eso perdía en silencio el mensaje que uno deja esperando a que el otro entre.
ch.salir_canal("canal-prueba-trabajo", "agt-eqb-prueba-qa")
ch.unirse_canal("canal-prueba-trabajo", "agt-eqb-prueba-otroqa")
chk([m["texto"] for m in ch.recibir("canal-prueba-trabajo", "agt-eqb-prueba-otroqa")["mensajes"]] ==
    ["corré las pruebas del armado"], "lee lo anterior al entrar")

print("== recibir_de_todos junta los canales ==")
ch.enviar_mensaje("canal-prueba-trabajo", "agt-eqb-prueba-otroqa", "listo, 12 pruebas OK")
ch.enviar_mensaje("canal-prueba-devops", "agt-eqb-prueba-sop", "desplegado en produccion")
r = ch.recibir_todo("agt-eqa-prueba-jhon")
chk({c["canal"] for c in r["canales"]} == {"canal-prueba-trabajo", "canal-prueba-devops"},
    f"trae los dos canales -> {[c['canal'] for c in r['canales']]}")
chk(ch.recibir_todo("agt-eqa-prueba-jhon")["canales"] == [], "y los marca vistos")

print("== long-poll: la espera se corta cuando el otro escribe ==")
def escribe_tarde():
    time.sleep(2)
    ch.enviar_mensaje("canal-prueba-trabajo", "agt-eqb-prueba-otroqa", "ahora si")
threading.Thread(target=escribe_tarde, daemon=True).start()
t0 = time.time()
r = ch.recibir_todo("agt-eqa-prueba-jhon", espera=20)
tardo = time.time() - t0
chk(r["canales"] and r["canales"][0]["mensajes"][0]["texto"] == "ahora si", "llegó el mensaje")
chk(1.5 < tardo < 8, f"volvió al escribir el otro, no al agotar la espera ({tardo:.1f}s)")

print("== la espera se agota sola si nadie escribe ==")
t0 = time.time()
r = ch.recibir_todo("agt-eqa-prueba-jhon", espera=3)
tardo = time.time() - t0
chk(r["canales"] == [] and 2.5 < tardo < 6, f"vuelve vacía a los ~3s ({tardo:.1f}s)")

print("== avisos útiles ==")
ch.crear_canal("canal-prueba-ayuda")
ch.unirse_canal("canal-prueba-ayuda", "agt-eqa-prueba-jhon")
r = ch.enviar_mensaje("canal-prueba-ayuda", "agt-eqa-prueba-jhon", "hola?")
chk(r.get("aviso") and "nadie más" in r["aviso"], f"avisa que no hay nadie -> {r.get('aviso')}")
falla(lambda: ch.enviar_mensaje("canal-prueba-trabajo", "agt-eqa-prueba-jhon", "   "), "vacío", "no manda mensajes vacíos")
falla(lambda: ch.recibir("canal-prueba-avisos", "x"), "no existe el canal", "canal inexistente da un mensaje claro")

print()
print("TODO OK" if not fallos else f"{len(fallos)} FALLOS: {fallos}")
raise SystemExit(1 if fallos else 0)
