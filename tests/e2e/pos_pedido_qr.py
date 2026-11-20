"""Prueba de punta a punta del módulo comercio_pos_pedido_qr (ADR 0009) en el laboratorio.

Requiere el lab levantado con config/ejemplos aplicada y Playwright:

    pip install playwright && python -m playwright install chromium
    .venv/bin/python tests/e2e/pos_pedido_qr.py [carpeta_capturas]

Flujo verificado:
0. Puesto cerrado: quien atiende lo abre con su PIN (nota de apertura con botón).
1. Puesto (quien atiende, rol supervisado): no hay «Pago»; «Imprimir pedido» sube el
   pedido al servidor e imprime el proforma con QR.
2. Caja: el lector USB «tipea» el código del QR → se abre ese pedido → se cobra.
3. Caja: si el lector falla, «Abrir pedido» con el número impreso.
En cada caso se verifica en el servidor: pedido cobrado, en la sesión de la caja.
No usar en producción: crea pedidos y cobros de prueba.
"""

from __future__ import annotations

import atexit
import os
import re
import sys
import tempfile
import time
from pathlib import Path

from playwright.sync_api import Page, expect, sync_playwright

from odoo_iac.client import connect
from odoo_iac.settings import load_environment

BASE = "http://localhost:8069"
# VER=1: abre el navegador en pantalla y va despacio, para mirar la prueba (instructivo:
# docs/runbooks/prueba-visual.md, sección 12)
VER = {"headless": False, "slow_mo": 400} if os.environ.get("VER") else {}
PIN_ATENCION = "1111"  # PIN ficticio de config/ejemplos/25-empleados.yaml
# Campo del PIN: Community dice «Ingresa tu NIP» y Enterprise «Escriba su NIP».
CAMPO_PIN = "input[placeholder*='NIP']"
# Lo que no va en el ticket del puesto: IVA, CUIT, cliente, cajero, precio por unidad, Odoo
NO_VA_EN_EL_TICKET = re.compile(r"\bIVA\b|Subtotal|CUIT|Odoo|proforma|Atendido|Consumidor Final|/ Unidades")


def xmlid(client, name: str) -> int:
    rows = client.search_read("ir.model.data", [("module", "=", "iac"), ("name", "=", name)], ["res_id"])
    return rows[0]["res_id"]


def forzar_qr(client, puesto_id: int) -> None:
    """Las pruebas del pedido con QR: el puesto de ejemplo cobra en la registradora (P-046,
    temporal) y en ese modo no hay QR. Mientras corre la prueba vuelve al QR; al terminar
    (aunque falle) queda como estaba."""
    campo = "comercio_cobro_en_registradora"
    antes = client.read("pos.config", [puesto_id], [campo])[0][campo]
    client.write("pos.config", [puesto_id], {campo: False})
    atexit.register(lambda: client.write("pos.config", [puesto_id], {campo: antes}))


def login(page: Page) -> None:
    page.goto(f"{BASE}/web/login?db=lab")  # con la copia de producción en el lab hay dos bases
    page.fill("input[name=login]", "admin")
    page.fill("input[name=password]", "admin")
    page.click("button[type=submit]")
    page.wait_for_url("**/odoo**", timeout=60000)


def abrir_pos(page: Page, config_id: int, pin: str | None = None) -> None:
    inicio = time.monotonic()
    page.goto(f"{BASE}/pos/ui/{config_id}")
    # Esperar a que el POS termine de cargar (con miles de productos tarda más que unos segundos)
    page.locator(f"{CAMPO_PIN}, input[placeholder='Buscar productos...'], "
                 "button:has-text('Desbloquear caja registradora'), button:has-text('Abrir caja'), "
                 ".opening-cash-control").first.wait_for(timeout=120_000)
    page.wait_for_timeout(1000)
    print(f"   (POS cargado en {time.monotonic() - inicio:.0f} s)")
    if page.get_by_text("Desbloquear caja registradora").count():
        # En pantalla, el logo en color de la empresa (el del ticket es blanco y negro)
        logo = page.locator(".screen-login-logo img").get_attribute("src") or ""
        assert "/web/binary/company_logo" in logo, f"la pantalla de entrada muestra otro logo: {logo[:60]}"
        page.get_by_text("Desbloquear caja registradora").click()
        page.wait_for_timeout(1500)
    if pin:
        page.fill(CAMPO_PIN, pin)
        page.keyboard.press("Enter")
        page.wait_for_timeout(2000)


