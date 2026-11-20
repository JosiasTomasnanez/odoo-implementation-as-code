"""Prueba de punta a punta del módulo comercio_factura_proveedor en el lab.

Con un proveedor FICTICIO nuevo en cada corrida (CUIT ficticio válido):

1. Su lista (CSV) con dos productos: uno se agrega a nuestro catálogo, el otro no.
2. Un PDF de factura armado acá (con texto, como el que manda el sistema de un proveedor)
   con cuatro artículos: el que tenemos (código al principio de la descripción), el que
   está solo en su lista, uno nuestro que este proveedor no tenía y uno desconocido.
3. Se sube como la administración (Compras → Facturas → Subir) sin que el proveedor tenga
   CUIT: la factura queda sin proveedor y avisa. Se elige el proveedor y «Leer factura»:
   carga el que tenemos (precio y bonificación de la factura), guarda el CUIT en el
   proveedor y pone tipo (factura A), número y fecha.
4. «Agregar» (desde su lista), «Es este» (uno nuestro elegido a mano) y «Crear producto»
   (desconocido): quedan los cuatro cargados, sin la digitalización paga de Odoo.
5. «Leer factura» otra vez no duplica líneas.

Uso: .venv/bin/python tests/e2e/factura_proveedor.py   (o make e2e-factura-proveedor)
No usar en producción: crea un proveedor, productos y una factura de prueba.
"""

from __future__ import annotations

import base64
import sys
import time

from odoo_iac.client import connect
from odoo_iac.settings import load_environment

c = connect(load_environment("lab"))
MARCA = str(int(time.time()))[-6:]


def cuit_ficticio(cuerpo: str) -> str:
    """CUIT «30» + 8 dígitos con su verificador (distinto en cada corrida: la anterior queda guardada)."""
    for prefijo in ("30", "33"):
        digitos = prefijo + cuerpo
        resto = sum(int(d) * p for d, p in zip(digitos, (5, 4, 3, 2, 7, 6, 5, 4, 3, 2), strict=True)) % 11
        if resto != 1:  # con resto 1 no hay verificador válido para ese prefijo
            return digitos + str(0 if resto == 0 else 11 - resto)
    raise ValueError(cuerpo)


CUIT = cuit_ficticio("71" + MARCA)
RUBRO = "[EJ] Ferretería"


def pdf_con_texto(renglones: list[tuple[float, float, str]]) -> bytes:
    """PDF mínimo de una página: cada renglón es (x, y, texto) en puntos, Helvetica 9."""

    def escapar(texto: str) -> str:
        return texto.replace("\\", "\\\\").replace("(", "\\(").replace(")", "\\)")

    contenido = (
        "BT /F1 9 Tf " + " ".join(f"1 0 0 1 {x} {y} Tm ({escapar(t)}) Tj" for x, y, t in renglones) + " ET"
    )
    flujo = contenido.encode("latin-1")
    objetos = [
        b"<< /Type /Catalog /Pages 2 0 R >>",
        b"<< /Type /Pages /Kids [3 0 R] /Count 1 >>",
        b"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 595 842] /Contents 4 0 R "
        b"/Resources << /Font << /F1 5 0 R >> >> >>",
        b"<< /Length " + str(len(flujo)).encode() + b" >>\nstream\n" + flujo + b"\nendstream",
        b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica /Encoding /WinAnsiEncoding >>",
    ]
    salida = bytearray(b"%PDF-1.4\n")
    posiciones = []
    for i, objeto in enumerate(objetos, start=1):
        posiciones.append(len(salida))
        salida += f"{i} 0 obj\n".encode() + objeto + b"\nendobj\n"
    xref = len(salida)
    salida += f"xref\n0 {len(objetos) + 1}\n0000000000 65535 f \n".encode()
    salida += b"".join(f"{p:010d} 00000 n \n".encode() for p in posiciones)
    salida += f"trailer\n<< /Size {len(objetos) + 1} /Root 1 0 R >>\nstartxref\n{xref}\n%%EOF\n".encode()
    return bytes(salida)


