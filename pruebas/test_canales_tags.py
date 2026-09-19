"""Tags de canales, contra un Qdrant desechable.

Los tags dicen QUÉ ES un canal (proyecto, tipo, si lleva acuse) y viajan con la
entrega para que el puente los ponga en el evento. No cambian la membresía ni la
entrega: un canal sin tags tiene que seguir funcionando exactamente igual."""
import os

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


print("== crear con tags ==")
c = ch.crear_canal("t-voz", "canal de voz", agente="ceo", cta="jhon",
                   tags=["Proyecto:Sagente", " tipo:voz ", "tipo:voz"])
chk(c["tags"] == ["proyecto:sagente", "tipo:voz"], f"se normalizan y no se repiten -> {c['tags']}")
c2 = ch.crear_canal("t-viejo", "sin tags", agente="ceo", cta="jhon")
chk(c2["tags"] == [], "un canal sin tags devuelve lista vacía, no falta la clave")
c3 = ch.crear_canal("t-texto", agente="ceo", cta="jhon", tags="proyecto:otro, efimero")
chk(c3["tags"] == ["proyecto:otro", "efimero"], "acepta también una cadena separada por comas")

print("== validación ==")
falla(lambda: ch.crear_canal("t-malo", tags=["x" * 41]), "pasa de", "un tag demasiado largo se rechaza")
falla(lambda: ch.crear_canal("t-muchos", tags=[f"t{i}" for i in range(9)]), "máximo", "más de 8 tags se rechaza")
chk(not any(x["nombre"] in ("t-malo", "t-muchos") for x in ch.listar_canales("jhon")),
    "si los tags están mal, el canal NO queda creado a medias")

print("== filtrar ==")
nombres = lambda cs: sorted(x["nombre"] for x in cs)          # noqa: E731
chk(nombres(ch.listar_canales("jhon", ["proyecto:sagente"])) == ["t-voz"], "filtro exacto")
chk(nombres(ch.listar_canales("jhon", ["proyecto:"])) == ["t-texto", "t-voz"], "un tag acabado en ':' casa por prefijo")
chk(nombres(ch.listar_canales("jhon", ["proyecto:sagente", "tipo:pantalla"])) == [], "varios tags = todos a la vez (Y, no O)")
chk({"t-voz", "t-viejo", "t-texto"} <= set(nombres(ch.listar_canales("jhon"))), "sin filtro salen todos, como antes")
chk(nombres(ch.mis_canales("ceo", ["efimero"])) == ["t-texto"], "mis_canales filtra igual")
chk(len(ch.mis_canales("ceo")) >= 3, "mis_canales sin filtro sigue trayendo todos")

print("== editar ==")
e = ch.editar_canal("t-viejo", tags=["proyecto:sagente", "sin-acuse"], cta="jhon")
chk(e["tags"] == ["proyecto:sagente", "sin-acuse"] and e["descripcion"] == "sin tags",
    "editar tags no toca la descripción")
e = ch.editar_canal("t-viejo", descripcion="ahora con descripción", cta="jhon")
chk(e["tags"] == ["proyecto:sagente", "sin-acuse"] and e["descripcion"] == "ahora con descripción",
    "editar descripción no toca los tags")
e = ch.editar_canal("t-viejo", tags=["tipo:avisos"], cta="jhon")
chk(e["tags"] == ["tipo:avisos"], "los tags REEMPLAZAN, no se suman")
e = ch.editar_canal("t-viejo", tags=[], cta="jhon")
chk(e["tags"] == [], "tags=[] los quita todos")
falla(lambda: ch.editar_canal("t-viejo", cta="jhon"), "nada que cambiar", "editar sin argumentos avisa")
falla(lambda: ch.editar_canal("t-voz", tags=["x"], cta="viviana"), "no es un canal tuyo",
      "otra cuenta no puede editar un canal ajeno")
chk(len(ch.mis_canales("ceo")) >= 3 and "ceo" in ch.listar_canales("jhon", ["proyecto:sagente"])[0]["agentes"],
    "editar no saca a nadie del canal")

print("== los tags viajan con la entrega ==")
ch.unirse_canal("t-voz", "app", cta="jhon")
ch.enviar_mensaje("t-voz", "app", "hola ceo")
r = ch.recibir_todo("ceo", marcar=False)
ent = next(x for x in r["canales"] if x["canal"] == "t-voz")
chk(ent["tags"] == ["proyecto:sagente", "tipo:voz"], f"recibir_todo trae los tags del canal -> {ent['tags']}")
chk(ent["mensajes"][0]["texto"] == "hola ceo", "y el mensaje llega igual que siempre")
r1 = ch.recibir("t-voz", "ceo")
chk(r1["tags"] == ["proyecto:sagente", "tipo:voz"], "recibir (un canal) también los trae")
ch.unirse_canal("t-texto", "otro", cta="jhon")
ch.editar_canal("t-texto", tags=[], cta="jhon")
ch.enviar_mensaje("t-texto", "otro", "sin tags")
r = ch.recibir_todo("ceo", marcar=False)
ent = next(x for x in r["canales"] if x["canal"] == "t-texto")
chk(ent["tags"] == [], "un canal sin tags entrega lista vacía")

for n in ("t-voz", "t-viejo", "t-texto"):
    ch.borrar_canal(n, "jhon")

print()
print("TODO OK" if not fallos else f"{len(fallos)} FALLOS: {fallos}")
raise SystemExit(1 if fallos else 0)
