{
    "name": "Comercio: cierre Z de las registradoras",
    "summary": "Cargar el cierre Z de cada registradora (a mano o leyendo la foto con IA): tique en el "
    "Libro IVA con el rango del día, cobros por medio de pago, y los puestos sin efecto contable.",
    "description": """
Ver ADR 0038 y P-070 en el repositorio de la implementación.

- Contabilidad → Clientes → Cierres Z: un registro por Z (registradora, fecha, número, primer y
  último tique, neto e IVA por alícuota, exento, no gravado, TOTAL y cómo se cobró), con su foto.
- «Leer foto con IA»: Gemini (clave propia del comercio) completa el formulario; siempre se revisa.
- Controles: las sumas tienen que cerrar con el TOTAL del Z, el IVA con su neto y los cobros con el
  total; avisa si falta un Z correlativo, si el número ya está cargado, la diferencia con lo que
  imprimieron los puestos ese día y si la caja de Odoo vendió sin factura ese día.
- Confirmar: comprobante «Tique» en el diario de la registradora (controlador fiscal externo, no va
  a ARCA) con el IVA impreso en el Z y la foto adjunta; un cobro por medio de pago.
- Libro IVA Digital: el comprobante del Z se informa del primer al último tique del día.
- Puestos que cobran en la registradora: su cierre no hace contabilidad (se revierte con nota de
  crédito y se anulan sus cobros), porque la venta contable es el Z. El stock no cambia.
""",
    "version": "20.0.1.0.0",
    "category": "Accounting/Localizations",
    "license": "OPL-1",
    "depends": ["account", "l10n_ar", "l10n_ar_reports", "point_of_sale", "comercio_pos_pedido_qr",
                "comercio_catalogo_ia"],
    "data": [
        "security/ir.access.csv",
        "views/cierre_z_views.xml",
    ],
    "installable": True,
}
