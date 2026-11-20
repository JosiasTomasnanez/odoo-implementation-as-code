"""Verificación con IA (ADR 0018): pedido, validación de la respuesta, reintentos y respaldo.

Sin red: la llamada a Gemini se reemplaza por funciones de prueba."""
import io
import json
import sys
import urllib.error
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parents[1] / "addons" / "comercio_catalogo_ia"))
from ia import verificar as ia  # noqa: E402

FILAS = [
    {"fila": 1, "descripcion": "TORNILLO FIX 4 X 40", "codigo": "10269", "unidad": "u",
     "candidatos": [{"id": 50, "nombre": "Tornillo Fix 4x40mm", "otras_descripciones": ["FIX 4X40"]},
                    {"id": 51, "nombre": "Tornillo Fix 4x50mm"}]},
    {"fila": 2, "descripcion": "CADENA Nº 40", "codigo": "763", "unidad": "m",
     "candidatos": [{"id": 60, "nombre": "Cadena galvanizada 4 mm"}]},
]


DESCRIPCION = {1: "TORNILLO FIX 4 X 40", 2: "CADENA Nº 40"}


def con_eco(filas: list[dict]) -> list[dict]:
    """La IA repite la descripción de cada fila (control contra filas mezcladas)."""
    return [{"descripcion": DESCRIPCION.get(f["fila"], "TORNILLO FIX 4 X 40"), **f} for f in filas]


def respuesta(filas: list[dict], modelo="gemini-prueba", tokens=100) -> dict:
    filas = con_eco(filas)
    return {"candidates": [{"content": {"parts": [{"text": json.dumps({"filas": filas})}]}}],
            "usageMetadata": {"totalTokenCount": tokens}, "modelVersion": modelo}


def http(codigo: int, mensaje: str = "This model is experiencing high demand") -> urllib.error.HTTPError:
    cuerpo = io.BytesIO(json.dumps({"error": {"message": mensaje}}).encode())
    return urllib.error.HTTPError("https://x", codigo, "error", {}, cuerpo)


def test_pedido_solo_lleva_descripciones_y_candidatos():
    texto = ia.armar_pedido(FILAS)
    datos = json.loads(texto.split("Filas:\n", 1)[1])
    assert datos[0]["lista_del_proveedor"] == {"descripcion": "TORNILLO FIX 4 X 40", "codigo": "10269",
                                               "unidad": "u"}
    assert [c["candidato_id"] for c in datos[0]["candidatos"]] == [50, 51]
    assert "costo" not in texto.lower().split("filas:")[1]  # ni costos ni datos del negocio


def test_valida_candidato_y_filas_faltantes():
    resultados = ia.validar({"filas": con_eco([
        {"fila": 1, "veredicto": "mismo", "candidato_id": 99, "confianza": 0.9, "motivo": "igual"},
        {"fila": 7, "veredicto": "mismo", "candidato_id": 50, "confianza": 1, "motivo": "no pedida"},
    ])}, FILAS)
    assert [(r.fila, r.veredicto, r.candidato_id) for r in resultados] == [
        (1, "dudoso", None), (2, "dudoso", None)]
    assert "no era candidato" in resultados[0].motivo and "no respondió" in resultados[1].motivo


def test_confianza_acotada_y_distinto_sin_candidato():
    r = ia.validar({"filas": con_eco([{"fila": 2, "veredicto": "distinto", "candidato_id": 60, "confianza": 7,
                                       "motivo": "otra medida"}])}, FILAS[1:])[0]
    assert (r.veredicto, r.candidato_id, r.confianza) == ("distinto", None, 1.0)


