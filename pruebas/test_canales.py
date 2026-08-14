"""Canales entre agentes, contra un Qdrant desechable."""
import os
import threading
import time

os.environ.setdefault("QDRANT_URL", "http://127.0.0.1:6399")
os.environ["EMBEDDINGS_ENABLED"] = "false"

from memory_server import canales as ch, store          # noqa: E402
from memory_server.models import MemoriaError           # noqa: E402

store.ensure_collections()
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
ch.crear_canal("qa", "pruebas del piloto")
ch.crear_canal("deploy")
chk({c["nombre"] for c in ch.listar_canales()} >= {"qa", "deploy"}, "los dos canales existen")
falla(lambda: ch.crear_canal("QA"), "ya existe", "el nombre se normaliza y no se duplica")

print("== dos por canal, ni uno más ==")
ch.unirse_canal("qa", "jhon-windows")
ch.unirse_canal("qa", "qa-ubuntu")
falla(lambda: ch.unirse_canal("qa", "tercero"), "ya tiene sus 2", "rechaza al tercero")
r = ch.unirse_canal("qa", "jhon-windows")
chk(r.get("reentro"), "reentrar con el mismo nombre no es error")

print("== un agente en VARIOS canales ==")
ch.unirse_canal("deploy", "jhon-windows")
ch.unirse_canal("deploy", "sop-server")
mios = [c["nombre"] for c in ch.mis_canales("jhon-windows")]
chk(sorted(mios) == ["deploy", "qa"], f"jhon-windows está en los dos -> {mios}")

print("== enviar y recibir ==")
falla(lambda: ch.enviar_mensaje("qa", "colado", "hola"), "no está en el canal",
      "no se puede escribir sin estar dentro")
ch.enviar_mensaje("qa", "jhon-windows", "corré las pruebas del armado")
r = ch.recibir("qa", "qa-ubuntu")
chk([m["texto"] for m in r["mensajes"]] == ["corré las pruebas del armado"], "le llegó al otro")
chk(ch.recibir("qa", "qa-ubuntu")["mensajes"] == [], "no se repite: quedó marcado como visto")
chk(ch.recibir("qa", "jhon-windows")["mensajes"] == [], "no te llega tu propio mensaje")

print("== quien llega después SÍ lee lo que se dijo antes ==")
# Cambiado a propósito: la primera versión ponía la marca en el último mensaje y
# eso perdía en silencio el mensaje que uno deja esperando a que el otro entre.
ch.salir_canal("qa", "qa-ubuntu")
ch.unirse_canal("qa", "otro-qa")
chk([m["texto"] for m in ch.recibir("qa", "otro-qa")["mensajes"]] ==
    ["corré las pruebas del armado"], "lee lo anterior al entrar")

print("== recibir_de_todos junta los canales ==")
ch.enviar_mensaje("qa", "otro-qa", "listo, 12 pruebas OK")
ch.enviar_mensaje("deploy", "sop-server", "desplegado en produccion")
r = ch.recibir_todo("jhon-windows")
chk({c["canal"] for c in r["canales"]} == {"qa", "deploy"},
    f"trae los dos canales -> {[c['canal'] for c in r['canales']]}")
chk(ch.recibir_todo("jhon-windows")["canales"] == [], "y los marca vistos")

print("== long-poll: la espera se corta cuando el otro escribe ==")
def escribe_tarde():
    time.sleep(2)
    ch.enviar_mensaje("qa", "otro-qa", "ahora si")
threading.Thread(target=escribe_tarde, daemon=True).start()
t0 = time.time()
r = ch.recibir_todo("jhon-windows", espera=20)
tardo = time.time() - t0
chk(r["canales"] and r["canales"][0]["mensajes"][0]["texto"] == "ahora si", "llegó el mensaje")
chk(1.5 < tardo < 8, f"volvió al escribir el otro, no al agotar la espera ({tardo:.1f}s)")

print("== la espera se agota sola si nadie escribe ==")
t0 = time.time()
r = ch.recibir_todo("jhon-windows", espera=3)
tardo = time.time() - t0
chk(r["canales"] == [] and 2.5 < tardo < 6, f"vuelve vacía a los ~3s ({tardo:.1f}s)")

print("== avisos útiles ==")
ch.crear_canal("solo")
ch.unirse_canal("solo", "jhon-windows")
r = ch.enviar_mensaje("solo", "jhon-windows", "hola?")
chk(r.get("aviso") and "nadie más" in r["aviso"], f"avisa que no hay nadie -> {r.get('aviso')}")
falla(lambda: ch.enviar_mensaje("qa", "jhon-windows", "   "), "vacío", "no manda mensajes vacíos")
falla(lambda: ch.recibir("inexistente", "x"), "no existe el canal", "canal inexistente da un mensaje claro")

print()
print("TODO OK" if not fallos else f"{len(fallos)} FALLOS: {fallos}")
raise SystemExit(1 if fallos else 0)
