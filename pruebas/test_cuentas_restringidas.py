"""Cuentas restringidas, de punta a punta contra un hub de prueba (HTTP real).

Lo levanta quien corre esto (ver más abajo): un hub con su Qdrant desechable,
ADMIN_TOKEN fijo. Crea las cuentas y la bandera directamente en el Qdrant de
prueba con el repositorio, y habla con el hub por HTTP como cualquier cliente.

  HUB=http://127.0.0.1:8099/mcp QDRANT_URL=http://...:6333 python pruebas/test_cuentas_restringidas.py
"""
import json, os, urllib.request
os.environ["EMBEDDINGS_ENABLED"] = "false"
from memory_server import repository as repo, store, canales as ch   # noqa: E402
store.ensure_collections()
import _catalogo  # noqa: E402,F401

HUB = os.environ.get("HUB", "http://127.0.0.1:8099/mcp")
fallos = []
def chk(c, m):
    print(("  OK   " if c else "  FALLO") + "  " + m)
    if not c: fallos.append(m)

class Cliente:
    def __init__(self, key):
        self.key, self.sid = key, None
        self._post({"jsonrpc": "2.0", "id": 1, "method": "initialize", "params": {
            "protocolVersion": "2025-03-26", "capabilities": {}, "clientInfo": {"name": "t", "version": "1"}}})
        self._post({"jsonrpc": "2.0", "method": "notifications/initialized"})
    def _post(self, body):
        h = {"Content-Type": "application/json", "Accept": "application/json, text/event-stream"}
        if self.key: h["X-API-Key"] = self.key
        if self.sid: h["mcp-session-id"] = self.sid
        r = urllib.request.urlopen(urllib.request.Request(HUB, json.dumps(body).encode(), h))
        self.sid = self.sid or r.headers.get("mcp-session-id")
        t = r.read().decode()
        for l in t.splitlines():
            if l.startswith("data:"): return json.loads(l[5:])
        return json.loads(t) if t.strip() else None
    def tool(self, n, **a):
        r = self._post({"jsonrpc": "2.0", "id": 2, "method": "tools/call", "params": {"name": n, "arguments": a}})["result"]
        texto = " ".join(c.get("text", "") for c in r.get("content", []))
        return (not r.get("isError")), (r.get("structuredContent") or texto), texto

def ok(cli, n, m, **a):
    bien, res, t = cli.tool(n, **a); chk(bien, f"{m} -> {t[:120]}"); return res
def no(cli, n, trozo, m, **a):
    bien, res, t = cli.tool(n, **a); chk((not bien) and trozo in t, f"{m} -> {t[:140]}")

K_J = repo.crear_cuenta("jhonp")["apikey"]
K_V = repo.crear_cuenta("vivip")["apikey"]
K_R = repo.crear_cuenta("estudiop")["apikey"]
repo.marcar_restringida("estudiop")
chk(any(c.get("restringida") for c in repo.listar_cuentas() if c["cuenta"] == "estudiop"), "listar_cuentas muestra la bandera")

J, V, Rc, Anon = Cliente(K_J), Cliente(K_V), Cliente(K_R), Cliente(None)

print("== cuentas sin bandera: igual que antes ==")
ok(J, "crear_canal", "jhon crea su canal", nombre="canal-eqa-eqb-comunicacion", agente="agt-eqa-prueba-j1")
ok(V, "unirse_canal", "viviana entra al de jhon por nombre", canal="canal-eqa-eqb-comunicacion", agente="agt-eqb-prueba-v1")
ok(V, "enviar_mensaje", "viviana escribe", canal="canal-eqa-eqb-comunicacion", agente="agt-eqb-prueba-v1", texto="hola")
r = ok(J, "recibir_mensajes", "jhon recibe", canal="canal-eqa-eqb-comunicacion", agente="agt-eqa-prueba-j1")
chk([m["texto"] for m in r["mensajes"]] == ["hola"], "y le llega el mensaje")
ok(J, "mis_canales", "mis_canales de jhon", agente="agt-eqa-prueba-j1")
ok(J, "recibir_de_todos", "recibir_de_todos de jhon", agente="agt-eqa-prueba-j1")
ok(J, "mis_mensajes", "mis_mensajes de jhon", agente="agt-eqa-prueba-j1")
ok(J, "registro_anotar", "jhon anota ficha", agente="agt-eqa-prueba-j1", descripcion="prueba")

