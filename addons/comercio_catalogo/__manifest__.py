{
    "name": "Comercio: listas de precios de proveedores",
    "summary": "Importar las listas de los proveedores desde Odoo: simular, revisar y aplicar; "
    "actualización automática por proveedor.",
    "description": """
Ver docs/areas/codigos.md y ADR 0014/0015 en el repositorio de la implementación.

- Cada proveedor tiene su «lista»: de dónde llega (subida a mano, link fijo o correo),
  cada cuántos días se actualiza y qué columna del Excel es cada dato (se sugiere sola).
- Importar: subir el Excel → simulación con la lista entera comparada con la anterior
  (costo anterior, nuevo y variación) → revisar → aplicar.
- Se aplican solos los cambios de costo hasta un tope (%); lo nuevo, las bajas, los
  posibles duplicados y lo dudoso esperan confirmación («Es el mismo» / «Es nuevo»).
- Historial de costos por proveedor; Odoo compra por defecto al más barato vigente.
- Costo del producto (P-044): al aplicar o deshacer una lista pasa a ser el precio por
  unidad vigente más barato entre sus proveedores (una tarea diaria cubre los precios que
  empiezan o vencen). Si alguien escribe el costo a mano, el producto queda con «Costo
  manual» y las listas no lo cambian hasta que se desmarque.
- Del precio de la lista al costo (catalogo/costo.py): moneda (dólar del día del Banco
  Nación vía ARCA, o fijo), descuentos en cadena de la lista, por familia, por producto y
  de la columna del archivo, recargo e IVA incluido (alícuota de la fila, del producto o de
  la lista). «Recalcular costos» vuelve a leer la última lista con los valores de ahora.
- El motor (códigos, similitud, plan, costo) está en catalogo/ y lo comparte con la
  herramienta de línea de comandos integrations/catalogo.
""",
    "version": "20.0.1.53.0",
    "category": "Inventory/Purchase",
    "license": "LGPL-3",
    "depends": ["product", "mail", "account"],  # account: supplier_rank (proveedores)
    "assets": {"web.assets_backend": ["comercio_catalogo/static/src/filas.scss",
                                      "comercio_catalogo/static/src/cargando.scss"]},
    "data": [
        "security/grupos.xml",
        "security/ir.access.csv",
        "data/ir_cron.xml",
        "wizard/importar_lista_views.xml",
        "wizard/corregir_fila_views.xml",
        "wizard/elegir_mismo_views.xml",
        "wizard/agregar_catalogo_views.xml",
        "wizard/costo_de_views.xml",
        "views/importacion_views.xml",
        "views/lista_proveedor_views.xml",
        "views/product_category_views.xml",
        "views/product_template_views.xml",
        "views/menus.xml",
        "views/busqueda_views.xml",
        "views/dolar_views.xml",
    ],
    "installable": True,
    "application": True,
}
