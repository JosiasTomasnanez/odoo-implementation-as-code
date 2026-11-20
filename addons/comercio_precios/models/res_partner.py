"""Margen de venta por proveedor (06/11, pedido de Daniel): entre el especial del producto y el
del rubro. Con varios proveedores manda el que hoy da el costo (el más barato vigente)."""
from odoo import _, api, fields, models
from odoo.exceptions import AccessError, ValidationError


CAMPOS_MARGEN_PROVEEDOR = {"comercio_margen_proveedor", "comercio_base_proveedor", "comercio_proveedor_base_id"}


class ResPartner(models.Model):
    _inherit = "res.partner"

    comercio_margen_proveedor = fields.Float(
        "Margen de venta (%)", digits=(16, 2), copy=False, tracking=True,
        help="Margen para los productos cuyo costo sale de este proveedor (el más barato vigente). "
             "Vacío o 0: el del rubro. Un producto con «Margen especial» usa el suyo.")

    # Sobre qué se calcula ese margen (06/11), como en «Margen especial»: el costo del producto o el
    # precio de un proveedor elegido. Vacío: como el rubro.
    comercio_base_proveedor = fields.Selection(
        [("costo", "Costo del producto"), ("proveedor", "Precio de un proveedor")], "Calcular sobre",
        copy=False, tracking=True,
        help="Solo si tiene margen. Vacío: como su rubro. Precio de un proveedor: el de ese proveedor aunque "
             "haya otros más baratos (si no lo vende, se usa el costo).")
    comercio_proveedor_base_id = fields.Many2one(
        "res.partner", "Proveedor de referencia", copy=False, tracking=True,
        domain="[('supplier_rank', '>', 0), ('parent_id', '=', False)]",
        help="Solo con «Calcular sobre: Precio de un proveedor». Vacío: este mismo proveedor.")

    @api.constrains("comercio_margen_proveedor")
    def _check_comercio_margen_proveedor(self):
        if any(p.comercio_margen_proveedor < 0 for p in self):
            raise ValidationError(_("El margen del proveedor no puede ser negativo."))

    def _check_permiso_margen_proveedor(self, vals_list):
        # Cambia precios sugeridos: solo «Costos y precios» o el administrador de productos, igual que
        # el margen del rubro (ProductCategory.write). Los demás pueden seguir editando el contacto.
        if any(vals.get(campo) for vals in vals_list for campo in CAMPOS_MARGEN_PROVEEDOR) and not self.env.su \
                and not self.env.user.has_group("comercio_catalogo.group_listas_proveedores") \
                and not self.env.user.has_group("product.group_product_manager"):
            raise AccessError(_("Solo quien tiene el permiso «Costos y precios» cambia el margen de un "
                                "proveedor."))

    @api.model_create_multi
    def create(self, vals_list):
        self._check_permiso_margen_proveedor(vals_list)
        return super().create(vals_list)

    def write(self, vals):
        if CAMPOS_MARGEN_PROVEEDOR & set(vals):  # también ponerlo en 0 cambia precios
            self._check_permiso_margen_proveedor([{"comercio_margen_proveedor": True}])
        res = super().write(vals)
        if CAMPOS_MARGEN_PROVEEDOR & set(vals):
            productos = self.env["product.template"].sudo().with_context(active_test=False).search(
                [("seller_ids.partner_id", "in", (self | self.child_ids).ids)])
            productos._comercio_calcular_precio()
        return res


class ComercioListaProveedor(models.Model):
    _inherit = "comercio.lista.proveedor"

    margen_proveedor = fields.Float(related="partner_id.comercio_margen_proveedor", readonly=False,
                                    string="Margen de venta del proveedor (%)")
