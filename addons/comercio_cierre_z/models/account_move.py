from odoo import fields, models

# REGINFO_CV_VENTAS_CBTE: fecha (8) + tipo (3) + punto de venta (5) + número desde (20) + número hasta (20)
HASTA_DESDE, HASTA_HASTA = 36, 56


class AccountMove(models.Model):
    _inherit = "account.move"

    comercio_cierre_z_id = fields.Many2one("comercio.cierre.z", "Cierre Z", readonly=True, copy=False, index=True)
    comercio_tique_hasta = fields.Integer(
        "Último tique", readonly=True, copy=False,
        help="Comprobante de un cierre Z: el último tique del día. El Libro IVA Digital informa «desde» el número "
        "del comprobante «hasta» este.")


class L10nArTaxReportHandler(models.AbstractModel):
    _inherit = "l10n_ar.tax.report.handler"

    def _vat_book_get_REGINFO_CV_CBTE(self, options, aliquots, tax_type, invoices):
        """Un cierre Z se informa como total diario: «número hasta» = el último tique del día (Odoo pone
        siempre el mismo número que «desde»)."""
        renglones = super()._vat_book_get_REGINFO_CV_CBTE(options, aliquots, tax_type, invoices)
        if tax_type != "sale":
            return renglones
        resultado = []
        for factura, renglon in zip(invoices, renglones, strict=True):
            hasta = factura.comercio_tique_hasta
            if hasta and len(renglon) >= HASTA_HASTA:
                renglon = renglon[:HASTA_DESDE] + f"{hasta:0>20d}" + renglon[HASTA_HASTA:]
            resultado.append(renglon)
        return resultado
