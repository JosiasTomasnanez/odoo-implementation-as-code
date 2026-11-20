from odoo import fields, models


class ResConfigSettings(models.TransientModel):
    _inherit = "res.config.settings"

    pos_comercio_balanza_numero = fields.Integer(
        related="pos_config_id.comercio_balanza_numero", readonly=False
    )
    pos_comercio_pesaje_automatico = fields.Boolean(
        related="pos_config_id.comercio_pesaje_automatico", readonly=False
    )
