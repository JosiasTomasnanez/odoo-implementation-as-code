"""Segunda opinión con IA (Gemini) sobre los «posibles duplicados» de una lista de proveedor.

Python puro, sin Odoo: arma el pedido, llama a la API y valida la respuesta. El módulo
guarda el resultado como **sugerencia**: nada se aplica sin que una persona lo confirme.

Qué se manda a Google (ADR 0018): solo descripciones y códigos de productos de las listas
de los proveedores y los nombres de nuestros productos candidatos. Nada de clientes,
ventas, costos ni datos del negocio.
"""
from __future__ import annotations

import json
import logging
import os
import re
import threading
import time
import unicodedata
import urllib.error
import urllib.request
from collections.abc import Callable
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass

_logger = logging.getLogger(__name__)

URL = "https://generativelanguage.googleapis.com/v1beta/models/{modelo}:generateContent"
TANDA = 20  # filas por pedido: menos pedidos (y tokens de instrucciones) que de a una
# Tandas en paralelo: cada pedido tarda ~25 s tenga 1 o 60 filas (medido 21/10), así que de a
# una 200 filas eran ~5 min; en paralelo, lo que tarda una sola
EN_PARALELO = 10
REINTENTOS = 2  # por modelo, ante «alta demanda» (429/503) o un corte de red
ESPERA_S = 3
TIEMPO_MAXIMO_S = 90  # fotos y PDF escaneados (varias páginas)
# Pedidos de texto (verificar, categorizar): responden en ~20 s aunque sea un producto (medido
# 26/10). A veces un intento se cuelga: con 90 s, un clic tardaba más de 2 minutos. Con 45 s se
# corta antes y se reintenta.
TIEMPO_TEXTO_S = 45
# Plan gratis de Gemini: 15 pedidos por minuto (06/11). Se queda en 14 por las dudas; con el plan pago,
# GEMINI_PEDIDOS_POR_MINUTO=0 (sin tope) o el número del plan, en el entorno del servidor.
PEDIDOS_POR_MINUTO_GRATIS = 14

MISMO, DISTINTO, DUDOSO = "mismo", "distinto", "dudoso"

INSTRUCCIONES = """Sos un asistente de un comercio argentino (ferretería, alimento para mascotas,
veterinaria, forrajería) que carga en su sistema las listas de precios de sus proveedores.
Para cada fila de la lista de un proveedor hay hasta 3 productos que YA tenemos y que se
parecen. Decidí si alguno es EXACTAMENTE el mismo artículo.

Es el mismo solo si coinciden: tipo de producto, marca (si alguna la dice), medidas, peso,
volumen o capacidad, y presentación (unidad suelta, caja, bolsa, pack de N). Las
diferencias de escritura no importan (mayúsculas, abreviaturas como «C/» = «con»,
«galv.» = «galvanizado», «x» entre medidas, unidades equivalentes 1000 g = 1 kg,
1/2" = media pulgada). Una medida, peso, cantidad por envase, color o variante distinta
lo hace OTRO producto. Si una descripción nombra un tipo, terminación o marca que la otra
no menciona o contradice (p. ej. «soldada» y «derecha», «con freno», «Giant», «galvanizado»
y «zincado»), no lo des por el mismo: usá «dudoso». Si coincide el artículo pero cambia el
envase (una dice «X 250 un» y la otra no), puede ser el mismo, pero aclaralo en el motivo.

veredicto: «mismo» (indicá cuál en candidato_id), «distinto» (ninguno es el mismo) o
«dudoso» (falta información para estar seguro). Ante la duda, «dudoso»: es preferible a
equivocarse. confianza entre 0 y 1. motivo: una frase corta en español rioplatense.
Respondé una entrada por cada fila, con su mismo número de fila, y copiá en «descripcion»
la descripción de esa fila tal cual (sirve para controlar que no se mezclen filas)."""

ESQUEMA = {
    "type": "OBJECT",
    "properties": {
        "filas": {
            "type": "ARRAY",
            "items": {
                "type": "OBJECT",
                "properties": {
                    "fila": {"type": "INTEGER"},
                    "descripcion": {"type": "STRING"},
                    "veredicto": {"type": "STRING", "enum": [MISMO, DISTINTO, DUDOSO]},
                    "candidato_id": {"type": "INTEGER", "nullable": True},
                    "confianza": {"type": "NUMBER"},
                    "motivo": {"type": "STRING"},
                },
                "required": ["fila", "descripcion", "veredicto", "confianza", "motivo"],
            },
        },
    },
    "required": ["filas"],
}


