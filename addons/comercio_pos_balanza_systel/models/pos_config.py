from odoo import _, api, fields, models
from odoo.exceptions import ValidationError


class PosConfig(models.Model):
    _inherit = "pos.config"

    comercio_balanza_numero = fields.Integer(
        string="Número de la balanza Systel",
        default=1,
        help="Número de identificación configurado en el menú de la balanza (1 a 99). "
        "El POS lo usa para pedirle el peso por USB.",
    )
    comercio_pesaje_automatico = fields.Boolean(
        string="Pesaje automático",
        default=True,
        help="Con una balanza Systel conectada, el producto pesable se agrega solo cuando "
        "el peso queda estable, sin tocar «Pedido». Apagado, el peso se ve en vivo y se "
        "agrega con «Pedido» o Enter: para ir agregando o sacando hasta el peso pedido.",
    )

    @api.constrains("comercio_balanza_numero")
    def _check_comercio_balanza_numero(self):
        for config in self:
            if not 1 <= config.comercio_balanza_numero <= 99:
                raise ValidationError(_("El número de la balanza va de 1 a 99 (menú de la balanza: "
                                        "Configuración → Conectividad → Identificación)."))
