"""Del precio de la lista al costo (addons/comercio_catalogo/catalogo/costo.py), sin Odoo."""

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parents[1] / "addons" / "comercio_catalogo"))
from catalogo.convertir import convertir, sugerir_mapeo  # noqa: E402
from catalogo.costo import (  # noqa: E402
    cadena,
    costo_desde_lista,
    descuentos_de_celda,
    normalizar_ajustes,
    porcentaje,
    regla_de_familia,
)


def calcular(precio, **ajustes):
    return costo_desde_lista(precio, normalizar_ajustes(ajustes))


def test_sin_ajustes_el_precio_es_el_costo():
    costo, cuenta = costo_desde_lista(100, normalizar_ajustes({}))
    assert costo == 100
    assert cuenta == "$ 100,00 → $ 100,00"


def test_descuentos_en_cadena_y_recargo():
    costo, cuenta = calcular(1000, descuentos="30+10", recargo=2.5)
    assert costo == pytest.approx(1000 * 0.7 * 0.9 * 1.025)
    assert "−30 % (lista)" in cuenta and "+2,5 % recargo" in cuenta


def test_lista_en_dolares_con_iva_incluido():
    costo, cuenta = calcular(10, moneda="usd", cotizacion=1450, trae_iva=True, iva=21)
    assert costo == pytest.approx(10 * 1450 / 1.21)
    assert cuenta.startswith("US$ 10 × 1.450,00")


def test_dolares_sin_cotizacion_es_un_error():
    with pytest.raises(ValueError, match="cotización"):
        calcular(10, moneda="usd")


def test_familia_producto_y_columna_se_suman_en_cadena():
    ajustes = normalizar_ajustes({
        "descuentos": "30",
        "reglas": [{"contiene": "BULON, TUERCA", "descuentos": "10"},
                   {"contiene": "BULON", "descuentos": "50"}],
        "excepciones": {"B-12": "5"},
    })
    costo, cuenta = costo_desde_lista(100, ajustes, "2", "", "BULONES CABEZA HEXAGONAL 1/4", "B-12")
    assert costo == pytest.approx(100 * 0.7 * 0.9 * 0.95 * 0.98)  # vale la primera regla, no la de 50
    assert "(BULON, TUERCA)" in cuenta and "(producto)" in cuenta and "(columna de la lista)" in cuenta


def test_iva_de_la_fila_del_producto_o_de_la_lista():
    ajustes = normalizar_ajustes({"trae_iva": True, "iva": 21, "iva_por_codigo": {"A1": 10.5}})
    assert costo_desde_lista(121, ajustes, "", "", "", "X")[0] == pytest.approx(100)  # el de la lista
    assert costo_desde_lista(110.5, ajustes, "", "", "", "A1")[0] == pytest.approx(100)  # el del producto
    assert costo_desde_lista(110.5, ajustes, "", "27", "", "A1")[0] == pytest.approx(100)  # manda el producto
    assert costo_desde_lista(127, ajustes, "", "27", "", "X")[0] == pytest.approx(100)  # si no, la columna
    assert costo_desde_lista(121, ajustes, "", "0,21", "", "X")[0] == pytest.approx(100)  # 21 % de Excel


def test_porcentajes_escritos_de_varias_formas():
    assert cadena("30+10+10") == [30, 10, 10]
    assert cadena("5 % + 2,5") == [5, 2.5]
    with pytest.raises(ValueError):
        cadena("treinta")
    with pytest.raises(ValueError):
        cadena("120")
    assert porcentaje("10,5") == 10.5
    assert porcentaje("0,105") == 10.5
    assert porcentaje("") is None
    assert descuentos_de_celda("10+5") == [10, 5]
    assert descuentos_de_celda("SIN DESC") == []


def test_regla_por_parte_de_palabra():
    reglas = [{"contiene": "bulon", "descuentos": "10"}]
    assert regla_de_familia(reglas, "BULONES 1/4 x 2", "")
    assert regla_de_familia(reglas, "Búlón", "")  # sin acentos
    assert not regla_de_familia(reglas, "TORNILLO", "")


def test_compatible_con_los_ajustes_de_antes():
    a = normalizar_ajustes({"cotizacion": 1500, "iva_incluido": 21})
    assert a["moneda"] == "usd" and a["trae_iva"] and a["iva"] == 21


def mapeo(columnas, **ajustes):
    return {"proveedor": "P", "columnas": columnas, "valores_fijos": {"unidad": "u"}, "ajustes": ajustes}


