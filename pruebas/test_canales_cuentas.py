"""Aislamiento por cuenta, borrado y filtro de rango."""
import os, time
os.environ.setdefault("QDRANT_URL", "http://127.0.0.1:6399")
os.environ["EMBEDDINGS_ENABLED"] = "false"
from memory_server import canales as ch, store          # noqa: E402
from memory_server.models import MemoriaError           # noqa: E402
store.ensure_collections()
fallos = []
def chk(c, m):
    print(("  OK   " if c else "  FALLO") + "  " + m)
    if not c: fallos.append(m)
def falla(fn, trozo, m):
    try: fn(); chk(False, m + " (no lanzó)")
    except MemoriaError as e: chk(trozo in str(e), f"{m} -> {e}")

print("== el catalogo ya no filtra la cuenta ajena ==")
ch.crear_canal("de-jhon", "cosas privadas de jhon", agente="j1", cta="jhon")
ch.crear_canal("de-vivi", "cosas de viviana", agente="v1", cta="viviana")
mios = [c["nombre"] for c in ch.listar_canales("jhon")]
chk(mios == ["de-jhon"], f"jhon solo ve el suyo -> {mios}")
suyos = [c["nombre"] for c in ch.listar_canales("viviana")]
chk(suyos == ["de-vivi"], f"viviana solo ve el suyo -> {suyos}")

print("== pero se puede entrar al ajeno por nombre exacto ==")
ch.unirse_canal("de-jhon", "v2", cta="viviana")
chk("de-jhon" in [c["nombre"] for c in ch.listar_canales("viviana")],
    "y desde entonces le aparece en su lista")
ch.enviar_mensaje("de-jhon", "v2", "hola desde otra cuenta")
chk(ch.recibir("de-jhon", "j1")["mensajes"][0]["texto"] == "hola desde otra cuenta",
    "y se hablan de verdad entre cuentas")

print("== borrar canal ==")
falla(lambda: ch.borrar_canal("de-vivi", "jhon"), "no es un canal tuyo",
      "no puedo borrar el de otro")
r = ch.borrar_canal("de-jhon", "jhon")
chk(r["mensajes_borrados"] == 1, f"borra tambien sus mensajes -> {r}")
falla(lambda: ch.recibir("de-jhon", "j1"), "no existe el canal", "el canal ya no existe")
chk(len(store.scroll(store.MENSAJES, must=[store.cond("de", "v2")], limit=50)) == 0,
    "no quedan mensajes huerfanos")

print("== el filtro de rango trae lo mismo que antes ==")
ch.crear_canal("rango", agente="a", cta="x")
ch.unirse_canal("rango", "b", cta="x")
for i in range(5):
    ch.enviar_mensaje("rango", "a", f"m{i}")
r = ch.recibir("rango", "b")
chk([m["texto"] for m in r["mensajes"]] == ["m0","m1","m2","m3","m4"],
    f"los 5 en orden -> {[m['texto'] for m in r['mensajes']]}")
chk(ch.recibir("rango", "b")["mensajes"] == [], "y ya no vuelven")
ch.enviar_mensaje("rango", "a", "nuevo")
chk([m["texto"] for m in ch.recibir("rango","b")["mensajes"]] == ["nuevo"],
    "solo lo posterior a la marca")

print()
print("TODO OK" if not fallos else f"{len(fallos)} FALLOS: {fallos}")
raise SystemExit(1 if fallos else 0)
