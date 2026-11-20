"""Similitud de nombres de productos, para detectar posibles duplicados entre proveedores.

Núcleo portado de `odoo-product-matcher` (core/normalization.py y core/matching.py,
ADR 0014). Sin IA: palabras normalizadas, unidades equivalentes (20 Kg = 20000 g),
abreviaturas (alim → alimento) y penalización si las cantidades no coinciden.

A diferencia del original, **no compara códigos**: el código de un proveedor solo vale
dentro de ese proveedor (docs/areas/codigos.md, D4) y los códigos de fábrica ya los
resuelve plan.py por coincidencia exacta. Este motor solo sugiere: la decisión es de
una persona.
"""
from __future__ import annotations

import math
import re
import unicodedata
from collections import defaultdict
from dataclasses import dataclass
from decimal import Decimal, InvalidOperation
from difflib import SequenceMatcher
from functools import lru_cache

PALABRAS_VACIAS = frozenset(
    {"de", "del", "la", "las", "el", "los", "x", "para", "con", "y", "en", "por", "a", "al", "c", "p"}
)

# unidad escrita → (unidad canónica, dimensión, factor a la unidad base de la dimensión)
_UNIDADES: dict[str, tuple[str, str, Decimal]] = {}


def _registrar(nombres: tuple[str, ...], canonica: str, dimension: str, factor: str) -> None:
    for nombre in nombres:
        _UNIDADES[nombre] = (canonica, dimension, Decimal(factor))


_registrar(("kg", "kgs", "kilo", "kilos", "kilogramo", "kilogramos"), "kg", "masa", "1000")
_registrar(("g", "gr", "grs", "gramo", "gramos"), "g", "masa", "1")
_registrar(("mg",), "mg", "masa", "0.001")
_registrar(("l", "lt", "lts", "litro", "litros"), "l", "volumen", "1000")
_registrar(("ml", "cc", "cm3"), "ml", "volumen", "1")
_registrar(("m", "mt", "mts", "metro", "metros"), "m", "longitud", "1000")
_registrar(("cm",), "cm", "longitud", "10")
_registrar(("mm",), "mm", "longitud", "1")
_registrar(("u", "un", "und", "unid", "unids", "unidad", "unidades"), "u", "cantidad", "1")

_PATRON_UNIDAD = "|".join(sorted((re.escape(u) for u in _UNIDADES), key=len, reverse=True))
_CANTIDAD_RE = re.compile(rf"(?<![a-z0-9])(\d+(?:[.,]\d+)?)\s*({_PATRON_UNIDAD})(?![a-z0-9])")


@dataclass(frozen=True)
class Cantidad:
    dimension: str
    valor_base: Decimal  # en la unidad base de su dimensión (g, ml, mm, u)


@dataclass(frozen=True)
class Configuracion:
    umbral_candidato: float = 0.50  # desde acá un producto es «posible duplicado»
    umbral_alto: float = 0.85  # muy parecido (igual lo confirma una persona)
    margen_ambiguo: float = 0.05  # si el segundo está más cerca que esto, es ambiguo
    max_candidatos: int = 3
    preseleccion: int = 60  # candidatos que pasan del índice al cálculo fino
    similitud_palabra: float = 0.85
    penalizacion_cantidad: float = 0.6


def sin_acentos(texto: str) -> str:
    descompuesto = unicodedata.normalize("NFKD", texto)
    return "".join(c for c in descompuesto if not unicodedata.combining(c))


def _basico(texto: str) -> str:
    return sin_acentos(texto or "").lower()


def _formatear_cantidad(numero: str, unidad: str) -> str:
    canonica = _UNIDADES[unidad][0]
    numero = numero.replace(",", ".")
    if "." in numero:
        numero = numero.rstrip("0").rstrip(".")
    return f"{numero}{canonica}"


def normalizar_texto(texto: str) -> str:
    """Minúsculas, sin acentos ni puntuación y con cantidades unificadas (``20 Kg.`` → ``20kg``)."""
    valor = _basico(texto)
    valor = _CANTIDAD_RE.sub(lambda m: _formatear_cantidad(m.group(1), m.group(2)), valor)
    valor = re.sub(r"[^a-z0-9.]+", " ", valor)
    valor = re.sub(r"(?<!\d)\.|\.(?!\d)", " ", valor)  # conserva solo el punto decimal
    return " ".join(valor.split())


def palabras(texto: str) -> list[str]:
    """Palabras significativas de un texto (sin palabras vacías)."""
    return [p for p in normalizar_texto(texto).split() if p not in PALABRAS_VACIAS]


def cantidades(texto: str) -> set[Cantidad]:
    """Cantidades con unidad del texto, convertidas a la unidad base."""
    encontradas = set()
    for numero, unidad in _CANTIDAD_RE.findall(_basico(texto)):
        _, dimension, factor = _UNIDADES[unidad]
        try:
            valor = Decimal(numero.replace(",", ".")) * factor
        except InvalidOperation:
            continue
        encontradas.add(Cantidad(dimension, valor.normalize()))
    return encontradas