def test_convertir_guarda_el_precio_de_la_lista_y_la_cuenta():
    filas = [{"Código": "1", "Descripción": "Martillo", "Precio": "1.000,00", "Desc.": "10", "IVA %": "21"}]
    salida = convertir(mapeo({"codigo_proveedor": "Código", "descripcion_proveedor": "Descripción",
                              "costo": "Precio", "descuento": "Desc.", "iva": "IVA %"},
                             descuentos="5"), filas)
    fila = salida[0]
    assert fila["precio_lista"] == "1.000,00"
    assert float(fila["costo"]) == pytest.approx(1000 * 0.95 * 0.9)  # sin «trae IVA», la columna no se usa
    assert fila["descuento_fila"] == "10" and fila["iva_fila"] == "21"
    assert "−10 % (columna de la lista)" in fila["calculo"]


def test_sin_ajustes_la_fila_queda_como_antes():
    filas = [{"Código": "1", "Descripción": "Martillo", "Precio": "1.000,00"}]
    fila = convertir(mapeo({"codigo_proveedor": "Código", "descripcion_proveedor": "Descripción",
                            "costo": "Precio"}), filas)[0]
    assert fila["costo"] == "1.000,00" and "calculo" not in fila


def test_familia_en_fila_aparte_cuenta_para_la_regla():
    filas = [{"Código": "", "Descripción": "BULONES", "Precio": ""},
             {"Código": "7", "Descripción": "1/4 x 2", "Precio": "100"}]
    fila = convertir(mapeo({"codigo_proveedor": "Código", "descripcion_proveedor": "Descripción",
                            "costo": "Precio"}, reglas=[{"contiene": "BULON", "descuentos": "10"}]), filas)[0]
    assert float(fila["costo"]) == pytest.approx(90)


def test_la_columna_descuento_nunca_se_sugiere_y_la_de_iva_si():
    titulos = ["Código", "Descripción", "Precio de lista", "Desc. %", "Descuento", "IVA %",
               "Precio final Ejemplo"]
    filas = [dict(zip(titulos, ["1", "Martillo", "100", "10", "10", "21", "95"], strict=True))]
    sugerido = sugerir_mapeo(titulos, filas)
    assert "descuento" not in sugerido
    assert sugerido["iva"] == "IVA %"
    assert sugerido["costo"] == "Precio de lista"  # nunca el «precio final» del comercio


def test_promociones_en_texto_como_las_de_fc():
    from catalogo.costo import leer_promocion

    assert leer_promocion("5% DTO. X UNIDAD") == {"unidad": [5.0], "escalones": [], "neto": None}
    assert leer_promocion("10% DTO. X 2 ROLLOS                       15% DTO. X 5 ROLLOS") == {
        "unidad": [], "escalones": [(2.0, 10.0), (5.0, 15.0)], "neto": None}
    assert leer_promocion("15% DTO. X 5P / 20% DTO. X 10P")["escalones"] == [(5.0, 15.0), (10.0, 20.0)]
    assert leer_promocion("15% DTO. X 12 UNIDADES (CAJA CERRADA)")["escalones"] == [(12.0, 15.0)]
    assert leer_promocion("23,5% DTO. X 25 KG.")["escalones"] == [(25.0, 23.5)]
    # no es una promoción
    assert leer_promocion("ESTAÑO 33%") == {"unidad": [], "escalones": [], "neto": None}
    assert leer_promocion("") == {"unidad": [], "escalones": [], "neto": None}


def test_promocion_por_unidad_baja_el_costo_y_por_cantidad_es_el_precio_por_mayor():
    titulos = {"codigo_proveedor": "Código", "descripcion_proveedor": "Descripción", "costo": "Precio",
               "promocion": "Promociones"}
    filas = [{"Código": "1", "Descripción": "Sacahojas", "Precio": "1000", "Promociones": "5% DTO. X UNIDAD"},
             {"Código": "2", "Descripción": "Media sombra", "Precio": "1000",
              "Promociones": "6% DTO. X 3 ROLLOS  16% DTO. X 5 ROLLOS"},
             {"Código": "3", "Descripción": "Guante", "Precio": "1000", "Promociones": ""}]
    unidad, cantidad, nada = convertir(mapeo(titulos), filas)
    assert float(unidad["costo"]) == pytest.approx(950)
    assert "(promoción del proveedor)" in unidad["calculo"] and unidad["promocion"] == "5% DTO. X UNIDAD"
    assert float(cantidad["costo"]) == pytest.approx(1000)  # el costo es el de una unidad
    assert float(cantidad["costo_mayor"]) == pytest.approx(940) and cantidad["cantidad_mayor"] == "3"
    assert nada["costo"] == "1000" and "promocion" not in nada


def test_la_columna_de_promociones_se_sugiere_si_trae_porcentajes():
    titulos = ["Código", "Descripción", "Precio de lista FC", "Descuentos y Promociones Vigentes"]
    filas = [dict(zip(titulos, ["1", "Sacahojas", "100", "5% DTO. X UNIDAD"], strict=True))]
    assert sugerir_mapeo(titulos, filas)["promocion"] == "Descuentos y Promociones Vigentes"


