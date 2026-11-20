"""Prueba de punta a punta del módulo comercio_precios en el lab (P-030, ADR 0016).

Con una categoría y productos FICTICIOS nuevos en cada corrida:

1. Producto nuevo sin precio de venta (como los que crea una lista): toma solo el sugerido
   (costo + margen + IVA, redondeado para arriba) y queda en «Etiquetas a reimprimir».
2. Producto nuevo con precio cargado: no se toca; aparece en «Precios a actualizar» y al
   aplicar pasa al sugerido con el IVA de la categoría.
3. Cambiar el margen de la categoría: nuevo sugerido, sin tocar el precio de venta.
4. Precio escrito a mano: «Precio manual», sale de «Precios a actualizar»; al desmarcarlo
   vuelve.
5. Subcategoría sin margen: usa el de la madre. Base «precio de un proveedor».
6. «Marcar impresas» vacía las etiquetas pendientes.
7. Margen especial por producto («Agregar producto» en «Márgenes especiales»), con su
   propia base (costo o precio de un proveedor) como en las categorías.
8. IVA: manda el del producto; el del rubro se pone a los nuevos y a los que no tienen.
9. «Diferencia chica»: un cambio hasta ese porcentaje sale en naranja y no se muestra en
   «Precios a actualizar»; uno más grande sí.

Uso: .venv/bin/python tests/e2e/precios.py
"""
from __future__ import annotations

import sys
import time

from odoo_iac.client import connect
from odoo_iac.settings import load_environment

c = connect(load_environment("lab"))
MARCA = str(int(time.time()))[-6:]


def leer(tmpl: int) -> dict:
    return c.read("product.template", [tmpl], [
        "list_price", "comercio_precio_calculado", "comercio_precio_desactualizado",
        "comercio_precio_manual", "comercio_etiqueta_pendiente", "taxes_id", "comercio_precio_detalle"])[0]


