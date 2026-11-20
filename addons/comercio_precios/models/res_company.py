from odoo import fields, models


class ResCompany(models.Model):
    _inherit = "res.company"

    comercio_diferencia_chica = fields.Float(
        "Diferencia chica (%)", digits=(16, 1),
        help="Si el precio nuevo cambia hasta este porcentaje (para arriba o para abajo), no vale la pena "
             "cambiarlo: en «Precios a actualizar» sale en naranja y queda oculto. 0: se muestran todos.")
