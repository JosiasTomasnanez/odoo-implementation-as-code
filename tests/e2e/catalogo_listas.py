"""Prueba de punta a punta del módulo comercio_catalogo (listas de proveedores) en el lab.

Por la API JSON-2, como lo haría la pantalla. Con un proveedor FICTICIO nuevo en cada
corrida (no depende de corridas anteriores):

1. Primera lista (Excel con una fila de título antes de los encabezados): las columnas se
   sugieren solas; dos productos nuevos y un posible duplicado de un producto existente.
2. «Es el mismo» une el duplicado al producto existente; «Aplicar» crea los nuevos.
3. Segunda lista: suba chica (se aplica sola, con historial), suba grande (espera
   revisión), un producto que ya no está (se cierra su precio) y aviso de que otro
   proveedor quedó más barato.
4. Dos listas el mismo día: la baja de un precio que empezó hoy se aplica, «Ignorar»
   cierra la importación y «Retomar» la vuelve a dejar para decidir.
5. El proveedor cambia el formato (otros títulos, más filas arriba): las columnas se
   detectan solas, se avisa y no se aplica nada automáticamente; si no aparece el costo,
   queda en error para que lo resuelva una persona.
6. Del precio de la lista al costo (ADR 0029): descuentos de la lista, por familia, por
   producto y de la columna; IVA incluido con la alícuota de la columna o del producto;
   lista en dólares (fija y del día); «Recalcular costos» sin subir la lista otra vez.

Uso: .venv/bin/python tests/e2e/catalogo_listas.py
No usar en producción: crea proveedores y productos de prueba.
"""
from __future__ import annotations

import base64
import io
import random
import string
import sys
import time

import openpyxl

from odoo_iac.client import connect
from odoo_iac.settings import load_environment

CATALOGO = __import__("pathlib").Path(__file__).parents[2] / "addons" / "comercio_catalogo" / "catalogo"
sys.path.insert(0, str(CATALOGO))

c = connect(load_environment("lab"))
# Sin la revisión con IA al agregar (comercio_catalogo_ia): estas pruebas no dependen de Gemini
c.context["sin_revision_ia"] = True
MARCA = str(int(time.time()))[-6:]
PROVEEDOR = f"[EJ] Proveedor prueba {MARCA}"


def palabra() -> str:
    """Palabra al azar: los productos de prueba no se parecen a los de corridas anteriores."""
    return "".join(random.choices(string.ascii_uppercase, k=9))


AZUL = f"{palabra()} {palabra()} 1KG"
VERDE = f"{palabra()} {palabra()} 2KG"


def excel(filas: list[list]) -> str:
    libro = openpyxl.Workbook()
    hoja = libro.active
    hoja.append([f"LISTA DE PRECIOS {PROVEEDOR}"])  # título antes de los encabezados
    hoja.append(["Cód.", "Descripción", "EAN", "Precio s/IVA"])
    for fila in filas:
        hoja.append(fila)
    salida = io.BytesIO()
    libro.save(salida)
    return base64.b64encode(salida.getvalue()).decode()


def excel_con_formato(titulos: list[list], encabezados: list[str], filas: list[list]) -> str:
    """Excel con otro formato: filas de título a elección y otros encabezados."""
    libro = openpyxl.Workbook()
    hoja = libro.active
    for fila in [*titulos, encabezados, *filas]:
        hoja.append(fila)
    salida = io.BytesIO()
    libro.save(salida)
    return base64.b64encode(salida.getvalue()).decode()


def rubro() -> int:
    return c.search_read("product.category", [("name", "=", "[EJ] Mascotas")], ["id"])[0]["id"]


def importar(lista_id: int, filas: list[list], archivo: str | None = None) -> int:
    """Como en la pantalla «Importar lista»: se elige el proveedor (su lista ya existe)."""
    lista = c.read("comercio.lista.proveedor", [lista_id], ["partner_id", "categoria_id"])[0]
    # Con rubro (de él sale el precio de venta de lo que se agrega; sin margen no se deja agregar)
    wizard = c.create("comercio.importar.lista.wizard", {
        "partner_id": lista["partner_id"][0], "archivo": archivo or excel(filas),
        "nombre_archivo": "lista.xlsx",
        "categoria_id": lista["categoria_id"][0] if lista["categoria_id"] else rubro()})
    return c.call("comercio.importar.lista.wizard", "action_importar", [wizard])["res_id"]


def lineas(importacion_id: int) -> dict[str, dict]:
    filas = c.search_read("comercio.lista.importacion.linea", [("importacion_id", "=", importacion_id)],
                          ["codigo_proveedor", "accion", "estado", "costo", "costo_anterior", "variacion",
                           "candidato_ids", "producto_id", "automatico", "mas_barato_id"])
    return {f["codigo_proveedor"]: f for f in filas}


def precios(tmpl_id: int) -> list[dict]:
    return c.search_read("product.supplierinfo", [("product_tmpl_id", "=", tmpl_id)],
                         ["partner_id", "product_code", "price", "date_start", "date_end"])


def costo(tmpl_id: int) -> float:
    return c.read("product.template", [tmpl_id], ["standard_price"])[0]["standard_price"]


def mas_barato_vigente(tmpl_id: int) -> float:
    return min(p["price_discounted"] for p in c.search_read(
        "product.supplierinfo", [("product_tmpl_id", "=", tmpl_id), ("date_end", "=", False)],
        ["price_discounted"]))


def limpiar(socios: list[int], productos: list[int]) -> None:
    """Deja el lab como estaba: la prueba no ensucia lo que se usa para mirar a mano.
    Quita los precios de los proveedores de prueba, archiva sus productos, listas y contactos."""
    precios_prueba = c.search_read("product.supplierinfo", [("partner_id", "in", socios)], ["id"])
    if precios_prueba:
        c.call("product.supplierinfo", "unlink", [p["id"] for p in precios_prueba])
    activos = [p["id"] for p in c.search_read("product.template", [("id", "in", productos)], ["id"])]
    if activos:
        c.write("product.template", activos, {"available_in_pos": False})
        c.write("product.template", activos, {"active": False})
    listas = [x["id"] for x in c.search_read("comercio.lista.proveedor", [("partner_id", "in", socios)],
                                              ["id"], context={"active_test": False})]
    importaciones = [x["id"] for x in c.search_read("comercio.lista.importacion",
                                                    [("lista_id", "in", listas)], ["id"])]
    if importaciones:  # si no, quedan visibles en «Importaciones» del lab
        c.call("comercio.lista.importacion", "unlink", importaciones)
    if listas:
        c.call("comercio.lista.proveedor", "unlink", listas)
    c.write("res.partner", socios, {"active": False})


def main() -> int:
    socios_prueba: list[int] = []
    productos_prueba: list[int] = []
    try:
        return probar(socios_prueba, productos_prueba)
    finally:
        limpiar(socios_prueba, productos_prueba)
        print("   (datos de la prueba archivados: el lab queda limpio)")


