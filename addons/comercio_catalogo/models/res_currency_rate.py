from odoo import _, api, models


class ResCurrencyRate(models.Model):
    """Pantalla «Dólar» de Costos y precios (30/10, pedido del cliente): cargar a mano la
    cotización del día (el dólar cambia seguido) y recalcular las listas en dólares."""

    _inherit = "res.currency.rate"

    @api.model
    def default_get(self, fields_list):
        valores = super().default_get(fields_list)
        if self.env.context.get("comercio_dolar") and "currency_id" in fields_list:
            valores["currency_id"] = self.env.ref("base.USD").id  # pantalla «Dólar»
        return valores

    @api.model
    def action_comercio_recalcular_listas(self):
        """Botón «Recalcular listas en dólares»: con la última cotización cargada."""
        hechas = self.env["comercio.lista.proveedor"]._recalcular_dolar()
        if not hechas:
            mensaje = _("No hay listas en dólares para recalcular: ya están calculadas con esta cotización "
                        "(o la diferencia es menor a 0,5 %), o todavía tienen filas sin revisar.")
        else:
            mensaje = _("Se recalcularon %s listas en dólares. Los cambios chicos se aplicaron solos; los "
                        "grandes esperan revisión en «Importaciones».", hechas)
        return {"type": "ir.actions.client", "tag": "display_notification",
                "params": {"message": mensaje, "type": "success" if hechas else "info", "sticky": False}}
