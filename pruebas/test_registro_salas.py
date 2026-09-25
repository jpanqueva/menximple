"""Catálogo, nomenclatura estricta, salas sin tope y mensajes dirigidos.

Es lo que pidió el usuario tras una semana de agentes con nombres inventados:
que lo que no siga la nomenclatura falle de frente, que un canal sea una sala
(IRC) donde un mensaje puede ir dirigido a uno, y que se vea quién está en cada
canal, cuándo habló y cuánto tiene sin leer."""
import os

os.environ.setdefault("QDRANT_URL", "http://127.0.0.1:6399")
os.environ["EMBEDDINGS_ENABLED"] = "false"

from memory_server import canales as ch, registro as rg, store  # noqa: E402
from memory_server.models import MemoriaError                   # noqa: E402

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


print("== catálogo ==")
r = rg.crear("equipo", "Reg1", cta="jhon", hostname="MI-PC", tipo="pc", dueno="jhon")
chk(r["nombre"] == "reg1" and r["hostname"] == "mi-pc", "el equipo se normaliza a minúsculas")
falla(lambda: rg.crear("equipo", "reg2", hostname="mi-pc", tipo="pc"), "ya es del equipo",
      "dos equipos no comparten hostname")
falla(lambda: rg.crear("equipo", "reg3", tipo="pc"), "necesita hostname", "un equipo sin hostname se rechaza")
falla(lambda: rg.crear("equipo", "reg-4", hostname="h4", tipo="pc"), "inválido", "guiones en el nombre se rechazan")
falla(lambda: rg.crear("ambito", "amb1"), "necesita tipo", "un ámbito sin tipo se rechaza")
rg.crear("ambito", "amb1", tipo="empresa")
falla(lambda: rg.crear("agente", "agt-reg1-amb1-x"), "se registran solos", "los agentes no se crean a mano")
chk([x["nombre"] for x in rg.ver("equipo", hostname="mi-pc")] == ["reg1"], "se encuentra un equipo por hostname")
chk({x["nombre"] for x in rg.ver("actividad")} >= set(rg.ACTIVIDADES_BASE), "las actividades base están sembradas")
rg.crear("actividad", "pruebas", descripcion="para probar")
chk(any(x["nombre"] == "pruebas" for x in rg.ver("actividad")), "se puede ampliar el vocabulario")

print("== nombres ==")
falla(lambda: rg.partes_agente("agt-reg1-amb1"), "inválido", "faltan partes")
falla(lambda: rg.partes_agente("agt-reg1-nada-x1"), "no está en el catálogo", "ámbito desconocido")
chk(rg.partes_agente("AGT-REG1-AMB1-CEO") == ("reg1", "amb1", "ceo"), "se acepta en cualquier caja")
chk(rg.validar_canal("canal-amb1-pruebas")["ambito"] == "amb1", "canal de ámbito")
chk(rg.validar_canal("canal-eqa-reg1-pruebas")["equipos"] == ["eqa", "reg1"], "canal entre dos equipos")
falla(lambda: rg.validar_canal("canal-reg1-eqa-pruebas"), "orden alfabético", "equipos desordenados")
falla(lambda: rg.validar_canal("canal-reg1-reg1-pruebas"), "distintos", "el mismo equipo dos veces")

print("== los agentes se registran solos, con su última vez ==")
ch.crear_canal("canal-amb1-trabajo", "sala de amb1", agente="agt-reg1-amb1-ceo", cta="jhon")
ag = rg.ver("agente", nombre="agt-reg1-amb1-ceo")
chk(len(ag) == 1 and ag[0]["equipo"] == "reg1" and ag[0]["ambito"] == "amb1" and ag[0]["rol"] == "ceo",
    f"quedó en el catálogo con sus partes -> {ag}")
chk(ag[0]["visto"] is not None, "y con la hora en que se le vio")

print("== sala con varios y mensajes dirigidos ==")
for a in ("agt-eqa-amb1-w1", "agt-eqb-amb1-w2", "agt-eqc-amb1-w3"):
    ch.unirse_canal("canal-amb1-trabajo", a, cta="jhon")
c = ch.listar_canales("jhon")[0] if ch.listar_canales("jhon")[0]["nombre"] == "canal-amb1-trabajo" else \
    next(x for x in ch.listar_canales("jhon") if x["nombre"] == "canal-amb1-trabajo")
chk(len(c["agentes"]) == 4, f"cuatro en la sala -> {c['agentes']}")
chk("tipo:trabajo" in c["tags"] and "proyecto:amb1" in c["tags"], f"los tags salen del nombre -> {c['tags']}")

r = ch.enviar_mensaje("canal-amb1-trabajo", "agt-reg1-amb1-ceo", "empiezo; w1, revisa el disco",
                      para="agt-eqa-amb1-w1")
chk(r["para"] == ["agt-eqa-amb1-w1"], f"el dirigido dice a quién va -> {r['para']}")
falla(lambda: ch.enviar_mensaje("canal-amb1-trabajo", "agt-reg1-amb1-ceo", "x", para="agt-eqb-otro-nadie"),
      "no está en el canal", "no se puede dirigir a quien no está")