def buscar_mas(page: Page) -> None:
    """Si el producto no está entre los cargados, «Buscar más» lo trae del servidor.

    Con más de 5000 productos el POS de Odoo 20 no los carga todos al abrir: solo los
    favoritos y los modificados más recientemente (`point_of_sale.limited_product_count`)."""
    page.wait_for_timeout(1000)
    mas = page.get_by_role("button", name="Buscar más")
    if not page.locator("article.product").count() and mas.count():
        mas.click()
        page.locator("article.product").first.wait_for(timeout=15_000)


def armar_pedido(page: Page, out: Path, n: int) -> str:
    """Puesto: arma un pedido, lo imprime y devuelve el HTML del proforma."""
    for nombre in ["Alimento perro adulto 15 kg", "Cadena"]:
        page.fill("input[placeholder='Buscar productos...']", nombre)
        buscar_mas(page)
        page.locator("article.product").first.click()
        page.wait_for_timeout(500)
    page.fill("input[placeholder='Buscar productos...']", "")
    expect(page.locator("button.pay-order-button")).to_have_count(0)
    imprimir = page.locator("button.comercio-imprimir-pedido")
    expect(imprimir).to_be_visible()
    # Captura el proforma en lugar de mandarlo a la impresora
    page.evaluate(
        """() => { posmodel.ticketPrinter.printWithFallback = async ({ iframe }) => {
            window.__proforma = iframe.contentDocument.body.innerHTML; return true; }; }"""
    )
    page.screenshot(path=str(out / f"{n}_puesto_pedido.png"))
    imprimir.click()
    page.wait_for_timeout(3000)
    page.screenshot(path=str(out / f"{n}_puesto_impreso.png"))
    return page.evaluate("window.__proforma || ''")


def cobrar(page: Page, out: Path, n: int) -> None:
    page.locator("button.pay-order-button").first.click()
    page.wait_for_timeout(2000)
    page.get_by_text("[EJ] Efectivo caja").first.click()
    page.wait_for_timeout(1000)
    page.get_by_role("button", name="Validar").first.click()
    page.wait_for_timeout(4000)
    page.screenshot(path=str(out / f"{n}_caja_cobrado.png"))
    page.get_by_role("button", name="Continuar").first.click()  # vuelve a una venta nueva
    page.wait_for_timeout(1500)


def asegurar_sesion(client, config_id: int) -> None:
    """Deja abierta la sesión del punto de venta (apertura con efectivo 0, como el diálogo)."""
    def sesion(estados):
        rows = client.search_read(
            "pos.session", [("config_id", "=", config_id), ("state", "in", estados)], ["id"]
        )
        return rows[0] if rows else None

    if not sesion(["opened", "opening_control"]):
        client.call("pos.config", "open_ui", [config_id])
    s = sesion(["opening_control"])
    if s:
        client.call("pos.session", "set_opening_control", [s["id"]], cashbox_value=0, notes="")


def cerrar_otras_cajas(client, cajas_de_la_prueba: list[int]) -> None:
    """Cierra las sesiones de las demás cajas del lab (p. ej. Caja 1 y 2 de config/base).

    La regla de cierre cancela los pedidos pendientes recién al cerrar la **última** caja:
    otra caja abierta cambiaría el resultado de la prueba.
    """
    sesiones = client.search_read(
        "pos.session",
        [("state", "=", "opened"), ("config_id.comercio_arma_pedidos", "=", False),
         ("config_id", "not in", cajas_de_la_prueba)],
        ["id"],
    )
    for s in sesiones:
        client.call("pos.session", "close_session_from_ui", [s["id"]])


def ultimo_borrador(client, puesto_id: int) -> dict:
    rows = client.search_read(
        "pos.order", [("state", "=", "draft"), ("config_id", "=", puesto_id)],
        ["uuid", "pos_reference", "amount_total"],
    )
    assert rows, "el pedido del puesto no llegó al servidor"
    return max(rows, key=lambda r: r["id"])


def verificar_cobrado(client, uuid: str, caja_id: int) -> None:
    pedido = client.search_read(
        "pos.order", [("uuid", "=", uuid)], ["state", "config_id", "amount_total", "amount_paid"]
    )[0]
    assert pedido["state"] in ("paid", "done"), pedido
    assert pedido["config_id"][0] == caja_id, pedido
    assert abs(pedido["amount_total"] - pedido["amount_paid"]) < 0.01, pedido