print("== sin apikey: pasa como siempre (interruptor apagado) ==")
ok(Anon, "mis_canales", "mis_canales sin apikey", agente="agt-eqa-prueba-j1")
ok(Anon, "enviar_mensaje", "enviar sin apikey", canal="canal-eqa-eqb-comunicacion", agente="agt-eqa-prueba-j1", texto="anon")

print("== restringida: no crea, no entra, no toca el catálogo ==")
no(Rc, "crear_canal", "cuenta restringida", "no crea canal", nombre="canal-otro-trabajo", agente="agt-eqa-otro-r1")
no(Rc, "unirse_canal", "cuenta restringida", "no entra al de jhon", canal="canal-eqa-eqb-comunicacion", agente="agt-eqa-otro-r1")
no(Rc, "registro_anotar", "cuenta restringida", "no anota fichas", agente="agt-eqa-prueba-j1", descripcion="x")
no(Rc, "registro_crear", "cuenta restringida", "no crea en el catálogo", clase="actividad", nombre="pruebax")
no(Rc, "borrar_canal", "cuenta restringida", "no borra", canal="canal-eqa-eqb-comunicacion")
no(Rc, "editar_canal", "cuenta restringida", "no edita", canal="canal-eqa-eqb-comunicacion", descripcion="x")

print("== restringida: no se hace pasar por agentes de otra cuenta ==")
no(Rc, "enviar_mensaje", "no es un miembro de esta cuenta", "no escribe como j1",
   canal="canal-eqa-eqb-comunicacion", agente="agt-eqa-prueba-j1", texto="soy el ceo")
no(Rc, "recibir_mensajes", "no es un miembro", "no lee como j1", canal="canal-eqa-eqb-comunicacion", agente="agt-eqa-prueba-j1")
no(Rc, "recibir_de_todos", "no es un miembro", "no lee todo como j1", agente="agt-eqa-prueba-j1")
no(Rc, "mis_mensajes", "no es un miembro", "no repasa como j1", agente="agt-eqa-prueba-j1")
no(Rc, "mis_canales", "no es un miembro", "no lista como j1", agente="agt-eqa-prueba-j1")
no(Rc, "confirmar_entrega", "no es un miembro", "no confirma como j1", canal="canal-eqa-eqb-comunicacion", agente="agt-eqa-prueba-j1", hasta=1)
no(Rc, "salir_canal", "no es un miembro", "no saca a j1", canal="canal-eqa-eqb-comunicacion", agente="agt-eqa-prueba-j1")
no(Rc, "mis_canales", "no es un miembro", "agente sin canales tampoco", agente="agt-eqa-otro-r9")

print("== restringida: en el canal donde la metió un admin, normal ==")
ch.crear_canal("canal-otro-trabajo", "estudio", agente="agt-eqa-otro-j2", cta="jhonp")
ch.unirse_canal("canal-otro-trabajo", "agt-eqb-otro-r1", cta="estudiop")
ok(Rc, "enviar_mensaje", "r1 escribe en su canal", canal="canal-otro-trabajo", agente="agt-eqb-otro-r1", texto="trabajo listo", para="agt-eqa-otro-j2")
r = ok(J, "recibir_mensajes", "j2 lo recibe", canal="canal-otro-trabajo", agente="agt-eqa-otro-j2")
chk([m["texto"] for m in r["mensajes"]] == ["trabajo listo"], "con el texto")
ok(J, "enviar_mensaje", "j2 le contesta", canal="canal-otro-trabajo", agente="agt-eqa-otro-j2", texto="gracias", para="agt-eqb-otro-r1")
r = ok(Rc, "recibir_de_todos", "r1 recibe de todos", agente="agt-eqb-otro-r1")
ok(Rc, "recibir_mensajes", "r1 recibe del canal", canal="canal-otro-trabajo", agente="agt-eqb-otro-r1")
ok(Rc, "mis_canales", "r1 ve sus canales", agente="agt-eqb-otro-r1")
ok(Rc, "mis_mensajes", "r1 repasa lo suyo", agente="agt-eqb-otro-r1")
ok(Rc, "listar_canales", "listar_canales (ya filtra por cuenta)")
no(Rc, "enviar_mensaje", "no es un miembro", "pero no como j2 en su propio canal",
   canal="canal-otro-trabajo", agente="agt-eqa-otro-j2", texto="x")

print("== quitar la bandera la deja como las demás ==")
repo.marcar_restringida("estudiop", False)
ok(Rc, "mis_canales", "sin bandera vuelve a poder (como cualquier cuenta)", agente="agt-eqa-prueba-j1")

print()
print("TODO OK" if not fallos else f"{len(fallos)} FALLOS: {fallos}")
raise SystemExit(1 if fallos else 0)
