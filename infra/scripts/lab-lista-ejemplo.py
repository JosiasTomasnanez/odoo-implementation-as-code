"""Carga en el lab la lista de ejemplo de «[EJ] Ferretera Ejemplo» (FICTICIA, parecida a FC),
para mostrarle al negocio cómo se lee una lista y cómo se llega del precio de la lista al costo.

Tres partes, una por hoja de data/ejemplos/listas/ferretera-ejemplo-1.xlsx
(infra/scripts/generar-lista-ejemplo.py):

- General: pesos sin IVA; 5 % de descuento para toda la lista, 2,5 % de flete; la columna
  «Desc. %» del proveedor (ofertas); «Promociones vigentes» en texto (el martillo 5 % por
  unidad, el destornillador por cantidad); 10 % extra para la familia «TORNILLO» y 3 % para
  el martillo (EJ-4001). La columna «PRECIO FINAL (cálculo interno)» es del comercio: no se usa.
- Bulones: dos precios (suelto y por caja cerrada); 10 % extra para «TUERCA».
- Importados: dólares con IVA incluido y alícuota por fila; dólar del día (ARCA).

De cada parte se agregan a nuestro catálogo algunos productos (como haría el negocio con lo
que vende). La versión 2 (ferretera-ejemplo-2.xlsx) queda para subirla a mano y ver subas,
bajas, uno nuevo y el «formato cambiado» (docs/runbooks/prueba-visual.md, sección 2).
Idempotente: si la parte ya tiene una importación, no la repite.

Uso: .venv/bin/python infra/scripts/lab-lista-ejemplo.py   (o make lab-completo)
"""
from __future__ import annotations

import base64
import sys
from pathlib import Path

from odoo_iac.client import connect
from odoo_iac.settings import load_environment

RAIZ = Path(__file__).resolve().parents[2]
ARCHIVO = RAIZ / "data" / "ejemplos" / "listas" / "ferretera-ejemplo-1.xlsx"
PROVEEDOR = "[EJ] Ferretera Ejemplo"
RUBRO = "[EJ] Ferretería"
LINEA = "comercio.lista.importacion.linea"
# (parte, valores de la lista, reglas (tipo, texto o código, descuentos, nota), qué agregar al catálogo)
PARTES = [
    ("General", {
        "hoja": "Lista general",
        "col_codigo": "Código", "col_descripcion": "Detalle + Descripción del producto",
        "col_barras": "Código de barras", "col_costo": "Precio de lista", "col_descuento": "Desc. %",
        "col_promocion": "Promociones vigentes",
        "descuentos": "5", "recargo": 2.5,
    }, [("familia", "TORNILLO", "10", "Ejemplo: 10 % extra en tornillos"),
        ("producto", "EJ-4001", "3", "Ejemplo: acuerdo puntual por el martillo")],
     ["Martillo", "Pinza", "Tornillo", "Abrazadera", "Candado bronce 40", "Destornillador"]),
    ("Bulones", {
        "hoja": "Bulones",
        "col_codigo": "Código", "col_descripcion": "Detalle + Descripción / medidas",
        "col_costo": "Precio Unit. sin IVA", "col_costo_mayor": "Precio x caja (c/u)",
        "col_cantidad_mayor": "Unidades x caja",
        "descuentos": "5", "recargo": 2.5,
    }, [("familia", "TUERCA", "10", "Ejemplo: 10 % extra en tuercas")],
     ["Bulón cabeza", "Tuerca"]),
    ("Importados", {
        "hoja": "Importados USD",
        "col_codigo": "Código", "col_descripcion": "Descripción",
        # «c/IVA»: no se sugiere solo como costo (podría ser un precio del comercio); se elige a mano
        "col_costo": "Precio U$S c/IVA", "col_iva": "IVA %",
        "moneda": "usd", "trae_iva": True, "iva_por_defecto": 21,
    }, [], ["Taladro", "Amoladora"]),
]

c = connect(load_environment("lab"))


