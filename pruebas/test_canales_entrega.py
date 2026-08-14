"""Los dos defectos que salieron en el primer uso real."""
import os
os.environ.setdefault("QDRANT_URL", "http://127.0.0.1:6399")
os.environ["EMBEDDINGS_ENABLED"] = "false"
from memory_server import canales as ch, store          # noqa: E402
from memory_server.models import MemoriaError           # noqa: E402

store.ensure_collections()
fallos = []
def chk(c, m):
    print(("  OK   " if c else "  FALLO") + "  " + m)
    if not c: fallos.append(m)

print("== crear_canal mete al creador ==")
r = ch.crear_canal("con-agente", "x", agente="creador")
chk(r["agentes"] == ["creador"], f"queda dentro -> {r['agentes']}")
# y por tanto puede escribir de una, sin unirse aparte
ch.enviar_mensaje("con-agente", "creador", "primer mensaje")
chk(True, "puede escribir sin unirse_canal aparte")
r = ch.crear_canal("sin-agente")
chk(r["agentes"] == [], "sin agente sigue creando el canal vacio (compatible)")

print("== EL CASO REAL: escribo, y el otro entra despues ==")
ch.crear_canal("feedback", agente="primero")
ch.enviar_mensaje("feedback", "primero", "aqui van los 7 puntos")
ch.enviar_mensaje("feedback", "primero", "y un octavo")
r = ch.unirse_canal("feedback", "segundo")
chk("te_esperan" in r, f"al entrar le avisa que hay algo -> {r.get('te_esperan')}")
msgs = ch.recibir("feedback", "segundo")["mensajes"]
chk([m["texto"] for m in msgs] == ["aqui van los 7 puntos", "y un octavo"],
    f"SI ve lo escrito antes de llegar -> {[m['texto'] for m in msgs]}")
chk(ch.recibir("feedback", "segundo")["mensajes"] == [], "y no se repite")

print("== el historial se topa para no volcar un canal entero ==")
ch.crear_canal("largo", agente="viejo")
for i in range(30):
    ch.enviar_mensaje("largo", "viejo", f"m{i}")
r = ch.unirse_canal("largo", "nuevo")
chk("recortado" in r, f"avisa que recorto -> {r.get('recortado')}")
msgs = ch.recibir("largo", "nuevo")["mensajes"]
chk(len(msgs) == ch.RETROCESO, f"trae los ultimos {ch.RETROCESO} -> {len(msgs)}")
chk(msgs[-1]["texto"] == "m29", f"y el ultimo es el mas nuevo -> {msgs[-1]['texto']}")

print()
print("TODO OK" if not fallos else f"{len(fallos)} FALLOS: {fallos}")
raise SystemExit(1 if fallos else 0)
