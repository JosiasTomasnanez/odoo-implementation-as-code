"""Facturación desde las cajas contra ARCA homologación (ADR 0024; antes: make lab-arca).

1. Caja 1: venta con «Factura» marcado → factura B con CAE real de homologación, y el ticket con
   la factura, el CAE, su vencimiento, el QR de ARCA y la Ley 27.743 (comercio_pos_ticket_ar).
2. Dos facturas validadas a la vez en el mismo punto de venta (las 2 cajas comparten uno): cada
   una con su número, seguidos, y su propio CAE.
3. ARCA caído: con los servidores de homologación bloqueados en el contenedor, la Caja 2 cobra
   con «Factura» marcado: la venta queda cobrada sin factura de Odoo, marcada «ARCA no respondió»,
   y la caja lo avisa claro (comercio_pos_ticket_ar). El bloqueo se saca siempre.
4. Sin registradoras (facturacion.arca_caido = facturar_despues): la venta con «Factura» queda pendiente y
   el reintento la factura cuando ARCA vuelve; la cobrada sin «Factura» no se toca.

    .venv/bin/python tests/e2e/pos_factura_arca.py [carpeta_capturas]

No usar en producción: pide CAE (de homologación) y crea ventas de prueba.
"""

from __future__ import annotations

import subprocess
import sys
import tempfile
import threading
from pathlib import Path

from playwright.sync_api import sync_playwright
from pos_pedido_qr import VER, abrir_pos, asegurar_sesion, buscar_mas, login, xmlid

from odoo_iac.client import connect
from odoo_iac.settings import load_environment

CONTENEDOR = "odoo-lab-odoo-1"
SERVIDORES_ARCA = ("wswhomo.afip.gov.ar", "wsaahomo.afip.gov.ar")
MARCA = "# prueba ARCA caído"
CAE_FALSO = "68448767638166"  # el que inventa Odoo en homologación sin certificado
PIN_CAJERO = "2222"  # PIN ficticio de config/ejemplos/25-empleados.yaml


def ventas_nuevas(c, caja_id: int, antes: set[int]) -> list[dict]:
    return [o for o in c.search_read("pos.order", [("config_id", "=", caja_id)],
                                     ["state", "to_invoice", "account_move", "amount_total"])
            if o["id"] not in antes]


def vender(page, caja_id: int, out: Path, nombre: str, con_factura: bool = True) -> str:
    """Una venta cobrada en efectivo, con «Factura» marcado (o no). Devuelve el texto de la pantalla."""
    abrir_pos(page, caja_id, PIN_CAJERO)
    page.fill("input[placeholder='Buscar productos...']", "Cadena")
    buscar_mas(page)
    page.locator("article.product").first.click()
    page.wait_for_timeout(500)
    page.locator("button.pay-order-button").first.click()
    page.wait_for_timeout(2000)
    assert "highlight" in (page.locator("button.js_invoice").get_attribute("class") or "")
    if not con_factura:
        page.locator("button.js_invoice").click()
        page.wait_for_timeout(500)
    page.get_by_text("Efectivo Caja").first.click()
    page.wait_for_timeout(1000)
    page.get_by_role("button", name="Validar").first.click()
    page.wait_for_timeout(12000)  # el CAE tarda unos segundos
    page.screenshot(path=str(out / f"{nombre}.png"))
    pantalla = page.locator("body").inner_text()
    return pantalla


