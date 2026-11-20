from odoo import _, api, fields, models
from odoo.exceptions import AccessError, ValidationError

from ..calculo import leer_tramos, texto_redondeo

# Lo único que puede cambiar quien tiene «Costos y precios» sin administrar productos
CAMPOS_REGLA = {"comercio_margen", "comercio_base", "comercio_proveedor_base_id", "comercio_iva_venta_id",
                "comercio_redondeo", "comercio_redondeo_tramos"}


class ProductCategory(models.Model):
    """Regla de precio de venta del rubro (P-030). Una subcategoría sin dato usa el de su
    categoría madre (p. ej. «Mascotas / Alimento» sin margen → el de «Mascotas»)."""

    _inherit = "product.category"

    comercio_margen = fields.Float(
        "Margen (%)", tracking=True,
        help="Se suma a la base (costo o precio del proveedor). Vacío o 0: usa el de la "
             "categoría madre; si ninguna tiene, no se sugiere precio.")
    comercio_base = fields.Selection(
        [("costo", "Costo del producto"), ("proveedor", "Precio de un proveedor")],
        "Calcular sobre", tracking=True,
        help="Costo del producto: el precio por unidad más barato entre sus proveedores (lo "
             "mantienen las listas). Precio de un proveedor: el de ese proveedor aunque haya "
             "otros más baratos (si no lo vende, se usa el costo). Vacío: el de la madre.")
    comercio_proveedor_base_id = fields.Many2one("res.partner", "Proveedor de referencia", tracking=True)
    comercio_iva_venta_id = fields.Many2one(
        "account.tax", "IVA por defecto", domain=[("type_tax_use", "=", "sale")], tracking=True,
        help="El que se les pone a los productos nuevos del rubro y a los que no tienen IVA. Si un "
             "producto tiene otro IVA (p. ej. 10,5 %), manda el del producto: es el que cobra la caja. "
             "Vacío: el de la madre.")
    comercio_redondeo = fields.Float(
        "Redondear a ($)", tracking=True,
        help="El precio final se lleva al múltiplo siguiente (p. ej. 10 → $45.990 pasa a "
             "$46.000; nunca para abajo). Vacío o 0: el de la madre.")

    comercio_redondeo_tramos = fields.Char(
        "Redondeo por tramos", tracking=True,
        help="Según el precio (20/11): «10; 1000:100; 10000:500» = hasta $ 1.000 a $ 10, desde $ 1.000 "
             "a $ 100 y desde $ 10.000 a $ 500 (siempre hacia arriba). Si está, manda sobre «Redondear "
             "a». Vacío: el de la madre.")

    # Lo que termina usando la categoría (con lo heredado), para la pantalla de márgenes
    comercio_margen_efectivo = fields.Float("Margen que se usa (%)", compute="_compute_comercio_efectivo")
    comercio_regla_texto = fields.Char("Regla que se usa", compute="_compute_comercio_efectivo")
    comercio_cant_productos = fields.Integer("Productos", compute="_compute_comercio_cant_productos")

    @api.depends("comercio_margen", "comercio_base", "comercio_proveedor_base_id", "comercio_iva_venta_id",
                 "comercio_redondeo", "comercio_redondeo_tramos", "parent_id")
    def _compute_comercio_efectivo(self):
        for categoria in self:
            regla = categoria._comercio_regla()
            categoria.comercio_margen_efectivo = regla["margen"]
            if not regla["margen"]:
                categoria.comercio_regla_texto = "Sin margen: no se sugiere precio"
                continue
            base = (f"precio de {regla['proveedor'].name}" if regla["base"] == "proveedor" and regla["proveedor"]
                    else "costo")
            texto = f"{base} + {regla['margen']:g} %"
            texto += f" + IVA del producto (si no tiene, {regla['iva'].name})" if regla["iva"] else " + IVA del producto"
            texto += f", redondeo {texto_redondeo(regla['redondeo'])}" if regla["redondeo"] else ", sin redondeo"
            if not categoria.comercio_margen:
                texto += " (margen heredado)"
            categoria.comercio_regla_texto = texto

    @api.onchange("comercio_base", "comercio_proveedor_base_id")
    def _onchange_comercio_proveedor_base(self):
        """Avisa cuántos productos de la categoría no están en la lista del proveedor elegido."""
        categoria = self[:1]
        proveedor = categoria.comercio_proveedor_base_id
        if categoria.comercio_base != "proveedor" or not proveedor or not categoria._origin.id:
            return
        origen = categoria._origin

        def usa_esta_regla(producto):
            # Ni subcategorías con base propia ni margen especial con base propia
            if producto.comercio_margen_especial and producto.comercio_base_especial:
                return False
            cat = producto.categ_id
            while cat and cat != origen:
                if cat.comercio_base:
                    return False
                cat = cat.parent_id
            return True

        productos = self.env["product.template"].search(
            [("categ_id", "child_of", origen.id)]).filtered(usa_esta_regla)
        faltan = productos.filtered(lambda p: not p._comercio_precio_de(proveedor))
        if faltan:
            return {"warning": {
                "title": _("%s no tiene todo en su lista", proveedor.name),
                "message": _("%(n)s de %(total)s productos de esta categoría no están en la lista vigente de "
                             "%(prov)s (por ejemplo, «%(ej)s»). Para esos el precio se calcula sobre el "
                             "costo del producto.",
                             n=len(faltan), total=len(productos), prov=proveedor.name, ej=faltan[0].name)}}

    def _compute_comercio_cant_productos(self):
        for categoria in self:
            categoria.comercio_cant_productos = self.env["product.template"].search_count(
                [("categ_id", "=", categoria.id)])

    def _comercio_regla(self):
        """Datos de la regla, heredando de las categorías madre lo que falte."""
        self.ensure_one()
        regla = {"margen": 0.0, "base": False, "proveedor": self.env["res.partner"],
                 "iva": self.env["account.tax"], "redondeo": 0.0, "categoria": self}
        categoria = self
        while categoria:
            regla["margen"] = regla["margen"] or categoria.comercio_margen
            if not regla["base"]:
                regla["base"] = categoria.comercio_base
                regla["proveedor"] = categoria.comercio_proveedor_base_id
            regla["iva"] = regla["iva"] or categoria.comercio_iva_venta_id
            if not regla["redondeo"]:
                # Los tramos mandan sobre el redondeo único de la misma categoría
                regla["redondeo"] = leer_tramos(categoria.comercio_redondeo_tramos) or categoria.comercio_redondeo
            categoria = categoria.parent_id
        regla["base"] = regla["base"] or "costo"
        return regla

    @api.constrains("comercio_redondeo_tramos")
    def _check_comercio_redondeo_tramos(self):
        for categoria in self.filtered("comercio_redondeo_tramos"):
            try:
                leer_tramos(categoria.comercio_redondeo_tramos)
            except ValueError as error:
                raise ValidationError(_("Redondeo por tramos: escribilo como «10; 1000:100; 10000:500» "
                                        "(«desde:múltiplo» separados por punto y coma).")) from error

    def write(self, vals):
        # El permiso de modificar categorías del grupo «Costos y precios» (security/ir.access.csv)
        # es solo para la regla de precio: el nombre, la madre, las cuentas o el método de costo
        # siguen siendo del administrador de productos.
        if not self.env.su and not self.env.user.has_group("product.group_product_manager") \
                and set(vals) - CAMPOS_REGLA:
            raise AccessError(_("Con el permiso «Costos y precios» solo se cambia la regla de precio de "
                                "la categoría (margen, base, IVA y redondeo)."))
        res = super().write(vals)
        if (CAMPOS_REGLA | {"parent_id"}) & set(vals):
            productos = self.env["product.template"].search([("categ_id", "child_of", self.ids)])
            productos._comercio_calcular_precio()
        return res
