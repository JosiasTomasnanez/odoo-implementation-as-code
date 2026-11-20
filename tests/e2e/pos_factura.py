"""Prueba de punta a punta del módulo comercio_pos_factura (ADR 0024) en el laboratorio.

Caja de ejemplo (sin ARCA): en la pantalla de pago «Factura» viene marcado; al desmarcarlo
aparece una franja de color al costado (sin carteles). Cobrada así, la venta queda «sin factura
de Odoo» y aparece en «Ventas sin factura de Odoo». La venta con factura y CAE se prueba a mano
en Caja 1 o 2 (después de `make lab-arca`), porque depende de ARCA homologación.

    .venv/bin/python tests/e2e/pos_factura.py [carpeta_capturas]

No usar en producción: crea ventas de prueba.
"""

from __future__ import annotations

import sys
import tempfile
from pathlib import Path

from playwright.sync_api import expect, sync_playwright
from pos_pedido_qr import VER, abrir_pos, asegurar_sesion, buscar_mas, login, xmlid

from odoo_iac.client import connect
from odoo_iac.settings import load_environment


def main() -> int:
    out = Path(sys.argv[1] if len(sys.argv) > 1 else tempfile.mkdtemp(prefix="pos-factura-"))
    out.mkdir(parents=True, exist_ok=True)
    c = connect(load_environment("lab"))
    caja_id = xmlid(c, "ej_pos_caja")
    asegurar_sesion(c, caja_id)
    antes = {o["id"] for o in c.search_read("pos.order", [("config_id", "=", caja_id)], ["id"])}

    with sync_playwright() as p:
        navegador = p.chromium.launch(**VER)
        page = navegador.new_page(viewport={"width": 1366, "height": 800})
        login(page)
        abrir_pos(page, caja_id)
        page.fill("input[placeholder='Buscar productos...']", "Cadena")
        buscar_mas(page)
        page.locator("article.product").first.click()
        page.wait_for_timeout(500)
        page.locator("button.pay-order-button").first.click()
        page.wait_for_timeout(2000)

        factura = page.locator("button.js_invoice")
        expect(factura).to_contain_text("Factura")
        assert "highlight" in (factura.get_attribute("class") or ""), "«Factura» tiene que venir marcado"
        expect(page.locator(".comercio-sin-factura")).to_have_count(0)
        page.screenshot(path=str(out / "1_con_factura.png"))

        factura.click()
        page.wait_for_timeout(500)
        expect(page.locator(".comercio-sin-factura")).to_have_count(1)
        franja = page.locator(".payment-screen").first.evaluate(
            "e => getComputedStyle(e, '::before').backgroundColor")
        assert franja == "rgb(125, 147, 171)", f"sin factura, falta la franja al costado: {franja}"
        expect(page.get_by_text("SIN FACTURA", exact=False)).to_have_count(0)  # sin carteles
        page.screenshot(path=str(out / "2_sin_factura_franja.png"))
        print("✓ «Factura» marcado por defecto; desmarcado, una franja de color al costado y sin carteles")

        page.get_by_text("[EJ] Efectivo caja").first.click()
        page.wait_for_timeout(1000)
        page.get_by_role("button", name="Validar").first.click()
        page.wait_for_timeout(4000)
        page.screenshot(path=str(out / "3_cobrado.png"))
        navegador.close()

    nuevas = [
        o
        for o in c.search_read(
            "pos.order",
            [("config_id", "=", caja_id)],
            ["to_invoice", "account_move", "comercio_factura_odoo", "state"],
        )
        if o["id"] not in antes
    ]
    assert len(nuevas) == 1, nuevas
    venta = nuevas[0]
    assert venta["state"] in ("paid", "done") and not venta["to_invoice"] and not venta["account_move"], venta
    assert not venta["comercio_factura_odoo"], venta
    accion = c.search_read("ir.actions.act_window", [("name", "=", "Ventas sin factura de Odoo")], ["domain"])
    assert accion, "falta «Ventas sin factura de Odoo»"
    listado = c.search_read(
        "pos.order",
        [("comercio_factura_odoo", "=", False), ("state", "in", ("paid", "done")), ("id", "=", venta["id"])],
        ["id"],
    )
    assert listado, "la venta sin factura tiene que estar en «Ventas sin factura de Odoo»"
    print("✓ Cobrada sin factura de Odoo: sin comprobante y en «Ventas sin factura de Odoo»")

    # Se cobró sin factura por error y no se hizo en la registradora: «Facturar con CAE» (administración).
    # Pide CAE a ARCA homologación: solo si el lab tiene el diario electrónico (`make lab-arca`)
    if c.search_read("account.journal", [("l10n_ar_afip_pos_system", "=", "RAW_MAW")], ["id"]):
        accion = c.call("pos.order", "action_comercio_facturar_con_cae", [venta["id"]])
        factura = c.read(
            "account.move", [accion["res_id"]], ["l10n_ar_afip_auth_code", "payment_state", "journal_id"]
        )[0]
        assert factura["l10n_ar_afip_auth_code"] and factura["payment_state"] in ("paid", "in_payment"), (
            factura
        )
        assert c.read("pos.order", [venta["id"]], ["comercio_factura_odoo"])[0]["comercio_factura_odoo"]
        print(
            f"✓ «Facturar con CAE»: factura con CAE en {factura['journal_id'][1]}, cobrada, fuera de la lista"
        )
    else:
        print("  («Facturar con CAE» no se probó: falta el diario electrónico, correr `make lab-arca`)")
    print(f"Prueba de ventas con y sin factura: OK (capturas en {out})")
    return 0


if __name__ == "__main__":
    sys.exit(main())
