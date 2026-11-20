from odoo import _, api, fields, models
from odoo.exceptions import UserError
from odoo.tools import format_amount

from .product import dominio_vigente

SALVEDAD = "solo precio de lista; no incluye flete ni condiciones"


class PurchaseOrderLine(models.Model):
    _inherit = "purchase.order.line"

    def action_comercio_lista_proveedor(self):
        """Botón «Lista del proveedor» junto a «Catálogo» (23/10, pedido del cliente): la última
        lista entera de ese proveedor, sin filtrar lo que tenemos (eso ya lo muestra «Catálogo»,
        26/10); lo que no tenemos se agrega a nuestro catálogo y «Pedir» lo suma a esta orden."""
        orden = self.env["purchase.order"].browse(self.env.context.get("order_id")).exists()
        if not orden.partner_id:
            raise UserError(_("Elegí primero el proveedor de la orden."))
        socio = orden.partner_id.commercial_partner_id
        accion = self.env["ir.actions.act_window"]._for_xml_id("comercio_catalogo.action_buscar_producto")
        accion.update({
            "name": _("Lista de %s", socio.name),
            "domain": [("de_lista_vigente", "=", True), ("accion", "!=", "baja"), ("partner_id", "=", socio.id)],
            "context": {"comercio_pedido_id": orden.id},
            "target": "current",
        })
        return accion

    comercio_aviso_lista = fields.Char(
        "Lista del proveedor", compute="_compute_comercio_aviso_lista",
        help="El producto no está en la lista vigente de este proveedor.")
    comercio_aviso_minimo = fields.Char(
        "Mínimo del proveedor", compute="_compute_comercio_aviso_minimo",
        help="La cantidad no llega al mínimo de la lista vigente de este proveedor: no hay precio "
             "de lista para esa cantidad y Odoo pone el costo del producto.")
    comercio_aviso_bulto = fields.Char(
        "Bulto del proveedor", compute="_compute_comercio_aviso_bulto",
        help="El proveedor vende de a bultos enteros (p. ej. cajas de 100) y la cantidad no es un bulto entero.")
    comercio_mas_barato = fields.Char(
        "Más barato", compute="_compute_comercio_mas_barato",
        help="Otro proveedor tiene un precio vigente menor para esta cantidad. Compara solo el "
             "precio de lista con descuento: no incluye flete ni condiciones (P-004).")

    @api.depends("product_id", "partner_id", "order_id.date_order")
    def _compute_comercio_aviso_lista(self):
        Info = self.env["product.supplierinfo"]
        for line in self:
            line.comercio_aviso_lista = False
            if line.display_type or not line.product_id or not line.partner_id:
                continue
            partners = line.partner_id.commercial_partner_id | line.partner_id
            fecha = (line.order_id.date_order or fields.Datetime.now()).date()
            plantilla = line.product_id.product_tmpl_id
            if Info.search_count([("product_tmpl_id", "=", plantilla.id), *dominio_vigente(partners, fecha)]):
                continue
            cerrado = Info.search([("product_tmpl_id", "=", plantilla.id), ("partner_id", "in", partners.ids),
                                   ("date_end", "!=", False)], order="date_end desc", limit=1)
            if cerrado:
                line.comercio_aviso_lista = _("Ya no está en su lista (cerrado el %s)",
                                              cerrado.date_end.strftime("%d/%m/%Y"))
            elif Info.search_count([("partner_id", "in", partners.ids)]):
                # Solo si del proveedor hay lista cargada: si no, no hay con qué comparar
                line.comercio_aviso_lista = _("No está en su lista")

    @api.depends("product_id", "partner_id", "product_qty", "uom_id", "order_id.date_order")
    def _compute_comercio_aviso_minimo(self):
        for line in self:
            minimo = line._comercio_minimo_no_alcanzado()
            line.comercio_aviso_minimo = _("Mínimo %(cantidad)s %(unidad)s: sin precio de lista",
                                           cantidad=f"{minimo.min_qty:g}", unidad=minimo.uom_id.name
                                           ) if minimo else False

    def _comercio_bulto(self):
        """Unidades por bulto de este proveedor para el producto (0 si vende suelto)."""
        self.ensure_one()
        if self.display_type or not self.product_id or not self.partner_id:
            return 0.0
        suyos = self.product_id._get_filtered_sellers(
            partner_id=self.partner_id, quantity=None,
            date=fields.Date.context_today(self, timestamp=self.order_id.date_order),
            uom_id=self.uom_id, params=self._get_select_sellers_params(),
        )
        return max(suyos.mapped("comercio_bulto") or [0.0])

    def _comercio_presentaciones(self):
        """Las otras presentaciones de este producto en la lista del proveedor (display x 20…)."""
        self.ensure_one()
        suyos = self.product_id._get_filtered_sellers(
            partner_id=self.partner_id, quantity=None,
            date=fields.Date.context_today(self, timestamp=self.order_id.date_order),
            uom_id=self.uom_id, params=self._get_select_sellers_params(),
        )
        return " · ".join(filter(None, suyos.mapped("comercio_presentaciones")))

    @api.depends("product_id", "partner_id", "product_qty", "uom_id", "order_id.date_order")
    def _compute_comercio_aviso_bulto(self):
        for line in self:
            bulto = line._comercio_bulto()
            resto = (line.product_qty or 0) % bulto if bulto else 0
            if not bulto or resto <= 1e-6:
                line.comercio_aviso_bulto = False
                continue
            abajo, arriba = line.product_qty - resto, line.product_qty - resto + bulto
            line.comercio_aviso_bulto = (
                _("De a %(bulto)s: pedir %(abajo)s o %(arriba)s", bulto=f"{bulto:g}", abajo=f"{abajo:g}",
                  arriba=f"{arriba:g}") if abajo else _("De a %(bulto)s: pedir %(arriba)s", bulto=f"{bulto:g}",
                                                       arriba=f"{arriba:g}"))
            otras = line._comercio_presentaciones()
            if otras:  # no se decide por la persona: se nombran las otras presentaciones
                line.comercio_aviso_bulto += _(" (también: %s)", otras)

    def _comercio_minimo_no_alcanzado(self):
        """Precio vigente de este proveedor con el menor mínimo, si la cantidad no llega a ese
        mínimo (Odoo no tiene precio de lista para la línea y pone el costo del producto)."""
        self.ensure_one()
        Info = self.env["product.supplierinfo"]
        if self.display_type or not self.product_id or not self.partner_id or self._get_seller_info():
            return Info
        # Precios vigentes del proveedor sin mirar la cantidad. Si no hay ninguno, el producto
        # no está en su lista (lo avisa comercio_aviso_lista).
        suyos = self.product_id._get_filtered_sellers(
            partner_id=self.partner_id, quantity=None,
            date=fields.Date.context_today(self, timestamp=self.order_id.date_order),
            uom_id=self.uom_id, params=self._get_select_sellers_params(),
        )
        return min(suyos, key=lambda s: s.min_qty) if suyos else Info

    @api.depends("product_id", "partner_id", "product_qty", "uom_id", "price_unit", "discount",
                 "order_id.date_order")
    def _compute_comercio_mas_barato(self):
        for line in self:
            line.comercio_mas_barato = False
            if line.display_type or not line.product_id or not line.partner_id:
                continue
            partners = line.partner_id.commercial_partner_id | line.partner_id
            compania = line.company_id or self.env.company
            fecha = fields.Date.context_today(line, timestamp=line.order_id.date_order)

            def en_pesos(monto, moneda, fecha=fecha, compania=compania):
                return moneda._convert(monto, compania.currency_id, compania, fecha, round=False)

            # Los mismos precios que usa Odoo al elegir proveedor (vigentes, cantidad mínima, unidad)
            otros = line.product_id._get_filtered_sellers(
                quantity=abs(line.product_qty), date=fecha, uom_id=line.uom_id,
                params=line._get_select_sellers_params(),
            ).filtered(lambda s: s.partner_id not in partners)
            if not otros:
                continue
            mejor = min(otros, key=lambda s: en_pesos(s.price_discounted, s.currency_id))
            propio = line._get_seller_info()
            if propio:
                precio_propio = en_pesos(propio["price_discounted"], propio["currency_id"])
            else:
                precio_propio = en_pesos(line.price_unit * (1 - (line.discount or 0) / 100), line.currency_id)
            precio_mejor = en_pesos(mejor.price_discounted, mejor.currency_id)
            if precio_mejor < precio_propio - 0.005:
                line.comercio_mas_barato = _(
                    "%(proveedor)s: %(precio)s", proveedor=mejor.partner_id.name,
                    precio=format_amount(self.env, precio_mejor, compania.currency_id))

    @api.onchange("product_id")
    def _onchange_comercio_aviso_lista(self):
        avisos = []
        if self.comercio_aviso_lista:
            avisos.append(_("%(aviso)s de %(proveedor)s. Se puede pedir igual; conviene confirmarlo con el "
                            "proveedor.", aviso=self.comercio_aviso_lista, proveedor=self.partner_id.name))
        if self.comercio_mas_barato:
            avisos.append(_("Más barato: %s (%s).", self.comercio_mas_barato, SALVEDAD))
        if avisos:
            return {"warning": {
                "title": self.product_id.display_name,
                "message": " ".join(avisos),
                "type": "notification",
            }}

    @api.onchange("product_qty", "uom_id")
    def _onchange_comercio_aviso_minimo(self):
        bulto = self._comercio_bulto()
        if bulto and (self.product_qty or 0) % bulto > 1e-6:
            return {"warning": {
                "title": self.product_id.display_name,
                "message": _("%(proveedor)s lo vende de a bultos de %(bulto)s: %(cantidad)s no es un bulto "
                             "entero. %(aviso)s.", proveedor=self.partner_id.name, bulto=f"{bulto:g}",
                             cantidad=f"{self.product_qty:g}", aviso=self.comercio_aviso_bulto),
                "type": "notification",
            }}
        minimo = self._comercio_minimo_no_alcanzado()
        if minimo:
            return {"warning": {
                "title": self.product_id.display_name,
                "message": _("La lista de %(proveedor)s pide un mínimo de %(cantidad)s %(unidad)s. Por debajo "
                             "no hay precio de lista: Odoo pone el costo del producto (%(costo)s). "
                             "Confirmar el precio con el proveedor o pedir el mínimo.",
                             proveedor=self.partner_id.name, cantidad=f"{minimo.min_qty:g}",
                             unidad=minimo.uom_id.name,
                             costo=format_amount(self.env, self.price_unit, self.currency_id)),
                "type": "notification",
            }}