def prueba_caja_con_cae(c, page, out: Path) -> None:
    caja = xmlid(c, "pos_caja_1")
    asegurar_sesion(c, caja)
    antes = {o["id"] for o in c.search_read("pos.order", [("config_id", "=", caja)], ["id"])}
    vender(page, caja, out, "1_caja1_con_factura")
    nuevas = ventas_nuevas(c, caja, antes)
    assert len(nuevas) == 1 and nuevas[0]["account_move"], nuevas
    factura = c.read("account.move", [nuevas[0]["account_move"][0]],
                     ["name", "l10n_ar_afip_auth_code", "l10n_ar_afip_auth_code_due", "state"])[0]
    cae = factura["l10n_ar_afip_auth_code"]
    assert factura["state"] == "posted" and cae and cae != CAE_FALSO, factura
    ticket = c.call("pos.order", "order_receipt_generate_data", [nuevas[0]["id"]])
    pie = ticket["extra_data"].get("comercio_factura_ar") or {}
    assert ticket["conditions"].get("comercio_factura_ar") and pie["cae"] == cae, pie
    assert pie["factura"].endswith(factura["name"].split(" ", 1)[1]) or factura["name"] in pie["factura"], pie
    assert ticket["image"].get("comercio_qr_arca", "").startswith("data:image"), "falta el QR de ARCA"
    assert pie["impuestos"] and "27.743" in pie["titulo"], pie
    (out / "1_pie_del_ticket.txt").write_text(
        f"{pie['factura']}\nCAE: {pie['cae']}\nVto. CAE: {pie['vto']}\n[QR de ARCA]\n{pie['titulo']}\n"
        + "\n".join(f"{n}  {m}" for n, m in pie["impuestos"]))
    iva = " ".join(pie["impuestos"][0])
    print(f"1. Caja 1: {factura['name']} con CAE {cae} (vence {factura['l10n_ar_afip_auth_code_due']}); "
          f"el ticket trae la factura, el CAE, el QR de ARCA y {iva} ✓")


def prueba_dos_a_la_vez(c) -> None:
    diario = c.search_read("account.journal", [("code", "=", "FE1"), ("type", "=", "sale")], ["id"])[0]["id"]
    final = c.search_read("res.partner", [("name", "=ilike", "Consumidor Final An%nimo")], ["id"])[0]["id"]
    producto = c.search_read("product.product", [("name", "ilike", "Cadena"), ("sale_ok", "=", True)],
                             ["id"], limit=1)[0]["id"]
    borradores = [c.create("account.move", {
        "move_type": "out_invoice", "partner_id": final, "journal_id": diario,
        "invoice_line_ids": [(0, 0, {"product_id": producto, "quantity": 1, "price_unit": 1000})]})
        for _ in range(2)]
    errores, barrera = [], threading.Barrier(2)

    def validar(factura_id: int) -> None:
        cliente = connect(load_environment("lab"))  # una conexión propia, como cada caja
        barrera.wait()
        try:
            cliente.call("account.move", "action_post", [factura_id])
        except Exception as error:  # noqa: BLE001 - se informa abajo
            errores.append(str(error)[:300])

    hilos = [threading.Thread(target=validar, args=(f,)) for f in borradores]
    for hilo in hilos:
        hilo.start()
    for hilo in hilos:
        hilo.join()
    facturas = c.read("account.move", borradores,
                      ["name", "state", "l10n_ar_afip_auth_code", "sequence_number"])
    assert not errores, errores
    assert all(f["state"] == "posted" and f["l10n_ar_afip_auth_code"] not in (False, CAE_FALSO)
               for f in facturas), facturas
    numeros = sorted(f["sequence_number"] for f in facturas)
    assert numeros[1] == numeros[0] + 1, facturas
    assert facturas[0]["l10n_ar_afip_auth_code"] != facturas[1]["l10n_ar_afip_auth_code"]
    print(f"2. Dos a la vez: {facturas[0]['name']} y {facturas[1]['name']}, números seguidos y "
          "un CAE cada una ✓")


def bloquear_arca(bloquear: bool) -> None:
    if bloquear:
        lineas = "".join(f"127.0.0.1 {s} {MARCA}\\n" for s in SERVIDORES_ARCA)
        orden = f"printf '{lineas}' >> /etc/hosts"
    else:
        orden = f"grep -v '{MARCA}' /etc/hosts > /tmp/hosts && cat /tmp/hosts > /etc/hosts"
    subprocess.run(["docker", "exec", "-u", "root", CONTENEDOR, "sh", "-c", orden], check=True)


def prueba_arca_caido(c, page, out: Path) -> None:
    caja = xmlid(c, "pos_caja_2")
    asegurar_sesion(c, caja)
    antes = {o["id"] for o in c.search_read("pos.order", [("config_id", "=", caja)], ["id"])}
    bloquear_arca(True)
    try:
        pantalla = vender(page, caja, out, "3_caja2_arca_caido")
    finally:
        bloquear_arca(False)
    (out / "3_pantalla.txt").write_text(pantalla)
    assert "ARCA no respondió" in pantalla and "registradora" in pantalla, pantalla[-400:]
    assert "ConnectionError" not in pantalla, "el cajero no tiene que ver el error técnico"
    nuevas = ventas_nuevas(c, caja, antes)
    assert len(nuevas) == 1, nuevas
    venta = c.read("pos.order", [nuevas[0]["id"]],
                   ["state", "to_invoice", "account_move", "comercio_sin_factura_arca",
                    "comercio_factura_odoo"])[0]
    assert venta["state"] in ("paid", "done") and not venta["account_move"] and not venta["to_invoice"], venta
    assert venta["comercio_sin_factura_arca"] and not venta["comercio_factura_odoo"], venta
    print("3. ARCA caído: la venta queda cobrada sin factura de Odoo, marcada «ARCA no respondió», y la caja "
          "avisa que el comprobante va por la registradora ✓")