def probar(socios_prueba: list[int], productos_prueba: list[int]) -> int:
    cinta = c.search_read("product.template", [("name", "=", "[EJ] Cinta métrica 5 m")], ["id"])
    assert cinta, "falta el producto de ejemplo «[EJ] Cinta métrica 5 m» (data/plantillas/productos.csv)"
    cinta_id = cinta[0]["id"]
    socio = c.create("res.partner", {"name": PROVEEDOR, "is_company": True, "supplier_rank": 1})
    socios_prueba.append(socio)
    lista = c.create("comercio.lista.proveedor", {"partner_id": socio, "tope_automatico": 10,
                                                 "frecuencia_dias": 15, "lista_completa": True})

    # 1. Primera lista
    imp1 = importar(lista, [
        ["X1", "CINTA METRICA 5 MTS", "", 4000],
        ["X2", AZUL, "", 1000],
        ["X3", VERDE, "", 2000],
    ])
    cfg = c.read("comercio.lista.proveedor", [lista], ["col_codigo", "col_descripcion", "col_costo",
                                                      "fila_encabezado"])[0]
    assert (cfg["col_codigo"], cfg["col_descripcion"], cfg["col_costo"], cfg["fila_encabezado"]) == (
        "Cód.", "Descripción", "Precio s/IVA", 2), cfg
    print("1. Columnas sugeridas solas (fila de títulos 2: Cód., Descripción, Precio s/IVA) ✓")
    filas = lineas(imp1)
    x1 = filas["X1"]
    assert x1["accion"] == "posible duplicado" and cinta_id in x1["candidato_ids"], x1
    assert filas["X2"]["accion"] == filas["X3"]["accion"] == "nuevo", filas
    print("   X1 posible duplicado de «Cinta métrica 5 m»; X2 y X3 nuevos ✓")

    linea = {f["codigo_proveedor"]: f["id"] for f in filas.values()}
    c.write("comercio.lista.importacion.linea", [linea["X1"]], {"producto_elegido_id": cinta_id})
    c.call("comercio.lista.importacion.linea", "action_es_el_mismo", [linea["X1"]])
    c.call("comercio.lista.importacion.linea", "action_aplicar", [linea["X2"], linea["X3"]])
    filas = lineas(imp1)
    assert all(f["estado"] == "aplicada" for f in filas.values()), filas
    assert any(p["partner_id"][1] == PROVEEDOR and p["product_code"] == "X1" for p in precios(cinta_id))
    x3_id = filas["X3"]["producto_id"][0]
    # Las listas llegan cada ~15 días: la primera se fecha antes, así la segunda arma historial
    # (dos listas el mismo día corrigen el precio del día sin agregar historial)
    previos = [p["id"] for p in c.search_read("product.supplierinfo", [("partner_id", "=", socio)], ["id"])]
    c.write("product.supplierinfo", previos, {"date_start": "2026-01-01"})
    productos_prueba.extend([x3_id, filas["X2"]["producto_id"][0]])
    print("2. «Es el mismo» unió X1 a la cinta; «Aplicar» (dos filas juntas) creó X2 y X3 ✓")

    # 2. Segunda lista: X1 +5 % (sola), X2 +50 % (revisar), X3 ya no está
    imp2 = importar(lista, [
        ["X1", "CINTA METRICA 5 MTS", "", 4200],
        ["X2", AZUL, "", 1500],
    ])
    filas = lineas(imp2)
    assert filas["X1"]["automatico"] and not filas["X2"]["automatico"], filas
    assert round(filas["X2"]["variacion"]) == 50, filas["X2"]
    bajas = [f for f in filas.values() if f["accion"] == "baja"]
    assert len(bajas) == 1 and bajas[0]["producto_id"][0] == x3_id, bajas
    c.call("comercio.lista.importacion", "action_aplicar_automaticos", [imp2])
    filas = lineas(imp2)
    assert filas["X1"]["estado"] == "aplicada" and filas["X2"]["estado"] == "pendiente", filas
    historial = [p for p in precios(cinta_id) if p["partner_id"][1] == PROVEEDOR]
    precios_y_cierre = sorted((p["price"], bool(p["date_end"])) for p in historial)
    assert precios_y_cierre == [(4000, True), (4200, False)], historial
    print("3. Suba de 5 %: aplicada sola, con historial (4000 cerrado → 4200 vigente); suba de 50 % espera ✓")
    mas_barato = c.read("comercio.lista.importacion.linea", [filas["X1"]["id"]],
                        ["mas_barato_id", "mas_barato_precio"])[0]
    assert mas_barato["mas_barato_id"] and mas_barato["mas_barato_id"][1] != PROVEEDOR, mas_barato
    assert mas_barato["mas_barato_precio"] < 4200, mas_barato
    print(f"   Aviso: para la cinta, «{mas_barato['mas_barato_id'][1]}» "
          f"(${mas_barato['mas_barato_precio']:.0f}) quedó más barato ✓")

    c.call("comercio.lista.importacion.linea", "action_aplicar", [filas["X2"]["id"], bajas[0]["id"]])
    assert all(p["date_end"] for p in precios(x3_id) if p["partner_id"][1] == PROVEEDOR), precios(x3_id)
    estado = c.read("comercio.lista.importacion", [imp2], ["estado"])[0]["estado"]
    assert estado == "aplicada", estado
    print("4. Suba grande aplicada a mano; X3 ya no está en la lista: precio cerrado; importación completa ✓")
    x2_tmpl = c.search_read("product.supplierinfo", [("product_code", "=", "X2"), ("partner_id", "=", socio)],
                            ["product_tmpl_id"])[0]["product_tmpl_id"][0]
    assert costo(x2_tmpl) == 1500, costo(x2_tmpl)
    minimo = mas_barato_vigente(cinta_id)
    # El costo del producto va con 2 decimales; un precio de proveedor puede tener 4
    assert costo(cinta_id) == round(minimo, 2) < 4200, (costo(cinta_id), minimo)
    print(f"   Costo del producto: X2 pasa a 1500 (único proveedor); la cinta queda en "
          f"{costo(cinta_id):.0f} (el más barato vigente, no los 4200 de este proveedor) ✓")
    # Costo escrito a mano: queda «Costo manual» y deshacer la lista no lo pisa
    c.write("product.template", [x2_tmpl], {"standard_price": 1700})
    assert c.read("product.template", [x2_tmpl], ["comercio_costo_manual"])[0]["comercio_costo_manual"]
    print("   Costo escrito a mano (1700): el producto queda con «Costo manual» ✓")

    # 3. Dos listas simuladas: la vieja queda reemplazada y no se puede aplicar
    vieja = importar(lista, [["X1", "CINTA METRICA 5 MTS", "", 4300], ["X2", AZUL, "", 1500]])
    nueva = importar(lista, [["X1", "CINTA METRICA 5 MTS", "", 4400], ["X2", AZUL, "", 1500]])
    assert c.read("comercio.lista.importacion", [vieja], ["estado"])[0]["estado"] == "reemplazada"
    try:
        c.call("comercio.lista.importacion", "action_aplicar_automaticos", [vieja])
        raise AssertionError("se aplicó una importación vieja")
    except Exception as error:  # noqa: BLE001 - Odoo responde con un error de usuario
        assert "más nueva" in str(error) or "Reemplazada" in str(error), error
    print("5. Una lista vieja queda «reemplazada» y no se puede aplicar después de una más nueva ✓")

    # 4. Cambio a mano entre simular y aplicar: esa fila no se aplica y avisa
    x1 = [p for p in precios(cinta_id) if p["partner_id"][1] == PROVEEDOR and not p["date_end"]][0]
    c.write("product.supplierinfo", [x1["id"]], {"price": 1000})
    c.call("comercio.lista.importacion", "action_aplicar_automaticos", [nueva])
    fila_x1 = c.search_read("comercio.lista.importacion.linea",
                            [("importacion_id", "=", nueva), ("codigo_proveedor", "=", "X1")],
                            ["estado", "avisos"])[0]
    assert fila_x1["estado"] == "pendiente" and "Cambió desde la simulación" in fila_x1["avisos"], fila_x1
    assert c.read("product.supplierinfo", [x1["id"]], ["price"])[0]["price"] == 1000
    print("6. Si el precio cambió a mano después de simular, no se pisa: la fila avisa ✓")
    c.call("comercio.lista.importacion", "action_descartar", [nueva])
    assert c.read("comercio.lista.importacion", [nueva], ["estado", "es_vigente"])[0] == {
        "id": nueva, "estado": "descartada", "es_vigente": False}
    try:
        c.call("comercio.lista.importacion", "action_simular", [vieja])
        raise AssertionError("se volvió a simular una lista vieja")
    except Exception as error:  # noqa: BLE001
        assert "más nueva" in str(error), error
    print("7. «Descartar» la más nueva: queda descartada y la anterior vuelve a ser la vigente;")
    print("   una lista vieja no se vuelve a simular ✓")
    # Deshacer
    linea_x2 = c.search_read("comercio.lista.importacion.linea",
                             [("importacion_id", "=", imp2), ("codigo_proveedor", "=", "X2")],
                             ["id"])[0]["id"]
    x2_id = c.search_read("product.supplierinfo", [("product_code", "=", "X2"),
                                                   ("partner_id", "=", socio)], ["product_tmpl_id"])[0]
    x2_id = x2_id["product_tmpl_id"][0]
    c.call("comercio.lista.importacion.linea", "action_deshacer", [linea_x2])
    vigentes = [p["price"] for p in precios(x2_id) if p["partner_id"][1] == PROVEEDOR and not p["date_end"]]
    assert vigentes == [1000], precios(x2_id)
    assert costo(x2_id) == 1700, costo(x2_id)
    print("8. «Deshacer» la suba grande: vuelve el precio anterior (1000);")
    print("   el costo manual (1700) no se toca ✓")
    c.write("product.template", [x2_id], {"comercio_costo_manual": False})
    assert costo(x2_id) == 1000, costo(x2_id)
    print("   Al desmarcar «Costo manual», el costo vuelve a seguir la lista (1000) ✓")
    linea_x3 = c.search_read("comercio.lista.importacion.linea",
                             [("importacion_id", "=", imp1), ("codigo_proveedor", "=", "X3")],
                             ["id"])[0]["id"]
    try:
        c.call("comercio.lista.importacion.linea", "action_deshacer", [linea_x3])
        raise AssertionError("deshizo una lista más vieja que otra ya aplicada")
    except Exception as error:  # noqa: BLE001
        assert "más nueva" in str(error), error
    print("   Deshacer o ignorar en una lista que no es la vigente: no se permite ✓")
    try:
        c.write("comercio.lista.importacion.linea", [linea_x3], {"decision": "ignorar"})
        raise AssertionError("se cambió una fila de una lista vieja")
    except Exception as error:  # noqa: BLE001
        assert "más nueva" in str(error), error
    c.call("comercio.lista.importacion", "action_deshacer_todo", [imp2])
    c.call("comercio.lista.importacion", "action_descartar", [imp2])
    c.call("comercio.lista.importacion.linea", "action_deshacer", [linea_x3])
    existe = c.search_read("product.template", [("id", "=", x3_id)], ["id"], context={"active_test": False})
    activo = c.search_read("product.template", [("id", "=", x3_id)], ["id"])
    assert not activo, existe
    print("   «Deshacer todo» y descartar la segunda lista; después, deshacer el producto nuevo X3")
    print("   de la primera (vigente otra vez): se quita ✓")

    # Proveedor que renumera su lista: la cinta pasa de X1 a V-03
    renum = c.create("res.partner", {"name": f"[EJ] Proveedor prueba renumera {MARCA}", "is_company": True})
    socios_prueba.append(renum)
    lista_r = c.create("comercio.lista.proveedor", {"partner_id": renum})
    otras = [[f"R{k}", f"{palabra()} {palabra()}", "", 100 * k] for k in range(1, 4)]
    r1 = importar(lista_r, [["X1", "CINTA METRICA 5 MTS", "", 4000]] + otras)
    filas_r = lineas(r1)
    c.write("comercio.lista.importacion.linea", [filas_r["X1"]["id"]], {"producto_elegido_id": cinta_id})
    c.call("comercio.lista.importacion.linea", "action_es_el_mismo", [filas_r["X1"]["id"]])
    c.call("comercio.lista.importacion.linea", "action_aplicar",
           [filas_r[f"R{k}"]["id"] for k in range(1, 4)])
    productos_prueba.extend(lineas(r1)[f"R{k}"]["producto_id"][0] for k in range(1, 4))
    r2 = importar(lista_r, [["V-03", "CINTA METRICA 5 MTS", "", 4100]] + otras)
    filas_r = lineas(r2)
    assert filas_r["V-03"]["accion"] == "posible duplicado" and filas_r["X1"]["accion"] == "baja", filas_r
    c.write("comercio.lista.importacion.linea", [filas_r["V-03"]["id"]], {"producto_elegido_id": cinta_id})
    c.call("comercio.lista.importacion.linea", "action_es_el_mismo", [filas_r["V-03"]["id"]])
    vigente = [p for p in precios(cinta_id) if p["partner_id"][0] == renum and not p["date_end"]]
    assert [(p["product_code"], p["price"]) for p in vigente] == [("V-03", 4100)], vigente
    assert lineas(r2)["X1"]["estado"] == "sin_cambios", lineas(r2)["X1"]
    print("9. Proveedor que cambia el código (X1 → V-03): «Es el mismo» actualiza el código, sin baja ✓")

    # Dos listas el mismo día: la segunda ya no trae Y2 (baja de un precio que empezó hoy)
    dia = c.create("res.partner", {"name": f"[EJ] Proveedor prueba mismo día {MARCA}", "is_company": True})
    socios_prueba.append(dia)
    lista_d = c.create("comercio.lista.proveedor", {"partner_id": dia})
    y1, y2 = f"{palabra()} {palabra()}", f"{palabra()} {palabra()}"
    d1 = importar(lista_d, [["Y1", y1, "", 500], ["Y2", y2, "", 700]])
    c.call("comercio.lista.importacion.linea", "action_aplicar", [f["id"] for f in lineas(d1).values()])
    y2_id = lineas(d1)["Y2"]["producto_id"][0]
    productos_prueba.extend([lineas(d1)["Y1"]["producto_id"][0], y2_id])
    d2 = importar(lista_d, [["Y1", y1, "", 500]])
    baja = lineas(d2)["Y2"]
    assert baja["accion"] == "baja", baja
    c.call("comercio.lista.importacion.linea", "action_ignorar", [baja["id"]])
    assert c.read("comercio.lista.importacion", [d2], ["estado"])[0]["estado"] == "aplicada"
    c.call("comercio.lista.importacion.linea", "action_deshacer", [baja["id"]])
    assert lineas(d2)["Y2"]["estado"] == "pendiente"
    assert c.read("comercio.lista.importacion", [d2], ["estado"])[0]["estado"] == "simulada"
    print("10. «Ignorar» la única fila cierra la importación; «Retomar» la deja otra vez para decidir ✓")
    precio_y2 = [p for p in precios(y2_id) if p["partner_id"][0] == dia]
    inicio = precio_y2[0]["date_start"]
    c.call("comercio.lista.importacion.linea", "action_aplicar", [baja["id"]])
    cerrado = c.read("product.supplierinfo", [precio_y2[0]["id"]], ["date_start", "date_end"])[0]
    assert lineas(d2)["Y2"]["estado"] == "aplicada", lineas(d2)["Y2"]
    assert cerrado["date_end"] and cerrado["date_end"] < inicio, cerrado
    c.call("comercio.lista.importacion.linea", "action_deshacer", [baja["id"]])
    reabierto = c.read("product.supplierinfo", [precio_y2[0]["id"]], ["date_start", "date_end"])[0]
    assert not reabierto["date_end"] and reabierto["date_start"] == inicio, reabierto
    print("    Baja de un precio que empezó hoy: se cierra hasta ayer; «Deshacer» devuelve las fechas ✓")

    # Producto creado a mano sin códigos: recibe referencia y código propio 20… solos
    from codigos import es_gtin_valido  # noqa: PLC0415
    a_mano = c.create("product.template", {"name": f"[EJ] Producto a mano {MARCA}"})
    productos_prueba.append(a_mano)
    r = c.read("product.template", [a_mano], ["default_code", "barcode"])[0]
    assert r["default_code"].isdigit() and r["barcode"].startswith("20") and es_gtin_valido(r["barcode"]), r
    assert int(r["barcode"][2:12]) == int(r["default_code"]), r
    print(f"   Producto creado a mano: referencia {r['default_code']} y código {r['barcode']} solos ✓")

    # 5. Proveedor nuevo desde «Importar lista», sin crear la lista antes: se crea sola
    otro = c.create("res.partner", {"name": f"[EJ] Proveedor sin lista {MARCA}", "is_company": True})
    socios_prueba.append(otro)
    wizard = c.create("comercio.importar.lista.wizard", {
        "partner_id": otro, "archivo": excel([["N1", f"{palabra()} {palabra()}", "", 100]]),
        "nombre_archivo": "lista.xlsx", "categoria_id": rubro()})
    c.call("comercio.importar.lista.wizard", "action_importar", [wizard])
    listas = c.search_read("comercio.lista.proveedor", [("partner_id", "=", otro)],
                           ["col_codigo", "col_costo"])
    assert len(listas) == 1 and listas[0]["col_costo"] == "Precio s/IVA", listas
    productos_prueba.extend(p["product_tmpl_id"][0] for p in c.search_read(
        "product.supplierinfo", [("partner_id", "=", otro)], ["product_tmpl_id"]))
    print("11. Proveedor nuevo desde «Importar lista»: su lista se crea sola con las columnas ✓")

    # El proveedor cambia el formato: otros títulos y dos filas más arriba
    fmt = c.create("res.partner", {"name": f"[EJ] Proveedor prueba formato {MARCA}", "is_company": True})
    socios_prueba.append(fmt)
    lista_f = c.create("comercio.lista.proveedor", {"partner_id": fmt, "tope_automatico": 10})
    z1 = f"{palabra()} {palabra()}"
    f1 = importar(lista_f, [["Z1", z1, "", 1000]])
    c.call("comercio.lista.importacion.linea", "action_aplicar", [lineas(f1)["Z1"]["id"]])
    productos_prueba.append(lineas(f1)["Z1"]["producto_id"][0])
    c.write("product.supplierinfo", [p["id"] for p in c.search_read(
        "product.supplierinfo", [("partner_id", "=", fmt)], ["id"])], {"date_start": "2026-01-01"})
    nuevo_formato = excel_con_formato([["DISTRIBUIDORA"], ["Lista octubre"], []],
                                      ["Código", "Detalle", "Precio neto"], [["Z1", z1, 1050]])
    f2 = importar(lista_f, [], nuevo_formato)
    imp = c.read("comercio.lista.importacion", [f2], ["estado", "aviso_formato"])[0]
    assert imp["estado"] == "simulada" and "Precio neto" in imp["aviso_formato"], imp
    fila_z1 = lineas(f2)["Z1"]
    assert round(fila_z1["variacion"]) == 5 and not fila_z1["automatico"], fila_z1
    cfg = c.read("comercio.lista.proveedor", [lista_f], ["col_costo", "fila_encabezado"])[0]
    assert (cfg["col_costo"], cfg["fila_encabezado"]) == ("Precio neto", 4), cfg
    print("12. Formato nuevo del proveedor: columnas detectadas solas, aviso y nada automático ✓")
    sin_costo = excel_con_formato([], ["Código", "Detalle", "Observaciones"], [["Z1", z1, "x"]])
    f3 = importar(lista_f, [], sin_costo)
    assert c.read("comercio.lista.importacion", [f3], ["estado"])[0]["estado"] == "error"
    print("    Sin columna de costo reconocible: queda en error para que lo resuelva una persona ✓")

    # Dos precios del proveedor: por unidad y por bulto (desde 12)
    may = c.create("res.partner", {"name": f"[EJ] Proveedor prueba mayor {MARCA}", "is_company": True})
    socios_prueba.append(may)
    lista_m = c.create("comercio.lista.proveedor", {"partner_id": may, "tope_automatico": 10})
    m1 = f"{palabra()} {palabra()}"
    titulos = ["Código", "Descripción", "Precio unitario", "Precio x bulto", "Unidades x bulto"]
    i1 = importar(lista_m, [], excel_con_formato([], titulos, [["M1", m1, 1000, 900, 12]]))
    cfg = c.read("comercio.lista.proveedor", [lista_m],
                 ["col_costo", "col_costo_mayor", "col_cantidad_mayor"])[0]
    assert (cfg["col_costo"], cfg["col_costo_mayor"], cfg["col_cantidad_mayor"]) == (
        "Precio unitario", "Precio x bulto", "Unidades x bulto"), cfg
    c.call("comercio.lista.importacion.linea", "action_aplicar", [lineas(i1)["M1"]["id"]])
    m1_id = lineas(i1)["M1"]["producto_id"][0]
    productos_prueba.append(m1_id)
    campos = ["price", "min_qty", "comercio_precio_mayor", "comercio_escala_de_id", "date_start", "date_end"]
    def filas_m():
        return sorted(c.search_read("product.supplierinfo", [("partner_id", "=", may)], campos),
                      key=lambda r: r["min_qty"])
    principal, escala = filas_m()
    assert principal["price"] == 1000 and principal["comercio_precio_mayor"] == 900, principal
    assert escala["min_qty"] == 12 and escala["price"] == 900, escala
    assert escala["comercio_escala_de_id"][0] == principal["id"], escala
    assert costo(m1_id) == 1000, costo(m1_id)
    variante = c.search_read("product.product", [("product_tmpl_id", "=", m1_id)], ["id"])[0]["id"]
    def precio_compra(cantidad):
        # Como en la pantalla: se agrega el producto y después se escribe la cantidad
        o = c.create("purchase.order", {"partner_id": may, "order_line": [(0, 0, {"product_id": variante})]})
        linea = c.search_read("purchase.order.line", [("order_id", "=", o)], ["id"])[0]["id"]
        c.write("purchase.order.line", [linea], {"product_qty": cantidad})
        precio = c.read("purchase.order.line", [linea], ["price_unit"])[0]["price_unit"]
        c.call("purchase.order", "button_cancel", [o])
        c.call("purchase.order", "unlink", [o])
        return precio
    assert (precio_compra(1), precio_compra(12)) == (1000, 900)
    print("13. Dos precios del proveedor (unidad 1000, bulto de 12 a 900): columnas reconocidas solas;")
    print("    Compras usa 1000 para 1 y 900 para 12; el costo del producto es el de la unidad (1000) ✓")

    c.write("product.supplierinfo", [principal["id"]], {"date_start": "2026-01-01"})
    assert filas_m()[1]["date_start"] == "2026-01-01", filas_m()
    i2 = importar(lista_m, [], excel_con_formato([], titulos, [["M1", m1, 1000, 950, 12]]))
    fila_m1 = lineas(i2)["M1"]
    assert fila_m1["automatico"], fila_m1
    c.call("comercio.lista.importacion", "action_aplicar_automaticos", [i2])
    assert [r["price"] for r in filas_m()] == [1000, 950], filas_m()
    linea_m1 = c.search_read("comercio.lista.importacion.linea", [("importacion_id", "=", i2),
                                                                   ("codigo_proveedor", "=", "M1")], ["id"])
    c.call("comercio.lista.importacion.linea", "action_deshacer", [linea_m1[0]["id"]])
    assert [r["price"] for r in filas_m()] == [1000, 900], filas_m()
    print("    Precio por mayor +5,6 %: se aplica solo y Compras lo usa; «Deshacer» lo devuelve ✓")

    probar_catalogo(socios_prueba, productos_prueba)
    probar_unidad_de_compra(socios_prueba, productos_prueba)
    probar_hojas(socios_prueba)
    probar_costo(socios_prueba, productos_prueba)
    probar_descartar(socios_prueba, productos_prueba)
    probar_aplicar_todo(socios_prueba, productos_prueba)
    probar_codigo_de_fabrica(socios_prueba, productos_prueba)
    print("Todo OK.")
    return 0


