from odoo import _, api, fields, models
from odoo.exceptions import UserError


class PosOrder(models.Model):
    _inherit = "pos.order"

    comercio_en_caja = fields.Boolean(
        string="Enviado a caja",
        help="El puesto imprimió el pedido para cobrarlo en la caja: el puesto ya no lo "
        "vuelve a cargar como pedido abierto.",
        copy=False,
    )

    @api.model
    def _load_pos_data_domain(self, data):
        domain = super()._load_pos_data_domain(data)
        if data["pos.config"].comercio_arma_pedidos:
            domain = [*domain, ("comercio_en_caja", "=", False)]
        return domain

    @api.model
    def comercio_estado_pedido(self, uuid):
        """Estado del pedido en el servidor. La caja lo consulta antes de cobrar, por si
        otra caja ya lo cobró (en el local cobran dos cajas, P-035)."""
        pedido = self.search([("uuid", "=", uuid)], limit=1)
        return pedido.state if pedido else False

    def comercio_cobrar_en_registradora(self):
        """Puesto que «se cobra en la registradora» (P-046, temporal): al imprimir, el pedido
        queda cobrado con el medio «Cobrado en registradora» y se procesa como cualquier venta
        pagada (baja el stock). Si el cliente después no paga o pide otra cosa, es otro ticket."""
        for pedido in self.filtered(lambda p: p.state == "draft"):
            config = pedido.config_id
            metodo = config.comercio_metodo_registradora_id
            if not (config.comercio_arma_pedidos and config.comercio_cobro_en_registradora and metodo):
                raise UserError(_("Este puesto no está configurado para cobrar en la registradora."))
            pedido.add_payment({
                "pos_order_id": pedido.id,
                "session_id": pedido.session_id.id,
                "payment_method_id": metodo.id,
                "amount": pedido._get_rounded_amount(pedido.amount_total),
                "name": _("Cobrado en registradora"),
            })
            pedido._process_saved_order(False)
        return True
