"""Qué se publica en la tienda y cómo viaja cada producto (ADR 0033)."""
from __future__ import annotations

from odoo import Command, _, api, fields, models
from odoo.exceptions import AccessError, UserError

# Campos de la plantilla que, si cambian, cambian lo que ve la tienda.
CAMPOS_TIENDA = {
    "name", "barcode", "default_code", "list_price", "taxes_id", "pos_categ_ids", "image_1920",
    "description_sale", "uom_id", "uom_ids", "active", "sale_ok", "categ_id", "seller_ids",
    "comercio_tienda_publicar", "comercio_tienda_consultar", "comercio_tienda_nuevo_hasta",
}


class ProductTemplate(models.Model):
    _inherit = "product.template"

    comercio_tienda_publicar = fields.Boolean(
        "Publicar en la tienda", copy=False, index=True,
        help="Aparece en la tienda online (comercio-ejemplo.example). Si se desmarca, deja de verse; los "
             "pedidos que ya lo tienen no se tocan.")
    comercio_tienda_consultar = fields.Boolean(
        "Consultar disponibilidad", copy=False,
        help="Se vende y se paga igual, sin tope de stock; el cliente ve «Te confirmamos "
             "disponibilidad en el día» y, si no está, se encarga al proveedor.")

    comercio_tienda_nuevo_hasta = fields.Date(
        "Nuevo en la tienda hasta", copy=False,
        help="Hasta esa fecha lleva la etiqueta «Nuevo» y aparece en «Llegó mercadería nueva».")

    # Lista «A reponer» (pedido del implementador, 03/11): un producto publicado cuyo stock libre
    # llega al margen pasa solo a «consultar disponibilidad» en la tienda (se sigue vendiendo, sin
    # tope) y entra a la lista; sale solo cuando el stock vuelve. Sin avisos: se mira la lista.
    comercio_tienda_bajo_minimo = fields.Boolean(
        "Bajo el mínimo de la tienda", readonly=True, copy=False, index=True,
        help="El stock libre llegó al margen de la tienda: se ofrece como «Consultar disponibilidad» "
             "hasta que se reponga.")
    comercio_tienda_bajo_desde = fields.Datetime("Bajo el mínimo desde", readonly=True, copy=False)
    comercio_tienda_reponer = fields.Selection(
        [("pendiente", "Para decidir"), ("pedido", "Pedido al proveedor"), ("no_reponer", "No reponer por ahora")],
        "Reposición", readonly=True, copy=False,
        help="Qué se decidió en la lista «A reponer». Vuelve a vacío cuando el stock se repone.")
    comercio_tienda_stock_libre = fields.Float("Stock libre (tienda)", readonly=True, copy=False)
    comercio_tienda_margen = fields.Float("Margen (tienda)", readonly=True, copy=False)

    @api.model_create_multi
    def create(self, vals_list):
        plantillas = super().create(vals_list)
        if plantillas.filtered("pos_categ_ids"):
            self.env["product.pricelist"]._comercio_tienda_reaplicar_rubros()
        plantillas.filtered("comercio_tienda_publicar")._comercio_tienda_anotar()
        return plantillas

    def write(self, vals):
        cambia_publicar = "comercio_tienda_publicar" in vals
        antes = self.filtered("comercio_tienda_publicar") if cambia_publicar else self.browse()
        res = super().write(vals)
        if "pos_categ_ids" in vals:
            self.env["product.pricelist"]._comercio_tienda_reaplicar_rubros()
        if CAMPOS_TIENDA & set(vals):
            # Los publicados, más los que se acaban de despublicar (para sacarlos de la tienda).
            (self.filtered("comercio_tienda_publicar") | antes)._comercio_tienda_anotar(forzar=True)
        return res

    def _comercio_tienda_anotar(self, forzar: bool = False) -> None:
        variantes = self.with_context(active_test=False).mapped("product_variant_ids")
        if forzar:
            self.env["comercio.tienda.cambio"]._anotar("producto", variantes.ids)
        else:
            self.env["comercio.tienda.cambio"]._anotar_productos(variantes)

    def action_comercio_tienda_publicar(self):
        self.write({"comercio_tienda_publicar": True})

    def action_comercio_tienda_quitar(self):
        self.write({"comercio_tienda_publicar": False})

    def action_comercio_tienda_consultar(self):
        """Dejar a consultar para siempre (manual): sale de «A reponer»."""
        self.write({"comercio_tienda_consultar": True})
        self._comercio_tienda_marcar_bajo(False)

    def _comercio_tienda_puede_reponer(self) -> None:
        """Solo Compras o Inventario deciden la reposición (los campos son de solo lectura y se
        escriben con sudo: el permiso se revisa acá, antes)."""
        if not (self.env.user.has_group("purchase.group_purchase_user") or self.env.user.has_group("stock.group_stock_user")):
            raise AccessError(_("Para decidir la reposición hace falta el permiso de Compras o de Inventario."))
        self.check_access("read")

    def action_comercio_tienda_no_reponer(self):
        self._comercio_tienda_puede_reponer()
        self.sudo().write({"comercio_tienda_reponer": "no_reponer"})

    def action_comercio_tienda_pedir(self):
        """«Pedir al proveedor»: suma cada producto a la solicitud en borrador de su proveedor más
        conveniente según Odoo (_select_seller), con su cantidad mínima. Queda en borrador: alguien
        la revisa y la confirma."""
        if not self.env.user.has_group("purchase.group_purchase_user"):
            raise AccessError(_("Para armar pedidos hace falta el permiso de Compras."))
        self.check_access("read")
        Orden = self.env["purchase.order"]
        ordenes, sin_proveedor = Orden, []
        for t in self:
            producto = t.product_variant_id
            proveedor = t._comercio_tienda_proveedor(producto)
            if not proveedor:
                sin_proveedor.append(t.name)
                continue
            orden = Orden.search([("partner_id", "=", proveedor.partner_id.id), ("state", "=", "draft")],
                                 order="id desc", limit=1) or Orden.create({"partner_id": proveedor.partner_id.id})
            cantidad = max(proveedor.min_qty or 1.0, 1.0)
            unidad = proveedor.uom_id or producto.uom_id
            ya = orden.order_line.filtered(lambda o, p=producto, u=unidad: o.product_id == p and o.uom_id == u)[:1]
            if ya:
                ya.product_qty = max(ya.product_qty, cantidad)
            else:
                orden.order_line = [Command.create({"product_id": producto.id, "product_qty": cantidad, "uom_id": unidad.id})]
            ordenes |= orden
            t.sudo().comercio_tienda_reponer = "pedido"
        if sin_proveedor and not ordenes:
            raise UserError(_("No tienen proveedor cargado: %s", ", ".join(sin_proveedor[:5])))
        accion = {"type": "ir.actions.act_window", "res_model": "purchase.order", "name": _("Pedidos a proveedores")}
        if len(ordenes) == 1:
            return accion | {"view_mode": "form", "views": [(False, "form")], "res_id": ordenes.id}
        return accion | {"view_mode": "list,form", "views": [(False, "list"), (False, "form")],
                         "domain": [("id", "in", ordenes.ids)]}

    def _comercio_tienda_proveedor(self, producto):
        """El precio de proveedor vigente más barato, como elige Odoo (_select_seller ordena por
        precio con descuento, pasado a pesos), pero sin filtrar por la compra mínima: la cantidad
        a pedir es justamente ese mínimo. Odoo 20: _select_seller devuelve un dict, por eso se
        usa _get_filtered_sellers."""
        empresa = self.env.company
        hoy = fields.Date.context_today(self)
        vigentes = producto._get_filtered_sellers(quantity=None)
        return vigentes.sorted(lambda s: (s.currency_id._convert(s.price_discounted, empresa.currency_id, empresa, hoy, round=False),
                                          s.sequence, s.id))[:1]

    def _comercio_tienda_marcar_bajo(self, bajo: bool, libre: float = 0.0, margen: float = 0.0) -> None:
        """Actualiza la marca sin volver a anotar el producto en la cola (no es un dato de la tienda)."""
        for t in self.sudo():
            vals = {}
            if bajo and not t.comercio_tienda_bajo_minimo:
                vals = {"comercio_tienda_bajo_minimo": True, "comercio_tienda_bajo_desde": fields.Datetime.now(),
                        "comercio_tienda_reponer": "pendiente"}
            elif not bajo and t.comercio_tienda_bajo_minimo:
                vals = {"comercio_tienda_bajo_minimo": False, "comercio_tienda_bajo_desde": False,
                        "comercio_tienda_reponer": False}
            if bajo and (t.comercio_tienda_stock_libre != libre or t.comercio_tienda_margen != margen):
                vals |= {"comercio_tienda_stock_libre": libre, "comercio_tienda_margen": margen}
            if vals:
                t.write(vals)