def probar_catalogo(socios_prueba: list[int], productos_prueba: list[int]) -> None:
    """P-048: la lista es el catálogo del proveedor; se agrega solo lo que se quiere vender."""
    linea = "comercio.lista.importacion.linea"

    def filas_de(imp: int, campos: list[str], **filtro) -> dict[str, dict]:
        dominio = [("importacion_id", "=", imp)] + [(k, "=", v) for k, v in filtro.items()]
        encontradas = c.search_read(linea, dominio, ["codigo_proveedor", *campos])
        return {f["codigo_proveedor"]: f for f in encontradas}

    ferreteria = c.search_read("product.category", [("name", "=", "[EJ] Ferretería")], ["id"])[0]["id"]
    vivero = c.search_read("product.category", [("name", "=", "[EJ] Vivero")], ["id"])[0]["id"]
    socio = c.create("res.partner", {"name": f"[EJ] Catálogo {MARCA}", "is_company": True,
                                     "supplier_rank": 1})
    socios_prueba.append(socio)
    # La propia empresa no es proveedor: no se le importa una lista
    empresa = c.search_read("res.company", [], ["partner_id"])[0]["partner_id"][0]
    propio = c.create("comercio.importar.lista.wizard", {
        "partner_id": empresa, "nombre_archivo": "lista.xlsx", "archivo": excel([["X1", "algo", "", 1]])})
    try:
        c.call("comercio.importar.lista.wizard", "action_importar", [propio])
        raise AssertionError("se importó una lista a nombre de la propia empresa")
    except AssertionError:
        raise
    except Exception as error:  # noqa: BLE001
        assert "nuestra empresa" in str(error), error
    assert not c.search_read("comercio.lista.proveedor", [("partner_id", "=", empresa)], ["id"])
    k1, k2, k3, k4 =(f"{palabra()} {palabra()} {n}" for n in ("10MM", "20MM", "30MM", "40MM"))
    wizard = c.create("comercio.importar.lista.wizard", {
        "partner_id": socio, "categoria_id": ferreteria, "nombre_archivo": "lista.xlsx",
        "archivo": excel([["K1", k1, "", 100], ["K2", k2, "", 200], ["K3", k3, "", 300],
                          ["K4", k4, "", 400]])})
    imp = c.call("comercio.importar.lista.wizard", "action_importar", [wizard])["res_id"]
    lista = c.search_read("comercio.lista.proveedor", [("partner_id", "=", socio)], ["categoria_id"])[0]
    assert lista["categoria_id"][0] == ferreteria, lista
    filas = filas_de(imp, ["accion", "categoria_id", "registrado"])
    assert all(f["accion"] == "nuevo" and f["categoria_id"][0] == ferreteria and not f["registrado"]
               for f in filas.values()), filas
    datos = c.read("comercio.lista.importacion", [imp], ["cant_revisar", "cant_catalogo"])[0]
    assert (datos["cant_revisar"], datos["cant_catalogo"]) == (0, 4), datos
    print("14. Catálogo: el rubro elegido al importar queda en la lista y en cada fila; los 4 productos")
    print("    que no tenemos no cuentan «para revisar» y no se crea ninguno solo ✓")

    # Categoría creada desde el desplegable; otra igual escrita distinto no se crea
    nueva = c.call("product.category", "name_create", name=f"[EJ] Bulonería {MARCA}")[0]
    try:
        c.call("product.category", "name_create", name=f"[EJ]  BULONERIA {MARCA}")
        raise AssertionError("se creó una categoría repetida")
    except AssertionError:
        raise
    except Exception as error:  # noqa: BLE001
        assert "Ya existe la categoría" in str(error), error
    # Desde la pestaña «Filas» de la importación: el formulario guarda la importación con la fila
    # cambiada adentro (antes daba «Una importación no se modifica a mano» y dejaba la pantalla trabada)
    IMP = "comercio.lista.importacion"
    c.write(IMP, [imp], {"linea_ids": [[1, filas["K1"]["id"], {"categoria_id": nueva}]]})
    assert filas_de(imp, ["categoria_id"])["K1"]["categoria_id"][0] == nueva
    for prohibido in ({"linea_ids": [[1, filas["K1"]["id"], {"costo": 1}]]}, {"estado": "aplicada"},
                      {"linea_ids": [[2, filas["K1"]["id"]]]}):
        try:
            c.write(IMP, [imp], prohibido)
            raise AssertionError(f"se pudo escribir {prohibido}")
        except AssertionError:
            raise
        except Exception as error:  # noqa: BLE001
            assert "solo se puede cambiar" in str(error) or "a mano" in str(error), error
    print("    La categoría se cambia también desde la pestaña «Filas» de la importación; costo,")
    print("    estado o borrar filas siguen bloqueados ✓")
    # Una fila sola y dos a la vez (marcar casillas y cambiar una: escribe en todas)
    c.write(linea, [filas["K1"]["id"]], {"categoria_id": vivero})
    c.write(linea, [filas["K2"]["id"], filas["K3"]["id"]], {"categoria_id": nueva})
    # La categoría recién creada no tiene margen: el producto quedaría a $1 en la caja → no se agrega
    try:
        c.call(linea, "action_aplicar", [filas[k]["id"] for k in ("K1", "K2", "K3")])
        raise AssertionError("se agregó un producto a una categoría sin margen")
    except AssertionError:
        raise
    except Exception as error:  # noqa: BLE001
        assert "no tiene margen" in str(error) and "Bulonería" in str(error), error
    assert all(f["estado"] == "pendiente" for f in filas_de(imp, ["estado"]).values())
    c.write("product.category", [nueva], {"comercio_margen": 50})
    print("    Categoría nueva sin margen: «Agregar» avisa que quedaría a $1 y no crea nada;")
    print("    con margen, sí ✓")
    # Antes de agregar se ve a cuánto se vendería (margen de la categoría elegida en la fila)
    estimado = {k: f["precio_venta"] for k, f in filas_de(imp, ["precio_venta"]).items()}
    assert all(estimado[k] > 0 for k in ("K1", "K2", "K3", "K4")), estimado
    c.call(linea, "action_aplicar", [filas[k]["id"] for k in ("K1", "K2", "K3")])
    creados = filas_de(imp, ["producto_id", "registrado", "estado"])
    categorias = {k: c.read("product.template", [creados[k]["producto_id"][0]],
                            ["categ_id"])[0]["categ_id"][0] for k in ("K1", "K2", "K3")}
    productos_prueba.extend(creados[k]["producto_id"][0] for k in ("K1", "K2", "K3"))
    assert categorias == {"K1": vivero, "K2": nueva, "K3": nueva}, categorias
    assert not creados["K4"]["producto_id"] and creados["K4"]["estado"] == "pendiente", creados["K4"]
    print("    Categoría creada desde la fila; «[EJ]  BULONERIA» repetida no se crea; «Agregar a nuestro")
    print("    catálogo» crea K1 en Vivero y K2-K3 (cambiadas juntas) en la nueva; K4 sigue sin crearse ✓")
    venta = {k: c.read("product.template", [creados[k]["producto_id"][0]], ["list_price"])[0]["list_price"]
             for k in ("K1", "K2", "K3")}
    assert venta == {k: estimado[k] for k in venta}, (venta, estimado)
    print(f"    «Precio de venta» antes de agregar = el que tomó el producto (K1 $ {venta['K1']:.2f}) ✓")

    # «Agregar al pedido»: a la solicitud en borrador de ese proveedor, con su mínimo y precio de lista
    c.call(linea, "action_agregar_a_pedido", [filas["K1"]["id"], filas["K2"]["id"]])
    c.call(linea, "action_agregar_a_pedido", [filas["K1"]["id"]])
    ordenes = c.search_read("purchase.order", [("partner_id", "=", socio), ("state", "=", "draft")], ["id"])
    assert len(ordenes) == 1, ordenes
    renglones = c.search_read("purchase.order.line", [("order_id", "=", ordenes[0]["id"])],
                              ["product_id", "product_qty", "price_unit"])
    pedidas = {o["product_id"][1]: (o["product_qty"], o["price_unit"]) for o in renglones}
    assert sorted(pedidas.values()) == [(1.0, 200.0), (2.0, 100.0)], pedidas
    try:
        c.call(linea, "action_agregar_a_pedido", [filas["K4"]["id"]])
        raise AssertionError("se pidió un producto que no está en nuestro catálogo")
    except AssertionError:
        raise
    except Exception as error:  # noqa: BLE001
        assert "no está en nuestro catálogo" in str(error), error
    c.call("purchase.order", "button_cancel", [ordenes[0]["id"]])
    c.call("purchase.order", "unlink", [ordenes[0]["id"]])
    print("    «Agregar al pedido»: K1 y K2 a una sola solicitud en borrador del proveedor, a precio de")
    print("    lista; K1 otra vez suma cantidad; K4 (no lo tenemos) pide agregarlo primero ✓")

    # Lista siguiente: lo nuestro primero; la importación queda revisada aunque K4 siga en el catálogo
    imp2 = importar(lista["id"], [["K1", k1, "", 100], ["K2", k2, "", 210], ["K3", k3, "", 300],
                                  ["K4", k4, "", 400], ["K5", f"{palabra()} {palabra()}", "", 500]])
    orden = [f["codigo_proveedor"] for f in c.search_read(linea, [("importacion_id", "=", imp2)],
                                                          ["codigo_proveedor"])]
    assert orden[:3] and set(orden[:3]) == {"K1", "K2", "K3"} and set(orden[3:]) == {"K4", "K5"}, orden
    k4_2 = filas_de(imp2, ["categoria_id"])["K4"]
    assert k4_2["categoria_id"][0] == ferreteria, k4_2
    c.call("comercio.lista.importacion", "action_aplicar_automaticos", [imp2])
    datos = c.read("comercio.lista.importacion", [imp2], ["estado", "cant_revisar", "cant_catalogo"])[0]
    assert datos == {"id": imp2, "estado": "aplicada", "cant_revisar": 0, "cant_catalogo": 2}, datos
    print("    Lista siguiente: K1-K3 (nuestros) arriba; con la suba de K2 aplicada queda «Aplicada»")
    print("    aunque K4 y K5 sigan en el catálogo del proveedor ✓")

    # Desde «Aplicada» se puede seguir agregando del catálogo
    c.call(linea, "action_aplicar", [filas_de(imp2, [])["K5"]["id"]])
    k5 = filas_de(imp2, ["producto_id"])["K5"]
    assert k5["producto_id"], k5
    productos_prueba.append(k5["producto_id"][0])

    # «Productos» del proveedor: filas de su última lista, filtradas en lo nuestro
    accion = c.call("comercio.lista.proveedor", "action_ver_productos", [lista["id"]])
    assert accion["res_model"] == "comercio.lista.importacion.linea", accion
    assert accion["context"].get("search_default_registrado") == 1, accion["context"]
    nuestros = c.search_read(linea, accion["domain"] + [("registrado", "=", True)], ["codigo_proveedor"])
    assert sorted(f["codigo_proveedor"] for f in nuestros) == ["K1", "K2", "K3", "K5"], nuestros
    print("    «Productos» del proveedor abre su última lista filtrada en lo nuestro (K1, K2, K3, K5);")
    print("    sin el filtro se ve el catálogo entero y desde ahí se agrega K5 ✓")
    # «Buscar producto»: palabras en otro orden, solo la última lista de cada proveedor
    p1, p2, medida = k4.split()
    consulta = f"{medida} {p2.lower()} {p1}"
    hallados = c.search_read(linea, [("de_lista_vigente", "=", True), ("buscar", "ilike", consulta)],
                             ["codigo_proveedor", "importacion_id", "registrado"])
    assert [(h["codigo_proveedor"], h["importacion_id"][0]) for h in hallados] == [("K4", imp2)], hallados
    tenemos = c.search_read(linea, [("de_lista_vigente", "=", True), ("buscar", "ilike", k1.split()[1]),
                                    ("registrado", "=", True)], ["codigo_proveedor"])
    assert [t["codigo_proveedor"] for t in tenemos] == ["K1"], tenemos
    c.call(linea, "action_aplicar", [hallados[0]["id"]])
    assert filas_de(imp2, ["registrado"])["K4"]["registrado"], "no se agregó K4 desde la búsqueda"
    print("    «Buscar producto»: encuentra K4 con las palabras en otro orden (solo en la última lista)")
    print("    y lo agrega a nuestro catálogo desde ahí; K1 aparece como «lo tenemos» ✓")
    productos_prueba.append(filas_de(imp2, ["producto_id"])["K4"]["producto_id"][0])

    # La categoría de prueba no queda en el lab: sus productos vuelven a Ferretería
    en_nueva = [p["id"] for p in c.search_read("product.template", [("categ_id", "=", nueva)], ["id"])]
    c.write("product.template", en_nueva, {"categ_id": ferreteria})
    c.call("product.category", "unlink", [nueva])

    # Lista en PDF (con texto): se lee sin IA, como un Excel; el PDF queda como original
    pdf = c.create("res.partner", {"name": f"[EJ] Proveedor PDF {MARCA}", "is_company": True})
    socios_prueba.append(pdf)
    ruta = __import__("pathlib").Path(__file__).parents[1] / "datos" / "lista_ficticia.pdf"
    wizard = c.create("comercio.importar.lista.wizard", {
        "partner_id": pdf, "categoria_id": ferreteria, "nombre_archivo": "lista.pdf",
        "archivo": base64.b64encode(ruta.read_bytes()).decode()})
    imp_pdf = c.call("comercio.importar.lista.wizard", "action_importar", [wizard])["res_id"]
    datos = c.read("comercio.lista.importacion", [imp_pdf],
                   ["estado", "cant_total", "leida_con_ia", "nombre_archivo", "nombre_original"])[0]
    assert datos["estado"] == "simulada" and datos["cant_total"] == 60 and not datos["leida_con_ia"], datos
    assert (datos["nombre_original"], datos["nombre_archivo"]) == ("lista.pdf", "lista.pdf.csv"), datos
    p001 = filas_de(imp_pdf, ["descripcion", "costo"])["P-001"]
    assert (p001["descripcion"], p001["costo"]) == ("ALIMENTO PERRO ADULTO X 15 KG", 30250.5), p001
    print("    Lista en PDF con texto: 60 productos leídos sin IA («$ 30.250,50» → 30250,5) y el PDF")
    print("    queda como archivo original ✓")



