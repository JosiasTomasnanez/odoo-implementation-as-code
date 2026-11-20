"""Los puestos que «cobran en la registradora» no hacen contabilidad: la venta contable es el cierre Z.

En Odoo 20, al cerrar una sesión el punto de venta crea un comprobante de cierre (factura interna
en el diario de cierre, sin documento fiscal) con las ventas y el IVA, y un cobro por cada medio de
pago. En los puestos todo se «cobra» con «Cobrado en registradora» (ADR 0019), que no es plata: si
además se carga el Z, la venta y el IVA quedarían dos veces.

Por eso, apenas se hace la contabilidad de una sesión de puesto (todos sus pagos con el medio de la
registradora), se anula su efecto contable: se anulan los cobros de «Cobrado en registradora» y cada
comprobante de cierre se revierte con su nota de crédito (queda a la vista, conciliado). El stock no
cambia (lo mueven los pedidos) y los pedidos siguen en los reportes del punto de venta.
"""

import logging

from markupsafe import Markup

from odoo import _, api, fields, models
from odoo.exceptions import AccessError, UserError

_logger = logging.getLogger(__name__)


class PosSession(models.Model):
    _inherit = "pos.session"

    comercio_contable_anulado = fields.Boolean(
        "Sin efecto contable (lo vende el Z)", readonly=True, copy=False,
        help="Puesto que cobra en la registradora: su comprobante de cierre se revirtió y sus cobros se anularon, "
        "porque la venta contable es el cierre Z de la registradora.")

    def _validate_session_accounting(self):
        resultado = super()._validate_session_accounting()
        self._comercio_anular_contable_puesto()
        return resultado

    def _comercio_metodos_registradora(self):
        return self.env["pos.config"].sudo().with_context(active_test=False).search([]).mapped(
            "comercio_metodo_registradora_id")

    def _comercio_solo_registradora(self, metodos):
        pagos = self.order_ids.payment_ids
        return bool(pagos) and all(p.payment_method_id in metodos for p in pagos)

    def _comercio_anular_contable_puesto(self):
        metodos = self._comercio_metodos_registradora()
        if not metodos:
            return 0
        anuladas = 0
        for sesion in self.sudo().filtered(lambda s: not s.comercio_contable_anulado):
            comprobantes = (sesion.sale_move_ids | sesion.refund_move_ids).filtered(lambda m: m.state == "posted")
            if not comprobantes or not sesion._comercio_solo_registradora(metodos):
                continue
            if comprobantes.reversal_move_ids:
                # Algún pedido se facturó después del cierre y Odoo ya lo sacó del cierre: revertir todo
                # lo descontaría dos veces. Pasa solo con sesiones de antes de este módulo; se revisa a mano.
                sesion.message_post(body=_(
                    "No se dejó sin efecto contable: algún pedido de esta sesión se facturó después del cierre. "
                    "Revisarlo a mano (P-070)."))
                continue
            pagos = self.env["account.payment"].sudo().search([
                ("pos_session_id", "=", sesion.id), ("pos_payment_method_id", "in", metodos.ids),
                ("state", "!=", "canceled")])
            pagos.move_id.line_ids.remove_move_reconcile()
            pagos.action_draft()
            pagos.action_cancel()
            notas = self.env["account.move"]
            for comprobante in comprobantes:
                notas |= comprobante._reverse_moves([{
                    "date": comprobante.date, "invoice_date": comprobante.invoice_date or comprobante.date,
                    "ref": _("Puesto: lo vende el cierre Z de la registradora (%s)", comprobante.name),
                    # que la nota de crédito no pase a ser otro «cierre» de la sesión
                    "pos_session_sales_id": False, "pos_session_refunds_id": False,
                }], cancel=True)
            sesion.comercio_contable_anulado = True
            enlaces = Markup(", ").join(n._get_html_link() for n in notas)
            sesion.message_post(body=Markup("%s %s") % (_(
                "Sin efecto contable: este puesto cobra en la registradora y la venta contable es su cierre Z. "
                "Se anularon los cobros de «Cobrado en registradora» y se revirtió el cierre con:"), enlaces))
            anuladas += 1
        return anuladas

    @api.model
    def comercio_anular_puestos_anteriores(self):
        """Para las sesiones de puestos que se cerraron antes de instalar este módulo. Idempotente.
        Se puede llamar por la API: solo un responsable de contabilidad (anula cobros y revierte cierres)."""
        if not self.env.user.has_group("account.group_account_manager"):
            raise AccessError(_("Solo un responsable de contabilidad puede dejar sin efecto contable los puestos."))
        sesiones = self.search([("comercio_contable_anulado", "=", False),
                                "|", ("sale_move_ids", "!=", False), ("refund_move_ids", "!=", False)])
        cantidad = sesiones._comercio_anular_contable_puesto()
        _logger.info("Cierre Z: %s sesiones de puestos quedaron sin efecto contable", cantidad)
        return cantidad


class PosOrder(models.Model):
    _inherit = "pos.order"

    def _generate_invoice_after_session_closing(self):
        """Un pedido de un puesto sin efecto contable ya lo documenta el tique de la registradora (su Z):
        facturarlo además con CAE lo documentaría dos veces y Odoo lo descontaría otra vez del cierre."""
        if self.session_id.comercio_contable_anulado:
            raise UserError(_(
                "%s es de un puesto que cobra en la registradora: lo documenta el tique de la registradora "
                "(su cierre Z). Si el cliente necesita factura, se hace en la registradora o en 3C.",
                self.pos_reference or self.name))
        return super()._generate_invoice_after_session_closing()
