from odoo import api, fields, models


class ComercioImportarListaWizard(models.TransientModel):
    """El margen del rubro en «Importar lista», para cargarlo al crear el rubro ahí mismo
    (pedido del 02/11) en vez de ir a «Márgenes por categoría»."""

    _inherit = "comercio.importar.lista.wizard"

    margen_rubro = fields.Float(
        "Margen del rubro (%)", compute="_compute_margen_rubro", store=True, readonly=False,
        help="Se guarda en el rubro al simular. Vacío o 0: usa el de la categoría madre; sin "
             "ninguno, los productos de este rubro no se pueden agregar al catálogo.")
    regla_rubro = fields.Char(related="categoria_id.comercio_regla_texto", string="Precio de venta")

    @api.depends("categoria_id", "lista_id")
    def _compute_margen_rubro(self):
        # El margen que REALMENTE usa el rubro: el propio o el heredado de la categoría madre
        # (06/11: antes mostraba solo el propio y una subcategoría que hereda el 60 % se veía en 0).
        for wizard in self:
            wizard.margen_rubro = wizard.categoria_id.comercio_margen_efectivo

    def action_importar(self):
        categoria = self.categoria_id
        # Solo si la persona lo cambió: así no se copia el heredado como propio en la subcategoría
        if categoria and self.margen_rubro > 0 and self.margen_rubro != categoria.comercio_margen_efectivo:
            categoria.comercio_margen = self.margen_rubro
        return super().action_importar()