def main() -> int:
    out = Path(sys.argv[1] if len(sys.argv) > 1 else tempfile.mkdtemp(prefix="e2e_pos_"))
    out.mkdir(parents=True, exist_ok=True)
    client = connect(load_environment("lab"))
    puesto_id, caja_id = xmlid(client, "ej_pos_puesto"), xmlid(client, "ej_pos_caja")
    forzar_qr(client, puesto_id)
    # El puesto arranca cerrado: lo abre quien atiende desde la pantalla, como a la mañana
    for s in client.search_read(
        "pos.session", [("config_id", "=", puesto_id), ("state", "=", "opened")], ["id"]
    ):
        client.call("pos.session", "close_session_from_ui", [s["id"]])
    asegurar_sesion(client, caja_id)

    with sync_playwright() as p:
        browser = p.chromium.launch(**VER)
        puesto = browser.new_context(viewport={"width": 1366, "height": 768}, locale="es-AR").new_page()
        caja = browser.new_context(viewport={"width": 1366, "height": 768}, locale="es-AR").new_page()
        login(puesto)
        login(caja)
        puesto.goto(f"{BASE}/pos/ui/{puesto_id}")
        bienvenida = puesto.get_by_text("Abrir caja registradora").first
        bienvenida.wait_for(timeout=120_000)  # con miles de productos el POS tarda en cargar
        bienvenida.click()  # pantalla de bienvenida
        puesto.wait_for_timeout(1500)
        puesto.fill(CAMPO_PIN, PIN_ATENCION)
        puesto.keyboard.press("Enter")
        puesto.wait_for_timeout(2500)
        apertura = puesto.locator(".modal").get_by_role("button", name="Abrir caja registradora")
        expect(apertura).to_be_visible()  # sin el módulo, quien atiende no ve este botón
        apertura.click()
        puesto.wait_for_timeout(2500)
        abiertas = client.search_read(
            "pos.session", [("config_id", "=", puesto_id), ("state", "=", "opened")], ["id"]
        )
        assert abiertas, "quien atiende no pudo abrir el puesto"
        print("0. Puesto: quien atiende abre la sesión del puesto con su PIN ✓")
        abrir_pos(caja, caja_id)

        # Quien atiende (rol supervisado) puede cerrar la sesión del puesto
        puesto.locator("i[data-icon=menu]").first.click()
        puesto.wait_for_timeout(1000)
        assert puesto.locator("[name=close_register], button:has(i[data-icon=key])").count(), \
            "quien atiende no ve «Cerrar caja»"
        puesto.keyboard.press("Escape")
        puesto.wait_for_timeout(500)
        print("0. Puesto: quien atiende puede cerrar la caja del puesto ✓")

        # El puesto no vuelve a cargar pedidos ya enviados a caja
        assert puesto.evaluate("posmodel.getOrder().isEmpty()"), "el puesto cargó un pedido viejo"

        # 1 y 2: proforma con QR, la caja lo escanea con el lector USB
        proforma = armar_pedido(puesto, out, 1)
        assert "Presentar en caja" in proforma and "data:image" in proforma, "el proforma no tiene el QR"
        sobra = NO_VA_EN_EL_TICKET.search(proforma)
        assert not sobra, f"el proforma del puesto muestra «{sobra and sobra.group()}»"
        pedido = ultimo_borrador(client, puesto_id)
        print(f"1. Puesto: pedido {pedido['pos_reference']} en el servidor, proforma con QR ✓")
        expect(caja.locator("button.comercio-abrir-pedido")).to_be_visible()
        codigo = "PED" + pedido["uuid"].replace("-", "")
        caja.keyboard.type(codigo + "\n", delay=5)  # así «tipea» un lector USB
        caja.wait_for_timeout(3000)
        caja.screenshot(path=str(out / "1_caja_escaneado.png"))
        expect(caja.locator("button.pay-order-button").first).to_be_enabled()
        cobrar(caja, out, 1)
        verificar_cobrado(client, pedido["uuid"], caja_id)
        print("2. Caja: escaneo con lector → pedido abierto, cobrado en la caja ✓")

        # 3: respaldo, tipear el número impreso
        armar_pedido(puesto, out, 2)
        pedido = ultimo_borrador(client, puesto_id)
        caja.wait_for_timeout(1500)
        caja.locator("button.comercio-abrir-pedido").click()
        caja.wait_for_timeout(800)
        caja.keyboard.type(pedido["pos_reference"])
        caja.keyboard.press("Enter")
        caja.wait_for_timeout(3000)
        caja.screenshot(path=str(out / "2_caja_tipeado.png"))
        cobrar(caja, out, 2)
        verificar_cobrado(client, pedido["uuid"], caja_id)
        print(f"3. Caja: número tipeado ({pedido['pos_reference']}) → pedido cobrado ✓")
        browser.close()

    print(f"Todo OK. Capturas en {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
