"""Los dos defectos que salieron en el primer uso real."""
import os
os.environ.setdefault("QDRANT_URL", "http://127.0.0.1:6399")
os.environ["EMBEDDINGS_ENABLED"] = "false"
from memory_server import canales as ch, store          # noqa: E402
from memory_server.models import MemoriaError           # noqa: E402

store.ensure_collections()
import _catalogo  # noqa: E402,F401
fallos = []
def chk(c, m):
    print(("  OK   " if c else "  FALLO") + "  " + m)
    if not c: fallos.append(m)

print("== crear_canal mete al creador ==")
r = ch.crear_canal("canal-prueba-comunicacion", "x", agente="agt-eqa-prueba-creador")
chk(r["agentes"] == ["agt-eqa-prueba-creador"], f"queda dentro -> {r['agentes']}")
# y por tanto puede escribir de una, sin unirse aparte
ch.enviar_mensaje("canal-prueba-comunicacion", "agt-eqa-prueba-creador", "primer mensaje")
chk(True, "puede escribir sin unirse_canal aparte")
r = ch.crear_canal("canal-prueba-soporte")
chk(r["agentes"] == [], "sin agente sigue creando el canal vacio (compatible)")

print("== EL CASO REAL: escribo, y el otro entra despues ==")
ch.crear_canal("canal-eqa-eqb-ayuda", agente="agt-eqa-prueba-primero")
ch.enviar_mensaje("canal-eqa-eqb-ayuda", "agt-eqa-prueba-primero", "aqui van los 7 puntos")
ch.enviar_mensaje("canal-eqa-eqb-ayuda", "agt-eqa-prueba-primero", "y un octavo")
r = ch.unirse_canal("canal-eqa-eqb-ayuda", "agt-eqb-prueba-segundo")
chk("te_esperan" in r, f"al entrar le avisa que hay algo -> {r.get('te_esperan')}")
msgs = ch.recibir("canal-eqa-eqb-ayuda", "agt-eqb-prueba-segundo")["mensajes"]
chk([m["texto"] for m in msgs] == ["aqui van los 7 puntos", "y un octavo"],
    f"SI ve lo escrito antes de llegar -> {[m['texto'] for m in msgs]}")
chk(ch.recibir("canal-eqa-eqb-ayuda", "agt-eqb-prueba-segundo")["mensajes"] == [], "y no se repite")

print("== el historial se topa para no volcar un canal entero ==")
ch.crear_canal("canal-eqa-eqb-trabajo", agente="agt-eqa-prueba-viejo")
for i in range(30):
    ch.enviar_mensaje("canal-eqa-eqb-trabajo", "agt-eqa-prueba-viejo", f"m{i}")
r = ch.unirse_canal("canal-eqa-eqb-trabajo", "agt-eqb-prueba-nuevo")
chk("recortado" in r, f"avisa que recorto -> {r.get('recortado')}")
msgs = ch.recibir("canal-eqa-eqb-trabajo", "agt-eqb-prueba-nuevo")["mensajes"]
chk(len(msgs) == ch.RETROCESO, f"trae los ultimos {ch.RETROCESO} -> {len(msgs)}")
chk(msgs[-1]["texto"] == "m29", f"y el ultimo es el mas nuevo -> {msgs[-1]['texto']}")

print()
print("TODO OK" if not fallos else f"{len(fallos)} FALLOS: {fallos}")
raise SystemExit(1 if fallos else 0)