def test_alta_demanda_reintenta_y_pasa_al_respaldo():
    llamadas = []

    def llamar(texto, clave, modelo):
        llamadas.append(modelo)
        if modelo == "principal":
            raise http(503)
        return respuesta([{"fila": 1, "veredicto": "mismo", "candidato_id": 50, "confianza": 0.95,
                           "motivo": "ok"},
                          {"fila": 2, "veredicto": "distinto", "confianza": 0.9, "motivo": "no"}], "respaldo")

    resultados, consumo = ia.verificar(FILAS, "clave", ["principal", "respaldo"], llamar,
                                       esperar=lambda s: None)
    assert llamadas == ["principal"] * (ia.REINTENTOS + 1) + ["respaldo"]
    assert [(r.veredicto, r.candidato_id) for r in resultados] == [("mismo", 50), ("distinto", None)]
    assert (consumo.pedidos, consumo.tokens, consumo.modelo) == (1, 100, "respaldo")


def test_modelo_retirado_pasa_al_respaldo_sin_esperar():
    esperas = []

    def llamar(texto, clave, modelo):
        if modelo == "viejo":
            raise http(404)
        return respuesta([{"fila": 1, "veredicto": "dudoso", "confianza": 0.4, "motivo": "?"},
                          {"fila": 2, "veredicto": "dudoso", "confianza": 0.4, "motivo": "?"}])

    resultados, _ = ia.verificar(FILAS, "clave", ["viejo", "nuevo"], llamar, esperar=esperas.append)
    assert len(resultados) == 2 and not esperas


def test_sin_clave_o_error_de_autorizacion_avisa():
    with pytest.raises(ia.ErrorIA, match="GEMINI_API_KEY"):
        ia.verificar(FILAS, "", ["m"])

    def llamar(texto, clave, modelo):
        raise http(403)

    with pytest.raises(ia.ErrorIA, match="clave de la IA no es válida.*GEMINI_API_KEY"):
        ia.verificar(FILAS, "clave", ["m"], llamar, esperar=lambda s: None)


def test_errores_de_la_ia_en_castellano():
    """Lo que dice Google (en inglés) se traduce a qué pasó y qué hacer."""
    def con(error):  # un error nuevo por intento, como en la realidad
        def llamar(texto, clave, modelo):
            raise error()
        with pytest.raises(ia.ErrorIA) as capturado:
            ia.verificar(FILAS, "clave", ["m", "respaldo"], llamar, esperar=lambda s: None)
        return str(capturado.value)

    assert "uso gratuito" in con(lambda: http(429, "You exceeded your current quota, please check your plan"))
    assert "demasiados pedidos" in con(lambda: http(429))
    assert "GEMINI_API_KEY" in con(lambda: http(400, "API key not valid. Please pass a valid API key."))
    assert "GEMINI_MODEL" in con(lambda: http(404, "models/m is not found"))
    assert "Google" in con(lambda: http(503))
    assert "conexión" in con(lambda: urllib.error.URLError("sin red"))


def test_tandas():
    muchas = [{**FILAS[0], "fila": n} for n in range(ia.TANDA + 5)]
    pedidos = []

    def llamar(texto, clave, modelo):
        filas = json.loads(texto.split("Filas:\n", 1)[1])
        pedidos.append(len(filas))
        return respuesta([{"fila": f["fila"], "veredicto": "dudoso", "confianza": 0.5, "motivo": "-"}
                          for f in filas])

    resultados, consumo = ia.verificar(muchas, "clave", ["m"], llamar)
    assert sorted(pedidos) == [5, ia.TANDA] and len(resultados) == len(muchas) and consumo.pedidos == 2


def test_filas_mezcladas_quedan_dudosas():
    """La IA juzgó otra fila (vista con listas reales: 2,5 x 12 respondido como 3,5 x 12)."""
    r = ia.validar({"filas": [{"fila": 1, "descripcion": "CADENA Nº 40", "veredicto": "mismo",
                               "candidato_id": 50, "confianza": 0.9, "motivo": "igual"}]}, FILAS[:1])[0]
    assert (r.veredicto, r.candidato_id) == ("dudoso", None) and "otra fila" in r.motivo


