"""Prueba las capacidades nuevas del hub contra un Qdrant desechable."""
import os

os.environ.setdefault("QDRANT_URL", "http://127.0.0.1:6399")
os.environ["EMBEDDINGS_ENABLED"] = "false"

from memory_server import repository as repo, store          # noqa: E402
from memory_server.models import MemoriaError                # noqa: E402

store.ensure_collections()
CTA = "prueba"
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


try:
    repo.crear_cuenta(CTA, "Cuenta de prueba")
except Exception:
    pass

print("== carpetas por RUTA (antes exigía uuid) ==")
raiz = repo.crear_carpeta(CTA, "acme")
sub = repo.crear_carpeta(CTA, "clientes", parent_id="acme")
hoja = repo.crear_carpeta(CTA, "rips", parent_id="acme/clientes")
chk(hoja["path"] == ["acme", "clientes"], f"padre resuelto por ruta -> {hoja['path']}")
chk(sub["parent_id"] == raiz["id"], "parent_id guardado es el uuid, no la ruta")

print("== crear con estado, por ruta ==")
e1 = repo.crear_entrada(CTA, "acme/clientes/rips", "Migrar el cruce de RIPS",
                        "como migrar el cruce de rips del cliente acme",
                        "Paso 1: revisar el mapeo.\nOJO: el CUPS viene sin ceros.",
                        "skill", ["rips"], estado="pendiente")
e2 = repo.crear_entrada(CTA, "acme/clientes/rips", "Token de la API de acme",
                        "credenciales y token de acceso al api de acme",
                        "TOKEN=abc123xyz", "credencial", ["acme"])
chk(e1["folder_id"] == hoja["id"], "la entrada quedó en la carpeta resuelta por ruta")
chk(e1["estado"] == "pendiente", f"estado guardado -> {e1['estado']}")
chk(e2["estado"] is None, "una credencial puede no tener estado")
falla(lambda: repo.crear_entrada(CTA, "acme", "x", "y", "z", "skill", None, "terminado"),
      "estado inválido", "rechaza un estado inventado")

print("== anexar sin reenviar el contexto ==")
antes = repo.obtener_entrada(CTA, str(e1["numero"]))["contexto"]
an = repo.anexar_entrada(CTA, str(e1["numero"]), "Hallazgo: el pagador 12 usa otro formato.")
ahora = repo.obtener_entrada(CTA, str(e1["numero"]))["contexto"]
chk(ahora.startswith(antes.rstrip()), "lo anterior quedó INTACTO")
chk("pagador 12" in ahora, "lo nuevo se agregó")
chk("aviso" in an, "avisa que el resumen quedó viejo")
an2 = repo.anexar_entrada(CTA, str(e1["numero"]), "Cerrado.",
                          resumen="migrar el cruce de rips de acme, ya cerrado",
                          estado="hecho")
chk("aviso" not in an2, "si actualizas el resumen, no avisa")
chk(an2["estado"] == "hecho", "anexar puede cambiar el estado")
chk(len(repo.ver_historial(CTA, str(e1["numero"]))["versiones"]) == 2,
    "cada anexo dejó su versión en el historial")

print("== editar sin contexto NO borra el cuerpo ==")
cuerpo = repo.obtener_entrada(CTA, str(e1["numero"]))["contexto"]
repo.editar_entrada(CTA, str(e1["numero"]), titulo="Migrar el cruce de RIPS (acme)")
chk(repo.obtener_entrada(CTA, str(e1["numero"]))["contexto"] == cuerpo,
    "el contexto sobrevivió a editar solo el título")

print("== filtrar por estado ==")
e3 = repo.crear_entrada(CTA, "acme/clientes/rips", "Revisar glosas", "revisar glosas del mes",
                        "pendiente de revisar", "general", None, estado="pendiente")
pend = repo.buscar(CTA, estado="pendiente")
chk({p["numero"] for p in pend} == {e3["numero"]},
    f"solo la pendiente -> {[p['numero'] for p in pend]}")
chk(all("estado" in p for p in pend), "el estado sale en el resultado")

print("== alcance: resumen vs completo ==")
# "ceros" solo está en el CUERPO de e1; "glosas" solo en el resumen de e3.
# Con alcance normal el cuerpo exige la FRASE ENTERA, así que "ceros glosas" no
# casa e1. Con alcance completo basta una palabra suelta y sí lo trae.
sup = [p["numero"] for p in repo.buscar(CTA, query="ceros glosas")]
prof = [p["numero"] for p in repo.buscar(CTA, query="ceros glosas", alcance="completo")]
chk(e1["numero"] not in sup, f"alcance resumen NO trae la del cuerpo -> {sup}")
chk(e1["numero"] in prof, f"alcance completo SÍ la trae -> {prof}")
# Y una palabra suelta ya entraba al cuerpo desde antes: eso no cambió.
chk(e1["numero"] in [p["numero"] for p in repo.buscar(CTA, query="ceros")],
    "una sola palabra sigue entrando al cuerpo con el alcance normal")
falla(lambda: repo.buscar(CTA, query="x", alcance="hondo"),
      "alcance inválido", "rechaza un alcance inventado")

print("== respuesta compacta ==")
r = repo.buscar(CTA, query="rips")
chk(r and "cuenta" not in r[0] and "version" not in r[0],
    f"compacta por defecto -> {sorted(r[0].keys())}")
d = repo.buscar(CTA, query="rips", detallado=True)
chk("id" in d[0] and "version" in d[0], "detallado=True trae todo")
chk(len(str(r)) < len(str(d)), f"compacta pesa menos ({len(str(r))} vs {len(str(d))} chars)")

print("== buscar filtrando por RUTA de carpeta ==")
chk(len(repo.buscar(CTA, folder_id="acme/clientes/rips")) == 3, "folder_id acepta ruta")

print("== arbol: ruta, y el estado a la vista ==")
t = repo.arbol(CTA, folder_id="acme/clientes")["texto"]
chk("rips/" in t, "arbol acepta la ruta como folder_id")
chk("[pendiente]" in t, "el estado se ve en el árbol")
mapa = repo.arbol(CTA, con_memorias=False, profundidad=3)
chk("#" not in mapa["texto"], "el mapa barato no trae memorias")

print("== mover por ruta ==")
otra = repo.crear_carpeta(CTA, "archivo", parent_id="acme")
mov = repo.editar_entrada(CTA, str(e3["numero"]), mover_a="acme/archivo")
chk(mov["folder_id"] == otra["id"], f"movida por ruta -> {mov['path']}")

print()
print("TODO OK" if not fallos else f"{len(fallos)} FALLOS: {fallos}")
raise SystemExit(1 if fallos else 0)