class ErrorIA(Exception):
    """La IA no respondió o respondió algo que no se pudo usar."""


@dataclass
class Resultado:
    fila: int
    veredicto: str
    candidato_id: int | None
    confianza: float
    motivo: str


@dataclass
class Consumo:
    pedidos: int = 0
    tokens: int = 0
    modelo: str = ""


def armar_pedido(filas: list[dict]) -> str:
    """`filas`: [{fila, descripcion, codigo, unidad, candidatos: [{id, nombre, otras_descripciones}]}]."""
    datos = [{
        "fila": f["fila"],
        "lista_del_proveedor": {"descripcion": f["descripcion"], "codigo": f.get("codigo") or "",
                                "unidad": f.get("unidad") or ""},
        "candidatos": [{"candidato_id": c["id"], "nombre": c["nombre"],
                        "como_lo_describen_otros_proveedores": c.get("otras_descripciones", [])[:3]}
                       for c in f["candidatos"][:3]],
    } for f in filas]
    return INSTRUCCIONES + "\n\nFilas:\n" + json.dumps(datos, ensure_ascii=False)


def _sin_acentos(texto: str) -> str:
    return "".join(c for c in unicodedata.normalize("NFKD", texto or "") if not unicodedata.combining(c))


def _clave(texto: str) -> str:
    return " ".join(re.sub(r"[^a-z0-9]+", " ", _sin_acentos(texto).lower()).split())


def numeros(texto: str) -> set[float]:
    """Medidas de una descripción: «3,5 x 12», «1/2"», «1.1/4» → {3.5, 12.0}, {0.5}, {1.25}."""
    texto = _sin_acentos(texto or "").lower()
    valores: set[float] = set()
    for entero, num, den in re.findall(r"(?:(\d+)[ .-])?(\d+)/(\d+)", texto):  # fracciones
        if int(den):
            valores.add(round((int(entero) if entero else 0) + int(num) / int(den), 4))
    texto = re.sub(r"(?:\d+[ .-])?\d+/\d+", " ", texto)
    for numero in re.findall(r"\d+(?:[.,]\d+)?", texto):
        valores.add(round(float(numero.replace(",", ".")), 4))
    return valores


def medidas_compatibles(fila: str, candidato: str) -> bool:
    """Toda medida del candidato tiene que estar en la fila (la fila puede traer además la
    cantidad por envase, p. ej. «X 250 un»). Si no, la IA probablemente se equivocó."""
    return numeros(candidato) <= numeros(fila)


def validar(respuesta: dict, filas: list[dict]) -> list[Resultado]:
    """Solo resultados de filas pedidas y con un candidato de esa fila; lo demás, «dudoso».

    Controles que no dependen de la IA: que repita la descripción de la fila que juzga (si
    no, mezcló filas) y que las medidas del candidato estén en la fila."""
    pedidas = {f["fila"]: {c["id"] for c in f["candidatos"]} for f in filas}
    descripcion = {f["fila"]: f["descripcion"] for f in filas}
    nombres = {(f["fila"], c["id"]): c["nombre"] for f in filas for c in f["candidatos"]}
    resultados: dict[int, Resultado] = {}
    for r in respuesta.get("filas", []):
        fila = r.get("fila")
        if fila not in pedidas or fila in resultados:
            continue
        veredicto = r.get("veredicto")
        candidato = r.get("candidato_id")
        confianza = max(0.0, min(1.0, float(r.get("confianza") or 0)))
        motivo = str(r.get("motivo") or "").strip()[:300]
        if veredicto == MISMO and candidato not in pedidas[fila]:
            motivo = f"La IA señaló un producto que no era candidato. {motivo}"
            veredicto, candidato = DUDOSO, None
        if veredicto not in (MISMO, DISTINTO, DUDOSO):
            veredicto = DUDOSO
        if _clave(r.get("descripcion", "")) != _clave(descripcion[fila]):
            veredicto, candidato = DUDOSO, None
            motivo = f"La IA respondió sobre otra fila («{str(r.get('descripcion'))[:60]}»): revisar a mano."
        elif veredicto == MISMO and not medidas_compatibles(descripcion[fila], nombres[(fila, candidato)]):
            nombre = nombres[(fila, candidato)]
            motivo = f"Las medidas no coinciden con «{nombre}»: revisar a mano. ({motivo})"
            veredicto, candidato = DUDOSO, None
        resultados[fila] = Resultado(fila, veredicto, candidato if veredicto == MISMO else None,
                                     confianza, motivo)
    for fila in pedidas:  # la IA se salteó una fila: no se inventa nada
        resultados.setdefault(fila, Resultado(fila, DUDOSO, None, 0.0, "La IA no respondió esta fila."))
    return [resultados[f["fila"]] for f in filas]


