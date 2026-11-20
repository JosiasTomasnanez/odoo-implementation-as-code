"""Listas de precios que viajan a la tienda: «Tienda online» (todos) y las mayoristas."""
from __future__ import annotations

from odoo import api, fields, models


class ProductPricelist(models.Model):
    _inherit = "product.pricelist"

    comercio_tienda_sincronizar = fields.Boolean(
        "Sincronizar con la tienda",
        help="Sus precios viajan a la tienda online: la «Tienda online» y las listas mayoristas "
             "(las ven solo los clientes mayoristas aprobados que la tengan asignada).")
    comercio_tienda_publica = fields.Boolean(
        "Es la de la tienda",
        help="La lista que ve todo el mundo en la tienda online. Una sola.")
    comercio_tienda_ref = fields.Char(
        "Pedida desde la tienda", copy=False, readonly=True, index=True,
        help="Lista creada desde la administración de la tienda (para no crearla dos veces).")

    comercio_tienda_reglas = fields.Json(
        "Condiciones pedidas desde la tienda", copy=False, readonly=True,
        help="Lista armada en la administración de la tienda: su lista base, el descuento general "
             "y los descuentos por rubro o por producto. Sus reglas se regeneran desde acá.")

    @api.model_create_multi
    def create(self, vals_list):
        listas = super().create(vals_list)
        listas.filtered("comercio_tienda_publica")._comercio_tienda_unica_publica()
        return listas

    def _comercio_tienda_aplicar_reglas(self) -> None:
        """Deja las reglas de la lista como dicen sus condiciones (ADR 0037): una general «base −
        X %», una por producto de cada rubro con descuento propio (los rubros son categorías del
        PdV y las reglas de Odoo no las conocen: se despliegan por producto) y una por producto
        suelto, que le gana a la de su rubro. Solo toca lo que cambió. Cada regla lleva la compra
        mínima que ese producto tiene en la lista base (nunca suelto)."""
        Item = self.env["product.pricelist.item"].sudo()
        Plantilla = self.env["product.template"].sudo()
        Producto = self.env["product.product"].sudo()
        for lista in self.sudo():
            d = lista.comercio_tienda_reglas
            base = self.sudo().browse(int((d or {}).get("base") or 0)).exists()
            if not d or not base or base == lista:
                continue
            generales = base.item_ids.filtered(lambda r: r.applied_on == "3_global")
            deseadas = {("3_global", 0): (float(d.get("descuento") or 0), min(generales.mapped("min_quantity") or [0]))}
            por_plantilla, por_producto = {}, {}
            for r in d.get("reglas") or []:
                if r.get("tipo") == "rubro":
                    for t in Plantilla.search([("pos_categ_ids", "child_of", int(r["id"]))]):
                        por_plantilla[t] = float(r["descuento"])
                elif r.get("tipo") == "producto":
                    p = Producto.browse(int(r["id"])).exists()
                    if p:
                        por_producto[p] = float(r["descuento"])
            variantes = Producto.browse([p.id for p in por_producto])
            for t in por_plantilla:
                variantes |= t.product_variant_ids
            minimos = variantes._comercio_tienda_minimos(base)
            for t, desc in por_plantilla.items():
                deseadas[("1_product", t.id)] = (desc, min((minimos[v.id] for v in t.product_variant_ids), default=1))
            for p, desc in por_producto.items():
                deseadas[("0_product_variant", p.id)] = (desc, minimos[p.id])
            actuales, sobran = {}, Item.browse()
            for it in lista.item_ids:
                clave = (it.applied_on, it.product_id.id if it.applied_on == "0_product_variant"
                         else it.product_tmpl_id.id if it.applied_on == "1_product" else 0)
                propia = it.base == "pricelist" and it.base_pricelist_id == base and it.compute_price == "discount"
                if clave in actuales or clave not in deseadas or not propia:
                    sobran |= it
                else:
                    actuales[clave] = it
            nuevas = []
            for clave, (desc, minimo) in deseadas.items():
                # Un mínimo de 1 es «sin mínimo» (como en la regla general de la base)
                minimo = 0 if minimo <= 1 and clave[0] != "3_global" else minimo
                it = actuales.get(clave)
                if it:
                    if abs(it.price_discount - desc) > 1e-6 or abs(it.min_quantity - minimo) > 1e-6:
                        it.write({"price_discount": desc, "min_quantity": minimo})
                    continue
                vals = {"pricelist_id": lista.id, "applied_on": clave[0], "base": "pricelist", "base_pricelist_id": base.id,
                        "compute_price": "discount", "price_discount": desc, "min_quantity": minimo}
                if clave[0] == "1_product":
                    vals["product_tmpl_id"] = clave[1]
                elif clave[0] == "0_product_variant":
                    vals["product_id"] = clave[1]
                nuevas.append(vals)
            sobran.unlink()
            if nuevas:
                Item.create(nuevas)

    @api.model
    def _comercio_tienda_reaplicar_rubros(self) -> None:
        """Un producto cambió de rubro (o es nuevo): las listas con descuento por rubro se
        vuelven a desplegar, así el producto toma (o deja) el descuento de su rubro."""
        listas = self.sudo().search([("comercio_tienda_reglas", "!=", False)])
        listas.filtered(
            lambda li: any(r.get("tipo") == "rubro" for r in (li.comercio_tienda_reglas or {}).get("reglas") or [])
        )._comercio_tienda_aplicar_reglas()

    def write(self, vals):
        res = super().write(vals)
        if vals.get("comercio_tienda_publica"):
            self._comercio_tienda_unica_publica()
        if {"comercio_tienda_sincronizar", "comercio_tienda_publica", "item_ids", "active"} & set(vals):
            self._comercio_tienda_anotar_todo()
        return res

    def _comercio_tienda_unica_publica(self) -> None:
        """Una sola lista «de la tienda»: al marcar una, se desmarcan las demás.
        Sin listas (p. ej. al crear una que no es la pública) no se toca nada: antes, con un
        conjunto vacío, se desmarcaba la «Tienda online» al crear la «Mayorista» (09/11)."""
        if not self:
            return
        otras = self.sudo().search([("comercio_tienda_publica", "=", True), ("id", "not in", self[-1:].ids)])
        if otras:
            otras.write({"comercio_tienda_publica": False})

    def _comercio_tienda_anotar_todo(self) -> None:
        productos = self.env["product.product"].sudo().search([("product_tmpl_id.comercio_tienda_publicar", "=", True)])
        self.env["comercio.tienda.cambio"]._anotar("producto", productos.ids)

    @api.model
    def _comercio_tienda_listas(self) -> list[dict]:
        listas = self.sudo().search([("comercio_tienda_sincronizar", "=", True)])
        return [{"id": lista.id, "nombre": lista.name, "publica": bool(lista.comercio_tienda_publica)} for lista in listas]


