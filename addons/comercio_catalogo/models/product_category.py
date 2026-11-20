from odoo import _, api, fields, models
from odoo.exceptions import AccessError, UserError

from ..catalogo.similitud import sin_acentos

# Lo que puede cargar al crear una categoría quien solo tiene «Costos y precios» (desde el
# desplegable de la lista del proveedor). Cuentas, método de costo y demás: administración.
CAMPOS_AL_CREAR = {"name", "parent_id", "comercio_controla_stock"}


def _clave_nombre(nombre: str) -> str:
    return " ".join(sin_acentos(nombre or "").lower().split())


class ProductCategory(models.Model):
    _inherit = "product.category"

    comercio_controla_stock = fields.Boolean(
        string="Controla stock",
        help="Los productos nuevos de esta categoría (y sus subcategorías) se cargan con control "
        "de stock. Adopción gradual: al principio solo alimentos (P-032).",
    )

    @api.model_create_multi
    def create(self, vals_list):
        """Categorías creadas al vuelo desde la lista del proveedor (P-048).

        Evita duplicados escritos distinto («Ferreteria» y «Ferretería») bajo la misma madre."""
        if not self.env.su and not self.env.user.has_group("product.group_product_manager"):
            # Tampoco por valores por defecto del contexto (default_property_cost_method…):
            # solo quedan los de los campos permitidos.
            self = self.with_context({k: v for k, v in self.env.context.items()
                                      if not k.startswith("default_") or k[len("default_"):] in CAMPOS_AL_CREAR})
            for vals in vals_list:
                if set(vals) - CAMPOS_AL_CREAR:
                    raise AccessError(_("Con el permiso «Costos y precios» se crea una categoría solo con "
                                        "nombre y categoría madre; lo demás lo completa administración."))
        for vals in vals_list:
            # Solo para personas (no instalaciones de módulos ni odoo-iac, que corren como su)
            if vals.get("name") and not self.env.su:
                vals["name"] = " ".join(vals["name"].split())
                parecida = self.search([("parent_id", "=", vals.get("parent_id") or False)]).filtered(
                    lambda c, n=_clave_nombre(vals["name"]): _clave_nombre(c.name) == n)
                if parecida:
                    raise UserError(_("Ya existe la categoría «%s»: elegila en la lista en vez de crear otra.",
                                      parecida[0].complete_name))
        return super().create(vals_list)