def factura_pdf(nuestro: str) -> bytes:
    columnas = [40, 100, 330, 380, 430, 490, 545]  # separadas como en una factura real
    filas = [
        ["CANTIDAD", "ARTÍCULO", "T.IVA", "PRECIO", "% BONIF.", "P.BONIF.", "IMPORTE"],
        ["2,00", f"A1-{MARCA} - TUERCA HEXAGONAL 1/4", "21,00", "1000,00", "10", "900,00", "1800,00"],
        ["3,00", f"A2-{MARCA} - ARANDELA PLANA 1/4", "21,00", "100,00", "10", "90,00", "270,00"],
        ["1,00", nuestro, "21,00", "500,00", "", "500,00", "500,00"],
        ["4,00", f"X9-{MARCA} - CANDADO BRONCE 40 MM", "21,00", "250,00", "", "250,00", "1000,00"],
        ["Subtotal", "", "", "", "", "", "3570,00"],
    ]
    renglones = [
        (40, 800, "FACTURA   ORIGINAL"),
        (40, 785, "A"),
        (300, 785, "Nº A 0003-00001234"),
        (40, 770, "Código: 1"),
        (300, 770, "Fecha: 20/10/2026"),
        (40, 755, f"CUIT: {CUIT[:2]}-{CUIT[2:10]}-{CUIT[10]}"),
        (40, 740, "Cliente: COMERCIO EJEMPLO"),
    ]
    y = 700
    for fila in filas:
        renglones += [(x, y, texto) for x, texto in zip(columnas, fila, strict=True) if texto]
        y -= 15
    return pdf_con_texto(renglones)


def contar(modelo, dominio) -> int:
    return len(c.search_read(modelo, dominio, ["id"]))


def lineas(move):
    return {
        f["descripcion"]: f
        for f in c.search_read(
            "comercio.factura.linea",
            [("move_id", "=", move)],
            [
                "descripcion",
                "estado",
                "producto_id",
                "precio",
                "bonificacion",
                "move_line_id",
                "lista_linea_id",
            ],
        )
    }


