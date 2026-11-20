"""Reglas de códigos e importación de productos (integrations/catalogo), sin Odoo."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parents[1] / "addons" / "comercio_catalogo"))
from catalogo.codigos import (  # noqa: E402
    FABRICANTE,
    INTERNO,
    INVALIDO,
    codigo_propio,
    es_gtin_valido,
    normalizar,
    numero_de_codigo_propio,
)
from catalogo.convertir import convertir, leer_filas, sugerir_mapeo  # noqa: E402
from catalogo.odoo_api import costo_por_unidad  # noqa: E402
from catalogo.plan import (  # noqa: E402
    ACTUALIZAR,
    NUEVO,
    POSIBLE_DUPLICADO,
    REVISAR,
    SIN_CAMBIOS,
    VINCULAR,
    Foto,
    es_automatico,
    planificar,
)

EAN = "7790000001017"  # EAN-13 ficticio válido


def test_codigo_propio_es_ean13_valido_con_prefijo_20():
    codigo = codigo_propio(1234)
    assert codigo == "2000000012346" and es_gtin_valido(codigo)
    assert numero_de_codigo_propio(codigo) == 1234
    assert numero_de_codigo_propio(EAN) is None


def test_normalizar_repara_lo_que_rompe_excel():
    assert normalizar(EAN) == (EAN, FABRICANTE)
    assert normalizar(f" {EAN}.0 ") == (EAN, FABRICANTE)
    assert normalizar("36000291452") == ("036000291452", FABRICANTE)  # UPC-A sin el 0 inicial
    assert normalizar("2000005550010")[1] == INTERNO
    assert normalizar("7,79E+12")[1] == INVALIDO
    assert normalizar("7790000001018")[1] == INVALIDO  # verificador mal
    assert normalizar("") == (None, None)
    # Código GS1 completo (01 + GTIN-14 + 17 vencimiento…): se usa el código de barras de adentro
    assert normalizar("010779236601960617270101") == ("7792366019606", FABRICANTE)
    assert normalizar("010779236682015817300200102025-2C") == ("7792366820158", FABRICANTE)  # lote con letras
    assert normalizar("0107792366019607")[1] == INVALIDO  # no es GS1 (corto) ni un GTIN válido


def fila(**v):
    base = {"proveedor": "Prov A", "codigo_proveedor": "A1", "descripcion_proveedor": "Algo",
            "codigo_barras": "", "nombre": "", "categoria": "", "unidad": "u", "costo": "100"}
    return {**base, **v}


def foto(productos=(), prov=()):
    categorias = {"Todos", "Mascotas", "Mascotas / Alimento"}
    return Foto(list(productos), list(prov), {"Prov A", "Prov B"}, categorias, hoy="2026-10-08")


def test_producto_nuevo_sin_codigo_recibe_el_siguiente_propio():
    existentes = [{"id": 1, "barcode": codigo_propio(7), "name": "X"}]
    a = planificar([fila()], foto(existentes))[0]
    assert a.tipo == NUEVO and a.producto["barcode"] == codigo_propio(8)
    assert a.producto["default_code"] == "8"  # D5: misma numeración


def test_una_sola_numeracion_para_referencia_y_codigo_propio():
    existentes = [{"id": 1, "barcode": EAN, "default_code": "41", "name": "X"}]
    acciones = planificar([fila(codigo_barras=EAN, proveedor="Prov B", codigo_proveedor="Z"),
                           fila(codigo_proveedor="A2", descripcion_proveedor="Tornillo")], foto(existentes))
    nuevo = acciones[1]
    assert nuevo.producto["default_code"] == "42" and nuevo.producto["barcode"] == codigo_propio(42)


def test_stock_solo_en_los_rubros_configurados_o_forzado_por_columna():
    con_stock = ["Mascotas / Alimento"]
    filas = [fila(categoria="Mascotas / Alimento"), fila(codigo_proveedor="A2", categoria="Mascotas"),
             fila(codigo_proveedor="A3", categoria="Mascotas", controla_stock="si")]
    assert [a.producto["is_storable"] for a in planificar(filas, foto(), con_stock)] == [True, False, True]


def test_mismo_codigo_de_barras_en_otro_proveedor_se_vincula():
    acciones = planificar([fila(codigo_barras=EAN), fila(proveedor="Prov B", codigo_proveedor="B9",
                                                          codigo_barras=EAN)], foto())
    assert [a.tipo for a in acciones] == [NUEVO, VINCULAR]
    assert not acciones[1].vuelve  # se agrega un proveedor, no vuelve
    assert acciones[1].tmpl == acciones[0].tmpl


def test_codigo_con_prefijo_2_queda_como_codigo_del_proveedor():
    a = planificar([fila(codigo_proveedor="", codigo_barras="2000005550010")], foto())[0]
    assert a.tipo == NUEVO and a.proveedor["product_code"] == "2000005550010"
    assert a.producto["barcode"].startswith("20") and a.producto["barcode"] != "2000005550010"


def test_conflicto_entre_codigo_de_barras_y_codigo_de_proveedor_se_revisa():
    productos = [{"id": 1, "barcode": EAN, "name": "P1"}, {"id": 2, "barcode": False, "name": "P2"}]
    prov = [{"id": 5, "partner": "Prov A", "tmpl": 2, "product_code": "A1", "product_name": "Algo",
             "price": 100.0, "min_qty": 0.0, "delay": 0}]
    assert planificar([fila(codigo_barras=EAN)], foto(productos, prov))[0].tipo == REVISAR


def test_idempotente_y_cambio_de_costo():
    productos = [{"id": 1, "barcode": EAN, "name": "P1"}]
    prov = [{"id": 5, "partner": "Prov A", "tmpl": 1, "product_code": "A1", "product_name": "Algo",
             "price": 100.0, "min_qty": 0.0, "delay": 0}]
    assert planificar([fila(codigo_barras=EAN)], foto(productos, prov))[0].tipo == SIN_CAMBIOS
    a = planificar([fila(codigo_barras=EAN, costo="1.250,50")], foto(productos, prov))[0]
    # D7: cambio de costo → historial: se cierra el anterior y se crea uno desde hoy
    assert a.tipo == ACTUALIZAR and a.historial and a.proveedor_id == 5
    assert a.proveedor["price"] == 1250.5 and a.proveedor["date_start"] == "2026-10-08"
    # Otro cambio el mismo día sobre un precio que empieza hoy: se corrige en el lugar
    prov[0]["date_start"] = "2026-10-08"
    a = planificar([fila(codigo_barras=EAN, costo="1.300")], foto(productos, prov))[0]
    assert not a.historial and a.proveedor == {"price": 1300.0}


def test_numeros_en_formato_argentino():
    from catalogo.plan import _numero

    assert _numero("1.300") == 1300 and _numero("12.500.000") == 12500000
    assert _numero("1.234,56") == 1234.56 and _numero("1250.5") == 1250.5 and _numero("$ 35") == 35


def test_vincular_a_confirmado_a_mano():
    productos = [{"id": 1, "barcode": False, "default_code": "77", "name": "P1"}]
    a = planificar([fila(proveedor="Prov B", codigo_proveedor="X9", vincular_a="77")], foto(productos))[0]
    assert a.tipo == VINCULAR and a.tmpl == 1
    assert planificar([fila(vincular_a="999")], foto(productos))[0].tipo == REVISAR


def test_mismo_codigo_de_proveedor_en_otro_proveedor_no_se_une():
    acciones = planificar([fila(codigo_proveedor="A-100"),
                           fila(proveedor="Prov B", codigo_proveedor="A-100",
                                descripcion_proveedor="Otra cosa")],
                          foto())
    assert [a.tipo for a in acciones] == [NUEVO, NUEVO]


def test_codigo_de_fabrica_reemplaza_al_propio_y_el_propio_queda_como_alternativo():
    # 20/11: una lista nueva trae el código de fábrica de un producto que tenía el propio (20…)
    productos = [{"id": 1, "barcode": codigo_propio(3), "name": "P1"}]
    prov = [{"id": 5, "partner": "Prov A", "tmpl": 1, "product_code": "A1", "product_name": "Algo",
             "price": 100.0, "min_qty": 0.0, "delay": 0}]
    a = planificar([fila(codigo_barras=EAN)], foto(productos, prov))[0]
    assert a.tipo == ACTUALIZAR and a.completar_barcode == EAN
    assert a.codigo_propio_anterior == codigo_propio(3)


def test_codigos_de_fabrica_distintos_para_el_mismo_producto_se_preguntan():
    # Guantes de dos marcas unidos al mismo guante nuestro (con código propio): son distintos
    productos = [{"id": 1, "barcode": codigo_propio(3), "default_code": "3", "name": "Guante L"}]
    otro_ean = "7790000001024"
    acciones = planificar([fila(codigo_proveedor="G1", codigo_barras=EAN, vincular_a="3"),
                           fila(codigo_proveedor="G2", codigo_barras=otro_ean, vincular_a="3",
                                descripcion_proveedor="Otra marca")], foto(productos))
    assert [a.tipo for a in acciones] == [POSIBLE_DUPLICADO, POSIBLE_DUPLICADO]
    assert all(a.candidatos[0].id == 1 and not a.completar_barcode for a in acciones)


def test_codigo_de_fabrica_de_otro_producto_no_se_le_pone_a_este():
    productos = [{"id": 1, "barcode": codigo_propio(3), "default_code": "3", "name": "P1"},
                 {"id": 2, "barcode": EAN, "default_code": "4", "name": "P2"}]
    a = planificar([fila(codigo_proveedor="Z1", vincular_a="3", codigo_barras=EAN)], foto(productos))[0]
    assert a.tipo == REVISAR


def test_categoria_inexistente_se_revisa_y_codigo_roto_se_carga_sin_codigo():
    acciones = planificar([fila(categoria="No existe")], foto())
    assert [a.tipo for a in acciones] == [REVISAR]
    # El código de barras roto (Excel) no frena la fila: se carga sin él y avisa (30/10)
    nuevo = planificar([fila(codigo_barras="7,79E+12")], foto())[0]
    assert nuevo.tipo == NUEVO and any("código de barras inválido" in a for a in nuevo.avisos)
    assert nuevo.producto["barcode"].startswith("20")


def test_convertir_excel_de_proveedor_con_mapeo(tmp_path):
    import openpyxl

    libro = openpyxl.Workbook()
    hoja = libro.active
    hoja.append(["LISTA DE PRECIOS OCTUBRE"])
    hoja.append(["Código", "Descripción", "EAN", "Precio s/IVA"])
    hoja.append(["A-100", "ALIM PERRO X 15KG", 7790000001017, 25000.5])
    hoja.append(["", "", "", ""])
    ruta = tmp_path / "lista.xlsx"
    libro.save(ruta)
    mapeo = {"proveedor": "Prov A", "columnas": {"codigo_proveedor": "Código",
             "descripcion_proveedor": "Descripción", "codigo_barras": "EAN", "costo": "Precio s/IVA"},
             "valores_fijos": {"unidad": "u"}}
    salida = convertir(mapeo, leer_filas(ruta, 0, fila_encabezado=2))
    assert len(salida) == 1
    assert salida[0]["codigo_barras"] == EAN and salida[0]["proveedor"] == "Prov A"
    assert salida[0]["unidad"] == "u"


def test_costo_por_unidad_no_usa_el_precio_por_bulto():
    """P-044: el costo del producto es el precio por unidad más barato, no el del bulto."""
    def p(precio, minimo):
        return {"price_discounted": precio, "min_qty": minimo}
    # Distribuidora vende por unidad a 25.000; el Mayorista, bulto de 10 a 24.500
    assert costo_por_unidad([p(25000, 1), p(24500, 10)]) == 25000
    # El mismo proveedor con precio por unidad y por bulto
    assert costo_por_unidad([p(26000, 0), p(24500, 10), p(25500, 1)]) == 25500
    # Nadie vende por unidad: el de menor cantidad mínima
    assert costo_por_unidad([p(24000, 12), p(24500, 6), p(24800, 6)]) == 24500
    assert costo_por_unidad([]) is None


def test_bulto_mas_barato_no_baja_el_costo():
    """Un precio por bulto más barato (aunque sea de otro proveedor) no baja el costo."""
    def p(precio, minimo):
        return {"price_discounted": precio, "min_qty": minimo}
    assert costo_por_unidad([p(1500, 1), p(1400, 12)]) == 1500


def test_dos_precios_del_proveedor_por_menor_y_por_mayor():
    """El proveedor da precio por unidad y por mayor (desde N unidades): se guardan los dos."""
    a = planificar([fila(costo="1.000", costo_mayor="900", cantidad_mayor="12")], foto())[0]
    assert a.tipo == NUEVO and a.proveedor["price"] == 1000
    assert a.proveedor["comercio_precio_mayor"] == 900 and a.proveedor["comercio_cantidad_mayor"] == 12
    # Sin cantidad (o no mayor que el mínimo) no se puede usar: aviso y solo el precio por menor
    a = planificar([fila(costo="1000", costo_mayor="900")], foto())[0]
    assert a.proveedor["comercio_precio_mayor"] == 0 and any("por mayor" in x for x in a.avisos)


def test_cambio_del_precio_por_mayor_respeta_el_tope():
    productos = [{"id": 1, "barcode": EAN, "name": "P1"}]
    prov = [{"id": 5, "partner": "Prov A", "tmpl": 1, "product_code": "A1", "product_name": "Algo",
             "price": 100.0, "min_qty": 0.0, "delay": 0, "date_start": "2026-10-08",
             "comercio_precio_mayor": 90.0, "comercio_cantidad_mayor": 12.0}]
    def plan(**v):
        return planificar([fila(codigo_barras=EAN, **v)], foto(productos, prov))[0]
    chico = plan(costo_mayor="93", cantidad_mayor="12")
    assert chico.tipo == ACTUALIZAR and chico.proveedor == {"comercio_precio_mayor": 93.0}
    assert es_automatico(chico, 0.10)
    grande = plan(costo_mayor="120", cantidad_mayor="12")
    assert not es_automatico(grande, 0.10)
    # Deja de dar precio por mayor: lo mira una persona
    sin_mayor = plan()
    assert sin_mayor.proveedor["comercio_precio_mayor"] == 0 and not es_automatico(sin_mayor, 0.10)


def test_columnas_de_dos_precios_se_reconocen_solas():
    m = sugerir_mapeo(["Código", "Descripción", "Precio unitario", "Precio x bulto", "Unidades x bulto"])
    assert m["costo"] == "Precio unitario" and m["costo_mayor"] == "Precio x bulto"
    assert m["cantidad_mayor"] == "Unidades x bulto" and "cantidad_minima" not in m
    # Una sola columna llamada «Precio mayorista»: es el costo
    m = sugerir_mapeo(["Código", "Descripción", "Precio mayorista"])
    assert m["costo"] == "Precio mayorista" and "costo_mayor" not in m


def test_producto_que_vuelve_a_la_lista_se_reconoce_por_su_codigo():
    """Se dio de baja (precio cerrado) y vuelve con el mismo código: no es un posible duplicado
    de sí mismo, se le vuelve a agregar el proveedor con el último precio como «anterior»."""
    productos = [{"id": 7, "name": "Hueso carnaza 15 cm"}]
    cerrado = {"id": 30, "partner": "Prov A", "tmpl": 7, "product_code": "A1",
               "product_name": "HUESO CARNAZA 15CM", "price": 1450.0}
    f = foto(productos)
    f.cerrados = [cerrado]
    a = planificar([fila(descripcion_proveedor="HUESO CARNAZA 15CM", costo="1500")], f)[0]
    assert a.tipo == VINCULAR and a.tmpl == 7 and "vuelve a la lista" in a.detalle
    assert a.costo_anterior == 1450.0 and a.costo == 1500.0
    # Sin código: por la descripción exacta
    sin_codigo = {**cerrado, "product_code": False}
    f.cerrados = [sin_codigo]
    a = planificar([fila(codigo_proveedor="", descripcion_proveedor="Hueso  carnaza 15cm")], f)[0]
    assert a.tipo == VINCULAR and a.tmpl == 7


def test_codigo_cerrado_no_pisa_un_precio_vigente():
    """Si el producto ya tiene otro precio vigente de ese proveedor (cambió el código), el
    código viejo no lo vuelve a unir: sigue el camino de siempre."""
    productos = [{"id": 7, "name": "Hueso carnaza 15 cm"}]
    vigente = {"id": 31, "partner": "Prov A", "tmpl": 7, "product_code": "A9",
               "product_name": "HUESO CARNAZA 15CM", "price": 1450.0}
    f = foto(productos, [vigente])
    f.cerrados = [{**vigente, "id": 30, "product_code": "A1"}]
    a = planificar([fila(codigo_proveedor="A1", descripcion_proveedor="Tornillo 3x40")], f)[0]
    assert a.tipo == NUEVO


def test_codigo_repetido_de_un_producto_nuestro_se_revisa():
    """La segunda fila con el mismo código no cambia nada del producto (Beta, P-061; FC)."""
    productos = [{"id": 1, "barcode": EAN, "name": "P1"}]
    prov = [{"id": 5, "partner": "Prov A", "tmpl": 1, "product_code": "A1", "product_name": "Algo",
             "price": 100.0, "min_qty": 0.0, "delay": 0}]
    filas = [fila(codigo_barras=EAN), fila(codigo_barras=EAN, descripcion_proveedor="Otro")]
    primera, segunda = planificar(filas, foto(productos, prov))
    assert primera.tipo == SIN_CAMBIOS
    assert segunda.tipo == REVISAR and "dos veces" in segunda.detalle


def _lista_tipo_gas_del_sur(n=30):
    """Lista ficticia como la de Gas del Sur: LISTA del proveedor, «C/ Dto.» = LISTA − 25 %, NETO =
    LISTA × 0,75 × el IVA de cada producto (10,5 o 21, alguno sin IVA) y PÚBLICO = NETO × 1,6."""
    titulos = ["COD", "DESCRIPCION", "LISTA", "C/ Dto.", "NETO", "PUBLICO"]
    filas = []
    for i in range(n):
        lista = 1000 + 37 * i
        iva = 1.105 if i % 3 == 0 else (1.0 if i == 4 else 1.21)
        neto = lista * 0.75 * iva
        filas.append({"COD": f"LG{i}", "DESCRIPCION": f"Producto {i}", "LISTA": f"{lista}",
                      "C/ Dto.": f"{lista * 0.75:.2f}", "NETO": f"{neto:.2f}",
                      "PUBLICO": f"{neto * 1.6:.2f}"})
    return titulos, filas


def test_analizar_cuentas_tipo_gas_del_sur():
    from catalogo.convertir import analizar_cuentas, descuento_detectado

    titulos, filas = _lista_tipo_gas_del_sur()
    analisis = analizar_cuentas(titulos, filas)
    assert set(analisis["derivadas"]) == {"C/ Dto.", "PUBLICO"}
    assert analisis["derivadas"]["C/ Dto."] == ("LISTA", 0.75)
    assert analisis["con_iva"] == ("NETO", "LISTA", 0.75)
    assert descuento_detectado(analisis, "LISTA") == 25
    mapeo = sugerir_mapeo(titulos, filas)
    assert mapeo["costo"] == "LISTA" and mapeo["precio_con_iva"] == "NETO"


def test_convertir_saca_el_iva_de_la_columna_con_iva():
    titulos, filas = _lista_tipo_gas_del_sur()
    salida = convertir({"proveedor": "Gas del Sur", "columnas": {
        "codigo_proveedor": "COD", "descripcion_proveedor": "DESCRIPCION", "costo": "LISTA",
        "precio_con_iva": "NETO"}}, filas)
    por_codigo = {f["codigo_proveedor"]: f for f in salida}
    assert por_codigo["LG0"]["iva_fila"] == "10,5"
    assert por_codigo["LG1"]["iva_fila"] == "21"
    assert "iva_fila" not in por_codigo["LG4"] and "IVA a confirmar" in por_codigo["LG4"]["aviso_iva"]
    assert por_codigo["LG1"]["costo"] == "1037"  # el costo sigue siendo la LISTA (descuento en la lista)


def test_analizar_cuentas_no_confunde_precio_sin_iva_ni_cuentas_de_cuentas():
    from catalogo.convertir import analizar_cuentas, descuento_detectado

    # Mu: primero el precio con IVA y después «PRECIOS» = con IVA ÷ 1,21: PRECIOS es el costo
    filas = [{"COD": f"P{i}", "DESC": f"Cosa {i}", "IVA": f"{(500 + i) * 1.21:.2f}", "PRECIOS": f"{500 + i}"}
             for i in range(20)]
    assert not analizar_cuentas(["COD", "DESC", "IVA", "PRECIOS"], filas)["derivadas"]
    assert sugerir_mapeo(["COD", "DESC", "IVA", "PRECIOS"], filas)["costo"] == "PRECIOS"
    # LUMINA: una cuenta (× 0,76) sobre el precio con IVA no es un descuento de la lista
    analisis = {"derivadas": {"Columna M": ("ivb", 0.76)}, "con_iva": ("ivb", "Precio s/IVA", 1.0)}
    assert descuento_detectado(analisis, "Precio s/IVA") is None


def test_presentacion_aparte_se_suma_a_la_descripcion_repetida():
    # 20/11, lista de un vivero: «Tierra Mejorada» en 5, 10 y 25 dm³ son tres productos
    titulos = ["PRODUCTO", "PRESENTACIÓN", "PRECIO SIN IVA"]
    filas = [dict(zip(titulos, f, strict=True)) for f in (("Tierra Mejorada", "5 dm³", "1400"),
                                              ("Tierra Mejorada", "10 dm³", "2300"),
                                              ("Compost", "10 dm³", "2900"), ("Compost", "25 dm³", "5300"),
                                              ("Mezcla para cactus", "5 dm³", "1900"))]
    assert sugerir_mapeo(titulos, filas)["descripcion_proveedor"] == "PRODUCTO + PRESENTACIÓN"


def test_precio_discontinuado_no_se_carga():
    # 20/11, Xi: «DISC.» en la columna del precio = ya no lo vende (no es un error a corregir)
    titulos = ["COD", "DESCRIPCION", "PRECIO"]
    datos = (("1", "PLATO Nº 30", "$ 700,00"), ("2", "PLATO Nº 35", "DISC."),
             ("3", "PLATO Nº 45", "Discontinuado"), ("4", "PLATO Nº 55", "Consultar"))
    filas = [dict(zip(titulos, f, strict=True)) for f in datos]
    columnas = {"codigo_proveedor": "COD", "descripcion_proveedor": "DESCRIPCION", "costo": "PRECIO"}
    mapeo = {"proveedor": "Prov A", "columnas": columnas}
    salida = convertir(mapeo, filas)
    assert [f["descripcion_proveedor"] for f in salida] == ["PLATO Nº 30", "PLATO Nº 55"]
    assert salida[1]["costo"] == ""  # «Consultar»: a revisar, como antes


def test_productos_lado_a_lado_se_apilan():
    # 20/11, Nu: tres líneas de macetas en columnas lado a lado con los mismos títulos
    from catalogo.convertir import filas_con_titulos, redetectar

    tabla = [["Lista"], ["", "DESCRIPCION", "PRECIO", "DESCRIPCION", "PRECIO"],
             ["", "DENISE 15 cm.", "1390", "ECONOMICA N 25", "3050"],
             ["", "DENISE 20 cm.", "2390", "", ""]]
    filas = filas_con_titulos(tabla, 2)
    assert [(f["DESCRIPCION"], f["PRECIO"]) for f in filas] == [
        ("DENISE 15 cm.", "1390"), ("DENISE 20 cm.", "2390"), ("ECONOMICA N 25", "3050")]
    assert redetectar(tabla) == (2, {"descripcion_proveedor": "DESCRIPCION", "costo": "PRECIO"})