def test_producto_nuevo_lleva_el_iva_de_la_columna():
    from catalogo.plan import NUEVO, Foto, planificar

    titulos = {"codigo_proveedor": "Código", "descripcion_proveedor": "Descripción", "costo": "Precio",
               "iva": "IVA"}
    filas = convertir(mapeo(titulos), [{"Código": "1", "Descripción": "Hidrolavadora", "Precio": "100",
                                        "IVA": "10,5"}])
    foto = Foto([], [], {"P"}, {"Todos"}, hoy="2026-10-30", socios={1: "P"})
    accion = planificar(filas, foto)[0]
    assert accion.tipo == NUEVO and accion.producto["iva"] == 10.5
    assert float(filas[0]["costo"]) == 100  # sin «trae IVA», el precio no cambia


def test_sugerencia_como_la_lista_de_fc():
    """Detalle + Descripción juntas, el IVA en una columna sin ese título y «Unidades x caja» como
    bulto (se compra de a cajas enteras) cuando no hay precio por mayor."""
    titulos = ["Código", "Detalle", "Descripción del producto", "Precio de lista FC", "Precio con I.V.A"]
    filas = [dict(zip(titulos, [str(i), "ABRAZADERA", f"{i} mm", "100", "10,5" if i == 3 else "21"],
                      strict=True)) for i in range(1, 8)]
    sugerido = sugerir_mapeo(titulos, filas)
    assert sugerido["descripcion_proveedor"] == "Detalle + Descripción del producto"
    assert sugerido["iva"] == "Precio con I.V.A"
    assert sugerido["costo"] == "Precio de lista FC"
    bulones = ["Código", "Detalle", "Descripción / medidas", "Unidades x caja", "Precio Unit. sin IVA"]
    filas = [dict(zip(bulones, [str(i), "BULON", "1/4", "100", "42"], strict=True)) for i in range(1, 8)]
    sugerido = sugerir_mapeo(bulones, filas)
    assert sugerido["bulto"] == "Unidades x caja" and "cantidad_minima" not in sugerido


def test_bulto_y_stock_como_la_lista_de_Chi():
    titulos = ["SKU", "Descripción", "UxB", "Precio s/IVA", "Stock"]
    filas = [dict(zip(titulos, [str(i), f"Lampara {i}W", "100", "0,59", "NO" if i % 2 else "SI"],
                      strict=True))
             for i in range(1, 9)]
    sugerido = sugerir_mapeo(titulos, filas)
    assert sugerido["bulto"] == "UxB" and sugerido["stock"] == "Stock"
    salida = convertir(mapeo({"codigo_proveedor": "SKU", "descripcion_proveedor": "Descripción",
                              "costo": "Precio s/IVA",
                              "bulto": "UxB", "stock": "Stock"}), filas)
    assert [f["codigo_proveedor"] for f in salida] == ["2", "4", "6", "8"]  # los «NO» no se cargan
    assert salida[0]["bulto"] == "100"


def test_precio_por_bulto_con_sus_unidades_sigue_siendo_precio_por_mayor():
    titulos = ["Código", "Descripción", "Precio unitario", "Precio x caja", "Unidades x caja"]
    filas = [dict(zip(titulos, [str(i), f"Bulon {i}", "42", "36", "100"], strict=True)) for i in range(1, 6)]
    sugerido = sugerir_mapeo(titulos, filas)
    assert sugerido["cantidad_mayor"] == "Unidades x caja" and "bulto" not in sugerido


def test_ean13_con_12_digitos_no_se_completa_queda_para_verificar():
    from catalogo.codigos import FABRICANTE, INVALIDO, normalizar
    from catalogo.plan import NUEVO, Foto, planificar

    assert normalizar("471008932410")[1] == INVALIDO  # incompleto: no se adivina el dígito
    assert normalizar("036000291452") == ("036000291452", FABRICANTE)  # UPC-A válido de 12: queda
    fila = {"proveedor": "P", "codigo_proveedor": "3240", "descripcion_proveedor": "Proyector", "costo": "10",
            "codigo_barras": "471008932410", "nombre": "", "categoria": "", "unidad": "u"}
    a = planificar([fila], Foto([], [], {"P"}, {"Todos"}, hoy="2026-10-30", socios={1: "P"}))[0]
    assert a.tipo == NUEVO and a.producto["codigo_lista"] == "471008932410"
    assert a.producto["barcode"].startswith("20")

