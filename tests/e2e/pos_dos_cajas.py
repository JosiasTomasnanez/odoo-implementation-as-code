"""Prueba con dos cajas del módulo comercio_pos_pedido_qr (P-035).

En el local cobran dos cajas juntas. Se verifica:
1. la caja 2 abre y cobra un pedido del puesto igual que la caja 1;
2. si las dos cajas abren el mismo pedido y la caja 1 lo cobra, la caja 2 avisa
   «Pedido ya cobrado» y no lo cobra de nuevo (un solo pago en el servidor);
3. fin del día: cerrado el puesto, un pedido no cobrado sigue cobrable mientras quede
   una caja abierta y se cancela al cerrar la última.

ATENCIÓN: abre y cierra sesiones de los POS de ejemplo del laboratorio.
Uso: .venv/bin/python tests/e2e/pos_dos_cajas.py [carpeta_capturas]
"""
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from playwright.sync_api import expect, sync_playwright  # noqa: E402
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
    ultimo_borrador,
    verificar_cobrado,
    xmlid,
)

from odoo_iac.client import connect  # noqa: E402
from odoo_iac.settings import load_environment  # noqa: E402

out = Path(sys.argv[1] if len(sys.argv) > 1 else tempfile.mkdtemp(prefix="e2e_dos_cajas_"))
out.mkdir(parents=True, exist_ok=True)
c = connect(load_environment("lab"))
puesto_id, caja1_id, caja2_id = (xmlid(c, n) for n in ("ej_pos_puesto", "ej_pos_caja", "ej_pos_caja_2"))
forzar_qr(c, puesto_id)


def sesion(config_id, estados=("opened",)):
    rows = c.search_read(
        "pos.session", [("config_id", "=", config_id), ("state", "in", list(estados))], ["id"]
    )
    return rows[0] if rows else None


def escanear(page, uuid):
    page.keyboard.type("PED" + uuid.replace("-", "") + "\n", delay=5)  # así «tipea» un lector USB
    page.wait_for_timeout(3000)


def estado(uuid):
    return c.call("pos.order", "comercio_estado_pedido", uuid=uuid)


cerrar_otras_cajas(c, [caja1_id, caja2_id])
for config_id in (puesto_id, caja1_id, caja2_id):
    asegurar_sesion(c, config_id)

with sync_playwright() as p:
    b = p.chromium.launch(**VER)

    def pagina():
        return b.new_context(viewport={"width": 1366, "height": 768}, locale="es-AR").new_page()

    puesto, caja1, caja2 = pagina(), pagina(), pagina()
    for pg in (puesto, caja1, caja2):
        login(pg)
    abrir_pos(puesto, puesto_id, PIN_ATENCION)
    abrir_pos(caja1, caja1_id)
    abrir_pos(caja2, caja2_id)

    # 1. La caja 2 cobra un pedido del puesto
    armar_pedido(puesto, out, 1)
    pedido = ultimo_borrador(c, puesto_id)
    escanear(caja2, pedido["uuid"])
    cobrar(caja2, out, 1)
    verificar_cobrado(c, pedido["uuid"], caja2_id)
    print(f"1. Caja 2: pedido {pedido['pos_reference']} escaneado y cobrado ✓")

    # 2. Las dos cajas abren el mismo pedido; cobra la 1 y la 2 avisa sin cobrar
    armar_pedido(puesto, out, 2)
    pedido = ultimo_borrador(c, puesto_id)
    escanear(caja1, pedido["uuid"])
    escanear(caja2, pedido["uuid"])
    cobrar(caja1, out, 2)
    caja2.locator("button.pay-order-button").first.click()
    caja2.wait_for_timeout(2000)
    caja2.get_by_text("[EJ] Efectivo caja 2").first.click()
    caja2.wait_for_timeout(1000)
    caja2.get_by_role("button", name="Validar").first.click()
    caja2.wait_for_timeout(3000)
    caja2.screenshot(path=str(out / "2_caja2_ya_cobrado.png"))
    expect(caja2.get_by_text("Pedido ya cobrado")).to_be_visible()
    caja2.get_by_role("button", name="De acuerdo").click()
    caja2.wait_for_timeout(1000)
    verificar_cobrado(c, pedido["uuid"], caja1_id)
    pagos = c.search_read("pos.payment", [("pos_order_id.uuid", "=", pedido["uuid"])], ["amount"])
    assert len(pagos) == 1, pagos
    assert caja2.evaluate("posmodel.getOrder().isEmpty()"), "la caja 2 se quedó con el pedido cobrado"
    print("2. Mismo pedido en las dos cajas: la caja 2 avisa «Pedido ya cobrado», un solo pago ✓")

    # 3. Pedido sin cobrar: sigue cobrable con una caja abierta; se cancela con la última
    armar_pedido(puesto, out, 3)
    pedido = ultimo_borrador(c, puesto_id)
    b.close()

# Fin del día: cierra el puesto (el pedido se desprende), después la caja 1 y la 2
assert c.call("pos.session", "close_session_from_ui", [sesion(puesto_id)["id"]])["status"]
assert c.call("pos.session", "close_session_from_ui", [sesion(caja1_id)["id"]])["status"]
assert estado(pedido["uuid"]) == "draft", "se canceló aunque la caja 2 seguía abierta"
print("3. Cierran el puesto y la caja 1 con la caja 2 abierta: el pedido sigue cobrable ✓")
assert c.call("pos.session", "close_session_from_ui", [sesion(caja2_id)["id"]])["status"]
assert estado(pedido["uuid"]) == "cancel", estado(pedido["uuid"])
print("   Cierra la caja 2 (la última): el pedido no cobrado se cancela ✓")

# Deja el lab como lo esperan las otras pruebas: puesto y caja 1 abiertos, caja 2 cerrada
asegurar_sesion(c, puesto_id)
asegurar_sesion(c, caja1_id)
print(f"Todo OK. Capturas en {out}")