class Ritmo:
    """No pasar de N pedidos en cualquier minuto (ventana móvil), para todos los hilos del proceso.
    Los primeros N salen enseguida; el siguiente espera a que se libere un lugar."""

    def __init__(self, por_minuto: int, reloj: Callable[[], float] = time.monotonic,
                 esperar: Callable[[float], None] = time.sleep):
        self.por_minuto, self.reloj, self.esperar = por_minuto, reloj, esperar
        self._salidas: list[float] = []
        self._candado = threading.Lock()

    def turno(self) -> None:
        if self.por_minuto <= 0:
            return
        while True:
            with self._candado:
                ahora = self.reloj()
                self._salidas = [t for t in self._salidas if ahora - t < 60]
                if len(self._salidas) < self.por_minuto:
                    self._salidas.append(ahora)
                    return
                espera = 60 - (ahora - self._salidas[0]) + 0.05
            self.esperar(espera)


def pedidos_por_minuto() -> int:
    """GEMINI_PEDIDOS_POR_MINUTO del entorno (0 = sin tope); si no está, el del plan gratis."""
    try:
        return int(os.environ.get("GEMINI_PEDIDOS_POR_MINUTO", PEDIDOS_POR_MINUTO_GRATIS))
    except ValueError:
        return PEDIDOS_POR_MINUTO_GRATIS


RITMO = Ritmo(pedidos_por_minuto())


def llamar_gemini(texto: str | list[dict], clave: str, modelo: str, tiempo_maximo: float = TIEMPO_MAXIMO_S,
                  esquema: dict | None = None) -> dict:
    """Un pedido a la API de Gemini con respuesta JSON según el esquema (por defecto ESQUEMA).
    `texto` puede ser una lista de partes (texto, imágenes o PDF). Devuelve la respuesta cruda.
    Respeta el tope de pedidos por minuto (RITMO)."""
    RITMO.turno()
    partes = [{"text": texto}] if isinstance(texto, str) else texto
    cuerpo = {
        "contents": [{"parts": partes}],
        "generationConfig": {"responseMimeType": "application/json", "responseSchema": esquema or ESQUEMA,
                             "temperature": 0},
    }
    pedido = urllib.request.Request(
        URL.format(modelo=modelo), data=json.dumps(cuerpo).encode(),
        headers={"Content-Type": "application/json", "x-goog-api-key": clave}, method="POST")
    with urllib.request.urlopen(pedido, timeout=tiempo_maximo) as respuesta:  # noqa: S310 (URL fija)
        return json.loads(respuesta.read())


def llamar_gemini_texto(texto: str | list[dict], clave: str, modelo: str,
                        esquema: dict | None = None) -> dict:
    """Pedido de texto (sin fotos ni PDF): se corta antes si se cuelga (TIEMPO_TEXTO_S)."""
    return llamar_gemini(texto, clave, modelo, TIEMPO_TEXTO_S, esquema)


def _texto_de(respuesta: dict) -> dict:
    try:
        texto = respuesta["candidates"][0]["content"]["parts"][0]["text"]
        return json.loads(texto)
    except (KeyError, IndexError, TypeError, ValueError) as error:
        raise ErrorIA(f"respuesta inesperada de la IA: {str(respuesta)[:200]}") from error


def _detalle_http(error: urllib.error.HTTPError) -> str:
    try:
        return json.loads(error.read()).get("error", {}).get("message", "")[:300]
    except Exception:  # noqa: BLE001
        return ""