def test_otra_presentacion_del_mismo_producto_no_es_un_error():
    from catalogo.plan import NUEVO, REVISAR, SIN_CAMBIOS, Foto, planificar

    def fila(codigo, descripcion, bulto, precio="0,69"):
        return {"proveedor": "P", "codigo_proveedor": codigo, "descripcion_proveedor": descripcion,
                "codigo_barras": "4710089500501", "nombre": "", "categoria": "", "unidad": "u",
                "costo": precio,
                "bulto": bulto}

    filas = [fila("5005", "Lampara 9W", "100"), fila("5005D20", "Lampara 9W display x 20", "20"),
             fila("5005", "Lampara 9W quarter pallet", "512", "369"), fila("5005", "Lampara 9W", "100")]
    foto = Foto([], [], {"P"}, {"Todos"}, hoy="2026-10-30", socios={1: "P"})
    tipos = [a.tipo for a in planificar(filas, foto)]
    # Primera: se carga; display y pallet: otras presentaciones (a la vista, sin corregir); la última
    # es la misma fila repetida (mismo código y bulto): esa sí se revisa
    assert tipos == [NUEVO, SIN_CAMBIOS, SIN_CAMBIOS, REVISAR]



def test_mismo_codigo_de_barras_en_dos_productos_distintos_se_cargan_los_dos():
    from catalogo.plan import NUEVO, Foto, planificar

    def fila(codigo, descripcion):
        return {"proveedor": "P", "codigo_proveedor": codigo, "descripcion_proveedor": descripcion,
                "codigo_barras": "4710089500501", "nombre": "", "categoria": "", "unidad": "u", "costo": "10"}

    foto = Foto([], [], {"P"}, {"Todos"}, hoy="2026-10-30", socios={1: "P"})
    filas = [fila("3101", "High bay 100W 11000lm"), fila("3111", "High bay HBX ULTRA 100W 15000lm")]
    acciones = planificar(filas, foto)
    # Los dos se cargan: el primero con el código de fábrica, el otro con uno propio (y la pista)
    assert [a.tipo for a in acciones] == [NUEVO, NUEVO]
    assert acciones[1].producto["codigo_lista"] == "4710089500501"



def test_codigo_de_barras_compartido_el_primero_se_lo_queda():
    from catalogo.plan import NUEVO, Foto, planificar

    def fila(codigo, descripcion):
        return {"proveedor": "P", "codigo_proveedor": codigo, "descripcion_proveedor": descripcion,
                "codigo_barras": "4710089500501", "nombre": "", "categoria": "", "unidad": "u", "costo": "10"}

    filas = [fila("5522", "Dicroica 7W"), fila("5523", "Dicroica black 7W")]
    primera, segunda = planificar(filas, Foto([], [], {"P"}, {"Todos"}, hoy="2026-10-30", socios={1: "P"}))
    assert primera.tipo == NUEVO and primera.producto["barcode"] == "4710089500501"
    assert segunda.tipo == NUEVO and segunda.producto["barcode"].startswith("20")
    assert segunda.producto["codigo_lista"] == "4710089500501"
    assert filas[1]["codigo_barras"] == "4710089500501"  # las filas originales no cambian


def test_otras_presentaciones_quedan_en_el_precio_del_proveedor():
    from catalogo.plan import NUEVO, Foto, planificar

    def fila(codigo, descripcion, bulto, precio):
        return {"proveedor": "P", "codigo_proveedor": codigo, "descripcion_proveedor": descripcion,
                "codigo_barras": "4710089500501", "nombre": "", "categoria": "", "unidad": "u",
                "costo": precio, "bulto": bulto}

    filas = [fila("5005", "Lampara 9W", "100", "0,69"),
             fila("5005D20", "Lampara 9W display box x 20", "20", "0,69")]
    primera = planificar(filas, Foto([], [], {"P"}, {"Todos"}, hoy="2026-10-30", socios={1: "P"}))[0]
    assert primera.tipo == NUEVO and "display box x 20" in primera.proveedor["comercio_presentaciones"]