def probar_unidad_de_compra(socios_prueba: list[int], productos_prueba: list[int]) -> None:
    """P-053: tornillos que se venden por kg y el proveedor vende en cajas de 1000."""
    linea = "comercio.lista.importacion.linea"
    kg = c.search_read("ir.model.data", [("module", "=", "uom"), ("name", "=", "product_uom_kgm")],
                       ["res_id"])[0]["res_id"]
    ferreteria = c.search_read("product.category", [("name", "=", "[EJ] Ferretería")], ["id"])[0]["id"]
    socio = c.create("res.partner", {"name": f"[EJ] Proveedor cajas {MARCA}", "is_company": True})
    socios_prueba.append(socio)
    lista = c.create("comercio.lista.proveedor", {"partner_id": socio, "tope_automatico": 10,
                                                 "categoria_id": ferreteria})
    cajas = [c.create("uom.uom", {"name": f"[EJ] Caja 1000 tornillos 6x1 {MARCA}", "relative_uom_id": kg,
                                  "relative_factor": 2.5})]
    try:
        t1, t3 = (c.create("product.template", {"name": f"[EJ] Tornillo {n} suelto {MARCA}", "uom_id": kg,
                                                "categ_id": ferreteria, "is_storable": True})
                  for n in ("6x1", "8x1"))
        productos_prueba.extend([t1, t3])
        c.create("product.supplierinfo", {"partner_id": socio, "product_tmpl_id": t1, "product_code": "T1",
                                          "price": 25000, "uom_id": cajas[0]})
        c.create("product.supplierinfo", {"partner_id": socio, "product_tmpl_id": t3, "product_code": "T3",
                                          "price": 10})  # en kg: sin unidad de compra
        imp = importar(lista, [], archivo=excel_con_formato(
            [["LISTA"]], ["Cód.", "Descripción", "Unidad", "Precio"],
            [["T1", "TORNILLO 6X1", "1000 u", 26000], ["T3", "TORNILLO 8X1", "1000 u", 30000]]))
        filas = {f["codigo_proveedor"]: f for f in c.search_read(
            linea, [("importacion_id", "=", imp)],
            ["codigo_proveedor", "accion", "costo", "producto_id", "detalle", "unidades_posibles_ids"])}
        assert filas["T1"]["accion"] == "actualizar" and filas["T1"]["costo"] == 26000, filas["T1"]
        assert filas["T3"]["accion"] == "revisar" and filas["T3"]["producto_id"][0] == t3, filas["T3"]
        assert "se vende por kg" in filas["T3"]["detalle"], filas["T3"]
        c.call("comercio.lista.importacion", "action_aplicar_automaticos", [imp])
        vigente = c.search_read("product.supplierinfo",
                                [("product_tmpl_id", "=", t1), ("date_end", "=", False)], ["price", "uom_id"])
        assert [(v["price"], v["uom_id"][0]) for v in vigente] == [(26000, cajas[0])], vigente
        assert costo(t1) == 10400, costo(t1)  # 26 000 la caja de 2,5 kg
        print("15. Unidad de compra: el tornillo se vende por kg y el proveedor lo vende en «Caja 1000»")
        print("    (2,5 kg): el precio nuevo de la caja (26 000) se guarda tal cual, sigue en cajas y el")
        print("    costo queda en 10 400 por kg ✓")

        # Fila a revisar (lista por caja de unidades, producto en kg): se elige la unidad en la fila,
        # creándola desde el desplegable como lo hace la pantalla
        cajas.append(c.create("uom.uom", {"name": f"[EJ] Caja 1000 tornillos 8x1 {MARCA}",
                                          "relative_factor": 3, "relative_uom_id": kg}))
        posibles = c.read(linea, [filas["T3"]["id"]], ["unidades_posibles_ids"])[0]["unidades_posibles_ids"]
        assert kg in posibles and cajas[1] in posibles and 1 not in posibles, posibles
        c.write(linea, [filas["T3"]["id"]], {"unidad_compra_id": cajas[1]})
        c.call(linea, "action_aplicar", [filas["T3"]["id"]])
        vigente = c.search_read("product.supplierinfo",
                                [("product_tmpl_id", "=", t3), ("date_end", "=", False)], ["price", "uom_id"])
        assert [(v["price"], v["uom_id"][0]) for v in vigente] == [(30000, cajas[1])], vigente
        assert costo(t3) == 10000, costo(t3)
        print("    Lista por caja de un producto en kg sin unidad de compra: va a revisar; se elige")
        print("    «Caja 1000 = 3 kg» en la fila y se aplica: 30 000 la caja, 10 000 por kg ✓")

        # «Pedir»: una caja, no un kg
        c.call(linea, "action_agregar_a_pedido", [filas["T1"]["id"]])
        orden = c.search_read("purchase.order", [("partner_id", "=", socio), ("state", "=", "draft")], ["id"])
        renglon = c.search_read("purchase.order.line", [("order_id", "=", orden[0]["id"])],
                                ["product_qty", "uom_id", "price_unit"])
        pedido = [(r["product_qty"], r["uom_id"][0], r["price_unit"]) for r in renglon]
        assert pedido == [(1, cajas[0], 26000)], pedido
        c.call("purchase.order", "button_cancel", [orden[0]["id"]])
        c.call("purchase.order", "unlink", [orden[0]["id"]])

        # Deshacer vuelve al precio anterior, en cajas
        c.call(linea, "action_deshacer", [filas["T1"]["id"], filas["T3"]["id"]])
        vigente = c.search_read("product.supplierinfo", [("product_tmpl_id", "in", [t1, t3]),
                                                         ("date_end", "=", False)], ["price", "uom_id"])
        assert sorted((v["price"], v["uom_id"][0]) for v in vigente) == [(10, kg), (25000, cajas[0])], vigente
        print("    «Pedir» deja 1 caja a 26 000 en la orden; «Deshacer» vuelve a 25 000 la caja y a")
        print("    10 por kg ✓")
    finally:
        precios_prueba = c.search_read("product.supplierinfo", [("partner_id", "=", socio)], ["id"])
        if precios_prueba:
            c.call("product.supplierinfo", "unlink", [p["id"] for p in precios_prueba])
        c.write("uom.uom", cajas, {"active": False})