class ProductPricelistItem(models.Model):
    _inherit = "product.pricelist.item"

    @api.model_create_multi
    def create(self, vals_list):
        reglas = super().create(vals_list)
        reglas._comercio_tienda_anotar()
        return reglas

    def write(self, vals):
        antes = self._comercio_tienda_productos()
        res = super().write(vals)
        self.env["comercio.tienda.cambio"]._anotar_productos(antes | self._comercio_tienda_productos())
        return res

    def unlink(self):
        productos = self._comercio_tienda_productos()
        res = super().unlink()
        self.env["comercio.tienda.cambio"]._anotar_productos(productos)
        return res

    def _comercio_tienda_anotar(self) -> None:
        self.env["comercio.tienda.cambio"]._anotar_productos(self._comercio_tienda_productos())

    def _comercio_tienda_productos(self):
        """Productos publicados a los que puede afectar la regla (si es por categoría o general,
        todos los publicados de esa categoría o todos)."""
        Producto = self.env["product.product"].sudo()
        resultado = Producto.browse()
        reglas = self.sudo().filtered(lambda r: r.pricelist_id.comercio_tienda_sincronizar)
        if not reglas:
            return resultado
        publicados = [("product_tmpl_id.comercio_tienda_publicar", "=", True)]
        for r in reglas:
            if r.applied_on == "0_product_variant" and r.product_id:
                resultado |= r.product_id
            elif r.applied_on == "1_product" and r.product_tmpl_id:
                resultado |= r.product_tmpl_id.product_variant_ids
            elif r.applied_on == "2_product_category" and r.categ_id:
                resultado |= Producto.search(publicados + [("categ_id", "child_of", r.categ_id.id)])
            else:
                return Producto.search(publicados)
        return resultado
