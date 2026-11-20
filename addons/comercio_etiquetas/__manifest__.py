{
    "name": "Comercio: etiquetas para la Zebra",
    "summary": "Etiqueta ZPL propia (nombre en dos líneas, código de barras angosto, medida del rollo "
    "configurable) para imprimir directo en la Zebra por la IoT de Odoo.",
    "description": """
Ver ADR 0030 y P-062 en el repositorio de la implementación.

- «Imprimir etiquetas» → formato «Etiquetas ZPL» → plantilla «Comercio Ejemplo»: el nombre en
  hasta dos líneas (la de Odoo lo corta en una), el código de barras en Code 128 modo
  automático (los números van de a pares: entra en etiquetas chicas y se lee mejor), la
  referencia interna y el precio.
- «Rollo» al imprimir: cada tipo de rollo (nombre, ancho y alto en mm) se declara en
  config/valores.yaml → etiquetas.rollos; la etiqueta se acomoda a la medida del elegido y cada
  usuario vuelve a ver el último que usó. Quien administra productos (Gerencia) puede crear
  un rollo nuevo desde ese mismo campo («Crear y editar…»).
- Impresión directa (sin descargar): la hace la IoT de Odoo (módulo iot) con la Zebra
  conectada por USB a una PC Windows; la etiqueta ZPL se vincula a esa impresora
  (docs/runbooks/etiquetas-zebra.md).
""",
    "version": "20.0.1.2.0",
    "category": "Inventory/Inventory",
    "license": "LGPL-3",
    "depends": ["product"],
    "data": [
        "security/ir.access.csv",
        "report/etiqueta_zpl.xml",
        "views/product_label_layout_views.xml",
    ],
    "installable": True,
}