def probar_hojas(socios_prueba: list[int]) -> None:
    """Un Excel con varias hojas (como FC: General y Bulones): se eligen las hojas y cada una
    queda como una parte de la lista del proveedor, creada sola."""
    libro = openpyxl.Workbook()
    for i, titulo in enumerate(("General", "Bulones")):
        hoja = libro.active if i == 0 else libro.create_sheet()
        hoja.title = titulo
        hoja.append(["Cód.", "Descripción", "Precio"])
        for n in range(6):
            hoja.append([f"{titulo[0]}{n}", f"{titulo.upper()} {palabra()}", 100 + n])
    libro.create_sheet("Notas").append(["Precios sin IVA", "-"])
    salida = io.BytesIO()
    libro.save(salida)
    archivo = base64.b64encode(salida.getvalue()).decode()
    socio = c.create("res.partner", {"name": f"[EJ] Proveedor hojas {MARCA}", "is_company": True})
    socios_prueba.append(socio)
    # Lo que deja la pantalla después de subir el archivo: una fila por hoja con datos
    wizard = c.create("comercio.importar.lista.wizard", {
        "partner_id": socio, "archivo": archivo, "nombre_archivo": "lista.xlsx", "categoria_id": rubro(),
        "hoja_ids": [[0, 0, {"nombre": "General", "filas": 7, "importar": True}],
                     [0, 0, {"nombre": "Bulones", "filas": 7, "importar": True}],
                     [0, 0, {"nombre": "Notas", "filas": 1, "importar": False}]]})
    accion = c.call("comercio.importar.lista.wizard", "action_importar", [wizard])
    importaciones = c.search_read("comercio.lista.importacion", accion["domain"],
                                  ["lista_id", "estado", "cant_total"])
    listas = c.search_read("comercio.lista.proveedor", [("partner_id", "=", socio)], ["parte", "hoja"])
    assert sorted((x["parte"], x["hoja"]) for x in listas) == [("Bulones", "Bulones"), ("General", "General")]
    assert len(importaciones) == 2 and all(i["estado"] == "simulada" and i["cant_total"] == 6
                                           for i in importaciones), importaciones
    print("16. Excel con hojas General, Bulones y Notas: se importan las dos marcadas; cada una queda")
    print("    como una parte de la lista del proveedor (creada sola) con sus 6 productos ✓")

    # Otro Excel del mismo proveedor con otros productos → «Es otra parte»
    otro = excel_con_formato([], ["Cód.", "Descripción", "Precio"],
                             [[f"H{n}", f"HERRAMIENTA {palabra()}", 900 + n] for n in range(5)])
    wizard = c.create("comercio.importar.lista.wizard", {
        "partner_id": socio, "archivo": otro, "nombre_archivo": "herramientas.xlsx", "categoria_id": rubro(),
        "nueva_parte": True, "nombre_parte": "Herramientas"})
    imp = c.call("comercio.importar.lista.wizard", "action_importar", [wizard])["res_id"]
    datos = c.read("comercio.lista.importacion", [imp], ["lista_id", "cant_total", "estado"])[0]
    assert datos["cant_total"] == 5 and datos["estado"] == "simulada", datos
    partes = sorted(x["parte"] for x in c.search_read("comercio.lista.proveedor",
                                                      [("partner_id", "=", socio)], ["parte"]))
    assert partes == ["Bulones", "General", "Herramientas"], partes
    wizard = c.create("comercio.importar.lista.wizard", {
        "partner_id": socio, "archivo": otro, "nombre_archivo": "herramientas.xlsx", "categoria_id": rubro(),
        "nueva_parte": True, "nombre_parte": "herramientas"})
    try:
        c.call("comercio.importar.lista.wizard", "action_importar", [wizard])
        raise AssertionError("se creó una parte repetida")
    except AssertionError:
        raise
    except Exception as error:  # noqa: BLE001
        assert "ya tiene una parte" in str(error), error
    print("    Otro Excel del mismo proveedor con «Es otra parte» → parte «Herramientas» nueva, sin")
    print("    compararlo con General ni Bulones; con el mismo nombre otra vez, avisa ✓")