def test_descuento_por_pack_completo_como_la_lista_de_Nortex():
    """«PACK 5% descuento»: el que dice «(pack x 12)» tiene precio por mayor desde 12; el costo
    por unidad no cambia y el que no dice pack queda igual."""
    from catalogo.costo import cantidad_de_pack

    assert cantidad_de_pack("AUTOPOLISH X 450cc      (pack x 12)") == 12
    assert cantidad_de_pack("BROCHES COMUNES      (PACK x 250)") == 250
    assert cantidad_de_pack("TRAPOS X 1 kg  (pack x 20 kg)") == 20
    assert cantidad_de_pack("Pack x 1") == 0 and cantidad_de_pack("PACKAGING") == 0
    titulos = {"codigo_proveedor": "Código", "descripcion_proveedor": "Descripción", "costo": "Precio"}
    filas = [{"Código": "1", "Descripción": "Autopolish x 450cc (pack x 12)", "Precio": "1000"},
             {"Código": "2", "Descripción": "Fastix blanco 25 g", "Precio": "1000"}]
    con_pack, sin_pack = convertir(mapeo(titulos, pack=5), filas)
    assert float(con_pack["costo"]) == pytest.approx(1000)
    assert con_pack["cantidad_mayor"] == "12" and float(con_pack["costo_mayor"]) == pytest.approx(950)
    assert "(pack completo)" in con_pack["calculo"]
    assert sin_pack["costo"] == "1000" and not sin_pack["costo_mayor"]
    # Con IVA incluido, el por mayor sale del costo ya sin IVA
    con_pack = convertir(mapeo(titulos, pack=5, trae_iva=True, iva=21), filas)[0]
    assert float(con_pack["costo_mayor"]) == pytest.approx(1000 / 1.21 * 0.95, abs=0.01)


def test_fila_de_titulos_repetida_a_mitad_de_la_lista_no_es_un_producto():
    titulos = {"codigo_proveedor": "Código", "descripcion_proveedor": "Descripción", "costo": "PRECIO",
               "unidad": "U/M"}
    filas = [{"Código": "1", "Descripción": "Fastix", "U/M": "C/U", "PRECIO": "100", "PUBLICO": "132"},
             {"Código": " ", "Descripción": "PRECIOS CON IVA INCLUIDO", "U/M": "U/M", "PRECIO": "COMERCIO",
              "PUBLICO": "PUBLICO"},
             {"Código": "2", "Descripción": "Barreta", "U/M": "C/U", "PRECIO": "200", "PUBLICO": "264"}]
    assert [f["codigo_proveedor"] for f in convertir(mapeo(titulos), filas)] == ["1", "2"]


def test_lista_en_dolares_con_un_precio_en_pesos_va_a_corregir():
    """Clorosur: US$ 21.408 en una lista donde la mitad cuesta menos de US$ 8."""
    from catalogo.plan import REVISAR, Foto, planificar

    titulos = {"codigo_proveedor": "Cod.", "descripcion_proveedor": "Descripcion", "costo": "Precio"}
    filas = [{"Cod.": str(i), "Descripcion": f"Cloro {i}", "Precio": str(3 + i)} for i in range(12)]
    filas.append({"Cod.": "13693", "Descripcion": "Limpiafondo LimpiaFacil", "Precio": "21408"})
    salida = convertir(mapeo(titulos, moneda="usd", cotizacion=1550), filas)
    assert "¿precio en pesos?" in salida[-1]["precio_dudoso"]
    assert not any("precio_dudoso" in f for f in salida[:-1])
    acciones = planificar(salida, Foto([], [], {"P"}, {"Todos"}, hoy="2026-11-02", socios={1: "P"}))
    assert acciones[-1].tipo == REVISAR and "¿precio en pesos?" in acciones[-1].detalle
    salida[-1]["corregida_a_mano"] = True  # «Corregir» con el precio en dólares: ya no se marca
    acciones = planificar(salida, Foto([], [], {"P"}, {"Todos"}, hoy="2026-11-02", socios={1: "P"}))
    assert acciones[-1].tipo != REVISAR
    # En pesos no se marca nada: un tornillo y una hidrolavadora pueden estar en la misma lista
    assert not any("precio_dudoso" in f for f in convertir(mapeo(titulos), filas))


def test_precio_simbolico_en_pesos_va_a_corregir():
    """FC: «TUBO EXHIBIDOR VACIO» a $ 0,02; como costo daría un precio de venta de centavos."""
    titulos = {"codigo_proveedor": "Cod.", "descripcion_proveedor": "Descripcion", "costo": "Precio"}
    filas = [{"Cod.": "1", "Descripcion": "Tubo exhibidor vacío", "Precio": "0,02"},
             {"Cod.": "2", "Descripcion": "Tornillo", "Precio": "1,77"}]
    salida = convertir(mapeo(titulos), filas)
    assert "¿precio simbólico?" in salida[0]["precio_dudoso"]
    assert "precio_dudoso" not in salida[1]
    # En dólares, centavos son un precio normal (LUMINA: US$ 0,51)
    en_dolares = convertir(mapeo(titulos, moneda="usd", cotizacion=1450), filas)
    assert not any("precio_dudoso" in f for f in en_dolares)


