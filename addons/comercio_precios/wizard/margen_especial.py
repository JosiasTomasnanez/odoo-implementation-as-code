from odoo import _, api, fields, models
from odoo.exceptions import UserError


class ComercioMargenEspecialWizard(models.TransientModel):
    """Dar margen especial a uno o varios productos desde «Márgenes especiales», sin ir a
    buscarlos a otra pantalla. Escribe los mismos campos que la ficha del producto (y por el
    mismo camino: permiso del grupo «Costos y precios» y registro en el chatter)."""

    _name = "comercio.margen.especial.wizard"
    _description = "Dar margen especial a productos"

    producto_ids = fields.Many2many(
        "product.template", string="Productos", required=True,
        help="Buscar por nombre, código o código de barras; se pueden elegir varios.")
    margen = fields.Float("Margen especial (%)", required=True,
                          help="Reemplaza al margen del rubro; el IVA y el redondeo siguen siendo los "
                          "de su categoría.")
    base = fields.Selection(
        [("costo", "Costo del producto"), ("proveedor", "Precio de un proveedor")], "Calcular sobre",
        help="Se completa con la de su rubro si todos los elegidos tienen la misma. Vacío: cada "
             "producto toma la de su rubro.")
    proveedor_id = fields.Many2one("res.partner", "Proveedor de referencia")
    rubros = fields.Char("Margen de su rubro", compute="_compute_rubros")

    @api.onchange("producto_ids")
    def _onchange_producto_ids(self):
        """Arranca con lo de su rubro (margen, base y proveedor) si todos los elegidos tienen
        la misma regla; después se cambia lo que haga falta."""
        reglas = [p.categ_id._comercio_regla() for p in self.producto_ids if p.categ_id]
        if not reglas or len(reglas) != len(self.producto_ids):
            return
        margenes = {r["margen"] for r in reglas}
        if not self.margen and len(margenes) == 1:
            self.margen = margenes.pop()
        bases = {(r["base"], r["proveedor"].id if r["base"] == "proveedor" else False) for r in reglas}
        if not self.base and len(bases) == 1:
            base, proveedor = bases.pop()
            self.base = base
            self.proveedor_id = proveedor

    @api.onchange("base", "proveedor_id", "producto_ids")
    def _onchange_proveedor_id(self):
        """Avisa qué productos no están en la lista del proveedor elegido."""
        if self.base != "proveedor" or not self.proveedor_id:
            return
        faltan = self.producto_ids.filtered(lambda p: not p._comercio_precio_de(self.proveedor_id))
        if faltan:
            nombres = ", ".join(faltan[:5].mapped("name")) + ("…" if len(faltan) > 5 else "")
            return {"warning": {
                "title": _("%s no los tiene en su lista", self.proveedor_id.name),
                "message": _("No están en la lista vigente de %(prov)s: %(prods)s. Para esos el precio se "
                             "calcula sobre el costo del producto hasta que los tenga.",
                             prov=self.proveedor_id.name, prods=nombres)}}

    @api.depends("producto_ids")
    def _compute_rubros(self):
        for w in self:
            w.rubros = ", ".join(f"{p.name}: {p.comercio_margen_rubro:g} %" for p in w.producto_ids[:5])

    def action_aplicar(self):
        if self.margen < 0:
            raise UserError(_("El margen no puede ser negativo."))
        if self.base == "proveedor" and not self.proveedor_id:
            raise UserError(_("Elegí el proveedor sobre cuyo precio se calcula."))
        vals = {"comercio_margen_especial": True, "comercio_margen_propio": self.margen}
        if self.base:
            vals.update(comercio_base_especial=self.base,
                        comercio_proveedor_especial_id=self.base == "proveedor" and self.proveedor_id.id)
        # Sin base elegida: cada producto toma la de su rubro (ProductTemplate.write)
        self.producto_ids.write(vals)
        return {"type": "ir.actions.act_window_close"}