def probar_costo(socios_prueba: list[int], productos_prueba: list[int]) -> None:
    """ADR 0029: del precio de la lista al costo, y «Recalcular costos» al cambiar una regla."""
    linea = "comercio.lista.importacion.linea"
    ferreteria = c.search_read("product.category", [("name", "=", "[EJ] Ferretería")], ["id"])[0]["id"]
    socio = c.create("res.partner", {"name": f"[EJ] Proveedor descuentos {MARCA}", "is_company": True})
    socios_prueba.append(socio)
    lista = c.create("comercio.lista.proveedor", {
        "partner_id": socio, "categoria_id": ferreteria, "tope_automatico": 50,
        "col_codigo": "Cód.", "col_descripcion": "Descripción", "col_costo": "Precio",
        "col_descuento": "Desc.", "descuentos": "10", "recargo": 2.5})
    familia = palabra()  # al azar: «BULON» se parecería a los bulones de la lista de ejemplo
    c.create("comercio.lista.regla", {"lista_id": lista, "tipo": "familia", "contiene": familia,
                                      "descuentos": "10"})
    c.create("comercio.lista.regla", {"lista_id": lista, "tipo": "producto", "codigo": "D3",
                                      "descuentos": "5"})
    # Palabras al azar: si no, se parecen entre sí o a otros productos (posibles duplicados)
    filas = [["D1", f"{palabra()} {palabra()}", 1000, ""], ["D2", f"{familia} {palabra()}", 1000, ""],
             ["D3", f"{palabra()} {palabra()}", 1000, 20]]
    archivo = excel_con_formato([["LISTA"]], ["Cód.", "Descripción", "Precio", "Desc."], filas)
    imp = importar(lista, [], archivo=archivo)
    datos = lineas(imp)
    esperado = {"D1": 1000 * 0.9 * 1.025, "D2": 1000 * 0.9 * 0.9 * 1.025,
                "D3": 1000 * 0.9 * 0.95 * 0.8 * 1.025}
    for codigo, valor in esperado.items():
        assert abs(datos[codigo]["costo"] - valor) < 0.01, (codigo, datos[codigo]["costo"], valor)
    calculo = c.search_read(linea, [("importacion_id", "=", imp), ("codigo_proveedor", "=", "D3")],
                            ["calculo", "precio_lista"])[0]
    assert "(producto)" in calculo["calculo"] and "(columna de la lista)" in calculo["calculo"], calculo
    ejemplo = c.read("comercio.lista.proveedor", [lista], ["ejemplo_calculo"])[0]["ejemplo_calculo"]
    assert ejemplo and f"({familia})" in ejemplo, ejemplo
    print("    Costo: lista 10 % + familia + producto + columna + recargo, con el cálculo de cada fila ✓")

    # Se agregan a nuestro catálogo y se cambia la regla de la familia: «Recalcular costos»
    ids = [f["id"] for f in c.search_read(linea, [("importacion_id", "=", imp)], ["id"])]
    c.call(linea, "action_aplicar", ids)
    bulon = lineas(imp)["D2"]["producto_id"][0]
    productos_prueba.extend(f["producto_id"][0] for f in lineas(imp).values() if f["producto_id"])
    antes = costo(bulon)
    regla = c.search_read("comercio.lista.regla", [("lista_id", "=", lista), ("tipo", "=", "familia")],
                          ["id"])
    c.write("comercio.lista.regla", [regla[0]["id"]], {"descuentos": "20"})
    accion = c.call("comercio.lista.proveedor", "action_recalcular", [lista])
    nueva = accion["res_id"]
    assert nueva != imp and lineas(nueva)["D2"]["accion"] == "actualizar", lineas(nueva)["D2"]
    c.call("comercio.lista.importacion", "action_aplicar_automaticos", [nueva])
    despues = costo(bulon)
    assert abs(despues - 1000 * 0.9 * 0.8 * 1.025) < 0.01 and despues < antes, (antes, despues)
    print(f"    «Recalcular costos» con la familia en 20 %: el bulón pasa de {antes:g} a {despues:g} ✓")

    # IVA incluido: alícuota de la columna, si no la del producto, si no la de la lista
    socio_iva = c.create("res.partner", {"name": f"[EJ] Proveedor con IVA {MARCA}", "is_company": True})
    socios_prueba.append(socio_iva)
    lista_iva = c.create("comercio.lista.proveedor", {
        "partner_id": socio_iva, "categoria_id": ferreteria, "col_codigo": "Cód.",
        "col_descripcion": "Descripción", "col_costo": "Precio", "col_iva": "IVA",
        "trae_iva": True, "iva_por_defecto": 21, "moneda": "usd", "cotizacion": 1000})
    archivo = excel_con_formato([], ["Cód.", "Descripción", "Precio", "IVA"],
                                [["I1", f"{palabra()} TALADRO", 121, 21],
                                 ["I2", f"{palabra()} CINTA", 110.5, 10.5],
                                 ["I3", f"{palabra()} MECHA", 121, ""]])
    datos = lineas(importar(lista_iva, [], archivo=archivo))
    for codigo in ("I1", "I2", "I3"):
        assert abs(datos[codigo]["costo"] - 100000) < 0.01, (codigo, datos[codigo]["costo"])
    print("    Lista en dólares (fija 1000) con IVA 21 y 10,5 por fila: costo sin IVA en pesos ✓")