falla(lambda: ch.enviar_mensaje("canal-amb1-trabajo", "agt-reg1-amb1-ceo", "x", para="agt-reg1-amb1-ceo"),
      "tú mismo", "ni a uno mismo")
r = ch.enviar_mensaje("canal-amb1-trabajo", "agt-reg1-amb1-ceo", "aviso para todos: hoy cerramos a las 6")
chk(sorted(r["para"]) == ["agt-eqa-amb1-w1", "agt-eqb-amb1-w2", "agt-eqc-amb1-w3"],
    f"sin `para` va a todos los demás -> {r['para']}")

w1 = ch.recibir("canal-amb1-trabajo", "agt-eqa-amb1-w1")["mensajes"]
w2 = ch.recibir("canal-amb1-trabajo", "agt-eqb-amb1-w2")["mensajes"]
chk([m["texto"][:7] for m in w1] == ["empiezo", "aviso p"], f"w1 recibe el dirigido y el general -> {[m['texto'][:7] for m in w1]}")
chk([m["texto"][:7] for m in w2] == ["aviso p"], f"w2 recibe solo el general -> {[m['texto'][:7] for m in w2]}")
chk(w1[0]["para"] == "agt-eqa-amb1-w1" and w1[1]["para"] is None, "cada mensaje dice si iba dirigido")
chk(ch.recibir("canal-amb1-trabajo", "agt-eqb-amb1-w2")["mensajes"] == [], "y a w2 no se le vuelve a entregar el dirigido a otro")

print("== recibir_de_todos respeta el destinatario ==")
ch.enviar_mensaje("canal-amb1-trabajo", "agt-eqb-amb1-w2", "ceo, terminé", para="agt-reg1-amb1-ceo")
r3 = ch.recibir_todo("agt-eqc-amb1-w3")
chk([m["texto"] for c in r3["canales"] for m in c["mensajes"]] == ["aviso para todos: hoy cerramos a las 6"],
    "w3 solo tiene el general pendiente")
rc = ch.recibir_todo("agt-reg1-amb1-ceo")
chk([m["texto"] for c in rc["canales"] for m in c["mensajes"]] == ["ceo, terminé"], "el ceo recibe lo dirigido a él")

print("== lo dirigido a otros no queda como pendiente de nadie ==")
ch.enviar_mensaje("canal-amb1-trabajo", "agt-reg1-amb1-ceo", "w2, lo tuyo", para="agt-eqb-amb1-w2")
r = ch.recibir_todo("agt-eqc-amb1-w3", marcar=False)     # como el puente: nada para w3
chk(r["canales"] == [], "w3 no recibe lo dirigido a w2")
c3 = next(x for x in ch.listar_canales("jhon") if x["nombre"] == "canal-amb1-trabajo")
f3 = {m["agente"]: m for m in c3["miembros"]}
chk(f3["agt-eqc-amb1-w3"]["pendientes"] == 0, f"y no le queda como pendiente -> {f3['agt-eqc-amb1-w3']['pendientes']}")
chk(f3["agt-eqb-amb1-w2"]["pendientes"] == 1, f"a w2 sí -> {f3['agt-eqb-amb1-w2']['pendientes']}")
ch.recibir("canal-amb1-trabajo", "agt-eqb-amb1-w2")

print("== fichas de miembros ==")
ch.enviar_mensaje("canal-amb1-trabajo", "agt-eqb-amb1-w2", "aviso general: cierro a las 6")   # para todos
c = next(x for x in ch.listar_canales("jhon") if x["nombre"] == "canal-amb1-trabajo")
f = {m["agente"]: m for m in c["miembros"]}
chk(f["agt-reg1-amb1-ceo"]["ultimo_escribio"] is not None, "se sabe cuándo escribió el ceo")
chk(f["agt-eqa-amb1-w1"]["ultimo_escribio"] is None and f["agt-eqa-amb1-w1"]["ultimo_leyo"] is not None,
    "w1 no ha escrito pero sí leyó")
chk(f["agt-eqa-amb1-w1"]["pendientes"] == 1 and f["agt-eqb-amb1-w2"]["pendientes"] == 0 and f["agt-reg1-amb1-ceo"]["pendientes"] == 1,
    f"pendientes = solo lo que es para cada uno -> w1 {f['agt-eqa-amb1-w1']['pendientes']}, w2 (lo escribió) {f['agt-eqb-amb1-w2']['pendientes']}, ceo {f['agt-reg1-amb1-ceo']['pendientes']}")
chk(c["mensajes"] == 5 and c["ultimo_mensaje"] is not None, "total de mensajes y hora del último")

ch.borrar_canal("canal-amb1-trabajo", "jhon")
print()
print("TODO OK" if not fallos else f"{len(fallos)} FALLOS: {fallos}")
raise SystemExit(1 if fallos else 0)