def test_medidas_distintas_no_pueden_ser_el_mismo():
    filas = [{"fila": 1, "descripcion": "TORNILLO fix  2,5 x 12      X 400 un",
              "candidatos": [{"id": 70, "nombre": "TORNILLO FIX 3.5  X  12"}]}]
    r = ia.validar({"filas": [{"fila": 1, "descripcion": "TORNILLO fix  2,5 x 12      X 400 un",
                               "veredicto": "mismo", "candidato_id": 70, "confianza": 0.9,
                               "motivo": "coincide"}]}, filas)[0]
    assert (r.veredicto, r.candidato_id) == ("dudoso", None) and "medidas no coinciden" in r.motivo
    assert ia.medidas_compatibles("TORNILLO fix 3 x 20 X 250 un", "TORNILLO FIX 3  X  20")
    assert ia.numeros('BULON 1/4-20 UNC x 1.1/4 C/T') == {0.25, 20.0, 1.25}
    assert ia.numeros("TORNILLO fix  2,5 x 12") == {2.5, 12.0}


def test_filas_con_problemas_la_ia_sugiere_que_hacer():
    from ia import problemas

    filas = [{"fila": 1, "descripcion": "Candado acero 60 mm", "codigo": "EJ-2003",
              "problema": "la lista no trae precio", "texto_precio": "Consultar"},
             {"fila": 2, "descripcion": "Pinza 8", "codigo": "EJ-4002", "problema": "aparece dos veces"}]
    pedido = problemas.armar_pedido(filas)
    assert "Consultar" in pedido and "aparece dos veces" in pedido
    respuesta = {"filas": [
        {"fila": 1, "descripcion": "Candado acero 60 mm", "accion": "consultar_proveedor",
         "explicacion": "Pedile el precio."},
        {"fila": 2, "descripcion": "Otra cosa", "accion": "ignorar", "explicacion": "Repetida."},
        {"fila": 9, "descripcion": "x", "accion": "ignorar", "explicacion": "no pedida"}]}
    uno, dos = problemas.validar(respuesta, filas)
    assert uno.accion == problemas.CONSULTAR
    assert dos.accion == problemas.REVISAR  # respondió sobre otra descripción: no se le cree


def test_leer_con_plazo_se_corta_si_google_no_responde():
    # 20/11: con la IA saturada, un PDF que igual se podía leer del texto tardaba 5 minutos
    import time

    from ia import leer

    def colgada(*args, **kwargs):
        time.sleep(0.4)
        raise TimeoutError("se colgó")

    inicio = time.monotonic()
    with pytest.raises(ia.ErrorIA):
        leer.leer(b"foto", "lista.jpg", "clave", ["modelo-a", "modelo-b"], llamar=colgada,
                  esperar=lambda s: None, productos=True, plazo=1.5)
    assert time.monotonic() - inicio < 2.5  # sin plazo: 6 intentos de 0,4 s y más


def test_leer_productos_arma_titulos_fijos():
    from ia import leer

    def responde(partes, clave, modelo, esquema=None):
        texto = json.dumps({"productos": [{"codigo": "A9-10", "descripcion": "VIGUETAS T1 L = 1,00 m",
                                           "precio": "$ 3945"},
                                          {"codigo": "", "descripcion": "HOLCIM X 25 KG", "precio": "$6662"},
                                          {"codigo": "", "descripcion": "TANQUES", "precio": ""}]})
        return {"candidates": [{"content": {"parts": [{"text": texto}]}}]}

    tabla, _consumo, paginas = leer.leer(b"foto", "lista.jpg", "clave", ["m"], llamar=responde,
                                         esperar=lambda s: None, productos=True)
    assert tabla == [["Código", "Descripción", "Precio"], ["A9-10", "VIGUETAS T1 L = 1,00 m", "$ 3945"],
                     ["", "HOLCIM X 25 KG", "$6662"]] and paginas == 1
