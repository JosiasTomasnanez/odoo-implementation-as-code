"""«Enviar por WhatsApp» en la orden de compra: abre el WhatsApp de quien está en la PC
(WhatsApp Web o la aplicación) con el chat del proveedor y el pedido escrito. Antes se
muestra el mensaje para corregirlo, como el mail. No usa la API de WhatsApp Business: sin
número exclusivo, sin plantillas de Meta, sin costo por mensaje y sin publicar el servidor.
Falta tocar «Enviar» (y adjuntar el PDF si se quiere)."""
import re
from urllib.parse import quote

from odoo import _, api, fields, models
from odoo.exceptions import UserError


def numero_whatsapp(numero: str, pais: str = "AR") -> str:
    """Solo dígitos, con código de país, como lo pide wa.me. En Argentina WhatsApp usa el 9
    de celular después del 54 («351 512-3456» → 5493515123456)."""
    digitos = re.sub(r"\D", "", numero or "")
    try:
        import phonenumbers  # viene con Odoo

        digitos = phonenumbers.format_number(phonenumbers.parse(numero, pais or "AR"),
                                             phonenumbers.PhoneNumberFormat.E164).lstrip("+")
    except Exception:  # noqa: BLE001 - número raro: se usa tal cual
        pass
    if digitos.startswith("54") and not digitos.startswith("549"):
        digitos = "549" + digitos[2:]
    return digitos


class PurchaseOrder(models.Model):
    _inherit = "purchase.order"

    def _comercio_detalle_para_proveedor(self, linea):
        """Cómo lo conoce el proveedor: su código y su descripción (de su lista vigente). Sin eso,
        nuestro nombre, nunca la referencia interna (al proveedor no le dice nada)."""
        # En Odoo 20 devuelve un dict ({} si no hay); el precio está en «supplierinfo»
        precio = linea.product_id._select_seller(
            partner_id=self.partner_id, quantity=linea.product_qty, date=self.date_order and self.date_order.date(),
            uom_id=linea.uom_id).get("supplierinfo") or self.env["product.supplierinfo"]
        nombre = precio.product_name or linea.product_id.name
        return f"[{precio.product_code}] {nombre}" if precio.product_code else nombre

    def _comercio_texto_whatsapp(self):
        self.ensure_one()
        renglones = []
        for linea in self.order_line.filtered(lambda li: li.product_id and not li.display_type):
            cantidad = f"{linea.product_qty:g}".replace(".", ",")
            renglones.append(f"• {cantidad} {linea.uom_id.name} - {self._comercio_detalle_para_proveedor(linea)}")
        saludo = _("Hola %s!", self.partner_id.name)
        pedido = _("Te paso el pedido %(n)s de %(e)s:", n=self.name, e=self.company_id.name)
        cierre = _("Por favor confirmame disponibilidad y fecha de entrega. ¡Gracias!")
        return "\n".join([saludo, pedido, "", *renglones, "", cierre])

    def _comercio_destino_whatsapp(self):
        """Número de WhatsApp del proveedor (wa.me), o un error claro si falta algo."""
        self.ensure_one()
        contacto = self.partner_id
        numero = contacto.phone or contacto.commercial_partner_id.phone
        if not numero:
            raise UserError(_("%s no tiene teléfono cargado: ponelo en su ficha (el celular del WhatsApp, "
                              "por ejemplo 351 15 512-3456) y volvé a tocar el botón.", contacto.name))
        if not self.order_line.filtered("product_id"):
            raise UserError(_("El pedido no tiene productos."))
        pais = (contacto.country_id or self.company_id.country_id).code or "AR"
        return numero, numero_whatsapp(numero, pais)

    def action_comercio_enviar_whatsapp(self):
        """Muestra el mensaje para revisarlo o corregirlo; «Abrir WhatsApp» lo manda al chat."""
        self.ensure_one()
        self._comercio_destino_whatsapp()  # avisa antes de abrir la ventana si falta el teléfono
        return {"type": "ir.actions.act_window", "res_model": "comercio.whatsapp.pedido",
                "view_mode": "form", "target": "new", "name": _("Enviar por WhatsApp"),
                "context": {"default_order_id": self.id}}

    def _comercio_abrir_whatsapp(self, texto):
        """Abre WhatsApp con el chat del proveedor y `texto` escrito."""
        self.ensure_one()
        numero, destino = self._comercio_destino_whatsapp()
        if self.state == "draft":
            self.write({"state": "sent"})  # como al mandarla por mail
        self.message_post(body=_("Se abrió WhatsApp para mandar el pedido a %(c)s (%(n)s). Confirmá en "
                                 "WhatsApp que se envió.", c=self.partner_id.name, n=numero))
        return {"type": "ir.actions.act_url", "target": "new",
                "url": f"https://wa.me/{destino}?text={quote(texto)}"}


class WhatsappPedido(models.TransientModel):
    _name = "comercio.whatsapp.pedido"
    _description = "Mensaje de WhatsApp del pedido"

    order_id = fields.Many2one("purchase.order", required=True, ondelete="cascade")
    partner_id = fields.Many2one(related="order_id.partner_id", string="Para")
    telefono = fields.Char(compute="_compute_telefono", string="WhatsApp")
    texto = fields.Text("Mensaje", compute="_compute_texto", store=True, readonly=False,
                        help="Se puede corregir antes de abrir WhatsApp; ahí también se puede seguir cambiando.")

    @api.depends("order_id")
    def _compute_telefono(self):
        for asistente in self:
            contacto = asistente.order_id.partner_id
            asistente.telefono = contacto.phone or contacto.commercial_partner_id.phone

    @api.depends("order_id")
    def _compute_texto(self):
        for asistente in self:
            asistente.texto = asistente.order_id._comercio_texto_whatsapp() if asistente.order_id else False

    def action_abrir(self):
        self.ensure_one()
        if not (self.texto or "").strip():
            raise UserError(_("El mensaje está vacío."))
        return self.order_id._comercio_abrir_whatsapp(self.texto)