def test_subtitulos_con_codigo_en_la_columna_del_codigo_son_familia():
    """Aluminio Phi: «MOLDE PAN / BUDÍN INGLÉS | U / B | CÓDIGO» a mitad de la hoja."""
    titulos = {"codigo_proveedor": "CODIGO EMPRESA", "descripcion_proveedor": "DESCRIPCION",
               "costo": "PRECIO"}
    filas = [{"CODIGO EMPRESA": "271012", "DESCRIPCION": "PASTAFROLA Nº 12", "PRECIO": "855,44"},
             {"CODIGO EMPRESA": "CÓDIGO", "DESCRIPCION": "MOLDE PAN / BUDÍN INGLÉS", "PRECIO": "0"},
             {"CODIGO EMPRESA": "261004", "DESCRIPCION": "BUDÍN INGLES Nº 4", "PRECIO": "5502,61"}]
    salida = convertir({**mapeo(titulos), "familia_en_descripcion": True}, filas)
    assert [f["codigo_proveedor"] for f in salida] == ["271012", "261004"]
    assert salida[1]["descripcion_proveedor"].startswith("MOLDE PAN")


def test_notas_con_precio_y_codigos_sueltos_no_son_familias():
    """Clorosur: «C/U $2800» (nota del comercio en otra columna) y un 0 suelto en la columna del
    código no se pegan delante de la descripción de los productos que siguen."""
    titulos = {"codigo_proveedor": "Cod.", "descripcion_proveedor": "Descripcion", "costo": "Precio"}
    filas = [{"Cod.": "", "Descripcion": "", "Precio": "", "Notas": "PASTILLAS"},
             {"Cod.": "CL310", "Descripcion": "Balde x 10 Kg.", "Precio": "60", "Notas": ""},
             {"Cod.": "", "Descripcion": "", "Precio": "", "Notas": "C/U $2800"},
             {"Cod.": "CL307", "Descripcion": "Granel x 50 Kg.", "Precio": "5", "Notas": ""},
             {"Cod.": "0", "Descripcion": "", "Precio": "", "Notas": ""},
             {"Cod.": "PS110", "Descripcion": "Test-kit", "Precio": "6", "Notas": ""}]
    salida = convertir({**mapeo(titulos), "familia_en_descripcion": True}, filas)
    assert [f["descripcion_proveedor"] for f in salida] == [
        "PASTILLAS Balde x 10 Kg.", "PASTILLAS Granel x 50 Kg.", "PASTILLAS Test-kit"]


def test_lista_con_pesos_y_dolares_segun_el_formato_de_la_celda(tmp_path):
    """LTX: en la misma columna, «$ 214,2» (formato de pesos) y 0,74 (sin «$», dólares)."""
    import openpyxl
    from catalogo.convertir import filas_con_titulos, leer_tabla

    libro = openpyxl.Workbook()
    hoja = libro.active
    hoja.append(["Código", "Descripción", "Precio"])
    filas = [("510/CHA", "Caja de chapa 5x10", 214.2, '"$"\\ #.00'),
             ("67183A", "Bornera 12 polos", 0.74, "0.00"),
             ("X", "Timer", 4.9, '[$USD] 0.00')]
    filas += [(f"P{i}", f"Producto en pesos {i}", 1000.0 + i, '"$"#,##0.00') for i in range(12)]
    filas.append(("0266/MC", "Morsa de suspensión", 1.85, '"$"\\ #.00'))  # en dólares con formato de pesos
    for codigo, descripcion, precio, formato in filas:
        hoja.append([codigo, descripcion, precio])
        hoja.cell(hoja.max_row, 3).number_format = formato
    archivo = tmp_path / "ltx.xlsx"
    libro.save(archivo)
    tabla = leer_tabla(archivo.read_bytes(), "ltx.xlsx", monedas=True)
    assert tabla[1][2] == "$ 214,2" and tabla[2][2] == "0,74" and tabla[3][2] == "US$ 4,9"
    assert leer_tabla(archivo.read_bytes(), "ltx.xlsx")[1][2] == "214,2"  # sin pedirlo, como siempre
    titulos = {"codigo_proveedor": "Código", "descripcion_proveedor": "Descripción", "costo": "Precio"}
    salida = convertir(mapeo(titulos, moneda="mixta", cotizacion=1000), filas_con_titulos(tabla))
    caja, bornera, timer = salida[:3]
    assert caja["moneda_fila"] == "ars" and float(caja["costo"]) == pytest.approx(214.2)
    assert bornera["moneda_fila"] == "usd" and float(bornera["costo"]) == pytest.approx(740)
    assert timer["moneda_fila"] == "usd" and float(timer["costo"]) == pytest.approx(4900)
    assert "¿precio en dólares?" in salida[-1]["precio_dudoso"]
    assert not any("precio_dudoso" in f for f in salida[:-1])


