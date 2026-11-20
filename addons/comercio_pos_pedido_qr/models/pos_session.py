import logging

from markupsafe import Markup

from odoo import _, api, models

_logger = logging.getLogger(__name__)


class PosSession(models.Model):
    _inherit = "pos.session"

    def _comercio_pedidos_pendientes(self, domain):
        return self.env["pos.order"].search(
            [("state", "=", "draft"), ("comercio_en_caja", "=", True),
             ("company_id", "=", self.company_id.id), *domain]
        )

    def _comercio_hay_caja_abierta(self):
        return bool(self.search_count([
            ("state", "=", "opened"),
            ("company_id", "=", self.company_id.id),
            ("config_id.comercio_arma_pedidos", "=", False),
        ]))

    def _comercio_cancelar(self, pedidos, motivo):
        if not pedidos:
            return
        pedidos.write({"state": "cancel"})
        for pedido in pedidos:
            pedido.message_post(body=motivo)
        enlaces = Markup().join(Markup("<li>%s</li>") % p._get_html_link() for p in pedidos)
        self.message_post(body=Markup("%s<ul>%s</ul>") % (motivo, enlaces))

    def close_session_from_ui(self, payment_method_closing={}):  # noqa: B006 (firma de Odoo)
        self.ensure_one()
        if self.config_id.comercio_arma_pedidos:
            pendientes = self._comercio_pedidos_pendientes([("session_id", "=", self.id)])
            if pendientes and self._comercio_hay_caja_abierta():
                # Resguardo: el cliente puede estar en la fila de la caja. El pedido se
                # desprende del puesto (como hace Odoo con los pedidos programados) y la
                # caja lo sigue pudiendo cobrar; se cancela al cerrar la caja.
                pendientes.session_id = False
                self.message_post(body=_(
                    "Pedidos enviados a caja sin cobrar al cerrar el puesto (la caja los "
                    "puede seguir cobrando hasta su cierre): %s",
                    ", ".join(pendientes.mapped("pos_reference")),
                ))
            else:
                self._comercio_cancelar(pendientes, _(
                    "Pedido cancelado al cerrar el puesto: se envió a caja y no se cobró."))
            return super().close_session_from_ui(payment_method_closing)

        resultado = super().close_session_from_ui(payment_method_closing)
        if resultado.get("status") and not self._comercio_hay_caja_abierta():
            # Fin del día: se cancelan los pedidos de puestos que nadie cobró.
            self._comercio_cancelar(
                self._comercio_pedidos_pendientes([("session_id", "=", False)]),
                _("Pedido cancelado al cerrar la caja: se envió a caja y no se cobró."),
            )
        return resultado

    @api.model
    def _cron_comercio_cerrar_puestos(self):
        """Cierra los puestos que quedaron abiertos. Los puestos no manejan plata; la caja
        nunca se cierra sola porque su cierre lleva el conteo del efectivo."""
        sesiones = self.search([
            ("state", "=", "opened"), ("config_id.comercio_arma_pedidos", "=", True),
        ])
        for sesion in sesiones:
            try:
                with self.env.cr.savepoint():
                    resultado = sesion.close_session_from_ui()
            except Exception as error:  # noqa: BLE001 (un puesto que falla no frena a los demás)
                _logger.exception("No se pudo cerrar automáticamente %s", sesion.name)
                sesion.message_post(body=_("No se pudo cerrar automáticamente: %s", error))
                continue
            if resultado.get("status"):
                sesion.message_post(body=_("Puesto cerrado automáticamente por la noche."))
            else:
                sesion.message_post(body=_(
                    "No se pudo cerrar automáticamente: %s", resultado.get("message")))