def probar_descartar(socios_prueba: list[int], productos_prueba: list[int]) -> None:
    """Descartar la lista más nueva: la anterior (con filas aplicadas) vuelve a ser la vigente y se
    puede seguir aplicando (antes decía «hay una importación más nueva», 30/10)."""
    linea = "comercio.lista.importacion.linea"
    socio = c.create("res.partner", {"name": f"[EJ] Proveedor descartar {MARCA}", "is_company": True})
    socios_prueba.append(socio)
    lista = c.create("comercio.lista.proveedor", {"partner_id": socio, "categoria_id": rubro()})
    filas = [["Z1", f"{palabra()} {palabra()}", "", 100], ["Z2", f"{palabra()} {palabra()}", "", 200]]
    primera = importar(lista, filas)

    def fila(imp, codigo):
        return c.search_read(linea, [("importacion_id", "=", imp), ("codigo_proveedor", "=", codigo)],
                             ["id", "estado", "producto_id"])[0]

    c.call(linea, "action_aplicar", [fila(primera, "Z1")["id"]])
    productos_prueba.append(fila(primera, "Z1")["producto_id"][0])
    segunda = importar(lista, filas)
    c.call("comercio.lista.importacion", "action_descartar", [segunda])
    assert c.read("comercio.lista.importacion", [primera], ["es_vigente"])[0]["es_vigente"]
    c.call(linea, "action_aplicar", [fila(primera, "Z2")["id"]])  # antes: «hay una importación más nueva»
    assert fila(primera, "Z2")["estado"] == "aplicada"
    productos_prueba.append(fila(primera, "Z2")["producto_id"][0])
    print("    Descartar la más nueva: en la anterior se puede seguir aplicando ✓")