def test_secciones_de_ltx_titulos_largos_y_notas_de_embalaje():
    """LTX: «PVC - CAÑOS - …» (más de 30 letras en la columna del código) es una familia; «100
    unidades por caja», «Velita 100 unidades…» y «CODIGO» solos no lo son."""
    titulos = {"codigo_proveedor": "CÓDIGO", "descripcion_proveedor": "DESCRIPCIÓN", "costo": "PRECIO"}
    filas = [{"CÓDIGO": "LÁMPARAS LED", "DESCRIPCIÓN": "", "PRECIO": ""},
             {"CÓDIGO": "100 unidades por caja", "DESCRIPCIÓN": "", "PRECIO": ""},
             {"CÓDIGO": "LTX-BLB7", "DESCRIPCIÓN": "Lámpara Bulb 7w", "PRECIO": "1"},
             {"CÓDIGO": "Velita 100 unidades por caja / Gota 100 unidades por caja", "DESCRIPCIÓN": "",
              "PRECIO": ""},
             {"CÓDIGO": "LTX-VEL5", "DESCRIPCIÓN": "Lámpara velita 5w", "PRECIO": "1"},
             {"CÓDIGO": "PVC - CAÑOS - ACCESORIOS - CAJAS DERIV-CAJAS P/TM IP65", "DESCRIPCIÓN": "",
              "PRECIO": ""},
             {"CÓDIGO": "CODIGO", "DESCRIPCIÓN": "", "PRECIO": ""},
             {"CÓDIGO": "WT04004", "DESCRIPCIÓN": "Caño rígido 3/4", "PRECIO": "2"}]
    salida = convertir({**mapeo(titulos), "familia_en_descripcion": True}, filas)
    assert [f["descripcion_proveedor"] for f in salida] == [
        "LÁMPARAS LED Lámpara Bulb 7w", "LÁMPARAS LED Lámpara velita 5w",
        "PVC - CAÑOS - ACCESORIOS - CAJAS DERIV-CAJAS P/TM IP65 Caño rígido 3/4"]


def test_nombre_armado_como_lumina_celdas_combinadas_parte_y_ficha_tecnica():
    """LUMINA: sin columna de descripción. Las celdas vacías valen lo de arriba (combinadas), sin
    familia el nombre empieza con la parte, la ficha técnica («Vida útil: …», varios renglones,
    una frase) no es nombre ni familia, y dos nombres iguales llevan el código."""
    titulos = {"codigo_proveedor": "SKU", "costo": "Precio s/IVA"}
    filas = [{"SKU": "3120", "Potencia": "6W", "Color": "3000K", "Base": "E27", "Precio s/IVA": "0,97"},
             {"SKU": "3120N", "Potencia": "", "Color": "4000K", "Base": "", "Precio s/IVA": "0,97"},
             {"SKU": "Vida útil: 15.000 horas", "Potencia": "", "Color": "", "Base": "", "Precio s/IVA": ""},
             {"SKU": "TEMPORIZADORES", "Potencia": "", "Color": "", "Base": "", "Precio s/IVA": ""},
             {"SKU": "Mecánicos y Digitales", "Potencia": "", "Color": "", "Base": "", "Precio s/IVA": ""},
             {"SKU": "Fácil programación y simple uso. Funcionamiento continuo.", "Potencia": "", "Color": "",
              "Base": "", "Precio s/IVA": ""},
             {"SKU": "1410", "Potencia": "Voltaje 230\nPotencia 40W", "Color": "", "Base": "",
              "Precio s/IVA": "6"},
             {"SKU": "1411", "Potencia": "Voltaje 230\nPotencia 40W", "Color": "", "Base": "",
              "Precio s/IVA": "7"}]
    salida = convertir({**mapeo(titulos), "parte": "Lámparas", "familia_en_descripcion": True}, filas)
    assert [(f["codigo_proveedor"], f["descripcion_proveedor"]) for f in salida] == [
        ("3120", "Lámparas 6W 3000K E27"), ("3120N", "Lámparas 6W 4000K E27"),
        ("1410", "TEMPORIZADORES Mecánicos y Digitales 1410"),
        ("1411", "TEMPORIZADORES Mecánicos y Digitales 1411")]


def test_la_columna_iva_tiene_que_traer_alicuotas_y_no_montos():
    """Epsilon y Mu: «IVA» es el precio con IVA de Daniel ($ 1.115), no la alícuota. LUMINA: entre
    «IVA» (0,105, del proveedor) e «iva» (montos, de Daniel) se elige la de las alícuotas."""
    titulos = ["Código", "Descripción", "Precio", "IVA"]
    filas = [dict(zip(titulos, [str(i), f"Caja {i}", "1844,16", "1115,71"], strict=True)) for i in range(8)]
    assert "iva" not in sugerir_mapeo(titulos, filas)
    titulos = ["SKU", "Precio s/IVA", "IVA", "iva"]
    filas = [dict(zip(titulos, [str(i), "0,97", "0,105", "1,07"], strict=True)) for i in range(8)]
    assert sugerir_mapeo(titulos, filas)["iva"] == "IVA"


