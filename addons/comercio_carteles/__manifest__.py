{
    "name": "Comercio: carteles de precio en A4",
    "summary": "Carteles grandes de precio para imprimir en hojas A4 (1, 2, 4 u 8 por hoja), con el texto "
    "que se quiera, el precio de Odoo (con IVA, redondeado o a mano) y aviso de los que quedaron viejos.",
    "description": """
Pedido del 20/11: hoy los carteles de precio se hacen a mano (fibrón y cartulina).

- «Carteles» (menú propio): cada cartel queda guardado, con su título (el nombre del producto o
  lo que se quiera), una aclaración («x kg», «c/u»), el precio y cómo se arma: el de Odoo con IVA,
  redondeado hacia arriba ($10, $50, $100, $1.000) o escrito a mano; «antes $ X» tachado para
  ofertas; código de barras opcional; copias; tamaño (1, 2, 4 u 8 por A4) y estilo (Clásico u
  Oferta, sobre blanco para no gastar tinta en la cartulina).
- Desde Productos (Acciones → «Hacer carteles») o uno suelto sin producto.
- «Imprimir»: PDF A4 con líneas de corte; guarda el precio impreso.
- «Carteles a actualizar»: los que muestran un precio distinto del que tendrían hoy (cambió el
  precio de venta después de imprimirlos).
- Independiente de los demás módulos propios (solo product y account).
""",
    "version": "20.0.1.1.1",
    "category": "Sales/Sales",
    "license": "LGPL-3",
    "depends": ["product", "account", "mail"],
    "data": [
        "security/ir.access.csv",
        "report/cartel_report.xml",
        "views/cartel_views.xml",
    ],
    "assets": {
        "web.assets_backend": ["comercio_carteles/static/src/cartel.scss"],
        "web.report_assets_common": ["comercio_carteles/static/src/cartel.scss"],
    },
    "installable": True,
    "application": True,
}
