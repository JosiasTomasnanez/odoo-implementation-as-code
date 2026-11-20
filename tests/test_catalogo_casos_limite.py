"""Casos límite encontrados en las pruebas adversariales (08/10) del motor del catálogo."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parents[1] / "addons" / "comercio_catalogo"))
from catalogo.convertir import _texto, leer_tabla, redetectar  # noqa: E402
from catalogo.plan import (  # noqa: E402
    ACTUALIZAR,
    BAJA,
    NUEVO,
    POSIBLE_DUPLICADO,
    REVISAR,
    SIN_CAMBIOS,
    Foto,
    _numero,
    planificar,
)
from catalogo.similitud import Buscador  # noqa: E402


def prov(id_, tmpl, codigo, nombre="X", partner="P", partner_id=1, precio=100.0):
    return {"id": id_, "partner": partner, "partner_id": partner_id, "tmpl": tmpl, "product_code": codigo,
            "product_name": nombre, "price": precio, "min_qty": 0.0, "delay": 0, "date_start": None}


def foto(productos=(), proveedores=(), socios=None):
    return Foto(list(productos), list(proveedores), {"P"}, {"Todos"}, hoy="2026-10-08",
                socios=socios if socios is not None else {1: "P"})


def fila(**v):
    return {"proveedor": "P", "codigo_proveedor": "A1", "descripcion_proveedor": "Algo", "unidad": "u",
            "costo": "100", **v}


PRODUCTOS = [{"id": t, "barcode": False, "default_code": str(t), "name": f"Producto {t}"}
             for t in range(1, 6)]
PRECIOS = [prov(10 + t, t, f"A{t}", f"Producto {t}") for t in range(1, 6)]


def test_fila_a_revisar_de_un_producto_existente_no_genera_baja():
    filas = [fila(codigo_proveedor=f"A{t}", descripcion_proveedor=f"Producto {t}") for t in range(1, 6)]
    filas[0]["unidad"] = "galón"  # unidad desconocida → revisar
    acciones = planificar(filas, foto(PRODUCTOS, PRECIOS), lista_completa_de=1)
    assert [a.tipo for a in acciones].count(REVISAR) == 1
    assert not [a for a in acciones if a.tipo == BAJA]


def test_lista_casi_vacia_no_da_de_baja_todo():
    acciones = planificar([fila(codigo_proveedor="A1", descripcion_proveedor="Producto 1")],
                          foto(PRODUCTOS, PRECIOS), lista_completa_de=1)
    assert not [a for a in acciones if a.tipo == BAJA]
    assert any(a.tipo == REVISAR and "no se calculan bajas" in a.detalle for a in acciones)


def test_proveedor_por_id_con_homonimos():
    socios = {1: "P", 2: "P"}  # dos contactos con el mismo nombre
    precios = [prov(11, 1, "A1", partner_id=2)]
    # Por nombre es ambiguo: a revisar
    assert planificar([fila()], foto(PRODUCTOS, precios, socios))[0].tipo == REVISAR
    # Con el id (lo pone el módulo) se reconoce al correcto
    a = planificar([fila(proveedor_id=2, descripcion_proveedor="X")], foto(PRODUCTOS, precios, socios))[0]
    assert a.tipo == SIN_CAMBIOS
    a = planificar([fila(proveedor_id=1, descripcion_proveedor="Zzz")], foto(PRODUCTOS, precios, socios))[0]
    assert a.tipo == NUEVO and a.proveedor["partner_id"] == 1


def test_fila_sin_codigos_se_reconoce_por_la_descripcion_exacta():
    precios = [prov(11, 1, False, "Tornillo suelto x kg")]
    a = planificar([fila(codigo_proveedor="", descripcion_proveedor="TORNILLO  suelto x kg")],
                   foto(PRODUCTOS, precios))[0]
    assert a.tmpl == 1 and a.tipo != NUEVO  # reconocido (actualiza el texto de la descripción)


def test_costo_vacio_va_a_revisar():
    assert planificar([fila(costo="")], foto())[0].tipo == REVISAR


def test_numeros_de_excel_y_formatos():
    assert _numero(_texto(0.125)) == 0.125
    assert _numero(_texto(1234.5)) == 1234.5
    assert _numero(_texto(1300.0)) == 1300
    assert _numero("1,234.56") == 1234.56
    assert _numero("1\xa0234,56") == 1234.56
    assert _numero("1.300") == 1300 and _numero("1,5") == 1.5


def test_referencia_numerica_larga_no_rompe_la_numeracion():
    productos = [{"id": 1, "barcode": False, "default_code": "7790000001017", "name": "Otro"}]
    a = planificar([fila(descripcion_proveedor="Zzz nuevo")], foto(productos))[0]
    assert a.tipo == NUEVO and a.producto["default_code"] == "1"


def test_lo_que_se_vende_por_kilo_es_pesable():
    a = planificar([fila(unidad="kg", descripcion_proveedor="Alimento suelto")], foto())[0]
    assert a.producto["to_weight"] is True
    a = planificar([fila(unidad="kg", pesable="no", descripcion_proveedor="Alambre")], foto())[0]
    assert a.producto["to_weight"] is False


def test_preseleccion_no_pierde_la_coincidencia_exacta():
    b = Buscador()
    for i in range(100):
        b.agregar(i, f"ROYAL CANIN MEDIUM ADULT 15KG SABOR {i}")
    b.agregar("exacto", "ROYAL CANIN MEDIUM ADULT 15KG")
    candidatos = b.candidatos("ROYAL CANIN MEDIUM ADULT 15KG", excluir=set(range(100)))
    assert candidatos and candidatos[0].id == "exacto" and candidatos[0].puntaje == 1.0
    assert b.candidatos("ROYAL CANIN MEDIUM ADULT 15KG")[0].id == "exacto"


def test_csv_de_excel_windows_y_separador_con_titulo():
    texto = "Lista de precios, octubre\nCódigo;Descripción;Precio\nA1;Alimento perro;100\n"
    contenido = texto.encode("cp1252")
    tabla = leer_tabla(contenido, "lista.csv")
    assert tabla[1] == ["Código", "Descripción", "Precio"] and tabla[2][1] == "Alimento perro"


def test_duplicado_de_otro_proveedor_sigue_detectandose():
    productos = [{"id": 1, "barcode": False, "default_code": "1", "name": "Alimento Perro Adulto 15 Kg"}]
    nueva = fila(proveedor_id=1, codigo_proveedor="Z9", descripcion_proveedor="ALIM PERRO ADULTO X 15KG")
    a = planificar([nueva], foto(productos))[0]
    assert a.tipo == POSIBLE_DUPLICADO


def test_proveedor_que_cambia_el_codigo_es_posible_duplicado_y_no_baja():
    # El proveedor tenía la cinta como X1; la lista nueva la trae como V-03
    cinta = {"id": 1, "barcode": False, "default_code": "1", "name": "Cinta métrica 5 m"}
    productos = [cinta] + PRODUCTOS[1:]
    precios = [prov(11, 1, "X1", "CINTA METRICA 5 MTS")] + PRECIOS[1:]
    filas = [fila(codigo_proveedor="V-03", descripcion_proveedor="CINTA METRICA 5 MTS")] + [
        fila(codigo_proveedor=f"A{t}", descripcion_proveedor=f"Producto {t}") for t in range(2, 6)]
    acciones = planificar(filas, foto(productos, precios), lista_completa_de=1)
    cinta = acciones[0]
    assert cinta.tipo == POSIBLE_DUPLICADO and cinta.candidatos[0].id == 1
    assert any("cambió el código" in a for a in cinta.avisos)
    # «Es el mismo»: se actualiza el código y no hay baja
    filas[0]["vincular_a"] = "1"
    acciones = planificar(filas, foto(productos, precios), lista_completa_de=1)
    assert acciones[0].tipo == ACTUALIZAR and acciones[0].proveedor["product_code"] == "V-03"
    assert not [a for a in acciones if a.tipo == BAJA]


def test_redetectar_formato_nuevo_del_proveedor():
    """Otros títulos y más filas arriba: se encuentran la fila de títulos y las columnas."""
    tabla = [["DISTRIBUIDORA"], ["Lista octubre"], [],
             ["Código", "Detalle", "Precio neto"], ["Z1", "X", "10"]]
    assert redetectar(tabla) == (4, {"codigo_proveedor": "Código", "descripcion_proveedor": "Detalle",
                                     "costo": "Precio neto"})


def test_redetectar_sin_costo_no_adivina():
    """Si no aparece una columna de costo reconocible, no se inventa: lo resuelve una persona."""
    assert redetectar([["Código", "Detalle", "Observaciones"], ["Z1", "X", "y"]]) is None


# --- Listas reales del 19/10 (FC, Gas del Sur): .xls, títulos repetidos y descripción partida
XLS = Path(__file__).parent / "datos" / "lista_ficticia.xls"


def _lista_xls():
    from catalogo.convertir import convertir, encontrar_encabezado, filas_con_titulos

    tabla = leer_tabla(XLS.read_bytes(), XLS.name)
    fila = encontrar_encabezado(tabla)
    mapeo = {"proveedor": "P", "columnas": {"codigo_proveedor": "Código",
                                            "descripcion_proveedor": "Detalle + Descripción del producto",
                                            "costo": "NETO", "cantidad_minima": "Min."}}
    return fila, convertir(mapeo, filas_con_titulos(tabla, fila))


def test_xls_se_lee_sin_convertir():
    tabla = leer_tabla(XLS.read_bytes(), "LISTA.XLS")
    assert tabla[0][0].startswith("[EJ] Distribuidora Ficticia")
    assert leer_tabla(XLS.read_bytes(), XLS.name, "OTRA")[0][0] == "x"
    assert leer_tabla(XLS.read_bytes(), XLS.name, "1")[0][0] == "x"


def test_xls_dañado_da_error_claro():
    import pytest

    with pytest.raises(ValueError, match=r"\.xls válido"):
        leer_tabla(b"esto no es un excel", "lista.xls")


def test_titulos_repetidos_no_se_pisan():
    from catalogo.convertir import titulos_unicos

    assert titulos_unicos(["NETO", "", "NETO", "", "Min."]) == ["NETO", "", "NETO (2)", "", "Min."]
    fila, filas = _lista_xls()
    assert fila == 3
    assert filas[0]["costo"] == "608,57"  # el primer NETO, no el último


def test_descripcion_partida_y_titulos_de_familia():
    _fila, filas = _lista_xls()
    # Las filas «ABRAZADERA» y «ELECTRICIDAD» (sin código ni precio) no son productos
    assert [f["codigo_proveedor"] for f in filas] == ["90001", "90002", "A-7"]
    assert filas[0]["descripcion_proveedor"] == "ABRAZADERA 10-20 MM"
    assert filas[2]["descripcion_proveedor"] == "LAMPARA LED 7 W LUZ DIA"
    assert filas[2]["cantidad_minima"] == "10"


def test_columna_combinada_que_falta_avisa_cambio_de_formato():
    import pytest
    from catalogo.convertir import FormatoCambiado, convertir

    with pytest.raises(FormatoCambiado):
        convertir({"proveedor": "P", "columnas": {"descripcion_proveedor": "Detalle + No existe"}},
                  [{"Detalle": "x"}])


def test_dos_listas_del_mismo_proveedor_no_se_dan_de_baja_entre_si():
    """FC manda la lista general y los bulones en otra hoja: una «lista» por hoja."""
    precios = [{**prov(10 + t, t, f"A{t}"), "lista_id": 1 if t <= 3 else 2} for t in range(1, 6)]
    precios.append(prov(20, 4, "SIN"))  # cargado a mano: sin lista anotada
    f = foto(PRODUCTOS, precios)
    filas = [fila(codigo_proveedor="A1", descripcion_proveedor="Producto 1"),
             fila(codigo_proveedor="A2", descripcion_proveedor="Producto 2")]
    bajas = [a for a in planificar(filas, f, lista_completa_de=1, lista_id=1, otras_listas=True)
             if a.tipo == BAJA]
    assert [a.proveedor_id for a in bajas] == [13]  # solo A3, de la lista 1
    # Con una sola lista, lo cargado sin lista también es de ella
    bajas = [a for a in planificar(filas, f, lista_completa_de=1, lista_id=1) if a.tipo == BAJA]
    assert sorted(a.proveedor_id for a in bajas) == [13, 20]


def test_unidades_como_las_escriben_las_listas():
    from catalogo.plan import normalizar_unidad

    assert [normalizar_unidad(u) for u in ("UN.", "KG.", "Kg", "PAQ.", "CAJA", "Mts", "LTS", "", None)] == \
        ["u", "kg", "kg", "u", "u", "m", "l", "u", "u"]
    assert normalizar_unidad("Caño") == "u"
    assert normalizar_unidad("100 U.") == "100 u"  # los envases los resuelve envase() en el plan


def test_precio_por_caja_se_guarda_por_unidad():
    """Gas del Sur (19/10): «24 u.», «100 U.», «12 par» = precio de la caja (100 regatones a
    $ 8505,77). Se guarda por unidad con la caja como compra mínima (media caja si «Min.» 0,5)."""
    from catalogo.plan import envase

    unidades = ("24 u.", "100 U.", "12 par", "12 UN", "UN.", "1 u", "")
    assert [envase(u) for u in unidades] == [24, 100, 12, 12, 1, 1, 1]
    acciones = planificar([fila(codigo_proveedor="R1", descripcion_proveedor="REGATON 20 x 20",
                                costo="8505,77", cantidad_minima="0,5", unidad="100 U."),
                           fila(codigo_proveedor="E1", descripcion_proveedor="ESCUADRA 64", costo="5635,58",
                                unidad="24 u.")], foto([], []))
    regaton, escuadra = acciones
    assert regaton.tipo == escuadra.tipo == NUEVO, acciones
    assert (regaton.proveedor["price"], regaton.proveedor["min_qty"]) == (85.0577, 50)
    assert (escuadra.proveedor["price"], escuadra.proveedor["min_qty"]) == (round(5635.58 / 24, 4), 24)
    assert any("caja de 100" in a for a in regaton.avisos)


def test_aplicar_en_tandas_no_confunde_medidas_de_la_misma_lista():
    """Bulones FC (19/10): al aplicar en tandas, el M20x120 se tomaba por el M20x100 ya
    creado en la tanda anterior («¿cambió el código?»), aunque el M20x100 sigue en la lista."""
    lista = [fila(codigo_proveedor=f"B{i}", descripcion_proveedor=f"BULON HEX MILIM M20 x {m}")
             for i, m in enumerate((100, 110, 120))]
    ya = [{"id": 1, "barcode": False, "default_code": "1", "name": "BULON HEX MILIM M20 x 100"}]
    f = foto(ya, [prov(10, 1, "B0", "BULON HEX MILIM M20 x 100")])
    solo_tanda = planificar(lista[2:], f)
    assert solo_tanda[0].tipo == POSIBLE_DUPLICADO  # sin la lista entera: falso duplicado
    con_lista = planificar(lista[2:], f, lista_entera=lista)
    assert con_lista[0].tipo == NUEVO


def test_lo_de_otra_parte_del_proveedor_no_es_posible_duplicado():
    """FC general: «BUJE 1/2 x 3/4» se ofrecía como «¿cambió el código?» de un tornillo de la
    lista de bulones del mismo proveedor."""
    ya = [{"id": 1, "barcode": False, "default_code": "1", "name": "BULON HEX MILIM M20 x 100"}]
    f = foto(ya, [{**prov(10, 1, "B0", "BULON HEX MILIM M20 x 100"), "lista_id": 2}])
    filas = [fila(codigo_proveedor="G1", descripcion_proveedor="BULON HEX MILIM M20 x 120")]
    assert planificar(filas, f, lista_id=2)[0].tipo == POSIBLE_DUPLICADO  # misma parte: se pregunta
    assert planificar(filas, f, lista_id=1, otras_listas=True)[0].tipo == NUEVO


def test_terminos_de_busqueda():
    from catalogo.busqueda import normalizar, terminos

    def encuentra(consulta, *textos):
        texto = normalizar(*textos)
        return all(p in texto for p in terminos(consulta))

    assert terminos("Tornillo FIX 4x40") == [" tornillo", " fix", " 4 ", " 40 "]
    assert normalizar("TORNILLO fix  2,5 x 10 X 400 un", "10269") == " tornillo fix 2.5 x 10 x 400 un 10269 "
    assert encuentra("fix 4x40", "TORNILLO FIX 4 X 40")
    assert not encuentra("fix 4x40", "TORNILLO fix  2,5 x 10      X 400 un")  # 4 y 40 no son 400
    assert encuentra("cadena galv 40", "CADENA DERECHA Nº 40 GALVANIZADA")
    assert encuentra("cinta métrica", "CINTA METRICA BELLOTA 5 MTS")
    assert encuentra("tornillo 2,5", "TORNILLO fix  2.5 x 12")
    assert encuentra("72541", "TANZA GRASSFIO", "72541")
    assert terminos("") == []


# P-053: tornillo vendido por kg; el proveedor lo vende en «Caja 1000 = 2,5 kg» (uom 31)
UNIDADES_KG = {1: {"nombre": "Unidades", "familia": "u"}, 16: {"nombre": "kg", "familia": "kg"},
               31: {"nombre": "Caja 1000 tornillos", "familia": "kg"}}
TORNILLO = [{"id": 1, "barcode": False, "default_code": "1", "name": "Tornillo 6x1", "familia": "kg"}]


def foto_kg(precios):
    f = foto(TORNILLO, precios)
    f.unidades = UNIDADES_KG
    return f


def test_precio_con_unidad_de_compra_se_guarda_tal_cual():
    """Precio del proveedor en su caja: la lista trae el de la caja y no se divide; el precio
    nuevo (historial) conserva la caja."""
    caja = {**prov(10, 1, "T1", "TORNILLO 6x1", precio=25000.0), "uom_id": 31, "unidad_propia": True}
    acciones = planificar([fila(codigo_proveedor="T1", descripcion_proveedor="TORNILLO 6x1",
                                costo="26000", unidad="1000 u")], foto_kg([caja]))
    (a,) = acciones
    assert a.tipo == ACTUALIZAR and a.historial, a
    assert (a.proveedor["price"], a.proveedor["uom_id"]) == (26000.0, 31)
    assert abs(a.variacion - 0.04) < 1e-9 and not a.cambia_unidad
    assert any("Caja 1000 tornillos" in t for t in a.avisos)


def test_unidad_de_la_lista_distinta_del_producto_va_a_revisar():
    """Producto en kg, lista por unidad o por caja de unidades, sin unidad de compra: antes se
    guardaba el precio como por kg; ahora la fila va a revisar, con el producto."""
    en_kg = {**prov(10, 1, "T1", "TORNILLO 6x1"), "uom_id": 16, "unidad_propia": False}
    for unidad in ("1000 u", "u"):
        (a,) = planificar([fila(codigo_proveedor="T1", descripcion_proveedor="TORNILLO 6x1",
                                unidad=unidad)], foto_kg([en_kg]))
        assert a.tipo == REVISAR and a.tmpl == 1 and "se vende por kg" in a.detalle, a
    (a,) = planificar([fila(codigo_proveedor="T1", descripcion_proveedor="TORNILLO 6x1", unidad="kg")],
                      foto_kg([en_kg]))
    assert a.tipo != REVISAR, a


def test_unidad_de_compra_elegida_en_la_fila():
    en_kg = {**prov(10, 1, "T1", "TORNILLO 6x1", precio=25.0), "uom_id": 16, "unidad_propia": False}
    (a,) = planificar([fila(codigo_proveedor="T1", descripcion_proveedor="TORNILLO 6x1", costo="25000",
                            unidad="1000 u", unidad_compra=31)], foto_kg([en_kg]))
    assert a.tipo == ACTUALIZAR and a.cambia_unidad and a.proveedor["uom_id"] == 31, a
    assert a.proveedor["price"] == 25000.0
    from catalogo.plan import es_automatico
    assert not es_automatico(a, 10)  # cambiar la unidad lo mira una persona
    (b,) = planificar([fila(codigo_proveedor="T1", descripcion_proveedor="TORNILLO 6x1",
                            unidad_compra=1)], foto_kg([en_kg]))  # unidades: no convierte a kg
    assert b.tipo == REVISAR and b.tmpl == 1, b


def test_producto_por_unidad_sigue_dividiendo_la_caja():
    por_u = [{**TORNILLO[0], "familia": "u"}]
    f = foto(por_u, [{**prov(10, 1, "T1", "TORNILLO 6x1"), "uom_id": 1, "unidad_propia": False}])
    f.unidades = UNIDADES_KG
    (a,) = planificar([fila(codigo_proveedor="T1", descripcion_proveedor="TORNILLO 6x1", costo="25000",
                            unidad="1000 u")], f)
    assert a.tipo == ACTUALIZAR and a.proveedor["price"] == 25.0 and "uom_id" not in a.proveedor, a


def test_hojas_del_excel_con_filas_con_datos():
    """FC manda General y Bulones en el mismo archivo: se ofrecen las hojas con productos."""
    import io

    import openpyxl
    from catalogo.convertir import hojas

    libro = openpyxl.Workbook()
    general = libro.active
    general.title = "General"
    general.append(["LISTA DE PRECIOS"])  # título: no cuenta
    for i in range(6):
        general.append([f"G{i}", f"Producto {i}", 100])
    libro.create_sheet("Bulones").append(["B1", "Bulón", 50])
    libro.create_sheet("Notas").append(["Precios sin IVA"])
    salida = io.BytesIO()
    libro.save(salida)
    assert hojas(salida.getvalue(), "lista.xlsx") == [("General", 6), ("Bulones", 1), ("Notas", 0)]
    assert hojas(b"a;b\n1;2", "lista.csv") == []


def test_archivo_de_otra_parte_no_da_de_baja_la_lista():
    """Se sube el Excel de bulones en la lista general del mismo proveedor: casi nada coincide
    → no se cierran los precios de la general; se avisa que puede ser otra parte."""
    otros = [fila(codigo_proveedor=f"Z{t}", descripcion_proveedor=f"Bulón {t}") for t in range(1, 7)]
    acciones = planificar(otros, foto(PRODUCTOS, PRECIOS), lista_completa_de=1)
    assert not [a for a in acciones if a.tipo == BAJA], acciones
    assert any(a.tipo == REVISAR and "otra parte" in a.detalle for a in acciones)
    # La misma lista con un producto menos: la baja sigue calculándose
    misma = [fila(codigo_proveedor=f"A{t}", descripcion_proveedor=f"Producto {t}") for t in range(1, 5)]
    assert [a.tmpl for a in planificar(misma, foto(PRODUCTOS, PRECIOS), lista_completa_de=1)
            if a.tipo == BAJA] == [5]
