from odoo import api, fields, models

from ..catalogo.codigos import codigo_propio, numero_de_codigo_propio
from ..catalogo.odoo_api import actualizar_costos


class ProductTemplate(models.Model):
    """Códigos automáticos al crear un producto a mano (docs/areas/codigos.md, D3 y D5).

    Si se deja vacía la referencia interna, recibe el siguiente número correlativo; si se
    deja vacío el código de barras (y es un bien, no un servicio), recibe el código propio
    «20» + ese número. Un código de fábrica escrito a mano se respeta. Es la misma
    numeración que usa el importador de listas.
    """

    _inherit = "product.template"

    comercio_codigo_lista = fields.Char(
        "Código de la lista (a verificar)", copy=False,
        help="El código de barras que traía la lista del proveedor y no se pudo usar (incompleto, mal escrito "
             "o de otro producto de la lista): para escanear el del envase en «Códigos de fábrica».")
    comercio_costo_manual = fields.Boolean(
        "Costo manual", copy=False,
        help="Marcado, las listas de proveedores no cambian el costo de este producto. Se marca "
             "solo al escribir el costo a mano; al desmarcarlo vuelve a seguir las listas (el precio "
             "por unidad vigente más barato entre sus proveedores).")

    comercio_costo_de_id = fields.Many2one(
        "res.partner", "Costo de", copy=False, tracking=True, domain="[('id', 'in', comercio_proveedores_ids)]",
        help="Vacío: el costo sale solo del proveedor más barato (precio por unidad vigente). Elegido: sale "
             "solo de ese proveedor, aunque haya otros más baratos (si deja de tener precio vigente, vuelve "
             "al más barato). En los dos casos se actualiza solo con cada lista.")
    comercio_proveedores_ids = fields.Many2many("res.partner", compute="_compute_comercio_proveedores")

    @api.depends("seller_ids.partner_id")
    def _compute_comercio_proveedores(self):
        for p in self:
            p.comercio_proveedores_ids = p.seller_ids.partner_id.commercial_partner_id

    def write(self, vals):
        # Costo escrito a mano: las listas dejan de cambiarlo (P-044). El cálculo automático
        # manda la marca en los mismos valores, así no cuenta como manual.
        if "standard_price" in vals and "comercio_costo_manual" not in vals \
                and not self.env.context.get("install_mode") and not self.env.context.get("comercio_creando"):
            vals = {**vals, "comercio_costo_manual": True}
        res = super().write(vals)
        if (vals.get("comercio_costo_manual") is False and "standard_price" not in vals) \
                or "comercio_costo_de_id" in vals:
            self._comercio_actualizar_costo()  # vuelve a seguir las listas (o el proveedor elegido)
        return res

    def _comercio_actualizar_costo(self):
        if self:
            actualizar_costos(_cliente_orm(self.sudo().env), self.ids, fields.Date.context_today(self).isoformat())

    @api.model
    def _cron_comercio_actualizar_costos(self):
        """Precios que empiezan o vencen por fecha cambian el costo sin que nadie edite nada."""
        con_proveedor = self.env["product.supplierinfo"].sudo().search([]).product_tmpl_id
        con_proveedor._comercio_actualizar_costo()

    def _comercio_ultimo_numero(self):
        """Último número usado en referencias (hasta 10 dígitos) o códigos propios 20…."""
        # Un solo número por vez aunque dos personas creen productos al mismo tiempo
        self.env.cr.execute("SELECT pg_advisory_xact_lock(hashtext('comercio_codigo_propio'))")
        # Variantes y plantillas: al archivar una variante Odoo 20 le borra la referencia y el código,
        # pero la plantilla los conserva (y el control de duplicados de Odoo los sigue viendo)
        self.env.cr.execute(
            """SELECT max(n) FROM (
                 SELECT default_code::bigint AS n FROM product_product WHERE default_code ~ '^[0-9]{1,10}$'
                 UNION ALL
                 SELECT default_code::bigint FROM product_template WHERE default_code ~ '^[0-9]{1,10}$'
               ) t"""
        )
        ultimo = self.env.cr.fetchone()[0] or 0
        self.env.cr.execute(
            """SELECT barcode FROM product_product WHERE barcode LIKE '20%%' AND length(barcode) = 13
               UNION SELECT barcode FROM product_template WHERE barcode LIKE '20%%' AND length(barcode) = 13"""
        )
        for (barcode,) in self.env.cr.fetchall():
            ultimo = max(ultimo, numero_de_codigo_propio(barcode) or 0)
        return ultimo

    @api.model_create_multi
    def create(self, vals_list):
        # No al instalar módulos (sus datos traen productos propios) ni si se pide explícitamente
        # Odoo guarda el costo de un producto nuevo con un write interno: no es un costo manual
        self = self.with_context(comercio_creando=True)
        if self.env.context.get("install_mode") or self.env.context.get("comercio_sin_codigos"):
            return super().create(vals_list).with_context(comercio_creando=False)
        sin_codigo = [
            vals for vals in vals_list
            if not vals.get("default_code")
            or (not vals.get("barcode") and vals.get("type", "consu") == "consu")
        ]
        if sin_codigo:
            ultimo = self._comercio_ultimo_numero()
            for vals in sin_codigo:
                if vals.get("default_code") and str(vals["default_code"]).isdigit():
                    numero = int(vals["default_code"])  # referencia numérica escrita a mano
                    ultimo = max(ultimo, numero) if len(str(numero)) <= 10 else ultimo
                else:
                    ultimo += 1
                    numero = ultimo
                    vals.setdefault("default_code", False)
                    if not vals["default_code"]:
                        vals["default_code"] = str(numero)
                if not vals.get("barcode") and vals.get("type", "consu") == "consu":
                    vals["barcode"] = codigo_propio(numero)
        return super().create(vals_list).with_context(comercio_creando=False)


def _cliente_orm(env):
    from .importacion import OrmCliente  # importacion importa este archivo indirectamente
    return OrmCliente(env)