class ProductProduct(models.Model):
    _inherit = "product.product"

    def write(self, vals):
        res = super().write(vals)
        if {"barcode", "default_code", "active", "image_variant_1920", "lst_price"} & set(vals):
            self.env["comercio.tienda.cambio"]._anotar_productos(self)
        return res

    def _comercio_tienda_id_imagen(self) -> str | None:
        """Identificador de la foto (el checksum del adjunto): cambia solo si cambia la foto."""
        self.ensure_one()
        for modelo, res_id, campo in (("product.product", self.id, "image_variant_1920"),
                                      ("product.template", self.product_tmpl_id.id, "image_1920")):
            adj = self.env["ir.attachment"].sudo().search(
                [("res_model", "=", modelo), ("res_id", "=", res_id), ("res_field", "=", campo)], limit=1)
            if adj:
                return adj.checksum
        return None

    def _comercio_tienda_datos(self) -> list[dict]:
        """Lo que la tienda necesita de cada producto, armado acá (el conector no lee modelos)."""
        if not self:
            return []
        almacen = self.env["stock.warehouse"].sudo().search([("company_id", "=", self.env.company.id)], limit=1)
        con_stock = self.with_context(warehouse_id=almacen.id) if almacen else self
        listas = self.env["product.pricelist"].sudo().search([("comercio_tienda_sincronizar", "=", True)])
        publica = listas.filtered("comercio_tienda_publica")[:1]
        precios = {lista.id: lista._compute_price_rule(self, 1.0) for lista in listas}
        # Listas mayoristas (ADR 0035): cada producto se vende desde su cantidad mínima (la de la
        # regla de la lista que le aplica) y el precio es el de esa cantidad.
        minimos = {lista.id: self._comercio_tienda_minimos(lista) for lista in listas - publica}
        for lista_id, por_producto in minimos.items():
            lista = listas.browse(lista_id)
            for cantidad in set(por_producto.values()) - {1}:
                grupo = self.filtered(lambda x: por_producto[x.id] == cantidad)
                precios[lista_id].update(lista._compute_price_rule(grupo, float(cantidad)))
        datos = []
        for p in con_stock:
            t = p.product_tmpl_id
            publicado = bool(t.comercio_tienda_publicar and t.active and p.active and t.sale_ok)
            margen = t.categ_id._comercio_tienda_margen()
            libre = p.free_qty if t.is_storable else None
            # Bajo el mínimo: se ofrece «a consultar» solo, sin frenar la venta, y va a «A reponer».
            bajo = bool(publicado and libre is not None and not t.comercio_tienda_consultar and libre <= margen)
            t._comercio_tienda_marcar_bajo(bajo, libre or 0.0, margen)
            fila = {
                "id": p.id,
                "publicado": publicado,
                "nombre": p.display_name if p.product_template_variant_value_ids else t.name,
                "codigo": p.barcode or None,
                "referencia": p.default_code or None,
                "categoria_id": t.pos_categ_ids[:1].id or None,
                "unidad": t.uom_id.name or "unidad",
                "descripcion": t.description_sale or None,
                "consultar": bool(t.comercio_tienda_consultar) or bajo,
                "nuevo_hasta": fields.Date.to_string(t.comercio_tienda_nuevo_hasta) if t.comercio_tienda_nuevo_hasta else None,
                "dias_encargo": min(t.seller_ids.mapped("delay"), default=None),
                "imagen": p._comercio_tienda_id_imagen(),
                "margen": margen,
                "stock_libre": libre,
                "bulto": p._comercio_tienda_bulto(),
                "precios": [],
            }
            if publicado:
                base = None
                if publica:
                    base = p._comercio_tienda_con_iva(p.lst_price)
                for lista in listas:
                    precio, regla_id = precios[lista.id][p.id]
                    final = p._comercio_tienda_con_iva(precio)
                    regla = self.env["product.pricelist.item"].sudo().browse(regla_id) if regla_id else None
                    referencia = base if lista == publica else (
                        p._comercio_tienda_con_iva(precios[publica.id][p.id][0]) if publica else None)
                    oferta = referencia is not None and final < referencia - 0.005
                    fila["precios"].append({
                        "lista_id": lista.id,
                        "precio": round(final * 100),
                        "precio_anterior": round(referencia * 100) if oferta else None,
                        "oferta_hasta": fields.Datetime.to_string(regla.date_end) if oferta and regla and regla.date_end else None,
                        "minimo": minimos.get(lista.id, {}).get(p.id, 1),
                    })
            datos.append(fila)
        return datos

    def _comercio_tienda_minimos(self, lista) -> dict[int, int]:
        """Cantidad mínima de cada producto en una lista: la menor «cantidad mínima» de las reglas
        de la lista que le aplican (vigentes hoy). Sin reglas o sin mínimo: 1.
        Usa métodos internos de Odoo (_get_applicable_rules, _is_applicable_for; docs/codigo-propio.md)."""
        hoy = fields.Datetime.now()
        res = {}
        for p in self:
            reglas = lista._get_applicable_rules(p, 1e9, hoy)
            reglas = reglas.filtered(lambda r, p=p: r._is_applicable_for(p, 1e9))
            minimo = min(reglas.mapped("min_quantity"), default=0.0)
            res[p.id] = max(1, int(-(-minimo // 1)))  # hacia arriba: 2,5 → 3
        return res

    def _comercio_tienda_bulto(self):
        """Bulto para mayoristas: el embalaje más chico del producto (Odoo 20: «Embalajes», uom_ids),
        en unidades del producto. Sin embalajes (o de 1): None, se vende por unidad."""
        t = self.product_tmpl_id
        cantidades = [e._compute_quantity(1.0, t.uom_id) for e in t.uom_ids if e != t.uom_id]
        cantidades = [round(c) for c in cantidades if c > 1 and abs(c - round(c)) < 1e-6]
        return min(cantidades, default=None)

    def _comercio_tienda_con_iva(self, precio: float) -> float:
        """Precio final con IVA, sirva el impuesto con IVA incluido o no."""
        impuestos = self.taxes_id.filtered(lambda i: i.company_id == self.env.company)
        if not impuestos:
            return precio
        return impuestos.compute_all(precio, product=self, quantity=1.0)["total_included"]


class ProductCategory(models.Model):
    _inherit = "product.category"

    comercio_tienda_margen_stock = fields.Float(
        "Margen de stock en la tienda",
        help="Unidades que no se ofrecen online, para cubrir lo que se vende en el mostrador mientras "
             "llega el dato a la tienda. Vacío o 0: se toma el de la categoría de arriba.")

    def write(self, vals):
        res = super().write(vals)
        if "comercio_tienda_margen_stock" in vals:
            productos = self.env["product.product"].sudo().search([
                ("categ_id", "child_of", self.ids), ("product_tmpl_id.comercio_tienda_publicar", "=", True)])
            self.env["comercio.tienda.cambio"]._anotar("producto", productos.ids)
        return res

    def _comercio_tienda_margen(self) -> float:
        cat = self
        while cat:
            if cat.comercio_tienda_margen_stock:
                return cat.comercio_tienda_margen_stock
            cat = cat.parent_id
        # Odoo 20: ir.config_parameter.get_str (ya no get_param).
        valor = self.env["ir.config_parameter"].sudo().get_str("comercio_tienda.margen_stock") or "1"
        try:
            return float(valor)
        except ValueError:
            return 1.0
