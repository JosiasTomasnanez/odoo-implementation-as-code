"""Prueba de la regla de cierre de sesión del módulo comercio_pos_pedido_qr (P-027).

Pedidos enviados a caja que nadie cobró:
1. el puesto cierra con la caja abierta → el pedido no se cancela y la caja lo cobra
2. fin del día (puesto y después caja) → se cancela al cerrar la caja
3. el puesto cierra después que la caja → se cancela en ese momento;
4. un puesto queda abierto a la noche → la tarea programada lo cierra (la caja nunca).

ATENCIÓN: cierra y reabre las sesiones de los POS de ejemplo del laboratorio.
Uso: .venv/bin/python tests/e2e/pos_cierre.py [carpeta_capturas]
"""
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from playwright.sync_api import sync_playwright  # noqa: E402
from pos_pedido_qr import (  # noqa: E402
    PIN_ATENCION,
    VER,  # noqa: E402
    abrir_pos,
    armar_pedido,
    asegurar_sesion,
    cerrar_otras_cajas,
    cobrar,
    forzar_qr,
    login,
    xmlid,
)

from odoo_iac.client import connect  # noqa: E402
from odoo_iac.settings import load_environment  # noqa: E402

out = Path(sys.argv[1] if len(sys.argv) > 1 else tempfile.mkdtemp(prefix="e2e_cierre_"))
out.mkdir(parents=True, exist_ok=True)
c = connect(load_environment("lab"))
puesto_id, caja_id = xmlid(c, "ej_pos_puesto"), xmlid(c, "ej_pos_caja")
forzar_qr(c, puesto_id)


def sesion(config_id, estados=("opened",)):
    rows = c.search_read(
        "pos.session", [("config_id", "=", config_id), ("state", "in", list(estados))], ["id", "name"]
    )
    return rows[0] if rows else None


def pedido(uuid):
    fields = ["pos_reference", "state", "session_id", "config_id"]
    return c.search_read("pos.order", [("uuid", "=", uuid)], fields)[0]


def nuevo_pedido_en_puesto(n):
    with sync_playwright() as p:
        b = p.chromium.launch(**VER)
        pg = b.new_page(viewport={"width": 1366, "height": 768}, locale="es-AR")
        login(pg)
        abrir_pos(pg, puesto_id, PIN_ATENCION)
        armar_pedido(pg, out, n)
        b.close()
    rows = c.search_read("pos.order", [("state", "=", "draft"), ("config_id", "=", puesto_id)], ["uuid"])
    return max(rows, key=lambda r: r["id"])["uuid"]


cerrar_otras_cajas(c, [caja_id])
asegurar_sesion(c, puesto_id)
asegurar_sesion(c, caja_id)

# Escenario 1: el puesto cierra con la caja abierta; el cliente en la fila paga igual
uuid = nuevo_pedido_en_puesto(1)
r = c.call("pos.session", "close_session_from_ui", [sesion(puesto_id)["id"]])
print("1. Cierre del puesto:", r)
d = pedido(uuid)
print("   Pedido tras cerrar el puesto:", d)
assert r["status"] and d["state"] == "draft" and not d["session_id"]
with sync_playwright() as p:
    b = p.chromium.launch(**VER)
    pg = b.new_page(viewport={"width": 1366, "height": 768}, locale="es-AR")
    login(pg)
    abrir_pos(pg, caja_id)
    pg.keyboard.type("PED" + uuid.replace("-", "") + "\n", delay=5)
    pg.wait_for_timeout(3000)
    cobrar(pg, out, 1)
    b.close()
d = pedido(uuid)
print("   Tras escanearlo en la caja:", d)
assert d["state"] in ("paid", "done") and d["config_id"][0] == caja_id
print("   ✓ el puesto cerró y la caja cobró el pedido igual")

# Escenario 2: fin del día; el pedido nadie lo cobra y se cancela al cerrar la caja
asegurar_sesion(c, puesto_id)
uuid = nuevo_pedido_en_puesto(2)
print("2. Cierre del puesto:", c.call("pos.session", "close_session_from_ui", [sesion(puesto_id)["id"]]))
r = c.call("pos.session", "close_session_from_ui", [sesion(caja_id)["id"]])
print("   Cierre de la caja:", r)
d = pedido(uuid)
print("   Pedido tras cerrar la caja:", d)
assert r["status"] and d["state"] == "cancel"
print("   ✓ al cerrar la caja se canceló el pedido no cobrado")

# Escenario 3: el puesto cierra cuando la caja ya cerró → se cancela en el momento
asegurar_sesion(c, puesto_id)
uuid = nuevo_pedido_en_puesto(3)
r = c.call("pos.session", "close_session_from_ui", [sesion(puesto_id)["id"]])
d = pedido(uuid)
print("3. Cierre del puesto con la caja cerrada:", r, "| pedido:", d["state"])
assert r["status"] and d["state"] == "cancel"
print("   ✓ se canceló al cerrar el puesto")

# Escenario 4: un puesto quedó abierto a la noche → la tarea programada lo cierra
asegurar_sesion(c, puesto_id)
asegurar_sesion(c, caja_id)
uuid = nuevo_pedido_en_puesto(4)
cron_xmlid = [("module", "=", "comercio_pos_pedido_qr"), ("name", "=", "ir_cron_cerrar_puestos")]
cron = c.search_read("ir.model.data", cron_xmlid, ["res_id"])[0]["res_id"]
c.call("ir.cron", "method_direct_trigger", [cron])
d = pedido(uuid)
print("4. Tarea nocturna: puesto abierto =", bool(sesion(puesto_id)),
      "| pedido:", d["state"], "| sesión:", d["session_id"])
assert not sesion(puesto_id) and d["state"] == "draft" and not d["session_id"]
print("   ✓ la tarea nocturna cerró el puesto; con la caja abierta, el pedido sigue cobrable")
r = c.call("pos.session", "close_session_from_ui", [sesion(caja_id)["id"]])
assert r["status"] and pedido(uuid)["state"] == "cancel"
print("   ✓ al cerrar la caja se canceló")

# Deja el lab listo para seguir probando
asegurar_sesion(c, puesto_id)
asegurar_sesion(c, caja_id)
print("Sesiones reabiertas.")