def probar_aplicar_todo(socios_prueba: list[int], productos_prueba: list[int]) -> None:
    """«Aplicar todo» (19/11): un botón aplica lo de los productos que ya tenemos, sin tope de
    variación, y nunca agrega lo que no tenemos. El descuento general se pone en el asistente."""
    linea = "comercio.lista.importacion.linea"
    socio = c.create("res.partner", {"name": f"[EJ] Proveedor aplicar todo {MARCA}", "is_company": True})
    socios_prueba.append(socio)
    w1, w2, w3 = (f"{palabra()} {palabra()}" for _ in range(3))
    wizard = c.create("comercio.importar.lista.wizard", {
        "partner_id": socio, "archivo": excel([["W1", w1, "", 100], ["W2", w2, "", 200]]),
        "nombre_archivo": "lista.xlsx", "categoria_id": rubro(), "descuentos": "10"})
    primera = c.call("comercio.importar.lista.wizard", "action_importar", [wizard])["res_id"]
    lista = c.read("comercio.lista.importacion", [primera], ["lista_id"])[0]["lista_id"][0]
    assert c.read("comercio.lista.proveedor", [lista], ["descuentos"])[0]["descuentos"] == "10"

    def fila(imp, codigo):
        return c.search_read(linea, [("importacion_id", "=", imp), ("codigo_proveedor", "=", codigo)],
                             ["id", "estado", "producto_id", "costo"])[0]

    assert fila(primera, "W1")["costo"] == 90, fila(primera, "W1")
    print("    Descuento general en el asistente: queda en la lista y el costo sale con él (100 → 90) ✓")
    c.call(linea, "action_aplicar", [fila(primera, "W1")["id"]])
    productos_prueba.append(fila(primera, "W1")["producto_id"][0])
    segunda = importar(lista, [["W1", w1, "", 150], ["W2", w2, "", 200], ["W3", w3, "", 300]])
    c.call("comercio.lista.importacion", "action_aplicar_todo", [segunda])
    assert fila(segunda, "W1")["estado"] == "aplicada" and fila(segunda, "W1")["costo"] == 135
    assert fila(segunda, "W2")["estado"] == fila(segunda, "W3")["estado"] == "pendiente"
    assert not fila(segunda, "W2")["producto_id"] and not fila(segunda, "W3")["producto_id"]
    print("    «Aplicar todo»: la suba de 50 % se aplica (sin tope) y lo que no tenemos no se agrega ✓")


def probar_codigo_de_fabrica(socios_prueba: list[int], productos_prueba: list[int]) -> None:
    """20/11: la lista nueva trae el código de fábrica de un producto que tenía el propio (20…): lo
    reemplaza y el propio queda como alternativo; «Deshacer» deja todo como estaba."""
    linea = "comercio.lista.importacion.linea"
    socio = c.create("res.partner", {"name": f"[EJ] Proveedor código de fábrica {MARCA}", "is_company": True})
    socios_prueba.append(socio)
    lista = c.create("comercio.lista.proveedor", {"partner_id": socio, "categoria_id": rubro()})
    nombre = f"{palabra()} {palabra()}"
    primera = importar(lista, [["F1", nombre, "", 100]])
    f1 = c.search_read(linea, [("importacion_id", "=", primera)], ["id"])[0]["id"]
    c.call(linea, "action_aplicar", [f1])
    tmpl = c.read(linea, [f1], ["producto_id"])[0]["producto_id"][0]
    productos_prueba.append(tmpl)
    propio = c.read("product.template", [tmpl], ["barcode"])[0]["barcode"]
    assert propio.startswith("20"), propio
    ean = "779" + "".join(random.choice(string.digits) for _ in range(9))
    ean += str((10 - sum(int(d) * (3 if i % 2 else 1) for i, d in enumerate(ean)) % 10) % 10)
    segunda = importar(lista, [["F1", nombre, ean, 100]])
    f2 = c.search_read(linea, [("importacion_id", "=", segunda)], ["id", "accion"])[0]
    assert f2["accion"] == "actualizar", f2
    c.call("comercio.lista.importacion", "action_aplicar_todo", [segunda])
    variante = c.search_read("product.product", [("product_tmpl_id", "=", tmpl)], ["id", "barcode"])[0]
    assert variante["barcode"] == ean, variante
    alternativos = c.search_read("product.uom", [("product_id", "=", variante["id"])], ["barcode"])
    assert [a["barcode"] for a in alternativos] == [propio], alternativos
    print(f"    Lista nueva con código de fábrica: {propio} → {ean}; el propio queda como alternativo ✓")
    c.call(linea, "action_deshacer", [f2["id"]])
    assert c.read("product.template", [tmpl], ["barcode"])[0]["barcode"] == propio
    assert not c.search_read("product.uom", [("product_id", "=", variante["id"])], ["id"])
    print("    «Deshacer»: vuelve el código propio y se borra el alternativo ✓")


if __name__ == "__main__":
    sys.exit(main())
