{
    "name": "Comercio: ventas del punto de venta con y sin factura de Odoo",
    "summary": "Botón «Factura» marcado por defecto en la caja; desmarcado, una franja de color al costado y la venta "
    "queda separada (la factura la emite la registradora o 3C), con su propio listado para el contador.",
    "description": """
Ver ADR 0024 en el repositorio de la implementación.

- Mientras las registradoras sigan en uso, cada venta de la caja elige: con factura de Odoo (con CAE,
  va al Libro IVA Ventas de Odoo) o sin factura de Odoo (el comprobante lo emite la registradora o 3C
  y le llega al contador por ese lado, como hoy).
- Es el botón «Factura» que ya trae Odoo en la pantalla de pago (la localización argentina lo deja
  marcado). Desmarcado, una franja de color al costado de la pantalla de pago (sin carteles), para que la cajera lo note.
- En Punto de venta → Pedidos: filtros «Con factura de Odoo» / «Sin factura de Odoo» y el listado
  «Ventas sin factura de Odoo» (por día y por caja), para mandarle al contador por separado.
- «Facturar con CAE» (administración), en la venta o con varias marcadas en la lista: para lo que quedó
  sin factura de Odoo y no se hizo en la registradora. Siempre en el diario de factura electrónica (el
  «Factura» de Odoo usa el del punto de venta: en un puesto sale un comprobante interno sin CAE; se oculta).
- El Libro IVA de Odoo solo toma lo que Odoo facturó con comprobante: lo de la registradora no se pisa.
""",
    "version": "20.0.1.1.6",
    "category": "Sales/Point of Sale",
    "license": "LGPL-3",
    "depends": ["point_of_sale", "l10n_ar_pos"],
    "data": [
        "views/pos_order_views.xml",
    ],
    "assets": {
        "point_of_sale._assets_pos": [
            "comercio_pos_factura/static/src/app/**/*",
        ],
    },
    "installable": True,
}