def main() -> int:
    rubro = c.search_read("product.category", [("name", "=", RUBRO)], ["id"])
    if not rubro:
        print(f"Falta la categoría «{RUBRO}»: correr antes `make apply`.", file=sys.stderr)
        return 1
    rubro = rubro[0]["id"]
    empresa = c.search_read("res.company", [], ["extract_in_invoice_digitalization_mode"])[0]
    assert empresa["extract_in_invoice_digitalization_mode"] == "no_send", empresa

    socio = c.create(
        "res.partner", {"name": f"[EJ] Bulonera factura {MARCA}", "is_company": True, "supplier_rank": 1}
    )
    # 1. Su lista: A1 se agrega a nuestro catálogo, A2 queda solo en su lista
    lista = c.create("comercio.lista.proveedor", {"partner_id": socio, "categoria_id": rubro})
    csv = (
        f"Código;Descripción;Precio\nA1-{MARCA};TUERCA HEXAGONAL 1/4;1000\n"
        f"A2-{MARCA};ARANDELA PLANA 1/4;100\n"
    ).encode()
    w = c.create(
        "comercio.importar.lista.wizard",
        {
            "partner_id": socio,
            "lista_id": lista,
            "categoria_id": rubro,
            "nombre_archivo": "lista.csv",
            "archivo": base64.b64encode(csv).decode(),
        },
    )
    importacion = c.call("comercio.importar.lista.wizard", "action_importar", [w])["res_id"]
    fila_a1 = c.search_read(
        "comercio.lista.importacion.linea",
        [("importacion_id", "=", importacion), ("codigo_proveedor", "=", f"A1-{MARCA}")],
        ["id"],
    )
    # En el lab puede parecerse a otra tuerca («posible duplicado»): se agrega como nuevo igual
    c.call("comercio.lista.importacion.linea", "action_es_nuevo", [fila_a1[0]["id"]])
    c.call("comercio.lista.importacion.linea", "action_aplicar", [fila_a1[0]["id"]])
    assert c.read("comercio.lista.importacion.linea", [fila_a1[0]["id"]], ["producto_id"])[0]["producto_id"]
    # Uno nuestro que este proveedor no vende (se elige a mano en la factura)
    nuestro = c.create(
        "product.template", {"name": f"[EJ] Pinza universal {MARCA}", "categ_id": rubro, "purchase_ok": True}
    )
    variante = c.search_read("product.product", [("product_tmpl_id", "=", nuestro)], ["id"])[0]["id"]

    # 3. Subirla como la administración
    adjunto = c.create(
        "ir.attachment",
        {
            "name": f"factura-{MARCA}.pdf",
            "raw": base64.b64encode(factura_pdf(f"PINZA UNIVERSAL 8 {MARCA}")).decode(),
        },
    )
    diario = c.search_read("account.journal", [("type", "=", "purchase")], ["id"])[0]["id"]
    move = c.call(
        "account.journal",
        "create_document_from_attachment",
        [diario],
        attachment_ids=[adjunto],
        context={"default_move_type": "in_invoice"},
    )["res_id"]
    datos = c.read("account.move", [move], ["partner_id", "comercio_lectura", "extract_state"])[0]

    def cuit_sin_proveedor(move):
        campo = "comercio_cuit_sin_proveedor"
        return c.read("account.move", [move], [campo])[0][campo]

    # Nadie tiene ese CUIT: no se adivina; cartel para elegir el proveedor (o crearlo)
    assert not datos["partner_id"], datos
    assert CUIT in (datos["comercio_lectura"] or ""), datos["comercio_lectura"]
    assert cuit_sin_proveedor(move) == CUIT
    assert datos["extract_state"] in ("no_extract_requested", False), datos
    print("✓ Subida sin la digitalización de Odoo; nadie tenía el CUIT", CUIT, "→ cartel «Elegir proveedor»")

    asistente = c.create("comercio.factura.elegir.proveedor", {"move_id": move, "partner_id": socio})
    c.call("comercio.factura.elegir.proveedor", "action_aceptar", [asistente])
    assert not cuit_sin_proveedor(move)
    datos = c.read(
        "account.move", [move], ["l10n_latam_document_type_id", "l10n_latam_document_number", "invoice_date"]
    )[0]
    assert datos["invoice_date"] == "2026-10-20", datos
    if datos.get("l10n_latam_document_type_id"):
        assert "FACTURAS A" in datos["l10n_latam_document_type_id"][1], datos
        assert datos["l10n_latam_document_number"].endswith("0003-00001234"), datos
    assert c.read("res.partner", [socio], ["vat"])[0]["vat"].replace("-", "") == CUIT
    leidas = lineas(move)
    assert len(leidas) == 4, list(leidas)
    a1 = leidas["TUERCA HEXAGONAL 1/4"]
    assert a1["estado"] == "cargada" and a1["precio"] == 1000 and a1["bonificacion"] == 10, a1
    # En su lista, o «¿Es este?» si se parece a una arandela que ya tenemos (corridas anteriores)
    assert leidas["ARANDELA PLANA 1/4"]["estado"] in ("en_lista", "parecido"), leidas["ARANDELA PLANA 1/4"]
    # «No está», o «¿Es este?» si una corrida anterior ya creó un candado igual (lo reconoce)
    assert leidas["CANDADO BRONCE 40 MM"]["estado"] in ("nuevo", "parecido"), leidas["CANDADO BRONCE 40 MM"]
    anotadas = c.search_read(
        "account.move.line",
        [("move_id", "=", move), ("display_type", "=", "product")],
        ["product_id", "quantity", "price_unit", "comercio_anotada"],
    )
    assert len(anotadas) == 4, anotadas  # los 4 en la factura: 1 con producto y 3 anotados sin producto
    assert sum(1 for ml in anotadas if not ml["product_id"] and ml["comercio_anotada"]) == 3, anotadas
    print("✓ «Leer factura»: proveedor, CUIT guardado, tipo, número, fecha; los 4 artículos en la factura")
    print("  (1 con su producto y 3 anotados sin producto, con la cantidad y el precio de la factura)")

    # 4. Agregar desde su lista, Es este y Crear producto
    ids = {d: f["id"] for d, f in leidas.items()}
    c.call("comercio.factura.linea", "action_agregar_desde_lista", [ids["ARANDELA PLANA 1/4"]])
    pinza = next(d for d in ids if "PINZA" in d)
    c.write("comercio.factura.linea", [ids[pinza]], {"producto_id": variante})
    c.call("comercio.factura.linea", "action_es_este", [ids[pinza]])
    c.write("comercio.factura.linea", [ids["CANDADO BRONCE 40 MM"]], {"categoria_id": rubro})
    c.call("comercio.factura.linea", "action_crear_producto", [ids["CANDADO BRONCE 40 MM"]])
    leidas = lineas(move)
    assert all(f["estado"] == "cargada" for f in leidas.values()), leidas
    candado = c.search_read(
        "product.supplierinfo",
        [("partner_id", "=", socio), ("product_code", "=", f"X9-{MARCA}")],
        ["product_tmpl_id", "price"],
    )
    assert candado and candado[0]["price"] == 250, candado
    # El costo llega después de crearlo: igual toma el precio de venta del margen (no queda en $1)
    precio = c.read("product.template", [candado[0]["product_tmpl_id"][0]], ["list_price"])[0]["list_price"]
    assert precio > 1, precio
    assert (
        contar("product.supplierinfo", [("partner_id", "=", socio), ("product_tmpl_id", "=", nuestro)]) == 1
    )
    facturadas = c.search_read(
        "account.move.line",
        [("move_id", "=", move), ("display_type", "=", "product")],
        ["product_id", "quantity", "price_unit", "discount"],
    )
    assert len(facturadas) == 4 and all(ml["product_id"] for ml in facturadas), facturadas  # no se duplicaron
    print(
        "✓ Agregar (de su lista), Es este (nuestro) y Crear producto (desconocido): "
        "las mismas 4 líneas, con producto"
    )

    # 5. Leer otra vez no duplica
    c.call("account.move", "action_comercio_leer_factura", [move])
    otra_vez = contar("account.move.line", [("move_id", "=", move), ("display_type", "=", "product")])
    assert otra_vez == 4, otra_vez
    assert all(f["estado"] == "cargada" for f in lineas(move).values())
    print("✓ «Leer factura» otra vez: las mismas 4 líneas, todas reconocidas")

    # 6. «Subir» de la app Compras (Odoo lo usa para pedidos en XML): con una factura, crea la factura
    adjunto = c.create(
        "ir.attachment",
        {
            "name": f"factura-compras-{MARCA}.pdf",
            "raw": base64.b64encode(factura_pdf("PINZA UNIVERSAL 8")).decode(),
        },
    )
    accion = c.call("purchase.order", "create_document_from_attachment", [], attachment_ids=[adjunto])
    assert accion["res_model"] == "account.move", accion
    otra = accion.get("res_id") or accion["domain"][0][2][0]
    datos = c.read("account.move", [otra], ["partner_id", "move_type", "invoice_line_ids"])[0]
    assert datos["partner_id"][0] == socio and datos["move_type"] == "in_invoice", datos
    assert len(datos["invoice_line_ids"]) == 4, datos
    print("✓ «Subir» de Compras con la factura: crea la factura del proveedor (no un pedido vacío)")

    # 7. «Lista del proveedor» desde una orden: su lista entera (lo nuestro está en «Catálogo»); «Pedir» suma
    orden = c.create("purchase.order", {"partner_id": socio})
    lista_accion = c.call(
        "purchase.order.line", "action_comercio_lista_proveedor", [], context={"order_id": orden}
    )
    assert not lista_accion["context"].get("search_default_registrado"), lista_accion
    filas = c.search_read("comercio.lista.importacion.linea", lista_accion["domain"], ["id", "producto_id"])
    # A1 y A2 de su lista, más el candado (creado) y la pinza (Es este) que se sumaron desde la factura
    assert len(filas) == 4 and all(f["producto_id"] for f in filas), filas
    aviso = c.call(
        "comercio.lista.importacion.linea",
        "action_agregar_a_pedido",
        [filas[0]["id"]],
        context={"comercio_pedido_id": orden},
    )
    assert aviso.get("tag") == "display_notification", aviso
    assert contar("purchase.order.line", [("order_id", "=", orden)]) == 1
    c.call("purchase.order", "button_cancel", [orden])
    print("✓ «Lista del proveedor» en la orden: su lista entera; «Pedir» suma a esa orden")

    # 8. «Crear orden de compra» desde la factura (llegó sin pedido en Odoo)
    accion = c.call("account.move", "action_comercio_crear_orden", [move])
    compra = c.read(
        "purchase.order", [accion["res_id"]], ["state", "order_line", "picking_ids", "partner_id"]
    )[0]
    assert compra["state"] == "purchase" and len(compra["order_line"]) == 4, compra
    assert compra["partner_id"][0] == socio and compra["picking_ids"], (
        compra
    )  # con la recepción para el stock
    unidas = c.search_read(
        "account.move.line",
        [("move_id", "=", move), ("display_type", "=", "product")],
        ["purchase_line_id", "price_unit", "discount"],
    )
    avisos_lista = c.search_read(
        "purchase.order.line", [("order_id", "=", accion["res_id"])], ["comercio_aviso_lista"]
    )
    assert not any(li["comercio_aviso_lista"] for li in avisos_lista), avisos_lista  # todo es de su lista
    assert all(ml["purchase_line_id"] for ml in unidas), unidas
    lineas_orden = c.read(
        "purchase.order.line", compra["order_line"], ["price_unit", "discount", "product_qty"]
    )
    assert sorted(ml["price_unit"] for ml in unidas) == sorted(lo["price_unit"] for lo in lineas_orden), (
        lineas_orden
    )
    print(
        "✓ «Crear orden de compra» desde la factura: confirmada, con la recepción y la factura unida a ella"
    )

    # 9. Otra factura con dos artículos que no tenemos ni están en su lista: «Crear orden de compra»
    #    no da error, abre los que faltan; «Agregar al catálogo» los dos de una vez (y se suman a su
    #    lista vigente); después la orden sale con todo
    renglones = [
        (40, 785, "A"),
        (300, 785, "Nº A 0003-00001299"),
        (40, 770, "Código: 1"),
        (300, 770, "Fecha: 21/10/2026"),
        (40, 755, f"CUIT: {CUIT[:2]}-{CUIT[2:10]}-{CUIT[10]}"),
    ]
    for y, fila in (
        (700, ["CANTIDAD", "ARTÍCULO", "T.IVA", "PRECIO", "% BONIF.", "P.BONIF.", "IMPORTE"]),
        (685, ["2,00", f"Y1-{MARCA} - SERRUCHO 18 PULGADAS", "21,00", "300,00", "", "300,00", "600,00"]),
        (670, ["3,00", f"Y2-{MARCA} - LIMA TRIANGULAR 6", "21,00", "50,00", "", "50,00", "150,00"]),
    ):
        renglones += [(x, y, t) for x, t in zip([40, 100, 330, 380, 430, 490, 545], fila, strict=True) if t]
    adjunto = c.create(
        "ir.attachment",
        {"name": f"factura2-{MARCA}.pdf", "raw": base64.b64encode(pdf_con_texto(renglones)).decode()},
    )
    nueva = c.call(
        "account.journal",
        "create_document_from_attachment",
        [diario],
        attachment_ids=[adjunto],
        context={"default_move_type": "in_invoice"},
    )["res_id"]
    aviso = c.call("account.move", "action_comercio_crear_orden", [nueva])
    assert (
        aviso.get("tag") == "display_notification"
        and aviso["params"]["next"]["res_model"] == "comercio.factura.linea"
    ), aviso
    faltan = [
        f["id"]
        for f in c.search_read(
            "comercio.factura.linea", [("move_id", "=", nueva), ("estado", "!=", "cargada")], ["id"]
        )
    ]
    assert len(faltan) == 2, faltan
    c.write("comercio.factura.linea", faltan, {"categoria_id": rubro})
    c.call("comercio.factura.linea", "action_agregar_al_catalogo", faltan)
    assert all(f["estado"] == "cargada" for f in lineas(nueva).values()), lineas(nueva)
    sumadas = c.search_read(
        "comercio.lista.importacion.linea",
        [("codigo_proveedor", "in", [f"Y1-{MARCA}", f"Y2-{MARCA}"]), ("de_lista_vigente", "=", True)],
        ["producto_id"],
    )
    assert len(sumadas) == 2 and all(f["producto_id"] for f in sumadas), sumadas
    orden2 = c.call("account.move", "action_comercio_crear_orden", [nueva])
    assert orden2["res_model"] == "purchase.order", orden2
    assert len(c.read("purchase.order", [orden2["res_id"]], ["order_line"])[0]["order_line"]) == 2
    print("✓ Factura con artículos que no tenemos: «Crear orden» abre los que faltan, «Agregar al catálogo»")
    print("  los suma de una vez (también a su lista vigente) y la orden sale con todo")

    # 10. Caso normal: orden → recepción → factura subida desde la orden. Pedidos 3 a $ 1000, se
    #     reciben 2 y la factura cobra 3 a $ 1100 con 10 % de bonificación: avisa cada diferencia y el
    #     control nativo (account_3way_match) la deja en «Excepción»
    tuerca = c.read("comercio.lista.importacion.linea", [fila_a1[0]["id"]], ["producto_id"])[0][
        "producto_id"
    ][0]
    variante_tuerca = c.search_read("product.product", [("product_tmpl_id", "=", tuerca)], ["id"])[0]["id"]
    compra = c.create(
        "purchase.order",
        {
            "partner_id": socio,
            "order_line": [(0, 0, {"product_id": variante_tuerca, "product_qty": 3, "price_unit": 1000})],
        },
    )
    c.call("purchase.order", "button_confirm", [compra])
    recepcion = c.read("purchase.order", [compra], ["picking_ids"])[0]["picking_ids"][0]
    for movimiento in c.search_read("stock.move", [("picking_id", "=", recepcion)], ["id"]):
        c.write("stock.move", [movimiento["id"]], {"quantity": 2, "picked": True})
    c.call(
        "stock.picking",
        "button_validate",
        [recepcion],
        context={"skip_backorder": True, "picking_ids_not_to_backorder": [recepcion]},
    )
    renglones = [
        (40, 785, "A"),
        (300, 785, "Nº A 0003-00001300"),
        (40, 770, "Código: 1"),
        (300, 770, "Fecha: 22/10/2026"),
        (40, 755, f"CUIT: {CUIT[:2]}-{CUIT[2:10]}-{CUIT[10]}"),
    ]
    for y, fila in (
        (700, ["CANTIDAD", "ARTÍCULO", "T.IVA", "PRECIO", "% BONIF.", "P.BONIF.", "IMPORTE"]),
        (685, ["3,00", f"A1-{MARCA} - TUERCA HEXAGONAL 1/4", "21,00", "1100,00", "10", "990,00", "2970,00"]),
    ):
        renglones += [(x, y, t) for x, t in zip([40, 100, 330, 380, 430, 490, 545], fila, strict=True) if t]
    # El pie, como el de FC: títulos arriba e importes debajo; flete gravado y percepción IIBB Córdoba
    for y, fila in (
        (640, ["Subtotal", "Flete 2,50%", "Neto Gravado", "IVA", "Percepciones", "TOTAL"]),
        (625, ["2970,00", "74,25", "3044,25", "639,29", "30,00", "3713,54"]),
    ):
        renglones += [(x, y, t) for x, t in zip([40, 140, 220, 340, 415, 520], fila, strict=True)]
    renglones.append((40, 600, "Perc.IIBB: CORDOBA 30,00"))
    adjunto = c.create(
        "ir.attachment",
        {"name": f"factura3-{MARCA}.pdf", "raw": base64.b64encode(pdf_con_texto(renglones)).decode()},
    )
    accion = c.call("purchase.order", "action_create_invoice", [compra], attachment_ids=[adjunto])
    desde_orden = accion.get("res_id") or accion["domain"][0][2][0]
    leida = list(lineas(desde_orden).values())
    assert len(leida) == 1 and leida[0]["estado"] == "cargada", leida
    diferencia = (
        c.read("comercio.factura.linea", [leida[0]["id"]], ["diferencia_orden"])[0]["diferencia_orden"] or ""
    )
    assert "Precio" in diferencia and "bonificación" in diferencia and "se recibió 2" in diferencia, (
        diferencia
    )
    unida = c.search_read(
        "account.move.line",
        [("move_id", "=", desde_orden), ("display_type", "=", "product"), ("comercio_extra", "=", False)],
        ["purchase_line_id", "quantity", "price_unit", "discount"],
    )
    assert len(unida) == 1 and unida[0]["purchase_line_id"] and unida[0]["quantity"] == 3, (
        unida
    )  # sin duplicar
    assert c.read("account.move", [desde_orden], ["release_to_pay"])[0]["release_to_pay"] == "exception"
    # El pie: flete y percepción en la factura (no en la orden) y el total igual al del proveedor
    extras = {
        ml["comercio_extra"]: ml
        for ml in c.search_read(
            "account.move.line",
            [("move_id", "=", desde_orden), ("comercio_extra", "!=", False)],
            ["comercio_extra", "price_unit", "purchase_line_id"],
        )
    }
    assert extras["flete"]["price_unit"] == 74.25 and not extras["flete"]["purchase_line_id"], extras
    assert "percepcion" in extras, extras
    pie = c.read(
        "account.move",
        [desde_orden],
        ["amount_total", "amount_residual", "comercio_total_factura", "comercio_total_distinto"],
    )[0]
    assert pie["comercio_total_factura"] == 3713.54 and abs(pie["amount_total"] - 3713.54) < 0.02, pie
    assert pie["amount_residual"] == pie["amount_total"], pie  # lo que se le debe, con la percepción
    # Flete y percepción no están en la orden: no bajan la «Coincidencia de órdenes de compra»
    coincidencia = c.read("account.move", [desde_orden], ["purchase_matched_ratio"])[0][
        "purchase_matched_ratio"
    ]
    assert coincidencia == 100, coincidencia
    assert not pie["comercio_total_distinto"], pie
    # Contra su lista (A1 a $ 1000): cobra $ 1100 y bonifica 10 % → $ 990 neto, distinto antes y después
    # de la bonificación: avisa. En la primera factura (1000 − 10 %) el bruto coincidía: sin aviso
    contra_lista = c.read("comercio.factura.linea", [leida[0]["id"]], ["diferencia_lista"])[0][
        "diferencia_lista"
    ]
    assert contra_lista and "Lista $ 1.000,00" in contra_lista, contra_lista
    sin_diferencia = lineas(move)["TUERCA HEXAGONAL 1/4"]["id"]  # releída en el paso 5: id nuevo
    assert not c.read("comercio.factura.linea", [sin_diferencia], ["diferencia_lista"])[0]["diferencia_lista"]
    print("✓ Orden → recepción → factura desde la orden: la factura manda (3 a $ 1100 − 10 %), avisa")
    print(f"  «{diferencia}» y «¿Pagar?» queda en Excepción (control nativo)")
    print("✓ El pie de la factura: flete con IVA y percepción IIBB Córdoba; total $ 3.713,54 como el papel")

    # 11. Compra sin factura: el proveedor no mandó la factura. El botón «Sin factura» de la orden
    #     la registra sin IVA en el diario sin factura, se confirma y se paga. Y un presupuesto en papel
    #     subido a ese diario: el IVA que cobra va como una línea más (sin crédito fiscal)
    provisorio = c.search_read("account.journal", [("comercio_sin_factura", "=", True)], ["id"])
    assert provisorio, "Falta el diario «Compras sin factura»: correr antes `make apply`."
    provisorio = provisorio[0]["id"]
    compra2 = c.create(
        "purchase.order",
        {
            "partner_id": socio,
            "order_line": [(0, 0, {"product_id": variante_tuerca, "product_qty": 2, "price_unit": 1000})],
        },
    )
    c.call("purchase.order", "button_confirm", [compra2])
    c.call(
        "stock.picking",
        "button_validate",
        c.read("purchase.order", [compra2], ["picking_ids"])[0]["picking_ids"],
    )
    accion = c.call("purchase.order", "action_comercio_factura_provisoria", [compra2])
    provisoria = accion.get("res_id") or accion["domain"][0][2][0]
    datos = c.read(
        "account.move",
        [provisoria],
        ["journal_id", "amount_total", "amount_tax", "comercio_provisoria", "release_to_pay"],
    )[0]
    assert datos["journal_id"][0] == provisorio and datos["comercio_provisoria"], datos
    assert datos["amount_total"] == 2000 and not datos["amount_tax"], datos  # sin IVA
    assert datos["release_to_pay"] == "yes", datos  # lo pedido, lo recibido y lo registrado coinciden
    c.write("account.move", [provisoria], {"invoice_date": "2026-10-23"})
    c.call("account.move", "action_post", [provisoria])
    contexto = {"active_model": "account.move", "active_ids": [provisoria]}
    pago = c.call("account.payment.register", "create", vals_list=[{}], context=contexto)
    c.call(
        "account.payment.register",
        "action_create_payments",
        [pago[0] if isinstance(pago, list) else pago],
        context=contexto,
    )
    assert c.read("account.move", [provisoria], ["payment_state"])[0]["payment_state"] in (
        "paid",
        "in_payment",
    )
    print("✓ «Sin factura» desde la orden: diario sin factura, sin IVA, «Se debe pagar: Sí», pagada")

    renglones = [(40, 800, "PRESUPUESTO Nº 77"), (300, 785, "Fecha: 23/10/2026")]
    for y, fila in (
        (700, ["CANTIDAD", "ARTÍCULO", "T.IVA", "PRECIO", "% BONIF.", "P.BONIF.", "IMPORTE"]),
        (685, ["2,00", f"A1-{MARCA} - TUERCA HEXAGONAL 1/4", "21,00", "1000,00", "", "1000,00", "2000,00"]),
    ):
        renglones += [(x, y, t) for x, t in zip([40, 100, 330, 380, 430, 490, 545], fila, strict=True) if t]
    for y, fila in (
        (640, ["Subtotal", "Neto Gravado", "IVA", "TOTAL"]),
        (625, ["2000,00", "2000,00", "420,00", "2420,00"]),
    ):
        renglones += [(x, y, t) for x, t in zip([40, 220, 340, 520], fila, strict=True)]
    adjunto = c.create(
        "ir.attachment",
        {"name": f"presupuesto-{MARCA}.pdf", "raw": base64.b64encode(pdf_con_texto(renglones)).decode()},
    )
    papel = c.call(
        "account.journal",
        "create_document_from_attachment",
        [provisorio],
        attachment_ids=[adjunto],
        context={"default_move_type": "in_invoice"},
    )["res_id"]
    c.write("account.move", [papel], {"partner_id": socio})
    c.call("account.move", "action_comercio_leer_factura", [papel])
    datos = c.read("account.move", [papel], ["amount_total", "amount_tax", "comercio_total_distinto"])[0]
    assert (
        datos["amount_total"] == 2420 and not datos["amount_tax"] and not datos["comercio_total_distinto"]
    ), datos
    sin_credito = c.search_read(
        "account.move.line", [("move_id", "=", papel), ("comercio_extra", "=", "sin_credito")], ["price_unit"]
    )
    assert [ml["price_unit"] for ml in sin_credito] == [420], sin_credito
    print("✓ Presupuesto subido a «Compras sin factura»: sin IVA y el IVA cobrado como costo ($ 2.420)")
    print("Prueba de la factura del proveedor: OK (factura en borrador:", move, ")")
    return 0


if __name__ == "__main__":
    sys.exit(main())
