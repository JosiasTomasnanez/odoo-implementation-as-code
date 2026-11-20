"""Protocolo de la Systel Cuora (integrations/balanza_systel/diagnostico.py), sin balanza."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parents[1] / "integrations" / "balanza_systel"))
from diagnostico import armar_pedido, consultar, interpretar_peso, separar_respuesta  # noqa: E402


def respuesta(numero: int, funcion: int, datos: str) -> bytes:
    return armar_pedido(numero, funcion, datos)  # misma estructura que el pedido


def test_pedido_de_peso_es_numero_funcion_xor():
    assert armar_pedido(1, 1) == bytes([1, 1, 0])
    assert armar_pedido(20, 1) == bytes([20, 1, 21])


def test_interpreta_peso_estable_inestable_negativo_y_error():
    assert interpretar_peso("001250e000150") == {"gramos": 1250, "estable": True, "tara_gramos": 150}
    assert interpretar_peso("000080i000000")["estable"] is False
    assert interpretar_peso("-00250e000000")["gramos"] == -250
    assert interpretar_peso("E4") == {"error": "E4"}
    assert interpretar_peso("basura") is None


def test_separa_trama_valida_entre_restos_y_rechaza_xor_incorrecto():
    buena = respuesta(1, 1, "001250e000000")
    assert separar_respuesta(b"\x07\x01" + buena, 1, 1) == "001250e000000"
    mala = buena[:-1] + bytes([buena[-1] ^ 0xFF])
    assert separar_respuesta(mala, 1, 1) is None
    assert separar_respuesta(buena, 2, 1) is None  # otra balanza


class PuertoFalso:
    """Cuora simulada: contesta la función 1 con un peso fijo."""

    def __init__(self, numero=1, datos="000800e000000"):
        self.numero, self.datos, self.pendiente = numero, datos, b""

    def reset_input_buffer(self):
        self.pendiente = b""

    def write(self, trama):
        if trama == armar_pedido(self.numero, 1):
            self.pendiente = respuesta(self.numero, 1, self.datos)

    def read(self, n):
        leido, self.pendiente = self.pendiente[:n], self.pendiente[n:]
        return leido


def test_consultar_con_balanza_simulada():
    assert consultar(PuertoFalso(), 1, 1) == "000800e000000"
    assert consultar(PuertoFalso(numero=5), 1, 1, espera=0.05) is None