def main() -> int:
    iva = c.search_read("ir.model.data", [("module", "=", "account"),
                                          ("name", "=", "1_ri_tax_vat_21_ventas")], ["res_id"])[0]["res_id"]
    incluido = c.search_read("res.company", [], ["account_price_include"])[0]["account_price_include"]
    assert incluido == "tax_included", "el lab carga precios con IVA incluido (ver 05-ajustes.yaml)"
    madre = c.create("product.category", {"name": f"[EJ] Precios {MARCA}", "comercio_margen": 50,
                                          "comercio_base": "costo", "comercio_iva_venta_id": iva,
                                          "comercio_redondeo": 10})
    hija = c.create("product.category", {"name": f"[EJ] Precios hija {MARCA}", "parent_id": madre})
    socio = c.create("res.partner", {"name": f"[EJ] Proveedor precios {MARCA}", "is_company": True})
    productos = []
    try:
        nuevo = c.create("product.template", {"name": f"[EJ] Precio nuevo {MARCA}", "categ_id": madre,
                                              "standard_price": 1000, "taxes_id": [(6, 0, [])]})
        productos.append(nuevo)
        d = leer(nuevo)
        # 1000 + 50 % = 1500; + IVA 21 % = 1815 → redondeo $10 para arriba = 1820
        assert d["list_price"] == 1820 and d["comercio_precio_calculado"] == 1820, d
        assert not d["comercio_precio_desactualizado"] and d["comercio_etiqueta_pendiente"], d
        assert d["taxes_id"] == [iva] and not d["comercio_precio_manual"], d
        print(f"1. Producto nuevo sin precio: toma solo 1820 ({d['comercio_precio_detalle']});")
        print("   IVA de la categoría y etiqueta para imprimir ✓")

        p = c.create("product.template", {"name": f"[EJ] Precio {MARCA}", "categ_id": madre,
                                          "standard_price": 1000, "list_price": 2500,
                                          "taxes_id": [(6, 0, [])]})
        productos.append(p)
        d = leer(p)
        assert d["list_price"] == 2500 and d["comercio_precio_desactualizado"], d
        assert not d["comercio_precio_manual"], d
        c.call("product.template", "action_comercio_aplicar_precio", [p])
        d = leer(p)
        assert d["list_price"] == 1820 and not d["comercio_precio_desactualizado"], d
        assert d["taxes_id"] == [iva] and d["comercio_etiqueta_pendiente"], d
        print("2. Producto con precio cargado (2500): no se toca; en «Precios a actualizar»;")
        print("   al aplicar pasa a 1820 con el IVA de la categoría ✓")

        c.write("product.category", [madre], {"comercio_margen": 60})
        d = leer(p)
        # 1000 + 60 % = 1600; + 21 % = 1936 → 1940
        assert d["comercio_precio_calculado"] == 1940 and d["list_price"] == 1820, d
        assert d["comercio_precio_desactualizado"], d
        print("3. Margen 60 %: sugerido 1940; el precio de venta sigue en 1820 hasta aplicarlo ✓")

        c.write("product.template", [p], {"list_price": 1999})
        d = leer(p)
        assert d["comercio_precio_manual"] and not d["comercio_precio_desactualizado"], d
        c.write("product.template", [p], {"comercio_precio_manual": False})
        assert leer(p)["comercio_precio_desactualizado"]
        print("4. Precio a mano (1999): «Precio manual», no se sugiere cambiarlo;")
        print("   al desmarcarlo vuelve ✓")

        q = c.create("product.template", {"name": f"[EJ] Precio hija {MARCA}", "categ_id": hija,
                                          "standard_price": 1000, "list_price": 5000})
        productos.append(q)
        assert leer(q)["comercio_precio_calculado"] == 1940, leer(q)
        c.create("product.supplierinfo", {"partner_id": socio, "product_tmpl_id": q, "price": 800})
        c.write("product.category", [hija], {"comercio_base": "proveedor",
                                             "comercio_proveedor_base_id": socio})
        d = leer(q)
        # 800 + 60 % (de la madre) = 1280; + 21 % = 1548,8 → 1550
        assert d["comercio_precio_calculado"] == 1550, d
        print("5. Subcategoría sin margen usa el de la madre (1940);")
        print("   sobre el precio del proveedor (800): 1550 ✓")

        c.call("product.template", "action_comercio_etiquetas_impresas", [p])
        assert not leer(p)["comercio_etiqueta_pendiente"]
        print("6. «Marcar impresas»: la etiqueta deja de estar pendiente ✓")

        # 7. Margen especial: excepción al rubro (base, IVA y redondeo siguen siendo de la categoría)
        # Desde «Márgenes especiales» → «Agregar producto» (sin buscarlo en otra pantalla)
        asistente = c.create("comercio.margen.especial.wizard", {"producto_ids": [(6, 0, [p])], "margen": 30})
        c.call("comercio.margen.especial.wizard", "action_aplicar", [asistente])
        d = leer(p)
        # 1000 + 30 % = 1300; + 21 % = 1573 → 1580 (el rubro diría 1940)
        assert d["comercio_precio_calculado"] == 1580 and "margen especial" in d["comercio_precio_detalle"], d
        # Sin elegir base, queda la de su rubro (costo), ya completada para cambiarla si hace falta
        base = c.read("product.template", [p], ["comercio_base_especial"])[0]["comercio_base_especial"]
        assert base == "costo", base
        especiales = c.search_read("product.template", [("comercio_margen_especial", "=", True),
                                                        ("id", "in", productos)], ["id"])
        assert [e["id"] for e in especiales] == [p], especiales
        # Con su propia base, como en las categorías: el precio de un proveedor. Mientras ese
        # proveedor no lo tenga en su lista, se usa el costo y «Cómo se calculó» lo dice.
        asistente = c.create("comercio.margen.especial.wizard", {
            "producto_ids": [(6, 0, [p])], "margen": 30, "base": "proveedor", "proveedor_id": socio})
        c.call("comercio.margen.especial.wizard", "action_aplicar", [asistente])
        d = leer(p)
        assert d["comercio_precio_calculado"] == 1580, d
        assert "no lo tiene en su lista" in d["comercio_precio_detalle"], d
        c.create("product.supplierinfo", {"partner_id": socio, "product_tmpl_id": p, "price": 900})
        d = leer(p)
        # 900 + 30 % = 1170; + 21 % = 1415,7 → 1420
        assert d["comercio_precio_calculado"] == 1420 and "Precio de" in d["comercio_precio_detalle"], d
        c.write("product.template", [p], {"comercio_base_especial": "costo"})
        assert leer(p)["comercio_precio_calculado"] == 1580, leer(p)  # vuelve al costo (1000)
        c.write("product.template", [p], {"comercio_base_especial": False})
        assert leer(p)["comercio_precio_calculado"] == 1580, leer(p)  # como su rubro: costo
        c.write("product.template", [p], {"comercio_margen_propio": 0})
        assert leer(p)["comercio_precio_calculado"] == 1210, leer(p)  # al costo + IVA
        c.write("product.template", [p], {"comercio_margen_especial": False})
        assert leer(p)["comercio_precio_calculado"] == 1940, leer(p)
        print("7. «Agregar producto» con margen especial 30 %: 1580 en vez de 1940 del rubro,")
        print("   con la base de su rubro ya completada (costo);")
        print("   con un proveedor que no lo tiene: costo y lo avisa; cuando lo tiene (900): 1420;")
        print("   sobre el costo o como el rubro: 1580;")
        print("   con 0 %, 1210 (costo + IVA); al desmarcarlo vuelve al del rubro ✓")

        # 8. Manda el IVA del producto (el que cobra la caja); el del rubro es el que se propone
        iva105 = c.search_read("ir.model.data", [("module", "=", "account"),
                                                 ("name", "=", "1_ri_tax_vat_10_ventas")],
                               ["res_id"])[0]["res_id"]
        r = c.create("product.template", {"name": f"[EJ] Precio IVA {MARCA}", "categ_id": madre,
                                          "standard_price": 1000})
        productos.append(r)
        assert leer(r)["taxes_id"] == [iva], leer(r)  # nuevo sin IVA elegido: el del rubro
        c.write("product.template", [r], {"taxes_id": [(6, 0, [iva105])]})
        d = leer(r)
        # 1000 + 60 % = 1600; + 10,5 % = 1768 → 1770
        assert d["comercio_precio_calculado"] == 1770 and "del producto" in d["comercio_precio_detalle"], d
        assert d["comercio_precio_desactualizado"], d
        c.call("product.template", "action_comercio_aplicar_precio", [r])
        d = leer(r)
        assert d["list_price"] == 1770 and d["taxes_id"] == [iva105], d
        print("8. Producto nuevo: toma el IVA del rubro (21 %); cambiado a 10,5 %: sugerido 1770,")
        print("   «Precios a actualizar» y al aplicar conserva su 10,5 % ✓")

        # 9. Diferencia chica: 1770 con precio actual 1740 (+1,7 %) es chico con 5 %; con 1500 (+18 %) no
        empresa = c.search_read("res.company", [], ["comercio_diferencia_chica"])[0]
        anterior = empresa["comercio_diferencia_chica"]

        def diferencia_chica(porcentaje: float) -> None:
            asistente = c.create("comercio.diferencia.chica.wizard", {"porcentaje": porcentaje})
            c.call("comercio.diferencia.chica.wizard", "action_guardar", [asistente])

        def chico(precio: float) -> bool:
            c.write("product.template", [r], {"list_price": precio, "comercio_precio_manual": False})
            campos = ["comercio_precio_cambio_chico", "comercio_precio_desactualizado"]
            d = c.read("product.template", [r], campos)[0]
            para_cambiar = c.search_read("product.template", [
                ("id", "=", r), ("comercio_precio_desactualizado", "=", True),
                ("comercio_precio_cambio_chico", "=", False)], ["id"])
            assert d["comercio_precio_desactualizado"], d
            assert d["comercio_precio_cambio_chico"] == (not para_cambiar), d
            return d["comercio_precio_cambio_chico"]

        diferencia_chica(5)
        try:
            assert chico(1740) and not chico(1500)
        finally:
            diferencia_chica(anterior)
        print("9. Diferencia chica 5 %: de 1740 a 1770 (+1,7 %) en naranja y oculto;")
        print("   de 1500 (+18 %) para cambiar ✓")
        print("Todo OK.")
        return 0
    finally:
        precios = [s["id"] for s in c.search_read("product.supplierinfo", [("partner_id", "=", socio)],
                                                  ["id"])]
        if precios:
            c.call("product.supplierinfo", "unlink", precios)
        # Productos recién creados y sin uso: se borran, y con ellos las categorías de la prueba
        try:
            if productos:
                c.call("product.template", "unlink", productos)
            c.call("product.category", "unlink", [hija, madre])
        except Exception:  # noqa: BLE001 — si algo los usó, quedan archivados
            if productos:
                c.write("product.template", productos, {"active": False})
        c.write("res.partner", [socio], {"active": False})
        print("   (datos de la prueba borrados: el lab queda limpio)")


if __name__ == "__main__":
    sys.exit(main())
