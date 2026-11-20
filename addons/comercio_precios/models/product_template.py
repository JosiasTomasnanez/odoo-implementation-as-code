from odoo import _, api, fields, models
from odoo.exceptions import AccessError
from odoo.fields import Domain
from odoo.addons.comercio_catalogo.catalogo.odoo_api import costo_por_unidad
from odoo.tools import format_amount

from ..calculo import precio_de_lista, precio_final, texto_redondeo

# Margen propio de un producto: lo cambia el grupo «Costos y precios» sin administrar productos
CAMPOS_MARGEN = {"comercio_margen_especial", "comercio_margen_propio", "comercio_base_especial",
                 "comercio_proveedor_especial_id"}


class ProductTemplate(models.Model):
    """Precio de venta sugerido por el margen de la categoría (P-030, ADR 0016).

    El precio de venta no cambia solo: el sugerido se recalcula cuando cambia el costo, la
    categoría o su regla, y los que difieren aparecen en «Precios a actualizar» para
    aplicarlos y reimprimir las etiquetas.
    """

    _inherit = "product.template"

    comercio_proveedor_costo_id = fields.Many2one(
        "res.partner", "Proveedor del costo", readonly=True, index=True,
        help="El proveedor que hoy da el costo (el más barato vigente). Se guarda al recalcular el precio "
             "sugerido, para agrupar y filtrar «Precios a actualizar» por proveedor.")
    comercio_precio_calculado = fields.Float(
        "Precio sugerido", readonly=True, digits="Product Price",
        help="Lo que debería valer según la regla de su categoría (en el mismo formato que el "
             "precio de venta: con IVA incluido si la empresa carga así los precios).")
    comercio_precio_detalle = fields.Char("Cómo se calculó", readonly=True)
    comercio_precio_manual = fields.Boolean(
        "Precio manual", copy=False,
        help="Marcado, no se sugiere cambiar el precio de venta de este producto. Se marca solo "
             "al escribir el precio a mano; al desmarcarlo vuelve a seguir el margen de su categoría.")
    comercio_precio_desactualizado = fields.Boolean(
        "Precio para actualizar", compute="_compute_comercio_precio_desactualizado", store=True)
    comercio_precio_variacion = fields.Float(
        "Cambio (%)", compute="_compute_comercio_precio_variacion", digits=(16, 1), store=True)
    comercio_precio_cambio_chico = fields.Boolean(
        "Diferencia chica", compute="_compute_comercio_precio_cambio_chico",
        search="_search_comercio_precio_cambio_chico",
        help="El precio nuevo cambia menos que la «diferencia chica» del negocio (naranja en «Precios a "
             "actualizar»): no vale la pena cambiarlo y no se muestra salvo con el filtro.")
    comercio_margen_especial = fields.Boolean(
        "Margen especial", copy=False,
        help="Marcado, este producto usa su propio margen en vez del de su rubro (categoría), y "
             "puede calcularse sobre otra base. El IVA y el redondeo siguen saliendo de la categoría.")
    comercio_margen_propio = fields.Float(
        "Margen del producto (%)", copy=False, digits=(16, 2),
        help="Solo si tiene «Margen especial». Puede ser 0 (se vende al costo más IVA).")
    comercio_base_especial = fields.Selection(
        [("costo", "Costo del producto"), ("proveedor", "Precio de un proveedor")],
        "Calcular sobre", copy=False,
        help="Solo si tiene «Margen especial». Al marcarlo arranca con la de su rubro y se puede "
             "cambiar. Costo del producto: el precio por unidad más barato entre sus proveedores. "
             "Precio de un proveedor: el de ese proveedor aunque haya otros más baratos (si no lo "
             "vende, se usa el costo). Vacío: como su rubro.")
    comercio_proveedor_especial_id = fields.Many2one(
        "res.partner", "Proveedor de referencia", copy=False,
        help="Solo con «Calcular sobre: Precio de un proveedor».")
    comercio_margen_rubro = fields.Float(
        "Margen del rubro (%)", related="categ_id.comercio_margen_efectivo",
        help="El de su categoría (o el que hereda de la madre).")
    comercio_etiqueta_pendiente = fields.Boolean(
        "Etiqueta para reimprimir", copy=False,
        help="El precio de venta cambió y la etiqueta de góndola todavía no se reimprimió.")

    @api.depends("list_price", "comercio_precio_calculado", "comercio_precio_manual")
    def _compute_comercio_precio_desactualizado(self):
        for p in self:
            p.comercio_precio_desactualizado = bool(
                not p.comercio_precio_manual and p.comercio_precio_calculado
                and abs(p.comercio_precio_calculado - p.list_price) > 0.005)

    @api.depends("list_price", "comercio_precio_calculado")
    def _compute_comercio_precio_variacion(self):
        for p in self:
            p.comercio_precio_variacion = (
                (p.comercio_precio_calculado - p.list_price) / p.list_price * 100
                if p.list_price and p.comercio_precio_calculado else 0.0)

    @api.depends("comercio_precio_variacion", "comercio_precio_desactualizado")
    @api.depends_context("company")
    def _compute_comercio_precio_cambio_chico(self):
        tolerancia = self.env.company.comercio_diferencia_chica
        for p in self:
            p.comercio_precio_cambio_chico = bool(
                tolerancia and p.comercio_precio_desactualizado
                and abs(p.comercio_precio_variacion) <= tolerancia)

    def _search_comercio_precio_cambio_chico(self, operator, value):
        if operator not in ("=", "!=") or not isinstance(value, bool):
            return NotImplemented
        tolerancia = self.env.company.comercio_diferencia_chica
        chico = Domain([("comercio_precio_desactualizado", "=", True),
                        ("comercio_precio_variacion", ">=", -tolerancia),
                        ("comercio_precio_variacion", "<=", tolerancia)]) if tolerancia else Domain.FALSE
        return chico if (operator == "=") == value else ~chico

    @api.onchange("comercio_margen_especial")
    def _onchange_comercio_margen_especial(self):
        """Al marcarlo, arranca con lo que venía usando por su rubro (margen, base y
        proveedor); después se cambia lo que haga falta."""
        for p in self:
            if not p.comercio_margen_especial or not p.categ_id:
                continue
            regla = p.categ_id._comercio_regla()
            if not p.comercio_margen_propio:
                p.comercio_margen_propio = regla["margen"]
            if not p.comercio_base_especial:
                p.comercio_base_especial = regla["base"]
                p.comercio_proveedor_especial_id = regla["base"] == "proveedor" and regla["proveedor"]

    @api.onchange("comercio_base_especial", "comercio_proveedor_especial_id")
    def _onchange_comercio_proveedor_especial(self):
        """Avisa si el proveedor elegido no tiene este producto en su lista."""
        p = self[:1]
        proveedor = p.comercio_proveedor_especial_id
        if p.comercio_margen_especial and p.comercio_base_especial == "proveedor" and proveedor \
                and not p._comercio_precio_de(proveedor):
            return {"warning": {
                "title": _("%s no lo tiene en su lista", proveedor.name),
                "message": _("«%(prod)s» no está en la lista vigente de %(prov)s: el precio se va a "
                             "calcular sobre el costo del producto hasta que lo tenga.",
                             prod=p.name or _("Este producto"), prov=proveedor.name)}}

    def _comercio_base_del_rubro(self):
        """Completa la base vacía de los que tienen margen especial con la de su rubro (cuando
        se marca sin pasar por la pantalla, p. ej. desde «Agregar producto» o la API)."""
        for p in self.filtered(lambda p: p.comercio_margen_especial and not p.comercio_base_especial
                               and p.categ_id):
            regla = p.categ_id._comercio_regla()
            super(ProductTemplate, p).write({
                "comercio_base_especial": regla["base"],
                "comercio_proveedor_especial_id": regla["base"] == "proveedor" and regla["proveedor"].id})

    # ------------------------------------------------------------------ cálculo

    def _comercio_precio_de(self, proveedor):
        """Precio por unidad vigente de ese proveedor para este producto (0: no lo vende)."""
        self.ensure_one()
        hoy = fields.Date.context_today(self)
        socios = proveedor | proveedor.child_ids
        suyos = self.seller_ids.filtered(
            lambda s: s.partner_id in socios
            and (not s.date_start or s.date_start <= hoy) and (not s.date_end or s.date_end >= hoy))
        return costo_por_unidad([{"price_discounted": s.price_discounted, "min_qty": s.min_qty}
                                 for s in suyos])

    def _comercio_proveedor_del_costo(self):
        """El proveedor que hoy da el costo: el elegido en «Costo de» si tiene precio vigente; si no,
        el de precio por unidad vigente más barato (el mismo criterio que el costo, costo_por_unidad)."""
        self.ensure_one()
        elegido = self.comercio_costo_de_id.commercial_partner_id
        if elegido and self._comercio_precio_de(elegido):
            return elegido
        hoy = fields.Date.context_today(self)
        vigentes = self.seller_ids.filtered(
            lambda s: (not s.date_start or s.date_start <= hoy) and (not s.date_end or s.date_end >= hoy))
        mejor, mejor_precio = self.env["res.partner"], 0.0
        for socio in vigentes.partner_id:
            precio = self._comercio_precio_de(socio.commercial_partner_id)
            if precio and (not mejor or precio < mejor_precio):
                mejor, mejor_precio = socio.commercial_partner_id, precio
        return mejor

    def _comercio_base(self, regla):
        """(importe, texto) de la base del precio: el costo o el precio de un proveedor."""
        self.ensure_one()
        if regla["base"] == "proveedor" and regla["proveedor"]:
            precio = self._comercio_precio_de(regla["proveedor"])
            if precio:
                return precio, _("precio de %s", regla["proveedor"].name)
            return self.standard_price, _("costo (%s no lo tiene en su lista)", regla["proveedor"].name)
        return self.standard_price, _("costo")

    def _comercio_iva(self, regla):
        """(porcentaje, de dónde sale) del IVA del precio. Manda el del producto, que es el que
        cobra la caja; el de la categoría es el que se propone a los que no tienen IVA."""
        self.ensure_one()
        propios = self.taxes_id.filtered(lambda t: t.amount_type == "percent")
        if propios:
            return sum(propios.mapped("amount")), _("del producto")
        if regla["iva"]:
            return sum(regla["iva"].mapped("amount")), _("del rubro")
        return 0.0, _("sin IVA")

    def _comercio_calcular_precio(self):
        """Recalcula el precio sugerido (no toca el precio de venta)."""
        incluido = self.env.company.account_price_include == "tax_included"
        moneda = self.env.company.currency_id
        for p in self.with_context(active_test=False):
            calculado, detalle = 0.0, False
            regla = p.categ_id._comercio_regla() if p.categ_id else None
            origen_margen = regla["categoria"].display_name if regla else ""
            del_costo = p._comercio_proveedor_del_costo()
            # Margen del proveedor que da el costo (06/11): entre el especial y el del rubro
            proveedor = del_costo if regla and not p.comercio_margen_especial else None
            if proveedor and proveedor.comercio_margen_proveedor:
                regla = dict(regla)
                regla["margen"] = proveedor.comercio_margen_proveedor
                origen_margen = _("margen de %s", proveedor.name)
                if proveedor.comercio_base_proveedor:  # sobre qué, si el proveedor lo eligió (06/11)
                    regla["base"] = proveedor.comercio_base_proveedor
                    regla["proveedor"] = proveedor.comercio_proveedor_base_id or proveedor
            if p.comercio_margen_especial:
                # Excepción al rubro: su margen y, si la eligió, su base; IVA y redondeo, de la categoría
                regla = dict(regla or {"base": "costo", "proveedor": self.env["res.partner"],
                                       "iva": self.env["account.tax"], "redondeo": 0.0})
                regla["margen"] = p.comercio_margen_propio
                if p.comercio_base_especial:
                    regla["base"] = p.comercio_base_especial
                    regla["proveedor"] = p.comercio_proveedor_especial_id
                origen_margen = _("margen especial del producto")
            if regla and (regla["margen"] or p.comercio_margen_especial):
                base, origen = p._comercio_base(regla)
                iva, origen_iva = p._comercio_iva(regla)
                if base > 0:
                    final = precio_final(base, regla["margen"], iva, regla["redondeo"])
                    calculado = precio_de_lista(final, iva, incluido)
                    detalle = _("%(origen)s %(base)s + %(margen)s %% (%(categoria)s) + IVA %(iva)s %% (%(origen_iva)s) → "
                                "%(final)s (redondeo %(redondeo)s)",
                                origen=origen.capitalize(), base=format_amount(self.env, base, moneda),
                                margen=f"{regla['margen']:g}", categoria=origen_margen,
                                iva=f"{iva:g}", origen_iva=origen_iva, final=format_amount(self.env, final, moneda),
                                redondeo=texto_redondeo(regla["redondeo"]))
            if (p.comercio_precio_calculado, p.comercio_precio_detalle or False, p.comercio_proveedor_costo_id) \
                    != (calculado, detalle, del_costo):
                # Como sistema: lo dispara también quien cambia un margen sin administrar productos
                p.sudo().write({"comercio_precio_calculado": calculado, "comercio_precio_detalle": detalle,
                                "comercio_proveedor_costo_id": del_costo.id})
        # Producto todavía sin precio de venta (en $1: recién creado, desde una lista o una factura del
        # proveedor, y el costo llegó después): toma el sugerido apenas lo hay. No hay precio anterior
        # ni etiqueta que cuidar; queda en «Etiquetas a reimprimir» para imprimir la primera.
        sin_precio = self.filtered(lambda p: p.list_price <= 1 and p.comercio_precio_calculado
                                   and not p.comercio_precio_manual)
        if sin_precio:
            sin_precio.sudo().action_comercio_aplicar_precio()

    @api.model
    def _cron_comercio_recalcular_precios(self):
        """Por las dudas: precios de proveedor que empiezan o vencen por fecha, etc."""
        self.search([])._comercio_calcular_precio()

    # ------------------------------------------------------------------ altas y cambios

    @api.model_create_multi
    def create(self, vals_list):
        # Sin IVA elegido: el de su categoría (si no, Odoo pondría el de la empresa)
        categorias = self.env["product.category"]
        for vals in vals_list:
            if "taxes_id" not in vals and vals.get("categ_id"):
                iva = categorias.browse(vals["categ_id"])._comercio_regla()["iva"]
                if iva:
                    vals["taxes_id"] = [(6, 0, iva.ids)]
        productos = super(ProductTemplate, self.with_context(comercio_creando=True)).create(vals_list)
        productos._comercio_calcular_precio()  # sin precio de venta: toma el sugerido de entrada
        return productos.with_context(comercio_creando=False)

    def write(self, vals):
        if (set(vals) & CAMPOS_MARGEN and set(vals) <= CAMPOS_MARGEN and not self.env.su
                and self.env.user.has_group("comercio_catalogo.group_listas_proveedores")):
            # Como los márgenes por rubro: el grupo «Costos y precios» lo cambia sin ser
            # administrador de productos (queda en el chatter quién fue)
            return self.sudo().with_context(comercio_quien=self.env.user.name).write(vals)
        # Precio escrito a mano: no se sugiere cambiarlo (como el «Costo manual»)
        if "list_price" in vals and "comercio_precio_manual" not in vals \
                and not self.env.context.get("install_mode") and not self.env.context.get("comercio_creando"):
            vals = {**vals, "comercio_precio_manual": True}
        res = super().write(vals)
        if vals.get("comercio_margen_especial") and "comercio_base_especial" not in vals:
            self._comercio_base_del_rubro()
        if {"standard_price", "categ_id", "taxes_id", "comercio_costo_de_id"} & set(vals) or CAMPOS_MARGEN & set(vals):
            self._comercio_calcular_precio()
        if CAMPOS_MARGEN & set(vals):
            quien = self.env.context.get("comercio_quien") or self.env.user.name
            for p in self:
                if not p.comercio_margen_especial:
                    margen = _("no, usa el de su rubro")
                elif p.comercio_base_especial == "proveedor" and p.comercio_proveedor_especial_id:
                    margen = _("%(m)s %% sobre el precio de %(prov)s", m=f"{p.comercio_margen_propio:g}",
                               prov=p.comercio_proveedor_especial_id.name)
                elif p.comercio_base_especial == "costo":
                    margen = _("%(m)s %% sobre el costo", m=f"{p.comercio_margen_propio:g}")
                else:
                    margen = f"{p.comercio_margen_propio:g} %"
                p.message_post(body=_("Margen especial: %(m)s (%(u)s).", u=quien, m=margen))
        return res

    # ------------------------------------------------------------------ acciones

    def _comercio_exigir_grupo(self):
        """Las acciones de precios las usa el grupo «Costos y precios» aunque no administre
        productos: se controla el grupo y se escribe como sistema (queda el usuario en el chatter)."""
        if not self.env.su and not self.env.user.has_group("comercio_catalogo.group_listas_proveedores"):
            raise AccessError(_("Hace falta el permiso «Costos y precios»."))
        return self.sudo()

    def action_comercio_aplicar_precio(self):
        """Pasa el precio sugerido al precio de venta (y el IVA de la categoría al producto que
        no tiene IVA)."""
        moneda = self.env.company.currency_id
        usuario = self.env.user.name
        for p in self._comercio_exigir_grupo().filtered("comercio_precio_desactualizado"):
            vals = {"list_price": p.comercio_precio_calculado, "comercio_precio_manual": False,
                    "comercio_etiqueta_pendiente": True}
            iva = p.categ_id._comercio_regla()["iva"]
            if iva and not p.taxes_id.filtered(lambda t: t.amount_type == "percent"):
                vals["taxes_id"] = [(6, 0, iva.ids)]
            p.message_post(body=_("Precio de venta: %(antes)s → %(nuevo)s (%(usuario)s). %(detalle)s",
                                  antes=format_amount(self.env, p.list_price, moneda),
                                  nuevo=format_amount(self.env, p.comercio_precio_calculado, moneda),
                                  usuario=usuario, detalle=p.comercio_precio_detalle or ""))
            p.write(vals)
        return True

    def action_comercio_recalcular_todo(self):
        self._comercio_exigir_grupo().search([])._comercio_calcular_precio()
        return True

    def action_comercio_imprimir_etiquetas(self):
        return self.filtered(lambda p: p.type != "service").action_open_label_layout()

    def action_comercio_etiquetas_impresas(self):
        self._comercio_exigir_grupo().write({"comercio_etiqueta_pendiente": False})
        return True
