from odoo import _, api, fields, models
from odoo.exceptions import UserError

from ..factura import leer


class ElegirProveedor(models.TransientModel):
    """Ningún proveedor tiene el CUIT de la factura: la persona elige cuál es (por ejemplo, uno que
    vino de una lista y todavía no tiene CUIT) o lo crea. No se adivina por los artículos (26/10)."""

    _name = "comercio.factura.elegir.proveedor"
    _description = "Elegir el proveedor de una factura"

    move_id = fields.Many2one("account.move", required=True, ondelete="cascade")
    cuit = fields.Char("CUIT de la factura", related="move_id.comercio_cuit_sin_proveedor")
    partner_id = fields.Many2one(
        "res.partner", "Proveedor", domain="[('parent_id', '=', False)]",
        help="Uno de los que ya tenemos. Si no tiene CUIT, se le guarda el de la factura.")
    nombre = fields.Char("O crear uno nuevo", help="Razón social del proveedor, como dice la factura.")

    @api.onchange("partner_id")
    def _onchange_partner_id(self):
        if self.partner_id:
            self.nombre = False

    def action_aceptar(self):
        self.ensure_one()
        move, cuit = self.move_id, self.cuit
        if self.partner_id:
            socio = self.partner_id
            if cuit and socio.vat and leer.solo_digitos(socio.vat) != cuit:
                raise UserError(_("%(p)s tiene el CUIT %(v)s y la factura es del %(c)s: no es el mismo proveedor.",
                                  p=socio.name, v=socio.vat, c=cuit))
        elif self.nombre and self.nombre.strip():
            socio = self.env["res.partner"].create(
                {"name": self.nombre.strip(), "is_company": True, "supplier_rank": 1})
        else:
            raise UserError(_("Elegí un proveedor o escribí el nombre del nuevo."))
        move.partner_id = socio
        # Con el proveedor elegido, el CUIT (y la condición de IVA) se le guardan aunque sus artículos
        # no estén en ninguna lista (proveedor nuevo)
        return move.with_context(comercio_proveedor_elegido=True).action_comercio_leer_factura()