def mensaje_claro(codigo: int | None, detalle: str = "") -> str:
    """Qué pasó y qué hacer, en castellano (Google responde en inglés y con códigos). El
    detalle técnico queda en el registro del servidor. `codigo` None = sin conexión."""
    texto = (detalle or "").lower()
    if codigo == 429 and any(p in texto for p in ("quota", "exhausted", "billing")):
        return ("se terminó el uso gratuito (o el cupo del día) de la IA. Probá más tarde o revisá el "
                "plan de Gemini; mientras tanto, decidí a mano")
    if codigo == 429:
        return "la IA tiene demasiados pedidos en este momento. Probá de nuevo en unos minutos"
    if codigo in (401, 403) or (codigo == 400 and "api key" in texto.replace("_", " ")):
        return ("la clave de la IA no es válida, venció o no tiene permiso: hay que cambiar "
                "GEMINI_API_KEY en el servidor")
    if codigo == 404:
        return "el modelo de la IA ya no existe: hay que cambiar GEMINI_MODEL en el servidor"
    if codigo is None:
        return "no hay conexión con la IA. Revisá internet y volvé a probar"
    if codigo >= 500:
        return "el servicio de la IA (Google) está con problemas. Probá de nuevo más tarde"
    return f"la IA rechazó el pedido (error {codigo})"


def pedir(hacer: Callable[[str], dict], modelos: list[str], consumo: Consumo,
          esperar: Callable[[float], None] = time.sleep) -> dict:
    """Un pedido con reintentos: ante «alta demanda» (429/5xx) o un corte de red espera y
    reintenta; un modelo retirado (404) o agotado pasa al de respaldo. Suma el consumo."""
    modelos = [m for m in modelos if m]
    if not modelos:
        raise ErrorIA("falta el modelo de la IA (GEMINI_MODEL en el servidor)")
    ultimo_error, ultimo_codigo = "", None
    for modelo in modelos:
        for intento in range(REINTENTOS + 1):
            try:
                respuesta = hacer(modelo)
            except urllib.error.HTTPError as error:
                detalle = _detalle_http(error)
                ultimo_error, ultimo_codigo = f"{modelo}: HTTP {error.code} {detalle}", error.code
                if error.code in (429, 500, 502, 503, 504):
                    _logger.warning("IA: %s; reintento en %s s", ultimo_error, ESPERA_S * (intento + 1))
                    esperar(ESPERA_S * (intento + 1))
                    continue
                if error.code == 404:
                    break  # modelo retirado: probar el de respaldo
                _logger.warning("IA: %s", ultimo_error)
                raise ErrorIA(mensaje_claro(error.code, detalle)) from error
            except (urllib.error.URLError, TimeoutError) as error:
                ultimo_error, ultimo_codigo = f"{modelo}: sin conexión ({error})", None
                _logger.warning("IA: %s; reintento en %s s", ultimo_error, ESPERA_S * (intento + 1))
                esperar(ESPERA_S * (intento + 1))
                continue
            consumo.pedidos += 1
            consumo.tokens += int(respuesta.get("usageMetadata", {}).get("totalTokenCount") or 0)
            consumo.modelo = respuesta.get("modelVersion") or modelo
            return respuesta
    _logger.warning("IA: no respondió (%s)", ultimo_error or "sin detalle")
    raise ErrorIA(mensaje_claro(ultimo_codigo, ultimo_error))


def verificar(filas: list[dict], clave: str, modelos: list[str],
              llamar: Callable[..., dict] = llamar_gemini_texto,
              esperar: Callable[[float], None] = time.sleep,
              ) -> tuple[list[Resultado], Consumo]:
    """Pide la opinión de la IA por tandas, en paralelo. Ante «alta demanda» reintenta y pasa
    al modelo de respaldo."""
    if not clave:
        raise ErrorIA("falta la clave de la IA (GEMINI_API_KEY en el servidor)")
    tandas = [filas[inicio:inicio + TANDA] for inicio in range(0, len(filas), TANDA)]

    def una_tanda(tanda: list[dict]) -> tuple[list[Resultado], Consumo]:
        consumo = Consumo()  # uno por tanda: los hilos no comparten contadores
        texto = armar_pedido(tanda)
        respuesta = pedir(lambda modelo: llamar(texto, clave, modelo), modelos, consumo, esperar)
        return validar(_texto_de(respuesta), tanda), consumo

    with ThreadPoolExecutor(max_workers=min(EN_PARALELO, len(tandas) or 1)) as hilos:
        hechas = list(hilos.map(una_tanda, tandas))  # en el orden de las filas; un error se propaga
    total = Consumo()
    resultados: list[Resultado] = []
    for parciales, consumo in hechas:
        resultados += parciales
        total.pedidos += consumo.pedidos
        total.tokens += consumo.tokens
        total.modelo = consumo.modelo or total.modelo
    return resultados, total
