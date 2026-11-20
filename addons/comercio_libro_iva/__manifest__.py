{
    "name": "Comercio: menú del Libro de IVA",
    "summary": "Menú «Libro de IVA» en Facturación → Reportes → Impuestos y finanzas.",
    "description": """
Pedido del 09/11. En Odoo 20 el Libro de IVA (variante argentina de la «Declaración fiscal»,
account_reports.action_account_report_gt) no tiene menú: el de «Reporte fiscal» abre otro informe.
Solo agrega el menú; el informe y su exportación (ZIP con los TXT del Libro IVA Digital) son de
l10n_ar_reports.
""",
    "version": "20.0.1.0.0",
    "category": "Accounting/Localizations/Reporting",
    "license": "OPL-1",
    "depends": ["account_reports", "l10n_ar_reports"],
    "data": ["data/menu.xml"],
    "installable": True,
}