@lru_cache(maxsize=200_000)
def _similitud_palabra(a: str, b: str) -> float:
    if a == b:
        return 1.0
    # Palabras con números (cantidades, modelos) tienen que coincidir exactas.
    if any(c.isdigit() for c in a) or any(c.isdigit() for c in b):
        return 0.0
    # Abreviaturas habituales en listas de proveedores: «alim» → alimento, «inox» → inoxidable.
    corta, larga = sorted((a, b), key=len)
    if len(corta) >= 4 and larga.startswith(corta):
        return 0.9
    return SequenceMatcher(None, a, b).ratio()


def _cubierto(origen: list[str], destino: list[str], minimo: float) -> float:
    total = 0.0
    for palabra in origen:
        mejor = max((_similitud_palabra(palabra, otra) for otra in destino), default=0.0)
        if mejor >= minimo:
            total += mejor
    return total


def _cantidades_en_conflicto(a: str, b: str) -> bool:
    qa, qb = cantidades(a), cantidades(b)
    for dimension in {q.dimension for q in qa} & {q.dimension for q in qb}:
        valores_a = {q.valor_base for q in qa if q.dimension == dimension}
        valores_b = {q.valor_base for q in qb if q.dimension == dimension}
        if not valores_a & valores_b:
            return True
    return False


def similitud(a: str, b: str, config: Configuracion | None = None) -> float:
    """Similitud 0..1 entre dos descripciones, tolerante a orden, acentos y errores menores."""
    config = config or Configuracion()
    pa, pb = palabras(a), palabras(b)
    if not pa or not pb:
        return 0.0
    cub_a = _cubierto(pa, pb, config.similitud_palabra)
    cub_b = _cubierto(pb, pa, config.similitud_palabra)
    dice = (cub_a + cub_b) / (len(pa) + len(pb))
    cobertura = max(cub_a / len(pa), cub_b / len(pb))
    por_palabras = 0.5 * dice + 0.5 * cobertura
    secuencia = SequenceMatcher(None, " ".join(sorted(pa)), " ".join(sorted(pb))).ratio()
    puntaje = 0.7 * por_palabras + 0.3 * secuencia
    if _cantidades_en_conflicto(a, b):
        puntaje *= config.penalizacion_cantidad
    return round(min(puntaje, 1.0), 4)


def _claves_indice(lista: list[str]) -> set[str]:
    claves = set(lista)
    claves.update("~" + p[:4] for p in lista if len(p) >= 4 and not any(c.isdigit() for c in p))
    return claves


@dataclass(frozen=True)
class Candidato:
    id: int | str
    nombre: str
    puntaje: float


class Buscador:
    """Índice de nombres del catálogo para encontrar candidatos parecidos rápido.

    Se le pueden agregar productos mientras se arma el plan (los nuevos de la misma
    importación), así dos proveedores con el mismo producto nuevo también se detectan.
    """

    def __init__(self, config: Configuracion | None = None):
        self.config = config or Configuracion()
        self._nombres: dict[int | str, list[str]] = defaultdict(list)
        self._indice: dict[str, set[int | str]] = defaultdict(set)
        # Nombre normalizado completo → productos: la coincidencia exacta nunca se pierde
        self._exactos: dict[str, set[int | str]] = defaultdict(set)

    def agregar(self, id_: int | str, nombre: str) -> None:
        """Suma un nombre del producto (su nombre, o cómo lo describe un proveedor)."""
        if not nombre or nombre in self._nombres[id_]:
            return
        self._nombres[id_].append(nombre)
        self._exactos[" ".join(palabras(nombre))].add(id_)
        for clave in _claves_indice(palabras(nombre)):
            self._indice[clave].add(id_)

    def _mejor(self, texto: str, id_) -> tuple[float, str]:
        return max((similitud(texto, n, self.config), n) for n in self._nombres[id_])

    def candidatos(self, texto: str, excluir: set = frozenset()) -> list[Candidato]:
        """Productos parecidos al texto, del más al menos parecido (solo los que superan el umbral)."""
        total = max(len(self._nombres), 1)
        pesos: dict[int | str, float] = defaultdict(float)
        for clave in _claves_indice(palabras(texto)):
            ids = self._indice.get(clave, ())
            for id_ in ids:
                pesos[id_] += math.log(1 + total / len(ids))
        # Se excluye antes de cortar, y las coincidencias exactas entran primero: si no, pueden
        # quedar afuera del corte detrás de muchos nombres parecidos.
        exactos = [i for i in self._exactos.get(" ".join(palabras(texto)), ()) if i not in excluir]
        ordenados = sorted((i for i in pesos if i not in excluir and i not in exactos),
                           key=lambda i: -pesos[i])
        encontrados = []
        for i in exactos[: self.config.max_candidatos] + ordenados[: self.config.preseleccion]:
            puntaje, nombre = self._mejor(texto, i)
            if puntaje >= self.config.umbral_candidato:
                encontrados.append(Candidato(i, nombre, puntaje))
        encontrados.sort(key=lambda c: (-c.puntaje, c.nombre))
        return encontrados[: self.config.max_candidatos]

    def es_ambiguo(self, candidatos: list[Candidato]) -> bool:
        if len(candidatos) < 2:
            return False
        return candidatos[0].puntaje - candidatos[1].puntaje < self.config.margen_ambiguo
