from odoo import _, api, fields, models
from odoo.addons.comercio_catalogo.catalogo import plan as motor
from odoo.exceptions import UserError

from ..calculo import precio_de_lista, precio_final


class ComercioListaImportacion(models.Model):
    _inherit = "comercio.lista.importacion"

    def _aplicar_o_encolar(self, lineas):
        """Un producto que se agrega a nuestro catálogo toma el precio de venta del margen de su
        categoría. Sin margen (p. ej. una categoría recién creada desde el desplegable) quedaría a
        $1 en la caja: se frena antes y se explica qué hacer."""
        crean = lineas.filtered(lambda li: li.estado == "pendiente" and (
            (li.accion == motor.NUEVO and li.decision == "aplicar")
            or (li.accion == motor.POSIBLE_DUPLICADO and li.decision == "es_nuevo")))
        con_margen_propio = bool(self.partner_id.commercial_partner_id.comercio_margen_proveedor)
        sin_margen = crean.mapped(lambda li: li.categoria_id or self.lista_id.categoria_id).filtered(
            lambda cat: not cat.comercio_margen_efectivo and not con_margen_propio)
        if crean.filtered(lambda li: not (li.categoria_id or self.lista_id.categoria_id)):
            raise UserError(_("Elegí la categoría de los productos a agregar: de ella sale su precio de venta."))
        if sin_margen:
            raise UserError(_(
                "La categoría %(c)s no tiene margen: el producto quedaría a $1 en la caja.\n\n"
                "Cargale el margen en Costos y precios → Precios de venta → Márgenes por categoría (o "
                "ponela dentro de una categoría que lo tenga) y volvé a tocar «Agregar». También se "
                "puede elegir otra categoría en la fila.",
                c=", ".join(f"«{cat.complete_name}»" for cat in sin_margen)))
        return super()._aplicar_o_encolar(lineas)


class ComercioListaImportacionLinea(models.Model):
    _inherit = "comercio.lista.importacion.linea"

    precio_venta = fields.Float(
        "Precio de venta", compute="_compute_precio_venta",
        help="Si lo tenemos: su precio de venta. Si no: el que tendría al agregarlo, con el costo de "
        "esta lista y el margen de la categoría elegida (vacío si la categoría no tiene margen).")

    @api.depends("producto_id.list_price", "costo", "categoria_id")
    def _compute_precio_venta(self):
        incluido = self.env.company.account_price_include == "tax_included"
        iva_empresa = self.env.company.account_sale_tax_id.filtered(lambda t: t.amount_type == "percent")
        for linea in self:
            if linea.producto_id:
                linea.precio_venta = linea.producto_id.list_price
                continue
            categoria = linea.categoria_id or linea.importacion_id.lista_id.categoria_id
            regla = categoria._comercio_regla() if categoria else None
            # Un producto nuevo tiene un solo proveedor (el de esta lista): si tiene margen propio, manda
            margen_prov = linea.importacion_id.partner_id.commercial_partner_id.comercio_margen_proveedor
            if regla and margen_prov:
                regla = dict(regla, margen=margen_prov)
            if not regla or not regla["margen"] or linea.costo <= 0:
                linea.precio_venta = 0.0
                continue
            # Como al crear el producto: base = costo de la lista (un producto nuevo tiene un solo
            # proveedor); IVA de la regla o el de venta de la empresa (el que recibe el producto).
            iva = sum((regla["iva"] or iva_empresa).mapped("amount"))
            final = precio_final(linea.costo, regla["margen"], iva, regla["redondeo"])
            linea.precio_venta = precio_de_lista(final, iva, incluido)
