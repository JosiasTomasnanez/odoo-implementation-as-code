from odoo import fields, models


class PosConfig(models.Model):
    _inherit = "pos.config"

    comercio_arma_pedidos = fields.Boolean(
        string="Puesto que arma pedidos (no cobra)",
        help="El botón principal imprime el pedido con un QR para cobrarlo en la caja, "
        "en lugar de «Pago».",
    )
    # P-046, decisión temporal (21/10): mientras las registradoras cobran, el puesto da el
    # pedido por cobrado al imprimirlo, así baja el stock sin sumar trabajo en la caja
    comercio_cobro_en_registradora = fields.Boolean(
        string="Se cobra en la registradora",
        help="Puesto que arma pedidos: «Imprimir pedido» además lo da por cobrado con el medio "
        "«Cobrado en registradora» (baja el stock), sin pedir medio de pago. El ticket sale sin QR.",
    )
    comercio_metodo_registradora_id = fields.Many2one(
        "pos.payment.method", string="Medio «Cobrado en registradora»",
        help="Medio de pago con que el puesto da por cobrado el pedido. Tiene que estar entre los "
        "medios de pago del puesto.",
    )
    # 17/11 (Daniel): precio unitario en el ticket del puesto, en chiquito debajo de la descripción
    comercio_ticket_unitario = fields.Selection(
        [
            ("no", "No"),
            ("siempre", "Siempre"),
            ("si_suma", "Solo si suma información (más de uno o pesado)"),
        ],
        string="Precio unitario en el ticket",
        default="no",
        required=True,
        help="Ticket del puesto: el precio unitario como lo muestra Odoo («$ 450,00 / Unidades») "
        "debajo de la descripción. «Solo si suma información» no lo repite cuando se lleva una unidad.",
    )
