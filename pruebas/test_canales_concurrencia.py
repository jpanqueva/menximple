"""Escrituras simultáneas sobre un mismo canal, contra un Qdrant desechable.

El canal es UN documento y todo lo que lo toca hace leer-modificar-guardar del
documento entero. Sin cerrojo, dos operaciones a la vez se pisan: `seq` retrocede,
el siguiente mensaje REPITE número y quien lo esperaba no lo ve nunca (pide "seq
mayor que el último que vi"). Pasó en producción el 2026-09-19: se perdieron un
RESULTADO de un worker y un mensaje de voz al usuario, con el hub diciendo
"entregado".

Aquí se reproduce el choque a propósito: uno envía, otro recibe marcando leído
(el long-poll de la app) y un tercero edita los tags (el latido de un DevOps),
todos a la vez sobre el mismo canal. Con el código viejo esta prueba falla casi
siempre; con el cerrojo no puede fallar."""
import os
import threading

os.environ.setdefault("QDRANT_URL", "http://127.0.0.1:6399")
os.environ["EMBEDDINGS_ENABLED"] = "false"

from memory_server import canales as ch, store          # noqa: E402

store.ensure_collections()
fallos = []


def chk(cond, msg):
    print(("  OK   " if cond else "  FALLO") + "  " + msg)
    if not cond:
        fallos.append(msg)


N = 60
ch.crear_canal("t-carrera", "choque de escrituras", agente="emisor", cta="jhon", tags=["tipo:voz"])
ch.unirse_canal("t-carrera", "receptor", cta="jhon")

recibidos, errores = [], []
fin = threading.Event()


def enviar():
    try:
        for i in range(N):
            ch.enviar_mensaje("t-carrera", "emisor", f"mensaje {i}")
    except Exception as e:                       # noqa: BLE001
        errores.append(f"enviar: {e}")
    finally:
        fin.set()


def recibir():
    try:
        while True:
            terminado = fin.is_set()             # se mira ANTES de leer: una vuelta más tras el último envío
            r = ch.recibir_todo("receptor", espera=0, marcar=True)
            for c in r["canales"]:
                recibidos.extend(m["texto"] for m in c["mensajes"])
            if terminado:
                break
    except Exception as e:                       # noqa: BLE001
        errores.append(f"recibir: {e}")


def editar():
    try:
        i = 0
        while not fin.is_set():
            i += 1
            ch.editar_canal("t-carrera", tags=["tipo:voz", f"latido:{i}"], cta="jhon")
    except Exception as e:                       # noqa: BLE001
        errores.append(f"editar: {e}")


def confirmar():
    """Lo que hace el puente: confirma hasta donde ya empujó, una y otra vez."""
    try:
        while not fin.is_set():
            ch.confirmar_entrega("t-carrera", "emisor", 0)
    except Exception as e:                       # noqa: BLE001
        errores.append(f"confirmar: {e}")


hilos = [threading.Thread(target=f) for f in (enviar, recibir, editar, confirmar)]
for h in hilos:
    h.start()
for h in hilos:
    h.join(timeout=180)

print("== escrituras simultáneas sobre un canal ==")
chk(not errores, f"ninguna operación falló -> {errores[:2]}")
c = ch._canal("t-carrera")
msgs = store.scroll(store.MENSAJES, must=[store.cond("canal_id", c["_id"])], limit=5000)
seqs = sorted(m["seq"] for m in msgs)
chk(len(msgs) == N, f"se guardaron los {N} mensajes -> {len(msgs)}")
chk(seqs == list(range(1, N + 1)), f"los seq van de 1 a {N} sin repetir ni saltar -> repetidos: "
    f"{sorted({s for s in seqs if seqs.count(s) > 1})[:8]}")
chk(c.get("seq") == N, f"el contador del canal quedó en {N} -> {c.get('seq')}")
chk(sorted(recibidos) == sorted(f"mensaje {i}" for i in range(N)),
    f"el receptor los vio TODOS, una vez cada uno -> vio {len(recibidos)}, distintos {len(set(recibidos))}")
chk("tipo:voz" in (c.get("tags") or []), "editar a la vez no dañó el canal")
chk({m["agente"] for m in c["miembros"]} == {"emisor", "receptor"}, "nadie se cayó del canal")

print("== un contador atrasado se corrige solo ==")
# El estado que dejó el fallo en producción: mensajes con seq mayor que el del canal.
c = ch._canal("t-carrera")
c["seq"] = N - 5
store.upsert(store.CANALES, c["_id"], c)
r = ch.enviar_mensaje("t-carrera", "emisor", "después del daño")
chk(r["seq"] == N + 1, f"el mensaje nuevo NO repite número -> seq {r['seq']}")
chk(ch._canal("t-carrera").get("seq") == N + 1, "y el contador del canal queda corregido")

ch.borrar_canal("t-carrera", cta="jhon")
print()
print("TODO OK" if not fallos else f"{len(fallos)} FALLO(S)")
raise SystemExit(1 if fallos else 0)