def proveedor() -> int:
    encontrado = c.search_read("res.partner", [("name", "=", PROVEEDOR)], ["id"])
    if encontrado:
        return encontrado[0]["id"]
    return c.create("res.partner", {"name": PROVEEDOR, "is_company": True, "supplier_rank": 1})


def lista(socio: int, parte: str, valores: dict, reglas: list, rubro: int) -> int:
    valores = {**valores, "partner_id": socio, "parte": parte, "categoria_id": rubro, "unidad_fija": "u",
               "familia_en_descripcion": False}
    existente = c.search_read("comercio.lista.proveedor", [("partner_id", "=", socio), ("parte", "=", parte)],
                              ["id"])
    if existente:
        lista_id = existente[0]["id"]
        c.write("comercio.lista.proveedor", [lista_id], valores)
    else:
        lista_id = c.create("comercio.lista.proveedor", valores)
    for tipo, texto, descuentos, nota in reglas:
        campo = "contiene" if tipo == "familia" else "codigo"
        dominio = [("lista_id", "=", lista_id), (campo, "=", texto)]
        existe = c.search_read("comercio.lista.regla", dominio, ["id"])
        if not existe:
            c.create("comercio.lista.regla", {"lista_id": lista_id, "tipo": tipo, campo: texto,
                                              "descuentos": descuentos, "nota": nota})
    return lista_id


def agregar(importacion: int, palabras: str) -> int:
    filas = c.search_read(LINEA, [("importacion_id", "=", importacion), ("accion", "=", "nuevo"),
                                  ("estado", "=", "pendiente"), ("descripcion", "ilike", palabras)], ["id"])
    if filas:
        c.call(LINEA, "action_aplicar", [f["id"] for f in filas])
    return len(filas)


def main() -> int:
    if not ARCHIVO.exists():
        print(f"Falta {ARCHIVO.relative_to(RAIZ)}: correr infra/scripts/generar-lista-ejemplo.py",
              file=sys.stderr)
        return 1
    rubro = c.search_read("product.category", [("name", "=", RUBRO)], ["id"])
    if not rubro:
        print(f"Falta la categoría «{RUBRO}»: correr antes `make apply`.", file=sys.stderr)
        return 1
    rubro = rubro[0]["id"]
    if not c.search_read("res.currency.rate", [("currency_id.name", "=", "USD")], ["id"], limit=1):
        # La parte en dólares necesita la cotización: la de ARCA homologación (de prueba, no la real)
        empresa = c.search_read("res.company", [("parent_id", "=", False)], ["id"])[0]["id"]
        c.call("res.company", "update_currency_rates", [empresa])
    socio = proveedor()
    for parte, valores, reglas, a_agregar in PARTES:
        lista_id = lista(socio, parte, valores, reglas, rubro)
        if c.search_read("comercio.lista.importacion", [("lista_id", "=", lista_id)], ["id"], limit=1):
            print(f"- {PROVEEDOR} ({parte}): ya tenía una importación (no se repite)")
            continue
        wizard = c.create("comercio.importar.lista.wizard", {
            "partner_id": socio, "lista_id": lista_id, "categoria_id": rubro, "nombre_archivo": ARCHIVO.name,
            "archivo": base64.b64encode(ARCHIVO.read_bytes()).decode()})
        importacion = c.call("comercio.importar.lista.wizard", "action_importar", [wizard])["res_id"]
        datos = c.read("comercio.lista.importacion", [importacion],
                       ["estado", "cant_total", "cant_revisar", "error", "cotizacion_usada"])[0]
        if datos["estado"] == "error":
            print(f"- {PROVEEDOR} ({parte}): ERROR {datos['error']}", file=sys.stderr)
            continue
        agregados = sum(agregar(importacion, palabras) for palabras in a_agregar)
        dolar = f", dólar {datos['cotizacion_usada']:.2f}" if datos["cotizacion_usada"] else ""
        print(f"- {PROVEEDOR} ({parte}): {datos['cant_total']} filas ({datos['estado']}), "
              f"{datos['cant_revisar']} para revisar, {agregados} agregados a nuestro catálogo{dolar}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