def prueba_facturar_despues(c, page, out: Path) -> None:
    """Sin registradoras (facturacion.arca_caido = facturar_despues): con ARCA caído, la venta con «Factura»
    queda pendiente (y el ticket lo dice); la cobrada sin «Factura» no. Cuando ARCA vuelve, el reintento
    factura solo la pendiente."""
    caja = xmlid(c, "pos_caja_2")
    asegurar_sesion(c, caja)
    parametro = c.search_read("ir.config_parameter",
                              [("key", "=", "comercio_pos_ticket_ar.arca_caido")], ["id"])
    c.write("ir.config_parameter", [parametro[0]["id"]], {"value": "facturar_despues"})
    antes = {o["id"] for o in c.search_read("pos.order", [("config_id", "=", caja)], ["id"])}
    try:
        bloquear_arca(True)
        try:
            pantalla = vender(page, caja, out, "4_caja2_factura_pendiente")
            nuevas = ventas_nuevas(c, caja, antes)
            vender(page, caja, out, "4_caja2_sin_factura", con_factura=False)
        finally:
            bloquear_arca(False)
        assert "factura pendiente" in pantalla.lower() and "registradora" not in pantalla, pantalla[-400:]
        assert len(nuevas) == 1, nuevas
        pendiente = nuevas[0]["id"]
        sin_factura = [o["id"] for o in ventas_nuevas(c, caja, antes) if o["id"] != pendiente]
        assert len(sin_factura) == 1, sin_factura
        campos = ["comercio_factura_pendiente", "comercio_sin_factura_arca", "comercio_factura_odoo",
                  "account_move"]
        venta, otra = c.read("pos.order", [pendiente, sin_factura[0]], campos)
        assert venta["comercio_factura_pendiente"] and not venta["account_move"], venta
        assert not otra["comercio_factura_pendiente"] and not otra["comercio_sin_factura_arca"], otra
        ticket = c.call("pos.order", "order_receipt_generate_data", [pendiente])
        assert ticket["conditions"].get("comercio_factura_pendiente"), ticket["conditions"]
        c.call("pos.order", "action_comercio_reintentar_facturas", [pendiente])
        venta, otra = c.read("pos.order", [pendiente, sin_factura[0]], campos)
        assert venta["comercio_factura_odoo"] and not venta["comercio_factura_pendiente"], venta
        factura = c.read("account.move", [venta["account_move"][0]], ["l10n_ar_afip_auth_code"])[0]
        cae = factura["l10n_ar_afip_auth_code"]
        assert cae and cae != CAE_FALSO, cae
        assert not otra["account_move"] and not otra["comercio_factura_odoo"], "sin «Factura» no se toca"
    finally:
        c.write("ir.config_parameter", [parametro[0]["id"]], {"value": "registradora"})
    print("4. Sin registradoras: con ARCA caído la venta con «Factura» queda pendiente (el ticket lo "
          "dice) y la cobrada sin «Factura» no; al volver ARCA, el reintento factura solo la pendiente ✓")


def main() -> int:
    out = Path(sys.argv[1] if len(sys.argv) > 1 else tempfile.mkdtemp(prefix="pos-arca-"))
    out.mkdir(parents=True, exist_ok=True)
    c = connect(load_environment("lab"))
    with sync_playwright() as p:
        navegador = p.chromium.launch(**VER)
        page = navegador.new_page(viewport={"width": 1366, "height": 800})
        login(page)
        prueba_caja_con_cae(c, page, out)
        prueba_dos_a_la_vez(c)
        prueba_arca_caido(c, page, out)
        prueba_facturar_despues(c, page, out)
        navegador.close()
    print(f"Todo OK. Capturas en {out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
