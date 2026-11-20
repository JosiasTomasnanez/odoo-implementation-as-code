"""Plan de importación de productos: qué crear, vincular, actualizar o revisar.

Función pura: recibe las filas de la planilla modelo y una foto de Odoo, y devuelve
las acciones. No llama a Odoo; así se prueba sin servidor y la simulación muestra
exactamente lo que después se aplica. Reglas en docs/areas/codigos.md.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field

from .codigos import FABRICANTE, INTERNO, INVALIDO, codigo_propio, normalizar, numero_de_codigo_propio
from .costo import porcentaje
from .similitud import Buscador, Candidato

UNIDADES = {"u": "product_uom_unit", "kg": "product_uom_kgm", "m": "product_uom_meter",
            "l": "product_uom_litre"}
# Cómo escriben la unidad las listas reales (Gas del Sur: «UN.», «KG.», «PAQ.», «CAJA»…).
# Un envase (paquete, caja, rollo, par, blíster) es una unidad: el producto es el envase.
SINONIMOS_UNIDAD = {
    "u": {"un", "und", "unid", "unidad", "unidades", "uni", "c/u", "cu", "pza", "pieza", "paq", "paquete",
          "caja", "cja", "rollo", "par", "blist", "blister", "bolsa", "bls", "juego", "jgo", "kit", "set",
          "caño", "cano", "varilla", "tira", "barra", "uno", "cj", "bulto", "pack", "estuche", "frasco",
          "lata", "bidon", "balde", "pomo", "sobre", "blis", "unid.", "u."},
    "kg": {"kgs", "kilo", "kilos", "kilogramo"},
    "m": {"mt", "mts", "mtr", "metro", "metros", "mts/mts", "mts real", "ml", "m/l"},
    "l": {"lt", "lts", "litro", "litros"},
}
SI = {"si", "sí", "s", "x", "1", "true"}


_ENVASE = re.compile(r"^(\d+)\s*(u|un|und|unid|unidades|par|pares)?\.?$")
DOCENA = {"docena", "doc", "dna", "dz"}


def envase(texto) -> int:
    """«24 u.», «100 U.», «12 par», «100», «Docena»: el precio de la unidad de la lista es por N
    (Gas del Sur, C Kappa). 1 si no es un envase. «Caja x 12» no: ver normalizar_unidad."""
    limpio = str(texto or "").strip().lower().rstrip(".")
    if limpio in DOCENA:
        return 12
    encontrado = _ENVASE.match(limpio)
    return int(encontrado.group(1)) if encontrado and int(encontrado.group(1)) > 1 else 1


def cantidad(texto) -> float:
    """Cantidad escrita con texto: «Caja x 12» → 12, «24 blisters» → 24, «10 tiras x 5» → 50,
    «Unidad» → 1. Lanza ValueError si no hay números."""
    try:
        return _numero(texto)
    except ValueError:
        pass
    limpio = str(texto or "").strip().lower()
    if limpio in ("unidad", "unid", "un", "u"):
        return 1.0
    if limpio in DOCENA:
        return 12.0
    numeros = [float(n.replace(",", ".")) for n in re.findall(r"\d+(?:[.,]\d+)?", limpio)]
    if not numeros:
        raise ValueError(texto)
    total = 1.0
    for n in numeros:
        total *= n
    return total


def normalizar_unidad(texto) -> str:
    """«UN.» → «u», «KG.» → «kg», «Mts» → «m»; lo que no reconoce queda igual (va a revisar).

    «Caja x 20 x 12 Unid», «Pack x unidad» (Rho): es la presentación en que se despacha; el
    precio de la lista es por unidad."""
    unidad = str(texto or "u").strip().lower().rstrip(".").strip()
    if unidad in UNIDADES:
        return unidad
    primera = unidad.split(" ", 1)[0].rstrip(".")
    if " x " in f" {unidad} " and primera in SINONIMOS_UNIDAD["u"]:
        return "u"
    for destino, sinonimos in SINONIMOS_UNIDAD.items():
        if unidad in sinonimos:
            return destino
    return unidad

# Tipos de acción
NUEVO = "nuevo"  # producto nuevo (con su proveedor)
VINCULAR = "vincular"  # producto existente: se le agrega este proveedor
ACTUALIZAR = "actualizar"  # cambian datos del proveedor o se completa el código de barras
SIN_CAMBIOS = "sin cambios"
REVISAR = "revisar"  # una persona tiene que mirarlo; no se toca nada
# Iba a ser nuevo pero se parece a productos existentes: una persona confirma una sola vez
# («es el mismo» → vincular_a, «es nuevo» → nuevo=si). No se toca nada (ADR 0014).
POSIBLE_DUPLICADO = "posible duplicado"
# El producto ya no está en la lista completa del proveedor: se cierra su precio (no se
# borra el producto; sigue con sus otros proveedores).
BAJA = "baja"


@dataclass
class Foto:
    """Estado actual de Odoo que necesita el plan."""

    productos: list[dict]  # {id (plantilla), barcode, default_code, name, familia}
    # Precios vigentes (sin fecha de fin): {id, partner, tmpl, product_code, product_name,
    # price, min_qty, delay, date_start, uom_id, unidad_propia}
    proveedores_producto: list[dict]
    proveedores: set[str]  # nombres de proveedores existentes (normalizados)
    categorias: set[str]  # nombres completos de categorías existentes
    hoy: str = "2000-01-01"  # fecha de la importación (AAAA-MM-DD): inicio de los precios nuevos
    socios: dict | None = None  # {id: nombre} de los contactos (para reconocer al proveedor)
    # Unidades de Odoo: {id: {"nombre", "familia"}}; familia = clave de UNIDADES («u», «kg»,
    # «m», «l») de la unidad de referencia, o None si es de otra (horas…)
    unidades: dict | None = None
    # Precios cerrados (dados de baja o reemplazados), el más reciente por proveedor y código:
    # {id, partner_id, tmpl, product_code, product_name, price}. Un producto que «vuelve a la
    # lista» se reconoce por acá en vez de salir como posible duplicado de sí mismo (21/10).
    cerrados: list[dict] | None = None


@dataclass
class Accion:
    fila: int
    tipo: str
    detalle: str
    producto: dict | None = None  # valores del producto nuevo
    tmpl: int | str | None = None  # id existente o clave de un producto nuevo del mismo plan
    proveedor: dict | None = None  # valores de product.supplierinfo a crear o escribir
    proveedor_id: int | None = None  # supplierinfo existente a actualizar
    # D7: el costo cambió y se guarda historial. Se cierra el precio anterior
    # (proveedor_id) y se crea uno nuevo desde hoy con todos los valores en `proveedor`.
    historial: bool = False
    cambia_unidad: bool = False  # cambia la unidad de compra del proveedor: lo mira una persona
    vuelve: bool = False  # VINCULAR de un producto que vuelve a la lista (su precio se había cerrado)
    completar_barcode: str | None = None
    # El código propio (20…) que reemplaza completar_barcode: queda como código alternativo
    # (puede estar pegado en el producto o la góndola), 20/11
    codigo_propio_anterior: str | None = None
    avisos: list[str] = field(default_factory=list)
    candidatos: list = field(default_factory=list)  # posibles duplicados (similitud.Candidato)
    # Datos de la fila, para mostrar la lista entera y compararla con la anterior
    codigo_proveedor: str = ""
    descripcion: str = ""
    codigo_barras: str = ""
    costo: float | None = None
    costo_anterior: float | None = None
    costo_mayor: float | None = None  # precio por mayor (desde cierta cantidad), si la lista lo trae
    mayor_anterior: float | None = None
    # Lo que hizo aplicar() con esta acción, para poder deshacerla (lo completa odoo_api)
    deshacer: dict = field(default_factory=dict)

    @property
    def variacion(self) -> float | None:
        """Variación del costo respecto del precio vigente anterior (0.1 = +10 %)."""
        if self.costo is None or not self.costo_anterior:
            return None
        return self.costo / self.costo_anterior - 1


def _clave(nombre: str) -> str:
    return " ".join(str(nombre or "").split()).casefold()


_MONEDA = re.compile(r"^(?:u\$s|u\$d|us\$|usd|ars|\$)+|(?:u\$s|u\$d|us\$|usd|ars)$")


def _numero(texto, por_defecto=0.0) -> float:
    """Número escrito a mano o leído de Excel: 1.234,56 / 1.300 / 1,5 / 1,234.56 / $ 35 / USD 31,60."""
    texto = str(texto or "").replace("\xa0", "").replace(" ", "").strip()
    texto = _MONEDA.sub("", texto.lower()).replace("$", "")
    if not texto:
        return por_defecto
    if "," in texto and "." in texto:
        if texto.rfind(",") < texto.rfind("."):  # formato inglés: 1,234.56
            texto = texto.replace(",", "")
        else:  # formato argentino: 1.234,56
            texto = texto.replace(".", "").replace(",", ".")
    elif "," in texto:  # coma decimal: 1,5
        texto = texto.replace(",", ".")
    elif re.fullmatch(r"\d{1,3}(\.\d{3})+", texto):  # 1.300 o 12.500.000: puntos de miles
        texto = texto.replace(".", "")
    return float(texto)


def _en_categorias(categoria: str | None, categorias: list[str]) -> bool:
    """La categoría es una de la lista o una subcategoría de alguna."""
    clave = _clave(categoria or "")
    return any(clave == _clave(c) or clave.startswith(_clave(c) + " / ") for c in categorias)


def _clave_prov(s: dict) -> str:
    """Identidad del proveedor de un precio: por id si se conoce (dos contactos pueden
    llamarse igual), si no por nombre."""
    return f"#{s['partner_id']}" if s.get("partner_id") else "n:" + _clave(s.get("partner"))


# Si la lista «completa» trae menos de esta parte de los productos que el proveedor tiene
# hoy, no se calculan bajas: probablemente el archivo vino cortado o mal mapeado.
MINIMO_LISTA_COMPLETA = 0.5
# Si de los productos que ya tenía esta lista vienen menos que esto, el archivo es otra cosa
# (otra parte de la lista del proveedor): no se dan de baja
MINIMO_COINCIDENCIAS = 0.2


def planificar(filas: list[dict], foto: Foto, categorias_con_stock: list[str] = (),
               lista_completa_de: str | int | None = None, lista_id: int | None = None,
               otras_listas: bool = False, lista_entera: list[dict] | None = None) -> list[Accion]:
    """Arma el plan.

    `categorias_con_stock`: rubros con control de stock (P-032).
    `lista_completa_de`: el proveedor (id o nombre) si las filas son **toda** su lista;
    entonces sus productos que no aparecen se dan de baja (se cierra su precio).
    Cada fila puede traer `proveedor_id` (lo pone el módulo); si no, se busca por nombre.
    `lista_id` / `otras_listas`: si el proveedor tiene varias listas (una por hoja, p. ej.),
    las bajas solo miran los precios que cargó esta lista; los que no tienen lista anotada
    (carga inicial, a mano) cuentan solo si el proveedor tiene una única lista.
    `lista_entera`: si `filas` es solo una parte (aplicar en tandas), la lista completa; sirve
    para saber qué productos del proveedor siguen en su lista y no ofrecerlos como «¿cambió el
    código?» (si no, un bulón nuevo se confundía con el de la medida de al lado, ya creado
    en la tanda anterior).
    """
    filas = _separar_barras_repetidas(filas)
    presentaciones: dict = {}  # (proveedor, producto) → otras presentaciones de la lista
    primera_accion: dict = {}  # (proveedor, producto) → (índice de la acción de su primera fila, existente)
    activo = {p["id"]: p.get("active", True) for p in foto.productos}
    familia_de = {p["id"]: p.get("familia") for p in foto.productos}
    unidades = foto.unidades or {}
    por_barcode = {p["barcode"]: p["id"] for p in foto.productos if p.get("barcode")}
    barcode_de = {p["id"]: p.get("barcode") or None for p in foto.productos}
    nombre_de = {p["id"]: p.get("name") or str(p["id"]) for p in foto.productos}
    # Lo que se escribe en vincular_a para elegir un producto: referencia o código de barras
    elegir_con = {p["id"]: p.get("default_code") or p.get("barcode") or f"id {p['id']}"
                  for p in foto.productos}
    por_codigo_prov = {
        (_clave_prov(s), s["product_code"]): s for s in foto.proveedores_producto if s["product_code"]
    }
    # Filas sin código ni código de barras: se reconocen por la descripción exacta del proveedor
    por_descripcion = {
        (_clave_prov(s), _clave(s["product_name"])): s
        for s in foto.proveedores_producto if s.get("product_name")
    }
    por_prov_y_producto = {(_clave_prov(s), s["tmpl"]): s for s in foto.proveedores_producto}
    cerrado_por_codigo: dict = {}
    cerrado_por_descripcion: dict = {}
    for s in foto.cerrados or []:  # del más reciente al más viejo: queda el último
        if s.get("product_code"):
            cerrado_por_codigo.setdefault((_clave_prov(s), s["product_code"]), s)
        elif s.get("product_name"):
            cerrado_por_descripcion.setdefault((_clave_prov(s), _clave(s["product_name"])), s)
    por_referencia = {p["default_code"]: p["id"] for p in foto.productos if p.get("default_code")}
    # D5: una sola numeración para la referencia interna y el código propio (1234 ↔ 20…1234…).
    # Solo cuentan referencias de hasta 10 dígitos (las más largas no son de esta numeración).
    ultimo = max(
        [n for p in foto.productos if (n := numero_de_codigo_propio(p.get("barcode")))]
        + [int(r) for p in foto.productos
           if (r := str(p.get("default_code") or "")).isdigit() and len(r) <= 10],
        default=0,
    )
    socios = foto.socios or {}
    categorias = {_clave(c) for c in foto.categorias}
    acciones: list[Accion] = []
    # Posibles duplicados: nombres de los productos y cómo los describe cada proveedor
    buscador = Buscador()
    for p in foto.productos:
        buscador.agregar(p["id"], p.get("name") or "")
    proveedores_de: dict = {}
    for s in foto.proveedores_producto:
        buscador.agregar(s["tmpl"], s.get("product_name") or "")
        proveedores_de.setdefault(s["tmpl"], set()).add(_clave_prov(s))
    # Productos de cada proveedor que no son candidatos a duplicado (ver «ya_suyos» abajo).
    # Se lleva al día en vez de recorrer todos los productos en cada fila: con listas de
    # 10 000 filas (FC) eso hacía la simulación cuadrática.
    suyos_de: dict = {}

    def es_suyo(tmpl, kp) -> None:
        proveedores_de.setdefault(tmpl, set()).add(kp)
        if isinstance(tmpl, str) or (kp, tmpl) in en_la_planilla:
            suyos_de.setdefault(kp, set()).add(tmpl)

    def clave_de_fila(proveedor: str, proveedor_id) -> str | None:
        if proveedor_id:
            return f"#{int(proveedor_id)}"
        if not socios:
            return "n:" + _clave(proveedor)
        ids = [i for i, nombre in socios.items() if _clave(nombre) == _clave(proveedor)]
        if len(ids) > 1:
            return None  # varios contactos con ese nombre
        return f"#{ids[0]}" if ids else "n:" + _clave(proveedor)

    # Primera pasada: qué productos de cada proveedor vienen en la planilla (por código, código
    # de barras o descripción). Los suyos que NO vienen pueden ser el mismo producto con otro
    # código (el proveedor renumeró su lista): esos sí se ofrecen como posible duplicado.
    en_la_planilla: set = set()
    for fila in lista_entera if lista_entera is not None else filas:
        kp = clave_de_fila(" ".join(str(fila.get("proveedor") or "").split()), fila.get("proveedor_id"))
        if not kp:
            continue
        cod = str(fila.get("codigo_proveedor") or "").strip()
        desc = str(fila.get("descripcion_proveedor") or "").strip()
        barras, tipo_barras = normalizar(fila.get("codigo_barras"))
        previo = (por_codigo_prov.get((kp, cod)) if cod else None) or (
            por_descripcion.get((kp, _clave(desc))) if not cod and desc else None)
        for t in filter(None, [previo and previo["tmpl"],
                               por_barcode.get(barras) if tipo_barras == FABRICANTE else None]):
            en_la_planilla.add((kp, t))
    for kp, t in en_la_planilla:
        if kp in proveedores_de.get(t, ()):
            suyos_de.setdefault(kp, set()).add(t)
    # Lo que el proveedor vende en otra parte de su lista (p. ej. los bulones de FC) tampoco
    # es candidato: no lo lista dos veces y no es un producto al que le cambió el código.
    if lista_id is not None:
        for s in foto.proveedores_producto:
            if s.get("lista_id") and s["lista_id"] != lista_id:
                suyos_de.setdefault(_clave_prov(s), set()).add(s["tmpl"])

    datos_fila: dict[int, dict] = {}
    vistos: set = set()  # (proveedor, producto) presentes en la planilla
    precios_usados: set = set()  # precios del proveedor que ya tomó una fila (código repetido)
    filas_del_proveedor = 0
    for posicion, fila in enumerate(filas, start=2):  # fila 1: encabezados
        # `_n`: número de fila original cuando se planifica solo una parte de la lista
        n = int(fila.get("_n") or posicion)
        datos_fila[n] = {"codigo_proveedor": str(fila.get("codigo_proveedor") or "").strip(),
                         "descripcion": str(fila.get("descripcion_proveedor") or "").strip(),
                         "codigo_barras": str(fila.get("codigo_barras") or "").strip()}

        def revisar(motivo: str, n: int = n, tmpl=None) -> None:
            acciones.append(Accion(n, REVISAR, motivo, tmpl=tmpl))

        proveedor = " ".join(str(fila.get("proveedor") or "").split())
        codigo_prov = str(fila.get("codigo_proveedor") or "").strip()
        descripcion = str(fila.get("descripcion_proveedor") or "").strip()
        nombre = str(fila.get("nombre") or "").strip() or descripcion
        if not proveedor:
            revisar("falta el proveedor")
            continue
        kprov = clave_de_fila(proveedor, fila.get("proveedor_id"))
        if kprov is None:
            revisar(f"hay varios contactos llamados «{proveedor}»: dejar uno solo o usar el módulo")
            continue
        codigo, tipo = normalizar(fila.get("codigo_barras"))
        # Antes de validar el resto: si la fila es de un producto que ya tiene, cuenta como
        # «sigue en la lista» aunque termine a revisar (si no, saldría como baja).
        conocido = (por_codigo_prov.get((kprov, codigo_prov)) if codigo_prov else None) or (
            por_descripcion.get((kprov, _clave(descripcion))) if not codigo_prov and descripcion else None)
        for t in filter(None, [conocido and conocido["tmpl"],
                               por_barcode.get(codigo) if tipo == FABRICANTE else None]):
            vistos.add((kprov, t))
        filas_del_proveedor += 1

        if not nombre:
            revisar("falta el nombre o la descripción")
            continue
        if not str(fila.get("costo") or "").strip():
            revisar("la lista no trae precio (¿sin stock o a consultar?, o columna de costo sin elegir)")
            continue
        try:
            costo = _numero(fila.get("costo"))
            plazo = int(_numero(fila.get("plazo_dias")))
            precio_venta = _numero(fila.get("precio_venta"), None)
            costo_mayor = _numero(fila.get("costo_mayor"), None)
        except ValueError:
            revisar(f"el costo «{fila.get('costo')}» (o el plazo o el precio por mayor) no es un número")
            continue
        if costo <= 0:
            # Un precio 0 no es un costo: el producto saldría a $ 0 (o a $ 1) en la caja
            revisar("la lista trae precio 0 (¿sin stock o a consultar?)")
            continue
        if fila.get("precio_dudoso") and not fila.get("corregida_a_mano"):
            revisar(fila["precio_dudoso"])  # lista en dólares con un precio en pesos (ver convertir)
            continue
        avisos_cantidad: list[str] = []
        texto_bulto = str(fila.get("bulto") or "").strip()
        try:
            bulto = cantidad(texto_bulto) if texto_bulto else 0.0
        except ValueError:
            bulto = 0.0
        texto_minimo = str(fila.get("cantidad_minima") or "").strip()
        try:
            minimo = cantidad(texto_minimo) if texto_minimo else 0.0
        except ValueError:
            minimo = 0.0
            avisos_cantidad.append(f"cantidad mínima «{texto_minimo}» no se entiende: no se carga")
        texto_mayor = str(fila.get("cantidad_mayor") or "").strip()
        try:
            cantidad_mayor = cantidad(texto_mayor) if texto_mayor else None
        except ValueError:
            cantidad_mayor = None
        categoria = str(fila.get("categoria") or "").strip()
        if categoria and _clave(categoria) not in categorias:
            revisar(f"la categoría «{categoria}» no existe en Odoo (se crean en config/)")
            continue

        avisos: list[str] = list(avisos_cantidad)
        codigo_lista = fila.get("codigo_lista") or None  # el código que traía la lista, para verificarlo
        if fila.get("aviso_barras"):
            avisos.append(fila["aviso_barras"])
        if fila.get("aviso_iva"):
            avisos.append(fila["aviso_iva"])
        if tipo == INVALIDO:
            # El producto y el precio están bien: se carga sin ese código (recibe el propio 20…) y se
            # escanea el del envase después («Códigos de fábrica»). No se adivina el bueno.
            avisos.append(f"código de barras inválido o incompleto en la lista «{codigo}»: no se carga; "
                          "escanear el del envase en «Códigos de fábrica»")
            codigo_lista = codigo_lista or codigo
            codigo, tipo = None, None
        if tipo == INTERNO:
            if not codigo_prov:
                codigo_prov = codigo
                avisos.append(f"{codigo} empieza con 2 (uso interno): se guarda como código del proveedor")
            else:
                avisos.append(f"{codigo} empieza con 2 (uso interno): se ignora como código de barras")
            codigo, tipo = None, None

        por_codigo = por_codigo_prov.get((kprov, codigo_prov)) if codigo_prov else None
        if por_codigo is None and not codigo_prov and tipo != FABRICANTE and descripcion:
            por_codigo = por_descripcion.get((kprov, _clave(descripcion)))
        tmpl_codigo = por_codigo["tmpl"] if por_codigo else None
        tmpl_barcode = por_barcode.get(codigo) if tipo == FABRICANTE else None
        if tmpl_codigo and tmpl_barcode and tmpl_codigo != tmpl_barcode:
            revisar(f"el código de barras {codigo} y el código de proveedor «{codigo_prov}» "
                    "son de productos distintos")
            continue
        tmpl = tmpl_codigo or tmpl_barcode
        # Vuelve a la lista: su código (o su descripción, sin código) es el de un precio de este
        # proveedor que se cerró, y el producto no tiene hoy otro precio vigente de él
        volvio = None
        if tmpl is None:
            volvio = (cerrado_por_codigo.get((kprov, codigo_prov)) if codigo_prov else
                      cerrado_por_descripcion.get((kprov, _clave(descripcion))) if descripcion else None)
            if volvio and (kprov, volvio["tmpl"]) not in por_prov_y_producto and volvio["tmpl"] in nombre_de:
                tmpl = volvio["tmpl"]
            else:
                volvio = None
        # D4: vínculo confirmado a mano una vez (referencia interna o código de barras del
        # producto existente). Después de aplicarlo, el código del proveedor ya lo reconoce.
        vincular_a = str(fila.get("vincular_a") or "").strip()
        if vincular_a:
            if vincular_a.startswith("id:") and vincular_a[3:].isdigit():  # elegido en la pantalla de Odoo
                elegido = int(vincular_a[3:]) if int(vincular_a[3:]) in nombre_de else None
            else:
                elegido = por_referencia.get(vincular_a) or por_barcode.get(normalizar(vincular_a)[0])
            if elegido is None:
                revisar(f"vincular_a «{vincular_a}»: no hay producto con esa referencia o código")
                continue
            if tmpl is not None and tmpl != elegido:
                revisar(f"vincular_a «{vincular_a}» apunta a otro producto que el de sus códigos")
                continue
            tmpl = elegido

        # Unidad: si el precio de este proveedor tiene su unidad de compra (p. ej. «Caja 1000
        # tornillos» = 2,5 kg, o la elegida en la fila), la lista trae el precio de esa unidad
        # y se guarda tal cual. Si no, la de la lista tiene que ser la del producto (P-053).
        previo = por_prov_y_producto.get((kprov, tmpl)) if tmpl is not None else None
        compra = None  # (id, nombre) de la unidad de compra
        elegida = fila.get("unidad_compra")
        if elegida and isinstance(tmpl, int):
            u = unidades.get(int(elegida))
            if u is None or (familia_de.get(tmpl) and u["familia"] != familia_de[tmpl]):
                revisar(f"la unidad de compra elegida no se puede convertir a la de «{nombre_de[tmpl]}»",
                        tmpl=tmpl)
                continue
            compra = (int(elegida), u["nombre"])
        elif previo and previo.get("unidad_propia"):
            compra = (previo["uom_id"], (unidades.get(previo["uom_id"]) or {}).get("nombre", "su unidad"))
        por_caja = envase(fila.get("unidad"))
        if compra:
            unidad = None
            avisos.append(f"precio por «{compra[1]}» (unidad de compra de este proveedor): "
                          "se guarda tal cual")
        elif por_caja > 1:
            # Precio por caja de N: se guarda por unidad, con la caja como compra mínima
            costo = round(costo / por_caja, 4)
            costo_mayor = round(costo_mayor / por_caja, 4) if costo_mayor else costo_mayor
            minimo = (minimo or 1) * por_caja  # mínimo en cajas (puede ser media caja) → unidades
            unidad = "u"
            avisos.append(f"precio por caja de {por_caja} ({fila.get('unidad')}): se guarda por unidad, "
                          f"compra mínima {minimo:g}")
        else:
            unidad = normalizar_unidad(fila.get("unidad"))
        if unidad is not None and unidad not in UNIDADES:
            revisar(f"unidad desconocida «{unidad}» (usar: {', '.join(UNIDADES)})")
            continue
        if unidad is not None and isinstance(tmpl, int) and familia_de.get(tmpl) not in (None, unidad):
            revisar(f"«{nombre_de[tmpl]}» se vende por {familia_de[tmpl]} y la lista de {proveedor} lo trae "
                    f"por {fila.get('unidad') or unidad}: elegí su unidad de compra en la fila "
                    f"(p. ej. «Caja 1000 = 2,5 kg»)", tmpl=tmpl)
            continue
        if costo_mayor and not (cantidad_mayor and cantidad_mayor > max(minimo, 1)):
            avisos.append(f"precio por mayor {costo_mayor:g} sin cantidad (o no mayor que el mínimo): "
                          "no se carga")
            costo_mayor = None
        if not costo_mayor:
            cantidad_mayor = None
        datos_fila[n]["costo"] = costo
        datos_fila[n]["costo_mayor"] = costo_mayor
        if tmpl is not None:
            vistos.add((kprov, tmpl))
            if not activo.get(tmpl, True):
                avisos.append("se quitó de nuestro catálogo (archivado): «Agregar» lo vuelve a poner")
        valores_prov = {"partner": proveedor, "product_code": codigo_prov or False,
                        "product_name": descripcion or False, "price": costo,
                        "min_qty": minimo, "delay": plazo,
                        "comercio_precio_mayor": costo_mayor or 0.0,
                        "comercio_cantidad_mayor": cantidad_mayor or 0.0}
        if "bulto" in fila:  # la lista trae «unidades por bulto»: se compra de a bultos enteros
            valores_prov["comercio_bulto"] = bulto if bulto > 1 else 0.0
        if compra:
            valores_prov["uom_id"] = compra[0]
        if kprov.startswith("#"):
            valores_prov["partner_id"] = int(kprov[1:])

        forzar_nuevo = str(fila.get("nuevo") or "").strip().lower() in SI
        if tmpl is None and not forzar_nuevo:
            # Los productos de este proveedor que vienen en la planilla no son candidatos (un
            # proveedor no lista dos veces lo mismo). Los suyos que no vienen, sí: puede que
            # haya cambiado el código.
            ya_suyos = suyos_de.get(kprov, frozenset())
            parecidos = []
            for texto in dict.fromkeys(filter(None, [nombre, descripcion])):
                for c in buscador.candidatos(texto, excluir=ya_suyos):
                    if all(c.id != o.id for o in parecidos):
                        parecidos.append(c)
            parecidos.sort(key=lambda c: -c.puntaje)
            if parecidos:
                def describir(c, kprov=kprov, avisos=avisos):
                    texto = f"[{elegir_con.get(c.id, '?')}] {c.nombre} ({c.puntaje:.0%})"
                    suyo = por_prov_y_producto.get((kprov, c.id))
                    if suyo and suyo.get("id"):
                        avisos.append(f"«{c.nombre}» ya era de este proveedor con el código "
                                      f"«{suyo.get('product_code') or '-'}»: ¿cambió el código? Si es el "
                                      "mismo, se actualiza el código y no se da de baja")
                        texto += " - ¿cambió el código?"
                    return texto

                lista = "; ".join(describir(c) for c in parecidos[:3])
                acciones.append(Accion(n, POSIBLE_DUPLICADO, f"{nombre} de {proveedor} se parece a: {lista}",
                                       candidatos=parecidos[:3], avisos=avisos))
                continue

        if tmpl is None:  # producto nuevo
            ultimo += 1
            if tipo != FABRICANTE:
                codigo = codigo_propio(ultimo)
                avisos.append(f"sin código de fábrica: código propio {codigo}")
            clave_nueva = f"nuevo:{n}"
            marca_pesable = str(fila.get("pesable") or "").strip().lower()
            # Lo que se vende por kilo se pesa en la balanza, salvo que la planilla diga que no
            pesable = marca_pesable in SI if marca_pesable else unidad == "kg"
            stock = str(fila.get("controla_stock") or "").strip().lower()
            controla_stock = stock in SI if stock else _en_categorias(categoria, categorias_con_stock)
            producto = {"name": nombre, "default_code": str(ultimo), "barcode": codigo,
                        "uom": UNIDADES[unidad], "categoria": categoria or None, "to_weight": pesable,
                        "is_storable": controla_stock, "standard_price": costo, "list_price": precio_venta,
                        # IVA de la columna de la lista (FC lo trae por producto): el del producto nuevo
                        "iva": porcentaje(fila.get("iva_fila")),
                        "codigo_lista": codigo_lista}
            primera_accion[(kprov, clave_nueva)] = (len(acciones), None)
            acciones.append(Accion(n, NUEVO, f"[{ultimo}] {nombre} [{codigo}] de {proveedor}",
                                   producto=producto, tmpl=clave_nueva, proveedor=valores_prov,
                                   avisos=avisos))
            por_barcode[codigo] = clave_nueva
            por_referencia[str(ultimo)] = clave_nueva
            elegir_con[clave_nueva] = str(ultimo)
            buscador.agregar(clave_nueva, nombre)
            buscador.agregar(clave_nueva, descripcion)
            es_suyo(clave_nueva, kprov)
            barcode_de[clave_nueva] = codigo
            nombre_de[clave_nueva] = nombre
            vistos.add((kprov, clave_nueva))
            nuevo_prov = {"id": None, "tmpl": clave_nueva, **valores_prov}
            por_prov_y_producto[(kprov, clave_nueva)] = nuevo_prov
            if codigo_prov:
                por_codigo_prov[(kprov, codigo_prov)] = nuevo_prov
            elif descripcion:
                por_descripcion[(kprov, _clave(descripcion))] = nuevo_prov
            continue

        # Producto existente: completar el código de barras si corresponde
        completar, propio_anterior = None, None
        actual = barcode_de.get(tmpl)
        if tipo == FABRICANTE and actual != codigo:
            duenio = por_barcode.get(codigo)
            if duenio is not None and duenio != tmpl:
                revisar(f"el código de fábrica {codigo} ya es de «{nombre_de.get(duenio, duenio)}»: "
                        f"no puede ser también de «{nombre_de.get(tmpl, tmpl)}»", tmpl=tmpl)
                continue
            if not actual:
                completar = codigo
            elif numero_de_codigo_propio(actual):
                # 20/11 (pedido del usuario): el código de fábrica tiene prioridad. El propio queda
                # como alternativo, así la caja sigue leyendo la etiqueta que ya esté pegada. Si
                # otra fila de esta lista le quiere poner otro código de fábrica al mismo producto,
                # se revisan las dos (ver más abajo): son productos distintos.
                completar, propio_anterior = codigo, actual
                por_barcode[codigo] = tmpl  # otra fila con el mismo código es el mismo producto
                avisos.append(f"llega el código de fábrica {codigo}: reemplaza al propio {actual}, que queda "
                              "como alternativo (la caja lo sigue leyendo)")

        existente = por_prov_y_producto.get((kprov, tmpl))
        if existente is None:
            if volvio:
                datos_fila[n]["costo_anterior"] = volvio.get("price")  # el último que tuvo
                detalle = f"{nombre_de[tmpl]}: vuelve a la lista de {proveedor} (su precio se había cerrado)"
            else:
                detalle = f"{nombre_de[tmpl]}: se agrega el proveedor {proveedor}"
            primera_accion[(kprov, tmpl)] = (len(acciones), None)
            acciones.append(Accion(n, VINCULAR, detalle,
                                   tmpl=tmpl, proveedor=valores_prov, completar_barcode=completar,
                                   codigo_propio_anterior=propio_anterior,
                                   avisos=avisos, vuelve=bool(volvio)))
            nuevo_prov = {"id": None, "tmpl": tmpl, **valores_prov}
            buscador.agregar(tmpl, descripcion)
            es_suyo(tmpl, kprov)
            por_prov_y_producto[(kprov, tmpl)] = nuevo_prov
            if codigo_prov:
                por_codigo_prov[(kprov, codigo_prov)] = nuevo_prov
            elif descripcion:
                por_descripcion[(kprov, _clave(descripcion))] = nuevo_prov
            continue
        if existente["id"] is None or existente["id"] in precios_usados:
            if _otra_presentacion(existente, valores_prov):
                # El mismo producto en otra presentación (otro código del proveedor u otro bulto:
                # «Display box x 20», «Quarter pallet»): no es un error. Se carga la primera y esta
                # queda en la lista, a la vista, sin pedir que se corrija (30/10).
                primera = existente.get("product_name") or ""
                bulto_otra = valores_prov.get("comercio_bulto")
                de_a = f", de a {bulto_otra:g}" if bulto_otra else ""
                presentaciones.setdefault((kprov, tmpl), []).append(
                    f"{descripcion} (código {codigo_prov or '-'}{de_a}, {costo:g})")
                acciones.append(Accion(n, SIN_CAMBIOS, f"Otra presentación de «{primera}» "
                                       f"({proveedor}): {descripcion} (código {codigo_prov or '-'}"
                                       + (f", de a {valores_prov['comercio_bulto']:g}"
                                          if valores_prov.get("comercio_bulto") else "") + ")",
                                       tmpl=tmpl if isinstance(tmpl, int) else None, avisos=avisos))
                continue
            if (valores_prov.get("product_code") or "") != (existente.get("product_code") or "") and codigo:
                # Con el código de fábrica que le pondría al producto: si es distinto del de la otra
                # fila, las dos pasan a «¿Es el mismo?» (_revisar_codigos_de_fabrica_distintos)
                primera = existente.get("product_name") or ""
                acciones.append(Accion(n, REVISAR, f"el código de barras {codigo} está en dos productos "
                                       f"distintos de la lista de {proveedor} («{primera}»): se usa la "
                                       "primera fila", tmpl=tmpl, completar_barcode=completar, avisos=avisos))
                continue
            # También si ya era nuestro: la segunda fila con el mismo código no cambia nada
            revisar(f"el producto aparece dos veces en la lista de {proveedor}: se usa la primera fila")
            continue
        precios_usados.add(existente["id"])
        datos_fila[n]["costo_anterior"] = existente.get("price")
        datos_fila[n]["mayor_anterior"] = existente.get("comercio_precio_mayor") or None
        cambios = {k: v for k, v in valores_prov.items()
                   if k not in ("partner", "partner_id") and _distinto(existente.get(k), v)}
        if "uom_id" in cambios and not existente.get("uom_id") and not existente.get("unidad_propia"):
            cambios.pop("uom_id")  # foto sin unidades (herramienta vieja): no es un cambio
        if cambios or completar:
            texto = ", ".join(f"unidad de compra → {compra[1]}" if k == "uom_id" and compra
                              else f"{k}: {existente.get(k)!r} → {v!r}" for k, v in cambios.items())
            if completar:
                texto = ", ".join(filter(None, [texto, f"código de barras → {completar}"]))
            historial = "price" in cambios and existente.get("date_start") != foto.hoy
            if historial:
                texto += " (el precio anterior queda en el historial)"
            primera_accion[(kprov, tmpl)] = (len(acciones), existente)
            acciones.append(Accion(n, ACTUALIZAR, f"{nombre_de[tmpl]} ({proveedor}): {texto}", tmpl=tmpl,
                                   proveedor=({**valores_prov, "date_start": foto.hoy} if historial
                                              else cambios),
                                   proveedor_id=existente["id"], historial=historial,
                                   cambia_unidad="uom_id" in cambios,
                                   completar_barcode=completar, codigo_propio_anterior=propio_anterior,
                                   avisos=avisos))
            existente.update(cambios)
        else:
            primera_accion[(kprov, tmpl)] = (len(acciones), existente)
            acciones.append(Accion(n, SIN_CAMBIOS, f"{nombre_de[tmpl]} ({proveedor})", tmpl=tmpl,
                                   proveedor_id=existente["id"], avisos=avisos))

    _revisar_codigos_de_fabrica_distintos(acciones, nombre_de)
    for a in acciones:
        for clave, valor in datos_fila.get(a.fila, {}).items():
            setattr(a, clave, valor)
    _anotar_presentaciones(acciones, primera_accion, presentaciones)

    if lista_completa_de:
        if isinstance(lista_completa_de, int):
            kprov, nombre_prov = f"#{lista_completa_de}", socios.get(lista_completa_de, "")
        else:
            kprov, nombre_prov = clave_de_fila(lista_completa_de, None), lista_completa_de
        actuales = [s for s in foto.proveedores_producto if _clave_prov(s) == kprov
                    and (lista_id is None or s.get("lista_id") == lista_id
                         or (not s.get("lista_id") and not otras_listas))]
        faltan = [s for s in actuales if (kprov, s["tmpl"]) not in vistos]
        if faltan and len(actuales) >= 4 and filas_del_proveedor < MINIMO_LISTA_COMPLETA * len(actuales):
            acciones.append(Accion(
                0, REVISAR, f"La lista trae {filas_del_proveedor} productos y {nombre_prov} tiene "
                f"{len(actuales)}: no se calculan bajas (¿archivo cortado o columnas mal elegidas?)"))
        elif (faltan and len(actuales) >= 4
              and len(actuales) - len(faltan) < MINIMO_COINCIDENCIAS * len(actuales)):
            # Archivo con otros productos del mismo proveedor (otra parte de su lista): darlos de
            # baja cerraría precios que no tienen nada que ver
            acciones.append(Accion(
                0, REVISAR, f"De los {len(actuales)} productos de esta lista de {nombre_prov} solo "
                f"{len(actuales) - len(faltan)} vienen en el archivo: no se calculan bajas. ¿Es otra parte "
                "de su lista? Descartá esta importación y subila con «Es otra parte»."))
        else:
            for s in faltan:
                acciones.append(Accion(
                    0, BAJA, f"{nombre_de.get(s['tmpl'], s['tmpl'])}: ya no está en la lista de "
                    f"{nombre_prov} (se cierra su precio)", tmpl=s["tmpl"], proveedor_id=s["id"],
                    codigo_proveedor=s.get("product_code") or "", descripcion=s.get("product_name") or "",
                    costo_anterior=s.get("price")))
    return acciones


# Palabras que dicen que una fila es otra presentación del mismo producto (no otro producto)
_PRESENTACION = re.compile(
    r"\b(display|box|pallet|caja|cajas|pack|blister|blíster|bulto|master|x\s*\d+\s*(u|un|unid))\b",
    re.IGNORECASE)


def _separar_barras_repetidas(filas: list[dict]) -> list[dict]:
    """El mismo código de barras de fábrica en dos productos distintos de una lista (Chi: la
    dicroica común y la black): el primero se lo queda y los otros se cargan sin él (reciben uno
    propio; el de la lista queda como pista para escanear el del envase en «Códigos de fábrica»).
    No toca las otras presentaciones del mismo producto ni las filas con el mismo código del
    proveedor (eso lo resuelve el plan). Devuelve copias: las filas originales no cambian."""
    salida, primero = [], {}
    for fila in filas:
        fila = dict(fila)
        barras = "".join(ch for ch in str(fila.get("codigo_barras") or "") if ch.isdigit())
        if barras:
            clave = (fila.get("proveedor_id") or fila.get("proveedor"), barras)
            otra = primero.setdefault(clave, fila)
            mismo_codigo = (otra.get("codigo_proveedor") or "") == (fila.get("codigo_proveedor") or "")
            if otra is not fila and not mismo_codigo and not _PRESENTACION.search(
                    str(fila.get("descripcion_proveedor") or "")):
                fila["codigo_lista"] = barras
                fila["codigo_barras"] = ""
                nombre_otra = otra.get("descripcion_proveedor")
                fila["aviso_barras"] = (
                    f"el código de barras {barras} también está en «{nombre_otra}» (otro producto de la "
                    "lista): ese se lo queda y este recibe uno propio; escanear el del envase en «Códigos "
                    "de fábrica»")
        salida.append(fila)
    return salida


def _anotar_presentaciones(acciones: list, primera_accion: dict, presentaciones: dict) -> None:
    """Las otras presentaciones de un producto quedan en el precio de su primera fila
    («comercio_presentaciones»): la orden de compra las nombra en el aviso del bulto."""
    for clave, (indice, existente) in primera_accion.items():
        texto = " · ".join(presentaciones.get(clave, [])) or False
        antes = (existente or {}).get("comercio_presentaciones") or False
        a = acciones[indice]
        if a.tipo in (NUEVO, VINCULAR) or (a.tipo == ACTUALIZAR and a.historial):
            if texto:
                a.proveedor["comercio_presentaciones"] = texto
        elif existente is not None and "comercio_presentaciones" in existente and texto != antes:
            if a.tipo == SIN_CAMBIOS:
                a.tipo, a.proveedor = ACTUALIZAR, {}
                a.detalle += " : otras presentaciones actualizadas"
            a.proveedor["comercio_presentaciones"] = texto


def _otra_presentacion(primera: dict, fila: dict) -> bool:
    """La fila es el mismo producto que `primera` pero en otra presentación: el mismo código con
    otro bulto, u otro código cuya descripción lo dice («display box x 20», «quarter pallet»). Dos
    descripciones distintas sin eso son dos productos con el mismo código de barras (un error de la
    lista): se revisa. Una fila repetida de verdad tiene código y bulto iguales."""
    mismo_codigo = (fila.get("product_code") or "") == (primera.get("product_code") or "")
    otro_bulto = _distinto(primera.get("comercio_bulto") or 0.0, fila.get("comercio_bulto") or 0.0)
    if mismo_codigo:
        return otro_bulto
    return bool(_PRESENTACION.search(fila.get("product_name") or ""))


def _distinto(actual, nuevo) -> bool:
    if isinstance(nuevo, float) or isinstance(actual, float):
        return abs(float(actual or 0) - float(nuevo or 0)) > 1e-6
    return (actual or False) != (nuevo or False)


def _revisar_codigos_de_fabrica_distintos(acciones: list[Accion], nombre_de: dict) -> None:
    """Varias filas de la lista le quieren poner códigos de fábrica distintos al mismo producto
    nuestro (p. ej. guantes de cuatro marcas unidos a un guante genérico, 20/11): son productos
    distintos, y como mucho uno es el nuestro. No se aplica ninguna: las revisa una persona."""
    por_producto: dict = {}
    for i, a in enumerate(acciones):
        if a.completar_barcode and a.tmpl is not None:
            por_producto.setdefault(a.tmpl, []).append(i)
    for tmpl, indices in por_producto.items():
        codigos = {acciones[i].completar_barcode for i in indices}
        if len(codigos) < 2:
            continue
        nombre = nombre_de.get(tmpl, tmpl)
        for i in indices:
            a = acciones[i]
            # «¿Es el mismo?» con ese producto como único parecido: la persona elige en cuál sí
            # (Es el mismo) y las demás se agregan como nuevas
            acciones[i] = Accion(a.fila, POSIBLE_DUPLICADO, (
                f"{len(indices)} filas de esta lista traen códigos de fábrica distintos "
                f"({', '.join(sorted(codigos))}) para «{nombre}»: son productos distintos. Como mucho "
                "una es «Es el mismo»; las demás, «Agregar como nuevo»"),
                candidatos=[Candidato(tmpl, str(nombre), 1.0)], avisos=list(a.avisos))


def es_automatico(a: Accion, tope: float) -> bool:
    """¿Se puede aplicar sin que nadie lo mire? Solo actualizaciones de un proveedor que ya
    estaba vinculado, sin tocar el código de barras, con una variación de costo de hasta
    `tope` (0.1 = 10 %). Lo nuevo, los posibles duplicados, las bajas y lo dudoso esperan."""
    if a.tipo != ACTUALIZAR or a.completar_barcode or a.cambia_unidad:
        return False
    # El precio por mayor sigue la misma regla; si aparece o desaparece, lo mira una persona
    antes, despues = a.mayor_anterior or 0, a.costo_mayor or 0
    if antes != despues and (not antes or not despues or abs(despues / antes - 1) > tope):
        return False
    if "price" not in (a.proveedor or {}):
        return True  # cambió la descripción, el mínimo o el plazo, no el costo
    return a.variacion is not None and abs(a.variacion) <= tope
