from odoo import api, fields, models

# Campos del precio principal que se copian a su fila «precio por mayor»
COPIADOS = ("partner_id", "product_tmpl_id", "product_id", "product_code", "product_name", "currency_id",
            "delay", "discount", "date_start", "date_end", "company_id", "uom_id", "comercio_bulto")
SINCRONIZAN = set(COPIADOS) | {"comercio_precio_mayor", "comercio_cantidad_mayor", "min_qty"}


class ProductSupplierinfo(models.Model):
    """Dos precios del mismo proveedor: por menor y por mayor (desde cierta cantidad).

    El precio principal (el que trae la lista) guarda también el precio por mayor y la
    cantidad. Con eso se mantiene sola una segunda fila nativa de Odoo con esa cantidad
    mínima, así Compras elige el precio que corresponde según la cantidad. La segunda fila
    sigue al principal: se cierra, se reabre y se borra con él (historial y deshacer).
    """

    _inherit = "product.supplierinfo"

    comercio_precio_mayor = fields.Float(
        "Precio por mayor", digits="Product Price",
        help="Precio del proveedor comprando desde «Por mayor desde». Lo carga la lista.")
    comercio_cantidad_mayor = fields.Float("Por mayor desde", digits="Product Unit")
    comercio_bulto = fields.Float(
        "Unidades por bulto", digits="Product Unit",
        help="El proveedor vende de a bultos enteros (p. ej. cajas de 100): se pide 100, 200… La orden de "
             "compra avisa si la cantidad no es un bulto entero. No es lo mismo que la compra mínima.")
    # Un proveedor puede mandar su lista partida (p. ej. FC: general y bulones en otra hoja) y
    # tener una «lista» por parte: las bajas de una no tienen que cerrar los precios de la otra.
    comercio_presentaciones = fields.Text(
        "Otras presentaciones",
        help="El mismo producto en otras presentaciones de la lista del proveedor (display x 20, pallet…): "
             "la orden de compra las nombra en el aviso del bulto.")
    comercio_lista_id = fields.Many2one(
        "comercio.lista.proveedor", "Lista del proveedor", index=True, ondelete="set null", readonly=True,
        help="La lista que cargó o actualizó este precio por última vez.")
    comercio_escala_de_id = fields.Many2one(
        "product.supplierinfo", "Precio por mayor de", ondelete="cascade", readonly=True, index=True,
        help="Fila creada sola a partir del precio por mayor de otra: se cambia desde esa.")

    def _comercio_sincronizar_escala(self):
        Info = self.with_context(comercio_sincronizando=True)
        for principal in self.filtered(lambda s: not s.comercio_escala_de_id):
            escala = Info.search([("comercio_escala_de_id", "=", principal.id)], limit=1)
            quiere = principal.comercio_precio_mayor > 0 and principal.comercio_cantidad_mayor > max(
                principal.min_qty, 1)
            if not quiere:
                escala.unlink()
                continue
            vals = {campo: principal._fields[campo].convert_to_write(principal[campo], principal)
                    for campo in COPIADOS}
            vals.update({"min_qty": principal.comercio_cantidad_mayor, "price": principal.comercio_precio_mayor,
                         "comercio_escala_de_id": principal.id})
            if escala:
                escala.write(vals)
            else:
                Info.create(vals)

    @api.model_create_multi
    def create(self, vals_list):
        precios = super().create(vals_list)
        if not self.env.context.get("comercio_sincronizando"):
            precios._comercio_sincronizar_escala()
        return precios

    def write(self, vals):
        res = super().write(vals)
        if SINCRONIZAN & set(vals) and not self.env.context.get("comercio_sincronizando"):
            self._comercio_sincronizar_escala()
        return res
