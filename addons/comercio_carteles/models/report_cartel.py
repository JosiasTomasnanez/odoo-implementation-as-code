from odoo import api, models


class ReportCartel(models.AbstractModel):
    _name = "report.comercio_carteles.cartel_a4"
    _description = "Carteles de precio en A4"

    @api.model
    def _get_report_values(self, docids, data=None):
        carteles = self.env["comercio.cartel"].browse(docids)
        return {"doc_ids": docids, "doc_model": "comercio.cartel", "docs": carteles, "hojas": carteles._hojas()}