def test_la_hoja_con_la_fecha_de_la_lista_se_encuentra_aunque_cambie(tmp_path):
    """Oeste le pone a la hoja la fecha («02_06_2026»); el mes siguiente es otra."""
    import openpyxl
    from catalogo.convertir import leer_tabla

    libro = openpyxl.Workbook()
    libro.active.title = "15_07_2026"
    libro.active.append(["Codigo", "Detalle", "Precio"])
    libro.create_sheet("BUSCADOR").append(["Buscar"])
    archivo = tmp_path / "Oeste.xlsx"
    libro.save(archivo)
    tabla = leer_tabla(archivo.read_bytes(), "Oeste.xlsx", "02_06_2026")
    assert tabla[0] == ["Codigo", "Detalle", "Precio"]
    with pytest.raises(ValueError, match="no tiene la hoja"):
        leer_tabla(archivo.read_bytes(), "Oeste.xlsx", "PRECIOS")


def test_precio_por_el_envase_de_la_descripcion_como_power():
    """«ABRAZADERA 12MM 100u» a $ 54.324: la caja de 100 ($ 543 cada una), solo con la opción."""
    from catalogo.plan import NUEVO, Foto, planificar

    titulos = {"codigo_proveedor": "SINONIMO", "descripcion_proveedor": "DESCRIPCION", "costo": "PRECIOS"}
    filas = [{"SINONIMO": "NA8009", "DESCRIPCION": "ABRAZADERA 12MM 12-22MM 100u", "PRECIOS": "54324"},
             {"SINONIMO": "O710", "DESCRIPCION": "ABRAZADERAS SET x 6", "PRECIOS": "1825"}]
    sin = convertir(mapeo(titulos), filas)
    assert [f["unidad"] for f in sin] == ["u", "u"]  # sin la opción, como siempre
    con = convertir({**mapeo(titulos), "envase_en_descripcion": True}, filas)
    assert [f["unidad"] for f in con] == ["100 u.", "u"]  # «SET x 6» no termina en «u»
    accion = planificar(con[:1], Foto([], [], {"P"}, {"Todos"}, hoy="2026-11-02", socios={1: "P"}))[0]
    assert accion.tipo == NUEVO and "precio por caja de 100" in " ".join(accion.avisos)


# --- Moneda sugerida al importar (06/11) -------------------------------------------------------
from catalogo.convertir import sugerir_moneda  # noqa: E402


def _tabla(precios, titulo="Precio", arriba=""):
    return [[arriba, ""], ["Código", titulo]] + [[str(i), p] for i, p in enumerate(precios)]


def test_moneda_por_formato_de_celda():
    assert sugerir_moneda(_tabla(["US$ 10"] * 9 + ["$ 5"]), 2, "Precio") == "usd"
    assert sugerir_moneda(_tabla(["$ 10"] * 10), 2, "Precio") == "ars"
    assert sugerir_moneda(_tabla(["$ 10"] * 5 + ["US$ 3"] * 5), 2, "Precio") == "mixta"


def test_moneda_por_titulo_o_texto_de_arriba():
    assert sugerir_moneda(_tabla(["10"] * 10, titulo="Precio U$S"), 2, "Precio U$S") == "usd"
    assert sugerir_moneda(_tabla(["10"] * 3, arriba="Lista en dólares"), 2, "Precio") == "usd"
    assert sugerir_moneda(_tabla(["10"] * 10), 2, "Precio") is None  # sin pistas: no se adivina


def test_ofertas_de_Omega_neto_y_porcentaje():
    # 20/11: la columna «Netos -10% pago» de Omega, al centavo
    from catalogo.costo import costo_desde_lista, leer_promocion, normalizar_ajustes

    assert leer_promocion("NETO $ 6900")["neto"] == 6900
    assert leer_promocion("OFERTA: 15%")["unidad"] == [15.0]
    ajustes = normalizar_ajustes({"descuentos": "28+10", "descuentos_neto": "10"})
    assert round(costo_desde_lista(23989, ajustes, promocion="NETO $ 6900")[0], 2) == 6210.0
    assert round(costo_desde_lista(12971, ajustes, promocion="OFERTA: 15%")[0], 2) == 7144.43
    assert round(costo_desde_lista(6470, ajustes)[0], 2) == 4192.56
    # Sin «descuentos sobre netos», el neto es el costo
    sin_neto = normalizar_ajustes({"descuentos": "28+10"})
    assert costo_desde_lista(23989, sin_neto, promocion="NETO $ 6900")[0] == 6900
