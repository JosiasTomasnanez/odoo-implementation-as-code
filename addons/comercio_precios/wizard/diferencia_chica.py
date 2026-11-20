from odoo import _, fields, models
from odoo.exceptions import UserError


class ComercioDiferenciaChicaWizard(models.TransientModel):
    """La «diferencia chica» de «Precios a actualizar»: se carga una vez para todo el negocio. Lo
    cambia el grupo «Costos y precios» sin ser administrador (se escribe como sistema)."""

    _name = "comercio.diferencia.chica.wizard"
    _description = "Diferencia chica de los precios"

    porcentaje = fields.Float(
        "Diferencia chica (%)", digits=(16, 1),
        default=lambda self: self.env.company.comercio_diferencia_chica,
        help="Los precios que cambian hasta este porcentaje salen en naranja y no se muestran: no vale "
             "la pena cambiarlos. 0: se muestran todos.")

    def action_guardar(self):
        self.ensure_one()
        if self.porcentaje < 0:
            raise UserError(_("La diferencia chica no puede ser negativa."))
        self.env["product.template"]._comercio_exigir_grupo()
        compania = self.env.company
        if compania.comercio_diferencia_chica != self.porcentaje:
            compania.sudo().comercio_diferencia_chica = self.porcentaje
        return {"type": "ir.actions.client", "tag": "soft_reload"}
