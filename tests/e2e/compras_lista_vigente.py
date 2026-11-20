"""Prueba de punta a punta del módulo comercio_compras_lista_vigente en el lab.

Con un proveedor FICTICIO nuevo en cada corrida:

1. Catálogo de la orden de compra filtrado por el proveedor: aparece lo de su lista
   vigente y lo que se le compró sin precio cargado; no aparece lo que ya no tiene
   (precio cerrado).
2. Líneas de una orden: sin aviso si está en la lista; «Ya no está en su lista» si el
   precio se cerró; «No está en su lista» si nunca lo tuvo.
3. Cartel «Más barato»: aparece si otro proveedor tiene precio vigente menor para esa
   cantidad (respeta su cantidad mínima), con la salvedad de flete y condiciones.
4. Cantidad por debajo del mínimo de su lista: «Mínimo … sin precio de lista» y el precio
   pasa al costo del producto; llegando al mínimo, vuelve el precio de lista sin aviso.
5. Recepción con un producto que el proveedor no tiene (agregado al recibir) y otro pedido
   por debajo de su mínimo: se recibe igual y queda una tarea en la orden para revisar
   esos precios antes de facturar.

Uso: .venv/bin/python tests/e2e/compras_lista_vigente.py
No usar en producción: crea un proveedor, productos y órdenes de prueba.
"""
from __future__ import annotations

import datetime
import html
import sys
import time
import urllib.parse

from odoo_iac.client import connect
from odoo_iac.settings import load_environment

c = connect(load_environment("lab"))
# Sin la revisión con IA al agregar (comercio_catalogo_ia): estas pruebas no dependen de Gemini
c.context["sin_revision_ia"] = True
MARCA = str(int(time.time()))[-6:]
AYER = (datetime.date.today() - datetime.timedelta(days=1)).isoformat()


