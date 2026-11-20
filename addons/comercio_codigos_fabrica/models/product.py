from odoo import _, api, fields, models
from odoo.addons.comercio_catalogo.catalogo.codigos import FABRICANTE, normalizar, numero_de_codigo_propio
from odoo.exceptions import AccessError, UserError


CAMPOS_CODIGO = {"comercio_codigo_fabrica", "comercio_sin_codigo_fabrica"}


class ProductTemplate(models.Model):
    _inherit = "product.template"

    comercio_sin_codigo_fabrica = fields.Boolean(
        "No tiene código de fábrica", copy=False,
        help="El producto no trae código de barras impreso (suelto, pesable, fraccionado…): se queda "
             "con el código propio 20… y sale de «Códigos de fábrica».")
    comercio_codigo_fabrica = fields.Char(
        "Escanear código de fábrica", compute="_compute_comercio_codigo_fabrica",
        inverse="_inverse_comercio_codigo_fabrica",
        help="Escanear el código del envase: reemplaza al código propio 20…, que queda como "
             "alternativo (la caja lo sigue leyendo en las etiquetas ya pegadas).")
    comercio_codigos_alternativos = fields.Char(
        "Códigos alternativos", compute="_compute_comercio_codigos_alternativos")

    def write(self, vals):
        # Escanear o marcar desde «Códigos de fábrica»: el grupo «Costos y precios» lo hace sin
        # administrar productos (como los márgenes en comercio_precios)
        if vals and set(vals) <= CAMPOS_CODIGO and not self.env.su:
            return super(ProductTemplate, self._comercio_exigir_permiso()).write(vals)
        return super().write(vals)

    def _compute_comercio_codigo_fabrica(self):
        self.comercio_codigo_fabrica = False

    def _compute_comercio_codigos_alternativos(self):
        for p in self:
            p.comercio_codigos_alternativos = ", ".join(
                self.env["product.uom"].search([("product_id", "in", p.product_variant_ids.ids)]).mapped("barcode")) \
                or False

    def _comercio_exigir_permiso(self):
        """Lo usa quien carga listas (grupo «Costos y precios») o administra productos: se
        controla el grupo y se escribe como sistema (queda el usuario en el chatter)."""
        if not self.env.su and not (self.env.user.has_group("comercio_catalogo.group_listas_proveedores")
                                    or self.env["product.template"].has_access("write")):
            raise AccessError(_("Hace falta el permiso «Costos y precios» para cambiar códigos de barras."))
        return self.sudo()

    def _inverse_comercio_codigo_fabrica(self):
        for plantilla in self.filtered("comercio_codigo_fabrica"):
            plantilla._comercio_poner_codigo_fabrica(plantilla.comercio_codigo_fabrica)

    def _comercio_poner_codigo_fabrica(self, escaneado):
        self.ensure_one()
        codigo, tipo = normalizar(escaneado)
        if tipo != FABRICANTE:
            raise UserError(_("«%(c)s» no es un código de barras de fábrica válido (¿se leyó mal? ¿es un código "
                              "interno que empieza con 2?). Producto: %(p)s.", c=escaneado, p=self.display_name))
        producto = self.product_variant_id
        if len(self.product_variant_ids) != 1:
            raise UserError(_("«%s» tiene variantes: poné el código en cada variante.", self.display_name))
        if producto.barcode == codigo:
            return
        otro = self.env["product.product"].with_context(active_test=False).search(
            [("barcode", "=", codigo), ("id", "!=", producto.id)], limit=1)
        otro = otro or self.env["product.uom"].search([("barcode", "=", codigo)], limit=1).product_id
        if otro:
            raise UserError(_("El código %(c)s ya es de «%(o)s»: ¿escaneaste el producto equivocado, o son el "
                              "mismo producto (Fusionar)?", c=codigo, o=otro.display_name))
        yo = self._comercio_exigir_permiso()
        anterior = producto.barcode
        yo.product_variant_id.barcode = codigo
        if anterior and numero_de_codigo_propio(anterior):
            # El 20… puede estar pegado en la góndola o en el producto: la caja lo sigue leyendo
            self.env["product.uom"].sudo().create(
                {"product_id": producto.id, "uom_id": producto.uom_id.id, "barcode": anterior})
        yo.comercio_sin_codigo_fabrica = False
        yo.comercio_codigo_lista = False  # ya verificado: la pista de la lista no hace falta
        self.message_post(body=_("Código de fábrica %(c)s (antes %(a)s, que queda como alternativo) — %(u)s.",
                                 c=codigo, a=anterior or "-", u=self.env.user.name))

    def action_comercio_sin_codigo_fabrica(self):
        self._comercio_exigir_permiso().write({"comercio_sin_codigo_fabrica": True})
        return True

    def action_comercio_con_codigo_fabrica(self):
        self._comercio_exigir_permiso().write({"comercio_sin_codigo_fabrica": False})
        return True

    def _comercio_ultimo_numero(self):
        """El próximo 20… también mira los alternativos: un número ya pegado no se repite."""
        ultimo = super()._comercio_ultimo_numero()
        self.env.cr.execute("SELECT barcode FROM product_uom WHERE barcode LIKE '20%%' AND length(barcode) = 13")
        for (barcode,) in self.env.cr.fetchall():
            ultimo = max(ultimo, numero_de_codigo_propio(barcode) or 0)
        return ultimo

    @api.model
    def _comercio_dominio_codigos_fabrica(self):
        return [("barcode", "=like", "20%"), ("comercio_sin_codigo_fabrica", "=", False)]
