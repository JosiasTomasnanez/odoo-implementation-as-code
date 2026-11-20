"""Prueba de punta a punta del puesto que «se cobra en la registradora» (P-046, temporal).

Mientras cobran las registradoras, el puesto da el pedido por cobrado al tocar «Imprimir
pedido» (medio «Cobrado en registradora»), sin pedir medio de pago, y así baja el stock.

    .venv/bin/python tests/e2e/pos_cobro_registradora.py [carpeta_capturas]

Flujo verificado:
1. Puesto (quien atiende): «Imprimir pedido» imprime el ticket sin QR («Presentar en caja»).
2. Servidor: el pedido queda cobrado con «Cobrado en registradora» y baja el stock del
   alimento en el momento.
3. Cierre del puesto (como el cierre nocturno): se cierra sin pedir conteo de efectivo.
No usar en producción: crea pedidos de prueba.
"""

from __future__ import annotations

import re
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from playwright.sync_api import sync_playwright  # noqa: E402
from pos_pedido_qr import (  # noqa: E402
    NO_VA_EN_EL_TICKET,
    PIN_ATENCION,
    VER,
    abrir_pos,
    armar_pedido,
    asegurar_sesion,
    login,
    xmlid,
)

from odoo_iac.client import connect  # noqa: E402
from odoo_iac.settings import load_environment  # noqa: E402


def main() -> int:
    out = Path(sys.argv[1] if len(sys.argv) > 1 else tempfile.mkdtemp(prefix="e2e_registradora_"))
    out.mkdir(parents=True, exist_ok=True)
    c = connect(load_environment("lab"))
    puesto_id = xmlid(c, "ej_pos_puesto")
    campo = "comercio_cobro_en_registradora"
    antes = c.read("pos.config", [puesto_id], [campo])[0][campo]
    c.write("pos.config", [puesto_id], {campo: True})
    try:
        return probar(c, puesto_id, out)
    finally:
        c.write("pos.config", [puesto_id], {campo: antes})


def probar(c, puesto_id: int, out: Path) -> int:
    asegurar_sesion(c, puesto_id)
    previos = {r["id"] for r in c.search_read("pos.order", [("config_id", "=", puesto_id)], ["id"])}

    with sync_playwright() as p:
        b = p.chromium.launch(**VER)
        pg = b.new_page(viewport={"width": 1366, "height": 768}, locale="es-AR")
        login(pg)
        abrir_pos(pg, puesto_id, PIN_ATENCION)
        ticket = armar_pedido(pg, out, 1)
        # Foto del ticket tal como sale, para mirarlo
        pg.set_content(ticket)
        pg.set_viewport_size({"width": 520, "height": 900})
        pg.screenshot(path=str(out / "1_ticket.png"), full_page=True)
        b.close()
    assert "Presentar en caja" in ticket, "el ticket no dice dónde pagar"
    assert "comercio_pedido_qr" not in ticket, "el ticket trae QR, pero esta caja no lo abre"
    assert "data:image" in ticket, "el ticket del puesto no trae el logo"
    numero = re.search(r"\d+-\d+-\d{6}", ticket).group()  # sesión-puesto-número
    assert ticket.count(numero) == 1, f"el número {numero} sale {ticket.count(numero)} veces"
    sobra = NO_VA_EN_EL_TICKET.search(ticket)
    assert not sobra, f"el ticket del puesto muestra «{sobra and sobra.group()}»"
    print("1. Puesto: ticket con logo y el número una vez; sin QR, IVA, CUIT, cliente, cajero ni Odoo ✓")

    nuevos = c.search_read("pos.order", [("config_id", "=", puesto_id), ("id", "not in", list(previos))],
                           ["state", "amount_total", "amount_paid", "payment_ids", "pos_reference"])
    assert len(nuevos) == 1, nuevos
    pedido = nuevos[0]
    assert pedido["state"] in ("paid", "done"), pedido
    assert abs(pedido["amount_total"] - pedido["amount_paid"]) < 0.01, pedido
    medios = c.read("pos.payment", pedido["payment_ids"], ["payment_method_id"])
    assert [m["payment_method_id"][1] for m in medios] == ["Cobrado en registradora"], medios
    # El stock baja en el momento: el movimiento de la venta queda hecho, con cada producto y cantidad
    # (no se mira un producto fijo: la búsqueda del puesto puede traer otro si el lab tiene listas reales)
    lineas = c.search_read("pos.order.line", [("order_id", "=", pedido["id"])], ["product_id", "qty"])
    movs = c.search_read("stock.move", [("picking_id.pos_order_id", "=", pedido["id"])],
                         ["product_id", "quantity", "state"])
    assert movs and all(m["state"] == "done" for m in movs), movs
    vendido = {(lin["product_id"][0], lin["qty"]) for lin in lineas}
    movido = {(m["product_id"][0], m["quantity"]) for m in movs}
    assert vendido == movido, (vendido, movido)
    print(f"2. Servidor: {pedido['pos_reference']} cobrado con «Cobrado en registradora»; "
          f"el stock bajó en el momento ({len(movs)} productos) ✓")

    abiertas = [("config_id", "=", puesto_id), ("state", "=", "opened")]
    sesion = c.search_read("pos.session", abiertas, ["id"])[0]
    resultado = c.call("pos.session", "close_session_from_ui", [sesion["id"]])
    assert resultado.get("status"), resultado
    estado = c.read("pos.session", [sesion["id"]], ["state"])[0]["state"]
    assert estado == "closed", estado
    print("3. Cierre del puesto (como el nocturno): se cierra solo, sin conteo de efectivo ✓")
    if "comercio_contable_anulado" in c.fields_get("pos.session"):
        from cierre_z import saldo_ventas_e_iva  # noqa: PLC0415 (solo con comercio_cierre_z instalado)

        campo = "comercio_contable_anulado"
        anulado = c.read("pos.session", [sesion["id"]], [campo])[0][campo]
        assert anulado, "el cierre del puesto quedó en la contabilidad (la venta contable es el Z)"
        assert saldo_ventas_e_iva(c, sesion["id"]) == 0.0, "ventas e IVA del puesto no quedaron en cero"
        pagos = c.search_read("account.payment", [("pos_session_id", "=", sesion["id"])], ["state"])
        assert all(p["state"] == "canceled" for p in pagos), pagos
        print("4. Contabilidad: el cierre del puesto no cuenta como venta "
              "(la venta contable es el cierre Z); "
              "el stock ya bajó ✓")
    print("Todo OK.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