def main() -> int:
    socio = c.create("res.partner", {"name": f"[EJ] Proveedor compras {MARCA}", "is_company": True})
    otro = c.create("res.partner", {"name": f"[EJ] Proveedor barato {MARCA}", "is_company": True})
    productos, ordenes = {}, []
    try:
        for nombre in ("vigente", "cerrado", "comprado", "nunca"):
            productos[nombre] = c.create("product.template", {"name": f"[EJ] {nombre} {MARCA}",
                                                              "purchase_ok": True})
        c.create("product.supplierinfo", {"partner_id": socio, "product_tmpl_id": productos["vigente"],
                                          "price": 100})
        c.create("product.supplierinfo", {"partner_id": socio, "product_tmpl_id": productos["cerrado"],
                                          "price": 200, "date_start": "2026-01-01", "date_end": AYER})
        variante = {k: c.search_read("product.product", [("product_tmpl_id", "=", v)], ["id"])[0]["id"]
                    for k, v in productos.items()}
        # Algo que se le compró sin tener precio cargado (proveedor sin lista para ese producto)
        compra = c.create("purchase.order", {"partner_id": socio, "order_line": [
            (0, 0, {"product_id": variante["comprado"], "product_qty": 1, "price_unit": 50})]})
        ordenes.append(compra)
        c.call("purchase.order", "button_confirm", [compra])

        catalogo = {p["id"] for p in c.search_read("product.product",
                                                   [("sold_by_vendor_id", "=", socio)], ["id"])}
        esperado = {variante["vigente"], variante["comprado"]}
        assert catalogo == esperado, (catalogo, variante)
        print("1. Catálogo del proveedor: lo vigente y lo comprado sin precio; no lo que ya no tiene ✓")

        orden = c.create("purchase.order", {"partner_id": socio, "order_line": [
            (0, 0, {"product_id": variante[k], "product_qty": 1}) for k in ("vigente", "cerrado", "nunca")]})
        ordenes.append(orden)
        avisos = {li["product_id"][0]: li["comercio_aviso_lista"] for li in c.search_read(
            "purchase.order.line", [("order_id", "=", orden)], ["product_id", "comercio_aviso_lista"])}
        assert not avisos[variante["vigente"]], avisos
        assert avisos[variante["cerrado"]].startswith("Ya no está en su lista"), avisos
        assert avisos[variante["nunca"]] == "No está en su lista", avisos
        print("2. Orden de compra: sin aviso lo vigente; «Ya no está en su lista» y «No está en su lista» ✓")

        # Otro proveedor: más barato desde 10 unidades (cantidad mínima)
        c.create("product.supplierinfo", {"partner_id": otro, "product_tmpl_id": productos["vigente"],
                                          "price": 80, "min_qty": 10})
        def cartel(cantidad: float) -> tuple:
            o = c.create("purchase.order", {"partner_id": socio, "order_line": [
                (0, 0, {"product_id": variante["vigente"], "product_qty": cantidad})]})
            ordenes.append(o)
            linea = c.search_read("purchase.order.line", [("order_id", "=", o)], ["comercio_mas_barato"])[0]
            resumen = c.read("purchase.order", [o], ["comercio_mas_barato_resumen"])[0]
            return linea["comercio_mas_barato"], resumen["comercio_mas_barato_resumen"]
        assert cartel(1) == (False, False), cartel(1)
        texto, resumen = cartel(10)
        assert f"[EJ] Proveedor barato {MARCA}" in texto and "80" in texto, texto
        resumen = html.unescape(resumen)
        assert texto in resumen and "flete ni condiciones" in resumen, resumen
        print(f"3. Línea «{texto}» y cartel con la salvedad (flete y condiciones) con 10 unidades;")
        print("   nada con 1 (no llega a su cantidad mínima) ✓")

        # Mínimo de su lista: un producto con precio solo desde 6 unidades
        minimo = c.create("product.template", {"name": f"[EJ] minimo {MARCA}", "purchase_ok": True,
                                                "standard_price": 999})
        productos["minimo"] = minimo
        c.create("product.supplierinfo", {"partner_id": socio, "product_tmpl_id": minimo,
                                          "price": 500, "min_qty": 6})
        var_minimo = c.search_read("product.product", [("product_tmpl_id", "=", minimo)], ["id"])[0]["id"]
        o = c.create("purchase.order", {"partner_id": socio, "order_line": [
            (0, 0, {"product_id": var_minimo, "product_qty": 6})]})
        ordenes.append(o)
        linea = c.search_read("purchase.order.line", [("order_id", "=", o)], ["id"])[0]["id"]
        campos = ["price_unit", "comercio_aviso_minimo", "comercio_aviso_lista"]
        def leer(cantidad):
            c.write("purchase.order.line", [linea], {"product_qty": cantidad})
            return c.read("purchase.order.line", [linea], campos)[0]
        debajo = leer(2)
        assert debajo["comercio_aviso_minimo"] == "Mínimo 6 Unidades: sin precio de lista", debajo
        assert debajo["price_unit"] == 999 and not debajo["comercio_aviso_lista"], debajo
        llega = leer(6)
        assert llega["price_unit"] == 500 and not llega["comercio_aviso_minimo"], llega
        print(f"4. Con 2 unidades: «{debajo['comercio_aviso_minimo']}» y precio del costo (999);")
        print("   con 6, precio de lista (500) y sin aviso ✓")

        # Recepción: llega además un producto que este proveedor nunca tuvo
        recibir = c.create("purchase.order", {"partner_id": socio, "order_line": [
            (0, 0, {"product_id": variante["vigente"], "product_qty": 2}),
            (0, 0, {"product_id": var_minimo, "product_qty": 6})]})
        # Bajar a 2 después de crear la línea, como en la pantalla (al agregarlo propone el mínimo)
        linea_min = c.search_read("purchase.order.line", [("order_id", "=", recibir),
                                                          ("product_id", "=", var_minimo)], ["id"])[0]["id"]
        c.write("purchase.order.line", [linea_min], {"product_qty": 2})
        ordenes.append(recibir)
        c.call("purchase.order", "button_confirm", [recibir])
        recepcion = c.read("purchase.order", [recibir], ["picking_ids"])[0]["picking_ids"][0]
        datos = c.read("stock.picking", [recepcion], ["location_id", "location_dest_id", "move_ids"])[0]
        for mov in c.read("stock.move", datos["move_ids"], ["product_uom_qty"]):
            c.write("stock.move", [mov["id"]], {"quantity": mov["product_uom_qty"]})
        c.create("stock.move", {"picking_id": recepcion, "product_id": variante["nunca"],
                                "product_uom_qty": 3, "quantity": 3,
                                "location_id": datos["location_id"][0],
                                "location_dest_id": datos["location_dest_id"][0]})
        c.call("stock.picking", "button_validate", [recepcion])
        assert c.read("stock.picking", [recepcion], ["state"])[0]["state"] == "done"
        tareas = c.search_read("mail.activity",
                               [("res_model", "=", "purchase.order"), ("res_id", "=", recibir)],
                               ["summary", "note"])
        assert len(tareas) == 1 and "fuera de la lista" in tareas[0]["summary"], tareas
        nota = tareas[0]["note"]
        assert f"[EJ] nunca {MARCA}" in nota and "No está en su lista" in nota, tareas
        assert f"[EJ] minimo {MARCA}" in nota and "Mínimo 6" in nota, tareas
        assert f"[EJ] vigente {MARCA}" not in nota, tareas
        print("5. Recepción con un producto que no tiene y otro por debajo de su mínimo: se recibe")
        print("   y queda una tarea para revisar esos dos precios ✓")
        # De la recepción se llega a su orden (botón «Orden de compra», solo para Compras)
        nombre_orden = c.read("purchase.order", [recibir], ["name"])[0]["name"]
        assert c.read("stock.picking", [recepcion], ["comercio_compra_nombre"])[0]["comercio_compra_nombre"] \
            == nombre_orden
        ir = c.call("stock.picking", "action_comercio_ver_compra", [recepcion])
        assert ir["res_model"] == "purchase.order" and ir["res_id"] == recibir, ir
        print(f"   la recepción lleva a su orden ({nombre_orden}) con el botón «Orden de compra» ✓")

        # 6. Enviar por WhatsApp: sin teléfono avisa; con el celular, abre wa.me con el pedido
        whats = c.create("purchase.order", {"partner_id": socio, "order_line": [
            (0, 0, {"product_id": variante["vigente"], "product_qty": 3})]})
        ordenes.append(whats)
        try:
            c.call("purchase.order", "action_comercio_enviar_whatsapp", [whats])
            raise AssertionError("abrió WhatsApp sin teléfono del proveedor")
        except AssertionError:
            raise
        except Exception as error:  # noqa: BLE001
            assert "no tiene teléfono" in str(error), error
        c.write("res.partner", [socio], {"phone": "351 512-3456"})  # celular escrito sin el 15
        # Al proveedor se le escribe con su código y su descripción, no con nuestra referencia
        c.write("product.template", [productos["vigente"]], {"default_code": f"REF{MARCA}"})
        vigente_prov = c.search_read("product.supplierinfo", [("partner_id", "=", socio),
                                                              ("product_tmpl_id", "=", productos["vigente"])],
                                     ["id"])[0]["id"]
        c.write("product.supplierinfo", [vigente_prov], {"product_code": "PV-7",
                                                         "product_name": f"ARTICULO VIGENTE {MARCA}"})
        ventana = c.call("purchase.order", "action_comercio_enviar_whatsapp", [whats])
        assert ventana["res_model"] == "comercio.whatsapp.pedido", ventana  # primero, el mensaje
        asistente = c.create("comercio.whatsapp.pedido", {"order_id": whats})
        texto = c.read("comercio.whatsapp.pedido", [asistente], ["texto"])[0]["texto"]
        assert f"[PV-7] ARTICULO VIGENTE {MARCA}" in texto and "• 3 " in texto, texto
        assert f"REF{MARCA}" not in texto, texto  # nuestra referencia interna no va
        c.write("comercio.whatsapp.pedido", [asistente], {"texto": texto + "\nPD: entregar a la mañana"})
        accion = c.call("comercio.whatsapp.pedido", "action_abrir", [asistente])
        url = urllib.parse.unquote(accion["url"])
        nombre = c.read("purchase.order", [whats], ["name", "state"])[0]
        assert accion["url"].startswith("https://wa.me/5493515123456?text="), accion
        assert nombre["name"] in url and f"ARTICULO VIGENTE {MARCA}" in url, url
        assert "PD: entregar a la mañana" in url, url  # el texto corregido
        assert nombre["state"] == "sent", nombre
        print("6. «Enviar por WhatsApp»: sin teléfono avisa; con «351 512-3456» muestra el mensaje,")
        print("   con el código y la descripción del proveedor (no nuestra referencia), se corrige y abre")
        print("   wa.me/5493515123456 con ese texto; la solicitud queda «enviada» ✓")
        print("Todo OK.")
        return 0
    finally:
        for orden in ordenes:
            try:
                c.call("purchase.order", "button_cancel", [orden])
                c.call("purchase.order", "unlink", [orden])
            except Exception:  # noqa: BLE001 — con recepción hecha no se cancela: queda en el lab
                pass
        precios = [p["id"] for p in c.search_read("product.supplierinfo",
                                                  [("partner_id", "in", [socio, otro])], ["id"])]
        if precios:
            c.call("product.supplierinfo", "unlink", precios)
        c.write("product.template", list(productos.values()), {"active": False})
        c.write("res.partner", [socio, otro], {"active": False})
        print("   (datos de la prueba archivados: el lab queda limpio)")


if __name__ == "__main__":
    sys.exit(main())
