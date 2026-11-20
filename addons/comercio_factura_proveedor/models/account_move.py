import base64
import copy
import logging
import time

from markupsafe import Markup

from odoo import Command, _, api, fields, models
from odoo.exceptions import UserError
from odoo.tools import float_compare

from odoo.addons.comercio_catalogo.catalogo.codigos import es_gtin_valido
from odoo.addons.comercio_catalogo.catalogo.pdf import renglones_desde_pdf, tabla_desde_pdf
from odoo.addons.comercio_catalogo.catalogo.similitud import Buscador, Configuracion, similitud
from odoo.addons.comercio_catalogo_ia.ia import verificar as ia
from odoo.addons.comercio_catalogo_ia.ia.leer import paginas
from odoo.addons.comercio_catalogo_ia.models.importacion import (
    CONFIANZA_PARA_PRESELECCIONAR,
    UMBRAL_AMPLIO,
    _configuracion,
)

from ..factura import leer
from ..factura.cuit import cuit_valido

_logger = logging.getLogger(__name__)

TIPOS = {"pdf": "application/pdf", "jpg": "image/jpeg", "png": "image/png", "webp": "image/webp"}
MAX_PAGINAS_IA = 5  # una factura no tiene más; más es otra cosa (o un error al subir)
PARECIDO_MINIMO = 0.85  # para sugerir, no para cargar: la persona confirma
# Contra nuestros productos (el motor de las listas marca «posible duplicado» desde 0,50): solo
# se sugiere lo muy parecido; lo dudoso lo mira la IA si se le pide
PARECIDO_NUESTRO = 0.85  # «muy parecido» del motor (con 0,75 sugería «reforzado» por «económico»)
MAXIMO_IA = 100  # artículos por clic en «Verificar con IA»
TOLERANCIA_LISTA = 0.005  # diferencias menores contra el precio de lista son redondeos
TOLERANCIA_TOTAL = 1.0  # pesos: menos es redondeo de centavos línea por línea
# Código ARCA del tributo de cada percepción (grupos de impuestos de l10n_ar)
TRIBUTO_PERCEPCION = {"iibb": "07", "iva": "06", "ganancias": "09"}


def _pesos(valor):
    numero = f"{valor:,.2f}".replace(",", " ").replace(".", ",").replace(" ", ".")
    return f"$ {numero}"  # $ 1.234,56


def _tipo_de_archivo(nombre, mimetype):
    nombre = (nombre or "").lower()
    mimetype = mimetype or ""
    if "pdf" in mimetype or nombre.endswith(".pdf"):
        return "pdf"
    if "jpeg" in mimetype or nombre.endswith((".jpg", ".jpeg")):
        return "jpg"
    if "png" in mimetype or nombre.endswith(".png"):
        return "png"
    if "webp" in mimetype or nombre.endswith(".webp"):
        return "webp"
    return None


class AccountMove(models.Model):
    _inherit = "account.move"

    comercio_factura_linea_ids = fields.One2many(
        "comercio.factura.linea", "move_id", "Leído de la factura", copy=False)
    comercio_lectura = fields.Html("Lectura de la factura", readonly=True, copy=False)
    comercio_pendientes = fields.Integer(compute="_compute_comercio_pendientes", string="Sin cargar")
    comercio_proveedor_factura_id = fields.Many2one(
        "res.partner", "Proveedor según la factura", readonly=True, copy=False,
        help="El CUIT de la factura es de otro proveedor que el elegido: probablemente se subió en el "
             "proveedor equivocado.")
    comercio_cuit_sin_proveedor = fields.Char(
        "CUIT sin proveedor", readonly=True, copy=False,
        help="El CUIT de la factura no es de ningún proveedor cargado: hay que elegirlo o crearlo.")
    comercio_total_factura = fields.Monetary(
        "Total según el proveedor", readonly=True, copy=False, currency_field="currency_id",
        help="El TOTAL impreso en la factura del proveedor (leído del PDF o de la foto). La factura de Odoo "
             "tiene que dar lo mismo: si no, falta algo (flete, percepciones, impuestos).")
    comercio_diferencia_total = fields.Monetary(
        "Diferencia con el total del proveedor", compute="_compute_comercio_diferencia_total",
        currency_field="currency_id")
    comercio_total_distinto = fields.Boolean(compute="_compute_comercio_diferencia_total")
    comercio_total_odoo = fields.Monetary(
        "Total de esta factura", compute="_compute_comercio_diferencia_total", currency_field="currency_id")

    @api.depends("amount_total", "comercio_total_factura", "state", "invoice_line_ids.price_total",
                 "invoice_line_ids.comercio_percepcion")
    def _compute_comercio_diferencia_total(self):
        for move in self:
            move.comercio_total_odoo = move._comercio_total_odoo()
            move.comercio_diferencia_total = move.comercio_total_odoo - move.comercio_total_factura \
                if move.comercio_total_factura else 0.0
            move.comercio_total_distinto = move._comercio_total_distinto()

    def _comercio_total_odoo(self):
        """El total del borrador sumando sus líneas, para que el cartel cambie apenas se toca una línea:
        mientras no se guarda, `amount_total` queda como estaba y Odoo pone las percepciones en $ 1."""
        self.ensure_one()
        if self.state != "draft":
            return self.amount_total
        lineas = self.invoice_line_ids.filtered(lambda ml: ml.display_type == "product")
        percepciones = lineas.filtered(lambda ml: ml.comercio_extra == "percepcion")
        return sum((lineas - percepciones).mapped("price_total")) + sum(percepciones.mapped("comercio_percepcion"))

    def _comercio_total_distinto(self):
        self.ensure_one()
        return bool(self.comercio_total_factura) and \
            abs(self._comercio_total_odoo() - self.comercio_total_factura) >= TOLERANCIA_TOTAL

    @api.depends("line_ids.comercio_extra")
    def _compute_is_purchase_matched(self):
        """«Coincidencia de órdenes de compra» (purchase): el flete y las percepciones del pie no están en la
        orden y no cuentan (si no, una factura con todo bien daba 33 %)."""
        super()._compute_is_purchase_matched()
        for move in self.filtered(lambda m: m.invoice_line_ids.filtered("comercio_extra")):
            lineas = move.invoice_line_ids.filtered(lambda ml: ml.display_type == "product" and not ml.comercio_extra)
            unidas = len(lineas.filtered("purchase_line_id"))
            move.purchase_matched_ratio = 100.0 * unidas / len(lineas) if lineas else 0.0
            move.is_purchase_matched = bool(lineas) and unidas == len(lineas)

    @api.depends("amount_total", "comercio_total_factura")
    def _compute_release_to_pay(self):
        """«Se debe pagar» (account_3way_match): el flete y las percepciones no están en la orden de compra
        y no ponen la factura en excepción; que el total no dé el de la factura del proveedor, sí."""
        super()._compute_release_to_pay()
        for move in self:
            if move.payment_state == "paid" or move.force_release_to_pay \
                    or move.move_type not in ("in_invoice", "in_refund"):
                continue
            if move._comercio_total_distinto():
                move.release_to_pay = "exception"
                continue
            extras = move.invoice_line_ids.filtered("comercio_extra")
            if move.release_to_pay != "exception" or not extras:
                continue
            estados = set((move.invoice_line_ids - extras).filtered(
                lambda ml: ml.display_type not in ("line_section", "line_subsection", "line_note")).mapped("can_be_paid"))
            if len(estados) == 1:
                move.release_to_pay = estados.pop()

    @api.depends("comercio_factura_linea_ids.estado")
    def _compute_comercio_pendientes(self):
        for move in self:
            move.comercio_pendientes = len(move.comercio_factura_linea_ids.filtered(lambda li: li.estado != "cargada"))

    # ------------------------------------------------------------ al subir el archivo
    def _get_import_file_type(self, file_data):
        """Fotos también (Odoo solo las reconoce si está su digitalización)."""
        tipo = super()._get_import_file_type(file_data)
        if tipo or not self.is_purchase_document(include_receipts=True):
            return tipo
        return _tipo_de_archivo(file_data.get("name"), file_data.get("mimetype"))

    def _get_edi_decoder(self, file_data, new=False):
        """Factura de proveedor en PDF o foto: la leemos nosotros (antes que la digitalización
        de Odoo, que cobra créditos). Un XML de factura electrónica sigue con su lector."""
        if (self.move_type in ("in_invoice", "in_refund") and file_data.get("attachment")
                and file_data.get("import_file_type") in TIPOS):
            return {"decoder": self._comercio_decodificar, "priority": 20}
        return super()._get_edi_decoder(file_data, new)

    def _comercio_decodificar(self, move, file_data, new):
        """Devuelve None si se leyó, o el motivo (Odoo lo deja en el chatter)."""
        adjunto = file_data.get("origin_attachment") or file_data.get("attachment")
        ya_leida = (self.env.context.get("comercio_facturas_leidas") or {}).get(adjunto.id if adjunto else None)
        try:
            factura = ya_leida or move._comercio_leer(file_data["raw"], file_data["name"])
        except UserError as error:
            return str(error)
        if factura is None:
            return _("no se encontró la tabla de artículos")
        move._comercio_cargar(factura, file_data["name"])
        return None

    # ------------------------------------------------------------ botón «Leer factura»
    def action_comercio_leer_factura(self):
        self.ensure_one()
        if self.state != "draft":
            raise UserError(_("La factura ya está confirmada: para leerla de nuevo, pasala a borrador."))
        adjunto = self.message_main_attachment_id
        if not adjunto or not _tipo_de_archivo(adjunto.name, adjunto.mimetype):
            adjunto = self.attachment_ids.filtered(lambda a: _tipo_de_archivo(a.name, a.mimetype))[:1]
        if not adjunto:
            raise UserError(_("Adjuntá la factura del proveedor (PDF o foto) y volvé a tocar «Leer factura»."))
        factura = self._comercio_leer(adjunto.raw, adjunto.name)
        if factura is None:
            raise UserError(_("No se encontró la tabla de artículos en «%s».", adjunto.name))
        self._comercio_cargar(factura, adjunto.name)
        return True

    # ------------------------------------------------------------ orden de compra desde la factura
    def action_comercio_crear_orden(self):
        """Llegó la factura y el pedido no se hizo en Odoo: se crea la orden de compra con los
        productos, cantidades y precios de la factura, se confirma (así sale la recepción que suma
        el stock) y las líneas de la factura quedan unidas a esa orden, como si se hubiera pedido
        antes. Las líneas sin producto se agregan primero al catálogo."""
        self.ensure_one()
        if self.move_type != "in_invoice":
            raise UserError(_("La orden de compra se crea desde una factura de proveedor."))
        if not self.partner_id:
            raise UserError(_("Elegí primero el proveedor de la factura."))
        productos = self.invoice_line_ids.filtered(lambda ml: ml.display_type == "product" and not ml.comercio_extra)
        sin_producto = productos.filtered(lambda ml: not ml.product_id)
        if sin_producto and not self.env.context.get("comercio_sin_faltantes"):
            # No es un error: se abren los que faltan para agregarlos (o crear la orden sin ellos)
            return {"type": "ir.actions.client", "tag": "display_notification", "params": {
                "type": "warning", "message": _(
                    "%s artículos de la factura no están en nuestro catálogo: agregalos (o tocá «Crear la orden "
                    "igual») y la orden se crea.", len(sin_producto)),
                "next": self.action_comercio_revisar_articulos()}}
        lineas = productos.filtered(lambda ml: not ml.purchase_line_id and ml.product_id)
        if not lineas:
            raise UserError(_("Todas las líneas de la factura ya están en una orden de compra."))
        numero = self.name if self.name and self.name != "/" else False
        orden = self.env["purchase.order"].create({
            "partner_id": self.partner_id.id,
            "partner_ref": self.ref or numero,  # el número de la factura del proveedor
            # Fecha de hoy, no la de la factura: con la de la factura (anterior a la última lista subida)
            # los precios de su lista no estaban vigentes y cada línea decía «No está en su lista»
            "origin": numero,
            "order_line": [Command.create({
                "product_id": ml.product_id.id, "product_qty": ml.quantity, "uom_id": ml.product_uom_id.id,
                "price_unit": ml.price_unit, "discount": ml.discount, "tax_ids": [Command.set(ml.tax_ids.ids)],
            }) for ml in lineas],
        })
        orden.button_confirm()
        for ml, linea_orden in zip(lineas, orden.order_line.sorted("id"), strict=True):
            ml.purchase_line_id = linea_orden
        self._comercio_ajustar_percepciones()
        if not self.invoice_origin:
            self.invoice_origin = orden.name
        orden.message_post(body=_("Creada desde la factura %(f)s por %(u)s.", f=self.display_name,
                                  u=self.env.user.name))
        if sin_producto:
            orden.message_post(body=_("Quedaron afuera (no están en nuestro catálogo): %s",
                                      ", ".join(sin_producto.mapped("name"))))
        return {"type": "ir.actions.act_window", "res_model": "purchase.order", "res_id": orden.id,
                "view_mode": "form", "views": [(False, "form")], "name": orden.name}

    def action_comercio_revisar_articulos(self):
        """Los artículos de la factura que no son nuestros, en una lista para resolverlos de a varios."""
        self.ensure_one()
        accion = self.env["ir.actions.act_window"]._for_xml_id("comercio_factura_proveedor.action_revisar_articulos")
        accion.update({
            "name": _("Artículos de %s", self.display_name),
            "domain": [("move_id", "=", self.id)],
            "context": {"search_default_sin_producto": 1, "comercio_move_id": self.id},
        })
        return accion

    # ------------------------------------------------------------ leer
    def _comercio_leer(self, contenido, nombre):
        """PDF con texto: sin IA. Foto o PDF escaneado: Gemini (clave propia del comercio)."""
        contenido = getattr(contenido, "content", contenido)
        if isinstance(contenido, str):
            contenido = base64.b64decode(contenido)
        tipo = _tipo_de_archivo(nombre, "")
        if tipo == "pdf":
            try:
                factura = leer.leer_pdf(contenido, tabla_desde_pdf, renglones_desde_pdf)
            except Exception as error:  # noqa: BLE001 - PDF dañado o raro: se prueba con la IA
                _logger.warning("No se pudo leer el texto de %s: %s", nombre, error)
                factura = None
            if factura is not None:
                return factura
        return self._comercio_leer_con_ia(contenido, nombre, tipo)

    def _comercio_leer_con_ia(self, contenido, nombre, tipo):
        clave, modelos = _configuracion()
        if not clave:
            raise UserError(_(
                "«%s» es una foto o un PDF escaneado: para leerlo hace falta la IA (GEMINI_API_KEY en el "
                "servidor), que no está configurada. Cargá los artículos a mano o pedile al proveedor el PDF.",
                nombre))
        mime = TIPOS.get(tipo)
        if not mime:
            raise UserError(_("«%s» no es un PDF ni una foto.", nombre))
        if tipo == "pdf" and len(paginas(contenido, mime)) > MAX_PAGINAS_IA:
            raise UserError(_("«%(n)s» tiene más de %(m)s páginas: ¿es una factura?", n=nombre, m=MAX_PAGINAS_IA))
        partes = [{"inline_data": {"mime_type": mime, "data": base64.b64encode(contenido).decode()}},
                  {"text": leer.INSTRUCCIONES_IA}]
        consumo = ia.Consumo()
        try:
            respuesta = ia.pedir(
                lambda modelo: ia.llamar_gemini(partes, clave, modelo, esquema=leer.ESQUEMA_IA),
                modelos, consumo, time.sleep)
            datos = ia._texto_de(respuesta)
        except ia.ErrorIA as error:
            raise UserError(_("No se pudo leer «%(n)s» con la IA: %(e)s", n=nombre, e=error)) from error
        _logger.info("IA: factura %s leída (%s tokens, %s)", nombre, consumo.tokens, consumo.modelo)
        factura = leer.desde_ia(datos if isinstance(datos, dict) else {})
        factura.avisos.append(_("Leída con IA (%(m)s, %(t)s tokens): revisá cantidades y precios contra la foto.",
                                m=consumo.modelo, t=consumo.tokens))
        return factura

    # ------------------------------------------------------------ cargar
    def _comercio_cargar(self, factura, nombre):
        """Completa la factura con lo leído y arma «Leído de la factura» (lo de antes se reemplaza;
        las líneas ya cargadas en la factura se reutilizan, no se duplican)."""
        self.ensure_one()
        avisos = list(factura.avisos)
        cuit, avisos_cabecera = self._comercio_cabecera(factura)
        avisos += avisos_cabecera
        # Leer otra vez: las anotadas sin producto se vuelven a anotar (las que tienen producto se reusan),
        # el flete y las percepciones también
        self.invoice_line_ids.filtered(
            lambda ml: (ml.comercio_anotada and not ml.product_id) or ml.comercio_extra).unlink()
        self.comercio_factura_linea_ids.unlink()
        Linea = self.env["comercio.factura.linea"]
        lineas = Linea.create([{
            "move_id": self.id, "secuencia": i, "cantidad": li.cantidad or 0.0,
            "codigos": ", ".join(dict.fromkeys(li.codigos)), "descripcion": li.descripcion,
            "precio": li.precio or 0.0, "bonificacion": li.bonificacion or 0.0, "importe": li.importe or 0.0,
            "iva": li.iva or 0.0, "avisos": "\n".join(li.avisos) or False,
        } for i, li in enumerate(factura.lineas, start=1)])
        lineas._buscar_productos()
        lineas.filtered(lambda li: li.producto_id and li.estado != "parecido")._cargar_en_factura()
        lineas._anotar_sin_producto()
        cargadas = lineas.filtered(lambda li: li.estado == "cargada")
        avisos += self._comercio_guardar_cuit(cuit, factura, lineas)
        avisos += self._comercio_documento(factura)
        avisos += self._comercio_cargar_pie(factura)
        sin_facturar = self.invoice_line_ids.filtered(
            lambda ml: ml.purchase_line_id and ml not in lineas.move_line_id)
        if sin_facturar:
            avisos.append(_("De la orden de compra no vienen en la factura: %s (revisá la cantidad de esas líneas).",
                            ", ".join(sin_facturar.product_id.mapped("display_name"))))
        caros = lineas.filtered(lambda li: li.diferencia_lista and "vieja" in li.diferencia_lista)
        if caros:
            avisos.insert(0, _("%s artículos cobran más que la lista vigente del proveedor (columna «Diferencia con su "
                               "lista»): ¿lista vieja? El costo y el precio de venta siguen la lista: pedile la "
                               "nueva y subila.", len(caros)))
        con_diferencias = lineas.filtered("diferencia_orden")
        if con_diferencias:
            avisos.insert(0, _("%(n)s artículos con diferencias con la orden de compra %(o)s (en amarillo, columna "
                               "«Diferencia con la orden»): la factura manda; si es un error del proveedor, pedile "
                               "una nota de crédito.", n=len(con_diferencias),
                               o=", ".join(con_diferencias.move_line_id.purchase_line_id.order_id.mapped("name"))))
        resumen = [_("«%(n)s»: %(t)s artículos leídos%(ia)s y anotados en la factura; %(c)s con su producto y "
                     "%(f)s sin producto (no los tenemos: agregalos al catálogo desde «Leído de la factura»).",
                     n=nombre, t=len(lineas), c=len(cargadas), f=len(lineas) - len(cargadas),
                     ia=_(" con IA") if factura.leida_con_ia else "")]
        resumen.append(self._comercio_resumen_pie(factura.totales, sum(lineas.mapped("importe"))))
        resumen += avisos
        self.comercio_lectura = Markup("<ul>%s</ul>") % Markup("").join(
            Markup("<li>%s</li>") % texto for texto in resumen)
        self.message_post(body=Markup("<p>%s</p>%s") % (_("Factura leída por el comercio (sin la digitalización "
                                                          "de Odoo)."), self.comercio_lectura))

    def _comercio_cabecera(self, factura):
        """El proveedor por su CUIT, si la factura no lo tiene. Devuelve (CUIT leído, avisos)."""
        avisos = []
        self.comercio_proveedor_factura_id = False
        self.comercio_cuit_sin_proveedor = False
        nuestros = {leer.solo_digitos(c.vat) for c in self.env["res.company"].sudo().search([]) if c.vat}
        cuits = [c for c in factura.cuits if cuit_valido(c)]
        cuit = next((c for c in cuits if c not in nuestros), None)
        if factura.cuits and not cuits:
            avisos.append(_("El CUIT leído no es válido (¿un dígito mal leído?): no se usó."))
        socio = self.partner_id.commercial_partner_id
        if cuit and not socio:
            encontrados = self.env["res.partner"].search(
                [("vat", "in", [cuit, f"{cuit[:2]}-{cuit[2:10]}-{cuit[10]}"]), ("parent_id", "=", False)], limit=2)
            if len(encontrados) == 1:
                self.partner_id = encontrados
                socio = encontrados
            else:
                # No se adivina: la persona elige el proveedor (o lo crea) desde el cartel de arriba
                self.comercio_cuit_sin_proveedor = cuit
                avisos.append(_("Ningún proveedor tiene el CUIT %s: elegilo o crealo con «Elegir proveedor» (arriba) "
                                "y se buscan sus productos.", cuit))
        elif cuit and socio and leer.solo_digitos(socio.vat) != cuit:
            otro = self.env["res.partner"].search(
                [("vat", "in", [cuit, f"{cuit[:2]}-{cuit[2:10]}-{cuit[10]}"]), ("parent_id", "=", False),
                 ("id", "!=", socio.id)], limit=1)
            if otro:
                # Cartel arriba de la factura con el botón para cambiar de proveedor
                self.comercio_proveedor_factura_id = otro
                avisos.append(_("Ojo: el CUIT %(c)s de la factura es de %(o)s, no de %(p)s.",
                                c=cuit, o=otro.name, p=socio.name))
            elif socio.vat:
                avisos.append(_("Ojo: la factura es del CUIT %(c)s y el proveedor elegido tiene %(p)s.",
                                c=cuit, p=socio.vat))
        return cuit, avisos

    def action_comercio_elegir_proveedor(self):
        """Cartel «Ningún proveedor tiene el CUIT…»: elegir uno de la lista o crearlo con ese CUIT."""
        self.ensure_one()
        return {"type": "ir.actions.act_window", "res_model": "comercio.factura.elegir.proveedor",
                "view_mode": "form", "target": "new", "name": _("Proveedor de la factura"),
                "context": {"default_move_id": self.id}}

    def action_comercio_usar_proveedor_factura(self):
        """La factura se subió en el proveedor equivocado: pasa al del CUIT y se lee de nuevo."""
        self.ensure_one()
        correcto = self.comercio_proveedor_factura_id
        if not correcto:
            return True
        if self.state != "draft":
            raise UserError(_("La factura ya está confirmada."))
        if self.invoice_line_ids.filtered("purchase_line_id"):
            raise UserError(_(
                "Esta factura viene de una orden de compra de %(p)s. Si la factura es de %(c)s, borrá este "
                "borrador y subila desde la orden de compra de %(c)s (o como factura nueva).",
                p=self.partner_id.name, c=correcto.name))
        self.partner_id = correcto
        self.comercio_proveedor_factura_id = False
        return self.action_comercio_leer_factura()

    def _comercio_guardar_cuit(self, cuit, factura, lineas):
        """El CUIT leído va al proveedor si no tenía, solo si sus artículos son de ese proveedor (si
        la factura se subió en otro proveedor, no se le pone un CUIT ajeno)."""
        socio = self.partner_id.commercial_partner_id
        if not (cuit and socio and not socio.vat):
            return []
        suyos = lineas.filtered(lambda li: li.proveedor_info_id.partner_id == socio or li.lista_linea_id)
        if len(suyos) * 3 < len(lineas) and not self.env.context.get("comercio_proveedor_elegido"):
            return [_("Casi ningún artículo está en la lista de %(p)s: ¿la factura es de otro proveedor? (CUIT de "
                      "la factura: %(c)s). No se le guardó el CUIT.", p=socio.name, c=cuit)]
        vals = {"vat": cuit}
        if factura.letra in ("A", "M") and "l10n_ar_afip_responsibility_type_id" in socio._fields \
                and not socio.l10n_ar_afip_responsibility_type_id:
            # Solo un responsable inscripto emite facturas A o M
            inscripto = self.env.ref("l10n_ar.res_IVARI", raise_if_not_found=False)
            if inscripto:
                vals["l10n_ar_afip_responsibility_type_id"] = inscripto.id
        try:
            with self.env.cr.savepoint():
                socio.sudo().write(vals)
        except Exception as error:  # noqa: BLE001 - validación del CUIT o de la condición de IVA
            return [_("No se pudo guardar el CUIT en el proveedor: %s", error)]
        return [_("Se guardó el CUIT %s en el proveedor (estaba vacío).", cuit)]

    def _comercio_documento(self, factura):
        """Tipo y número de comprobante, fecha y vencimiento: solo lo que esté vacío (el tipo, si
        Odoo puso otro por defecto). Después del CUIT: los tipos posibles dependen de la condición
        de IVA del proveedor. Devuelve avisos."""
        avisos = []
        if "l10n_latam_available_document_type_ids" in self._fields:
            # Si recién se le guardó el CUIT y la condición de IVA al proveedor, los tipos posibles
            # quedaron calculados sin ella (p. ej. solo «Despacho de importación»)
            self.invalidate_recordset(["l10n_latam_available_document_type_ids"])
        if factura.codigo_tipo and "l10n_latam_document_type_id" in self._fields and self.l10n_latam_use_documents:
            tipo = self.l10n_latam_available_document_type_ids.filtered(
                lambda t: t.code == factura.codigo_tipo)[:1]
            if tipo and self.l10n_latam_document_type_id != tipo:
                self.l10n_latam_document_type_id = tipo
            elif not tipo:
                avisos.append(_("El comprobante es código %s y no está entre los tipos posibles para este "
                                "proveedor (revisá su condición de IVA).", factura.codigo_tipo))
        if factura.numero and "l10n_latam_document_number" in self._fields and self.l10n_latam_use_documents:
            if not self.l10n_latam_document_number:
                try:
                    with self.env.cr.savepoint():
                        self.l10n_latam_document_number = factura.numero
                except Exception as error:  # noqa: BLE001 - formato que no acepta el tipo elegido
                    avisos.append(_("No se pudo poner el número %(n)s: %(e)s", n=factura.numero, e=error))
        elif factura.numero and not self.ref:
            self.ref = f"{factura.letra or ''} {factura.numero}".strip()
        if factura.fecha and not self.invoice_date:
            self.invoice_date = factura.fecha
        if factura.vencimiento and not self.invoice_payment_term_id and factura.vencimiento >= (factura.fecha or ""):
            self.invoice_date_due = factura.vencimiento
        return avisos


    # ------------------------------------------------------------ el pie: flete, percepciones, total
    def _comercio_cargar_pie(self, factura):
        """Lo que la factura cobra además de los artículos (no pasa a la orden de compra, pero se
        paga): el flete como una línea con su IVA y cada percepción con su impuesto de l10n_ar.
        Guarda el TOTAL del proveedor para comparar. Devuelve avisos."""
        totales, avisos = factura.totales, []
        self.comercio_total_factura = totales.total or 0.0
        if self.comercio_provisoria:
            return self._comercio_cargar_pie_sin_factura(totales)
        vals_list = []
        if totales.flete:
            alicuota = totales.iva_del_flete(factura.lineas, factura.letra)
            impuesto = self._comercio_iva_de_compra(alicuota) if alicuota else self._comercio_iva_no_gravado()
            vals_list.append({"name": totales.flete_texto or _("Flete"), "quantity": 1, "price_unit": totales.flete,
                              "tax_ids": [Command.set(impuesto.ids)], "comercio_extra": "flete"})
        detalle = totales.detalle_percepciones
        if totales.percepciones and not detalle:
            avisos.append(_("La factura tiene percepciones por %s y no dice de qué son (IIBB de qué provincia, IVA o "
                            "Ganancias): cargalas a mano.", _pesos(totales.percepciones)))
        elif totales.percepciones and abs(sum(p.importe for p in detalle) - totales.percepciones) >= TOLERANCIA_TOTAL:
            avisos.append(_("El detalle de las percepciones suma %(d)s y el pie dice %(p)s: revisalas.",
                            d=_pesos(sum(p.importe for p in detalle)), p=_pesos(totales.percepciones)))
        no_gravado = self._comercio_iva_no_gravado()
        for percepcion in detalle:
            impuesto = self._comercio_impuesto_percepcion(percepcion)
            if not impuesto:
                avisos.append(_("No hay un impuesto para la percepción «%(t)s» (%(i)s): cargala a mano.",
                                t=percepcion.texto, i=_pesos(percepcion.importe)))
                continue
            # Una línea sin importe que lleva la percepción (en l10n_ar es un impuesto, no un gasto). La
            # validación argentina exige un IVA por línea: «No gravado»
            vals_list.append({"name": impuesto.tax_group_id.name or impuesto.name, "quantity": 1, "price_unit": 0.0,
                              "tax_ids": [Command.set((no_gravado | impuesto).ids)], "comercio_extra": "percepcion",
                              "comercio_percepcion": percepcion.importe})
        if vals_list:
            self._comercio_crear_lineas(vals_list)
            self._comercio_ajustar_percepciones()
        return avisos

    def _comercio_cargar_pie_sin_factura(self, totales):
        """Compra sin factura: todo va sin impuestos (no hay crédito fiscal). El flete, y el IVA y las
        percepciones que cobró el proveedor, son líneas comunes: costo de la compra."""
        conceptos = [
            (totales.flete, totales.flete_texto or _("Flete")),
            (totales.iva, _("IVA cobrado por el proveedor (sin crédito fiscal)")),
            (totales.percepciones, _("Percepciones cobradas por el proveedor (sin crédito fiscal)")),
            (totales.otros, _("Otros tributos cobrados por el proveedor")),
        ]
        vals_list = [{"name": nombre, "quantity": 1, "price_unit": importe, "tax_ids": [Command.clear()],
                      "comercio_extra": "sin_credito"} for importe, nombre in conceptos if importe]
        if vals_list:
            self._comercio_crear_lineas(vals_list)
        return [_("Compra sin factura: sin IVA ni percepciones, no va al libro IVA. Cuando llegue la factura "
                  "real, la carga la administración.")]

    def _comercio_ajustar_percepciones(self):
        """Los impuestos de percepción de l10n_ar son fijos de 1 por unidad: el importe se pone a mano en
        el resumen de impuestos de la factura (`tax_totals`, como en la pantalla). Odoo lo vuelve a 1 si
        cambian las líneas: por eso se pone de nuevo después de cada cambio que hacemos nosotros."""
        for move in self.filtered(lambda m: m.state == "draft"):
            por_grupo = {}
            for ml in move.invoice_line_ids.filtered(lambda ml: ml.comercio_extra == "percepcion"):
                for impuesto in ml.tax_ids.filtered(lambda t: t.amount_type == "fixed"):
                    por_grupo[impuesto.tax_group_id.id] = por_grupo.get(impuesto.tax_group_id.id, 0.0) \
                        + ml.comercio_percepcion
            if not por_grupo:
                continue
            totales = copy.deepcopy(move.tax_totals)
            cambio = False
            for subtotal in totales.get("subtotals", []):
                for grupo in subtotal.get("tax_groups", []):
                    importe = por_grupo.get(grupo["id"])
                    if importe is not None and move.currency_id.compare_amounts(grupo["tax_amount_currency"], importe):
                        grupo["tax_amount_currency"] = importe
                        cambio = True
            if cambio:
                move.tax_totals = totales
                # «Cantidad por pagar» del borrador sale del resumen de impuestos: recalcularlo con la
                # percepción ya puesta (si no, queda el de antes, con la percepción en $ 1)
                move.invalidate_recordset(["tax_totals"])
                move._compute_amount()

    def _comercio_impuesto_percepcion(self, percepcion):
        """El impuesto de compra de l10n_ar para esa percepción (IIBB por provincia, IVA, Ganancias)."""
        Grupo = self.env["account.tax.group"]
        if "l10n_ar_tribute_afip_code" not in Grupo._fields:
            return self.env["account.tax"]
        impuestos = self.env["account.tax"].search([
            *self.env["account.tax"]._check_company_domain(self.company_id), ("type_tax_use", "=", "purchase"),
            ("tax_group_id.l10n_ar_tribute_afip_code", "=", TRIBUTO_PERCEPCION[percepcion.tipo])])
        if percepcion.tipo != "iibb":
            return impuestos[:1]
        jurisdiccion = percepcion.jurisdiccion or ""
        if any(a in jurisdiccion for a in ("caba", "agip", "capital", "ciudad", "autonoma")):
            buscar = "caba"
        elif any(a in jurisdiccion for a in ("arba", "buenos aires", "bs as", "bs. as", "pba")):
            buscar = "buenos aires"
        else:
            buscar = jurisdiccion
        return impuestos.filtered(
            lambda t: buscar and buscar in leer.sin_acentos(t.tax_group_id.name or "").casefold())[:1]

    def _comercio_iva_no_gravado(self):
        if "l10n_ar_vat_afip_code" not in self.env["account.tax.group"]._fields:
            return self.env["account.tax"]
        return self.env["account.tax"].search([
            *self.env["account.tax"]._check_company_domain(self.company_id), ("type_tax_use", "=", "purchase"),
            ("tax_group_id.l10n_ar_vat_afip_code", "=", "1")], limit=1)

    def _comercio_resumen_pie(self, totales, suma_articulos):
        """Una línea para «Leído de la factura»: el pie del proveedor y si la factura de Odoo da lo mismo."""
        partes = [_("artículos %s", _pesos(totales.subtotal if totales.subtotal is not None else suma_articulos))]
        if totales.flete:
            partes.append(_("%(n)s %(i)s", n=(totales.flete_texto or _("flete")).lower(), i=_pesos(totales.flete)))
        if totales.iva:
            partes.append(_("IVA %s", _pesos(totales.iva)))
        if totales.percepciones:
            partes.append(_("percepciones %s", _pesos(totales.percepciones)))
        if totales.otros:
            partes.append(_("otros tributos %s", _pesos(totales.otros)))
        if not totales.total:
            return _("Pie de la factura: %s. No se leyó el TOTAL: controlalo a mano contra el papel.", ", ".join(partes))
        if self._comercio_total_distinto():
            return _("Pie de la factura: %(p)s; TOTAL %(t)s. La factura de Odoo da %(o)s (diferencia %(d)s): "
                     "revisá qué falta antes de confirmar y de pagar.", p=", ".join(partes), t=_pesos(totales.total),
                     o=_pesos(self._comercio_total_odoo()), d=_pesos(self._comercio_total_odoo() - totales.total))
        return _("Pie de la factura: %(p)s; TOTAL %(t)s, igual que la factura de Odoo (flete y percepciones "
                 "cargados; no pasan a la orden de compra).", p=", ".join(partes), t=_pesos(totales.total))

    def _comercio_crear_lineas(self, vals_list):
        """Crea líneas de factura y las devuelve en el mismo orden."""
        antes = self.invoice_line_ids
        self.write({"invoice_line_ids": [Command.create(v) for v in vals_list]})
        return (self.invoice_line_ids - antes).sorted("id")

    def _comercio_iva_de_compra(self, alicuota):
        """El IVA de compra de esa alícuota (el de la empresa si coincide). Ninguno en una compra sin factura."""
        if not alicuota or self.journal_id.comercio_sin_factura:
            return self.env["account.tax"]
        por_defecto = self.company_id.account_purchase_tax_id
        if por_defecto and por_defecto.amount_type == "percent" and not float_compare(por_defecto.amount, alicuota, 2):
            return por_defecto
        return self.env["account.tax"].search([
            ("type_tax_use", "=", "purchase"), ("amount_type", "=", "percent"), ("amount", "=", alicuota),
            ("price_include", "=", False), ("company_id", "=", self.company_id.id)], limit=1)


class AccountMoveLine(models.Model):
    _inherit = "account.move.line"

    comercio_factura_linea_ids = fields.One2many("comercio.factura.linea", "move_line_id")
    comercio_anotada = fields.Boolean(
        "Anotada sin producto", copy=False,
        help="Artículo de la factura que no tenemos en el catálogo: se cargó con la descripción y el precio "
             "de la factura. Al agregarlo al catálogo desde «Leído de la factura», toma el producto.")
    comercio_extra = fields.Selection(
        [("flete", "Flete"), ("percepcion", "Percepción"), ("sin_credito", "Impuesto sin crédito fiscal")],
        "Del pie de la factura", copy=False,
        help="Cargado del pie de la factura del proveedor: no es un artículo ni está en la orden de compra.")
    comercio_percepcion = fields.Monetary(
        "Percepción según la factura", copy=False, currency_field="currency_id")


class ComercioFacturaLinea(models.Model):
    """Un artículo leído de la factura del proveedor y qué se hizo con él."""

    _name = "comercio.factura.linea"
    _description = "Artículo leído de la factura de un proveedor"
    _order = "move_id, secuencia"

    move_id = fields.Many2one("account.move", required=True, ondelete="cascade", index=True)
    partner_id = fields.Many2one(related="move_id.partner_id")
    secuencia = fields.Integer("N.º")
    cantidad = fields.Float("Cantidad", digits="Product Unit")
    codigos = fields.Char("Código", help="Códigos que trae la factura para este artículo (del proveedor o de barras).")
    descripcion = fields.Char("Descripción en la factura")
    precio = fields.Float("Precio", digits="Product Price", help="Unitario, antes de la bonificación.")
    bonificacion = fields.Float("Bonif. %", digits="Discount")
    importe = fields.Float("Importe")
    iva = fields.Float("IVA %")
    avisos = fields.Text("Avisos")
    estado = fields.Selection([
        ("cargada", "Con producto"),
        ("en_lista", "En su lista"),
        ("parecido", "¿Es este?"),
        ("nuevo", "No está"),
    ], "Estado", default="nuevo", required=True,
        help="Todos quedan anotados en la factura. Con producto: es uno nuestro. En su lista: lo vende este "
             "proveedor y no lo tenemos (Agregar). "
             "¿Es este?: se parece a uno; confirmarlo o elegir otro. No está: ni nuestro ni de su lista "
             "(Crear producto, o elegir el nuestro y Es este).")
    producto_id = fields.Many2one(
        "product.product", "Producto",
        help="Nuestro producto. Si no se encontró solo, se puede elegir acá y tocar «Es este».")
    lista_linea_id = fields.Many2one(
        "comercio.lista.importacion.linea", "En la lista del proveedor",
        help="La fila de la lista vigente del proveedor con este código o esta descripción.")
    categoria_id = fields.Many2one(
        "product.category", "Categoría",
        help="Dónde queda el producto al agregarlo a nuestro catálogo: de ella sale el precio de venta.")
    move_line_id = fields.Many2one("account.move.line", "Línea de la factura", ondelete="set null")
    proveedor_info_id = fields.Many2one("product.supplierinfo", "Precio del proveedor", readonly=True)
    parecido = fields.Float("Parecido", readonly=True, help="Cuánto se parece al producto sugerido (motor de las listas).")
    diferencia_lista = fields.Char(
        "Diferencia con su lista", readonly=True,
        help="El precio de la factura no coincide con el precio vigente de este proveedor (ni antes ni después "
             "de la bonificación). Más caro: ¿lista vieja? Pedile la nueva y subila (el costo y el precio de "
             "venta salen de las listas). Más barato: ¿un descuento?")
    diferencia_orden = fields.Char(
        "Diferencia con la orden", readonly=True,
        help="La factura dice otro precio, otra bonificación o más cantidad que la orden de compra o lo "
             "recibido. La factura manda (es lo que cobra el proveedor); si es un error, se le pide una nota "
             "de crédito.")
    ia_motivo = fields.Char("IA", readonly=True, help="Opinión de la IA («Verificar con IA»): solo sugiere.")

    # ------------------------------------------------------------ buscar
    def _lista_codigos(self):
        return [c.strip() for c in (self.codigos or "").split(",") if c.strip()]

    def _buscar_productos(self):
        """Por código del proveedor, código de barras o descripción exacta; en nuestros productos
        (precios del proveedor) y en su lista vigente. Lo parecido se sugiere, no se carga."""
        hoy = fields.Date.context_today(self)
        for move, lineas in self.grouped("move_id").items():
            socio = move.partner_id.commercial_partner_id
            precios = self.env["product.supplierinfo"].search(
                [("partner_id", "=", socio.id)], order="date_end desc, id desc") if socio else []
            por_codigo, por_nombre = {}, {}
            for info in precios:  # un precio vigente gana sobre uno cerrado con el mismo código
                vigente = not info.date_end or info.date_end >= hoy
                producto = info.product_id or info.product_tmpl_id.product_variant_id
                claves = ((por_codigo, info.product_code), (por_nombre, leer.clave(info.product_name)))
                for diccionario, clave in claves:
                    if clave and (vigente or clave not in diccionario):
                        diccionario[clave] = (producto, info)
            filas = self.env["comercio.lista.importacion.linea"].sudo().search(
                [("partner_id", "=", socio.id), ("de_lista_vigente", "=", True), ("accion", "!=", "baja")]
            ) if socio else self.env["comercio.lista.importacion.linea"]
            fila_por_codigo = {f.codigo_proveedor: f for f in filas if f.codigo_proveedor}
            fila_por_nombre = {leer.clave(f.descripcion): f for f in filas if f.descripcion}
            buscador = None
            for linea in lineas:
                codigos = linea._lista_codigos()
                nombre = leer.clave(linea.descripcion)
                encontrado = next((por_codigo[c] for c in codigos if c in por_codigo), None) or por_nombre.get(nombre)
                if not encontrado:
                    barras = [c for c in codigos if es_gtin_valido(c)]
                    producto = self.env["product.product"].search([("barcode", "in", barras)], limit=1) if barras \
                        else self.env["product.product"]
                    if producto:
                        encontrado = (producto, None)
                if encontrado:
                    producto, info = encontrado
                    linea.write({"producto_id": producto.id, "proveedor_info_id": info.id if info else False})
                    continue
                fila = next((fila_por_codigo[c] for c in codigos if c in fila_por_codigo), None) \
                    or fila_por_nombre.get(nombre)
                if fila and fila.producto_id:
                    linea.write({"producto_id": fila.producto_id.product_variant_id.id})
                    continue
                if fila:
                    vals = {"estado": "en_lista", "lista_linea_id": fila.id,
                            "categoria_id": (fila.categoria_id or fila.importacion_id.lista_id.categoria_id).id}
                    if fila.accion == "posible duplicado" and fila.candidato_ids:
                        # En su lista se parece a algo nuestro: se sugiere, la persona decide
                        candidato = fila.candidato_ids[:1]
                        vals.update({"estado": "parecido", "producto_id": candidato.product_variant_id.id,
                                     "parecido": similitud(linea.descripcion or "", candidato.name or "")})
                    linea.write(vals)
                    continue
                # Sin código ni descripción iguales: lo más parecido de su lista, para confirmar
                if buscador is None:
                    buscador = Buscador()
                    for f in filas:
                        buscador.agregar(f.id, f.descripcion or "")
                candidatos = [c for c in buscador.candidatos(linea.descripcion or "") if c.puntaje >= PARECIDO_MINIMO]
                if candidatos:
                    fila = filas.browse(candidatos[0].id)
                    linea.write({"estado": "parecido", "lista_linea_id": fila.id,
                                 "producto_id": fila.producto_id.product_variant_id.id or False,
                                 "categoria_id": (fila.categoria_id or fila.importacion_id.lista_id.categoria_id).id})
                elif not linea.categoria_id:
                    lista = self.env["comercio.lista.proveedor"].search([("partner_id", "=", socio.id)], limit=1) \
                        if socio else None
                    linea.categoria_id = lista.categoria_id if lista else False
            # ¿Ya lo tenemos con otro nombre? Lo que no se encontró por código se compara con nuestros
            # productos (el mismo motor de las listas). Solo se sugiere: la persona confirma «Es este»
            sueltas = lineas.filtered(lambda li: not li.producto_id and li.estado in ("en_lista", "nuevo"))
            if sueltas:
                nuestro = sueltas._buscador_nuestro()
                for linea in sueltas:
                    candidato = next(iter(nuestro.candidatos(linea.descripcion or "")), None)
                    if candidato and candidato.puntaje >= PARECIDO_NUESTRO:
                        plantilla = self.env["product.template"].browse(candidato.id)
                        linea.write({"estado": "parecido", "producto_id": plantilla.product_variant_id.id,
                                     "parecido": candidato.puntaje})

    def _buscador_nuestro(self, umbral=None):
        """Nuestros productos: su nombre y cómo los describe cada proveedor."""
        buscador = Buscador(Configuracion(umbral_candidato=umbral) if umbral else None)
        for producto in self.env["product.template"].search_read([("purchase_ok", "=", True)], ["name"]):
            buscador.agregar(producto["id"], producto["name"])
        for precio in self.env["product.supplierinfo"].search_read(
                [("product_name", "!=", False), ("product_tmpl_id.active", "=", True)],
                ["product_tmpl_id", "product_name"]):
            buscador.agregar(precio["product_tmpl_id"][0], precio["product_name"])
        return buscador

    # ------------------------------------------------------------ cargar en la factura
    def _valores_de_linea(self):
        self.ensure_one()
        vals = {"quantity": self.cantidad}
        if self.precio > 0:  # un remito no trae precios: queda el de la orden o el de Odoo
            vals.update({"price_unit": self.precio, "discount": self.bonificacion})
        return vals

    def _cargar_en_factura(self):
        """Una línea de la factura por artículo con producto. Si la factura viene de una orden de
        compra y ya tiene ese producto, se completa esa línea (cantidad y precio facturados). Si el
        artículo ya estaba anotado sin producto, esa misma línea pasa a tener el producto."""
        for move, lineas in self.grouped("move_id").items():
            if move.state != "draft":
                raise UserError(_("La factura ya está confirmada: no se le agregan líneas."))
            usadas = move.comercio_factura_linea_ids.move_line_id
            nuevas = []
            for linea in lineas.filtered("producto_id"):
                vals = linea._valores_de_linea()
                info = linea.proveedor_info_id
                if info and info.uom_id and info.uom_id != linea.producto_id.uom_id:
                    vals["product_uom_id"] = info.uom_id.id  # factura en la unidad del proveedor (caja)
                propia = linea.move_line_id.exists()
                de_la_orden = move.invoice_line_ids.filtered(
                    lambda ml, p=linea.producto_id, u=usadas: ml.purchase_line_id and ml.product_id == p
                    and ml not in u)[:1]
                if de_la_orden and propia != de_la_orden:
                    if propia and propia.comercio_anotada:
                        propia.unlink()  # estaba anotado sin producto: queda la línea de la orden
                    existente = de_la_orden
                elif propia:
                    existente = propia
                else:
                    existente = move.invoice_line_ids.filtered(
                        lambda ml, p=linea.producto_id, u=usadas: ml.product_id == p and ml not in u)[:1]
                if existente:
                    if existente.product_id != linea.producto_id:
                        vals["product_id"] = linea.producto_id.id
                    orden = existente.purchase_line_id
                    linea.diferencia_orden = linea._diferencias_con(orden) if orden else False
                    existente.write({**vals, "comercio_anotada": False})
                    usadas |= existente
                    linea.write({"move_line_id": existente.id, "estado": "cargada"})
                else:
                    nuevas.append((linea, {"product_id": linea.producto_id.id, **vals}))
            if nuevas:
                for linea, ml in zip([li for li, _v in nuevas], move._comercio_crear_lineas([v for _l, v in nuevas]),
                                     strict=True):
                    linea.write({"move_line_id": ml.id, "estado": "cargada"})
            lineas.filtered("producto_id")._comparar_con_lista()
            if move.invoice_line_ids.filtered("purchase_line_id"):
                # La factura es de una orden de compra: lo que cobra y no se pidió también es una diferencia
                for linea in lineas.filtered(lambda li: li.estado == "cargada" and li.move_line_id
                                             and not li.move_line_id.purchase_line_id):
                    linea.diferencia_orden = _("No está en la orden de compra: se cobra algo que no se pidió.")
            move._comercio_ajustar_percepciones()
            for linea in lineas.filtered(lambda li: li.estado == "cargada" and li.iva and li.move_line_id):
                tasas = linea.move_line_id.tax_ids.filtered(lambda t: t.amount_type == "percent").mapped("amount")
                if tasas and all(float_compare(t, linea.iva, 2) for t in tasas):
                    linea.avisos = "\n".join(filter(None, [linea.avisos, _(
                        "La factura dice IVA %(f)s %% y el producto tiene %(p)s %%: revisá el impuesto de la línea.",
                        f=f"{linea.iva:g}", p=", ".join(f"{t:g}" for t in tasas))]))

    def _comparar_con_lista(self):
        """Contra el precio vigente de este proveedor (el de su lista, que mueve el costo): avisa si la
        factura cobra otra cosa, antes y después de la bonificación (FC factura el precio de lista y
        bonifica aparte: eso no es una diferencia). Tiene que coincidir la unidad (no una caja)."""
        hoy = fields.Date.context_today(self)
        for linea in self:
            linea.diferencia_lista = False
            socio = linea.move_id.partner_id.commercial_partner_id
            if not socio or linea.precio <= 0:
                continue
            precios = linea.producto_id.product_tmpl_id.seller_ids.filtered(
                lambda s, socio=socio: s.partner_id == socio and not s.comercio_escala_de_id
                and (not s.date_start or s.date_start <= hoy) and (not s.date_end or s.date_end >= hoy)
                and (not s.uom_id or s.uom_id == linea.producto_id.uom_id))
            info = precios.sorted("min_qty")[:1]
            if not info or info.price <= 0:
                continue
            lista = info.price * (1 - (info.discount or 0) / 100)
            bruto, neto = linea.precio, linea.precio * (1 - (linea.bonificacion or 0) / 100)
            if any(abs(p / lista - 1) <= TOLERANCIA_LISTA for p in (bruto, neto)):
                continue
            variacion = neto / lista - 1
            texto = _("Lista %(l)s, factura %(f)s (%(v)s)", l=_pesos(lista), f=_pesos(neto),
                      v=f"{variacion:+.1%}".replace(".", ","))
            linea.diferencia_lista = texto + (_(": ¿lista vieja? Pedile la nueva") if variacion > 0
                                              else _(": ¿un descuento?"))

    def _diferencias_con(self, orden):
        """Qué dice distinto la factura que la línea de la orden de compra (y lo recibido)."""
        self.ensure_one()
        textos = []
        if self.precio > 0 and orden.currency_id.compare_amounts(orden.price_unit, self.precio):
            variacion = self.precio / orden.price_unit - 1 if orden.price_unit else 0
            textos.append(_("precio: orden %(o)s, factura %(f)s (%(v)s)", o=_pesos(orden.price_unit),
                            f=_pesos(self.precio), v=f"{variacion:+.1%}".replace(".", ",")))
        if self.precio > 0 and float_compare(orden.discount or 0, self.bonificacion or 0, 2):
            textos.append(_("bonificación: orden %(o)s %%, factura %(f)s %%", o=f"{orden.discount:g}",
                            f=f"{self.bonificacion:g}"))
        recibido = orden.qty_received
        if float_compare(self.cantidad, recibido, 3) > 0:
            textos.append(_("facturan %(f)s y se recibió %(r)s", f=f"{self.cantidad:g}", r=f"{recibido:g}")
                          if recibido else _("facturan %s y todavía no se recibió nada", f"{self.cantidad:g}"))
        elif float_compare(self.cantidad, orden.product_qty, 3) < 0:
            textos.append(_("se pidió %(p)s y facturan %(f)s", p=f"{orden.product_qty:g}", f=f"{self.cantidad:g}"))
        texto = "; ".join(textos)
        return texto[:1].upper() + texto[1:] if texto else False

    def _anotar_sin_producto(self):
        """Lo que no tenemos (o no está confirmado) también va a la factura, sin producto: con la
        descripción, la cantidad, el precio y la bonificación de la factura y el IVA leído. Así la
        factura queda completa; al agregarlo al catálogo, esa línea toma el producto."""
        for move, lineas in self.grouped("move_id").items():
            pendientes = lineas.filtered(lambda li: li.estado != "cargada" and not li.move_line_id.exists())
            if not pendientes:
                continue
            vals_list = []
            for linea in pendientes:
                codigo = next(iter(linea._lista_codigos()), "")
                vals = {"name": f"[{codigo}] {linea.descripcion}" if codigo else linea.descripcion,
                        "comercio_anotada": True, **linea._valores_de_linea()}
                if linea.precio <= 0:
                    vals["price_unit"] = linea.importe / linea.cantidad if linea.cantidad and linea.importe else 0.0
                impuesto = move._comercio_iva_de_compra(linea.iva)
                if impuesto:
                    vals["tax_ids"] = [Command.set(impuesto.ids)]
                vals_list.append(vals)
            for linea, ml in zip(pendientes, move._comercio_crear_lineas(vals_list), strict=True):
                linea.move_line_id = ml
            move._comercio_ajustar_percepciones()

    def _exigir_borrador(self):
        if any(li.move_id.state != "draft" for li in self):
            raise UserError(_("La factura ya está confirmada."))

    def _exigir_costos_y_precios(self):
        if not self.env.user.has_group("comercio_catalogo.group_listas_proveedores"):
            raise UserError(_("Agregar productos a nuestro catálogo lo hace quien maneja «Costos y precios». "
                              "Pedíselo o elegí en «Producto» uno que ya tengamos y tocá «Es este»."))

    # ------------------------------------------------------------ botones
    def action_agregar_desde_lista(self):
        """Como «Agregar» en «Buscar producto»: se crea con la categoría elegida, este proveedor y su
        costo de lista; después se carga en la factura."""
        self._exigir_borrador()
        self._exigir_costos_y_precios()
        lineas = self.filtered(lambda li: li.estado in ("en_lista", "parecido") and li.lista_linea_id)
        # «Agregar» sobre un «¿Es este?»: no era ese, se agrega como nuevo
        lineas.filtered(lambda li: li.estado == "parecido").producto_id = False
        if not lineas:
            raise UserError(_("Elegí artículos que estén en la lista del proveedor."))
        sin_categoria = lineas.filtered(lambda li: not li.categoria_id)
        if sin_categoria:
            raise UserError(_("Elegí la categoría de %s: de ella sale el precio de venta.",
                              ", ".join(f"«{li.descripcion}»" for li in sin_categoria[:3])))
        # Todas juntas: aplicar una fila de la lista planifica la lista entera del proveedor (FC: ~10 000
        # filas); de a una, 22 artículos eran 22 planificaciones (minutos). Así es una por lista.
        a_agregar = lineas.filtered(lambda li: not li.lista_linea_id.producto_id)
        for linea in a_agregar:
            linea.lista_linea_id.categoria_mostrada_id = linea.categoria_id
        filas = a_agregar.lista_linea_id
        duplicadas = filas.filtered(lambda f: f.accion == "posible duplicado")
        # «Agregar» sobre un posible duplicado = es nuevo; todo en una sola aplicación por lista
        duplicadas.write({"decision": "es_nuevo"})
        (filas - duplicadas).write({"decision": "aplicar"})
        if filas:
            filas._aplicar_por_importacion()
        for linea in lineas:
            fila = linea.lista_linea_id
            if fila.en_cola or not fila.producto_id:
                raise UserError(_("No se pudo agregar «%(d)s» desde la lista del proveedor (%(e)s). Abrilo en "
                                  "«Buscar producto».", d=linea.descripcion, e=fila.detalle or fila.estado))
            linea.producto_id = fila.producto_id.product_variant_id
        lineas._buscar_info()
        lineas._cargar_en_factura()
        return True

    def action_crear_producto(self):
        """No está en ninguna lista: producto nuevo con el nombre de la factura, la categoría elegida
        y este proveedor con su código y su precio (el precio de venta sale del margen)."""
        self._exigir_borrador()
        self._exigir_costos_y_precios()
        lineas = self.filtered(lambda li: li.estado in ("nuevo", "parecido") and not li.lista_linea_id
                               and (li.estado == "parecido" or not li.producto_id))
        if not lineas:
            raise UserError(_("Elegí artículos que no tengamos."))
        lineas.filtered(lambda li: li.estado == "parecido").producto_id = False  # no era el sugerido
        for linea in lineas:
            socio = linea.move_id.partner_id.commercial_partner_id
            if not socio:
                raise UserError(_("Elegí primero el proveedor de la factura."))
            if not linea.categoria_id:
                raise UserError(_("Elegí la categoría de «%s»: de ella sale el precio de venta.", linea.descripcion))
            if not linea.categoria_id.comercio_margen_efectivo:
                raise UserError(_(
                    "La categoría «%s» no tiene margen: el producto quedaría a $1 en la caja. Cargale el margen "
                    "(Costos y precios → Márgenes por categoría) o elegí otra.", linea.categoria_id.complete_name))
            codigos = linea._lista_codigos()
            barras = next((c for c in codigos if es_gtin_valido(c) and not c.startswith("2")), False)
            codigo_proveedor = next((c for c in codigos if c != barras), False)
            plantilla = self.env["product.template"].sudo().create({
                "name": linea.descripcion, "categ_id": linea.categoria_id.id, "barcode": barras,
                "purchase_ok": True, "sale_ok": True,
                "seller_ids": [Command.create({
                    "partner_id": socio.id, "product_code": codigo_proveedor, "product_name": linea.descripcion,
                    "price": linea.precio, "min_qty": 0.0})],
            })
            plantilla._comercio_actualizar_costo()
            plantilla.message_post(body=_("Creado desde la factura %(f)s de %(p)s por %(u)s.",
                                          f=linea.move_id.display_name, p=socio.name, u=self.env.user.name))
            linea.write({"producto_id": plantilla.product_variant_id.id,
                         "proveedor_info_id": plantilla.seller_ids[:1].id})
            linea._sumar_a_la_lista(plantilla.seller_ids[:1])
        lineas._cargar_en_factura()
        return True

    def action_es_este(self):
        """El producto elegido a mano (o el sugerido) es el de la factura. Si este proveedor no lo
        tenía, se le agrega con el código y el precio de la factura: la próxima vez se reconoce solo."""
        self._exigir_borrador()
        lineas = self.filtered(lambda li: li.estado != "cargada" and li.producto_id)
        if not lineas:
            raise UserError(_("Elegí en «Producto» cuál de nuestros productos es."))
        for linea in lineas:
            socio = linea.move_id.partner_id.commercial_partner_id
            plantilla = linea.producto_id.product_tmpl_id
            codigo = next((c for c in linea._lista_codigos() if not es_gtin_valido(c)), False)
            if socio and not plantilla.seller_ids.filtered(lambda s, socio=socio: s.partner_id == socio):
                if not self.env.user.has_group("comercio_catalogo.group_listas_proveedores"):
                    # Un precio de proveedor nuevo cambia el costo: eso es de «Costos y precios».
                    # La factura se carga igual; el vínculo lo hace quien tiene ese permiso.
                    linea.avisos = "\n".join(filter(None, [linea.avisos, _(
                        "No se le agregó %s como proveedor (lo hace quien maneja «Costos y precios»): la "
                        "próxima factura no lo va a reconocer solo.", socio.name)]))
                    continue
                info = self.env["product.supplierinfo"].sudo().create({
                    "product_tmpl_id": plantilla.id, "partner_id": socio.id, "product_code": codigo,
                    "product_name": linea.descripcion, "price": linea.precio})
                plantilla._comercio_actualizar_costo()
                linea.proveedor_info_id = info
                linea._sumar_a_la_lista(info)
        lineas._cargar_en_factura()
        return True

    def _sumar_a_la_lista(self, info):
        """Lo que vino en la factura y no estaba en la lista del proveedor se suma a su lista vigente
        (fila «agregado desde la factura»): así aparece en «Buscar producto» y en «Lista del
        proveedor». Si la próxima lista del proveedor no lo trae, se da de baja como cualquier otro."""
        self.ensure_one()
        socio = self.move_id.partner_id.commercial_partner_id
        listas = self.env["comercio.lista.proveedor"].search([("partner_id", "=", socio.id)])
        lista = listas.filtered(lambda li: not li.parte)[:1] or listas[:1]
        vigente = self.env["comercio.lista.importacion"]._vigente_de(lista) if lista else False
        if not vigente or not info:
            return
        info.sudo().comercio_lista_id = lista
        self.env["comercio.lista.importacion.linea"].sudo().create({
            "importacion_id": vigente.id, "fila": 0, "accion": "vincular", "estado": "aplicada", "decision": "nada",
            "detalle": _("Agregado desde la factura %s", self.move_id.display_name),
            "codigo_proveedor": info.product_code or False, "descripcion": self.descripcion,
            "costo": self.precio, "producto_id": info.product_tmpl_id.id, "proveedor_info_id": info.id,
            "categoria_id": info.product_tmpl_id.categ_id.id, "aplicada_por": self.env.user.id,
        })

    def action_agregar_al_catalogo(self):
        """Uno o varios de una vez (pantalla «Artículos de la factura»): cada uno como corresponde. Los
        que están en la lista del proveedor se agregan desde ahí; los demás se crean con la
        descripción, el código y el precio de la factura. Un «¿Es este?» que se agrega es otro producto."""
        self._exigir_borrador()
        self._exigir_costos_y_precios()
        pendientes = self.filtered(lambda li: li.estado != "cargada")
        if not pendientes:
            raise UserError(_("Los artículos elegidos ya tienen su producto."))
        sin_categoria = pendientes.filtered(lambda li: not li.categoria_id)
        if sin_categoria:
            raise UserError(_(
                "Elegí la categoría de %(n)s artículos (p. ej. «%(d)s»): de ella sale el precio de venta. Para "
                "varios: marcalos y cambiá la categoría en uno.", n=len(sin_categoria), d=sin_categoria[0].descripcion))
        de_lista = pendientes.filtered("lista_linea_id")
        if de_lista:
            de_lista.action_agregar_desde_lista()
        if pendientes - de_lista:
            (pendientes - de_lista).action_crear_producto()
        return {"type": "ir.actions.client", "tag": "display_notification", "params": {
            "type": "success", "message": _("%s agregados al catálogo y cargados en la factura.", len(pendientes)),
            "next": {"type": "ir.actions.client", "tag": "soft_reload"}}}

    def action_crear_orden_igual(self):
        """Desde «Artículos de la factura»: la orden con lo que ya tiene producto (lo demás queda afuera)."""
        move = self.env["account.move"].browse(self.env.context.get("comercio_move_id")).exists() or self.move_id[:1]
        if not move:
            raise UserError(_("Abrí esta pantalla desde la factura."))
        return move.with_context(comercio_sin_faltantes=True).action_comercio_crear_orden()

    def action_verificar_ia(self):
        """¿Ya lo tenemos con otro nombre? La IA compara cada artículo con nuestros productos más
        parecidos (umbral amplio, como en las listas) y solo sugiere: queda «¿Es este?» para confirmar."""
        lineas = self.filtered(lambda li: li.estado != "cargada")[:MAXIMO_IA]
        if not lineas:
            raise UserError(_("Elegí artículos sin producto."))
        clave, modelos = _configuracion()
        if not clave:
            raise UserError(_("Falta la clave de la IA (GEMINI_API_KEY) en el servidor."))
        buscador = lineas._buscador_nuestro(UMBRAL_AMPLIO)
        Plantilla = self.env["product.template"]
        filas = []
        for linea in lineas:
            candidatos = Plantilla.browse([c.id for c in buscador.candidatos(linea.descripcion or "")][:3])
            if candidatos:
                filas.append({"fila": linea.id, "descripcion": linea.descripcion, "codigo": linea.codigos or "",
                              "candidatos": [{"id": p.id, "nombre": p.name,
                                              "otras_descripciones": p.seller_ids.mapped("product_name")}
                                             for p in candidatos]})
        sin_parecidos = lineas - lineas.browse([f["fila"] for f in filas])
        sin_parecidos.write({"ia_motivo": _("Nada parecido entre nuestros productos.")})
        resultados = []
        if filas:
            try:
                resultados, _consumo = ia.verificar(filas, clave, modelos)
            except ia.ErrorIA as error:
                raise UserError(_("No se pudo consultar a la IA: %s", error)) from error
        mismos = 0
        for r in resultados:
            linea = lineas.browse(r.fila)
            veredicto = {ia.MISMO: _("Es el mismo"), ia.DISTINTO: _("Es otro"), ia.DUDOSO: _("Dudoso")}
            vals = {"ia_motivo": f"{veredicto.get(r.veredicto, '')}: {r.motivo}"}
            if r.veredicto == ia.MISMO and r.candidato_id and r.confianza >= CONFIANZA_PARA_PRESELECCIONAR:
                variante = Plantilla.browse(r.candidato_id).product_variant_id
                vals.update({"estado": "parecido", "producto_id": variante.id, "parecido": r.confianza})
                mismos += 1
            elif (r.veredicto == ia.DISTINTO and r.confianza >= CONFIANZA_PARA_PRESELECCIONAR
                  and linea.estado == "parecido"):
                # La sugerencia del motor no era: vuelve a «en su lista» o «no está»
                vals.update({"estado": "en_lista" if linea.lista_linea_id else "nuevo", "producto_id": False,
                             "parecido": 0.0})
            linea.write(vals)
        return {"type": "ir.actions.client", "tag": "display_notification", "params": {
            "type": "info", "message": _("La IA cree que %(m)s de %(n)s ya los tenemos (quedan como «¿Es este?» para "
                                         "confirmar).", m=mismos, n=len(lineas)),
            "next": {"type": "ir.actions.client", "tag": "soft_reload"}}}

    def _buscar_info(self):
        for linea in self.filtered("producto_id"):
            socio = linea.move_id.partner_id.commercial_partner_id
            linea.proveedor_info_id = linea.producto_id.product_tmpl_id.seller_ids.filtered(
                lambda s, socio=socio: s.partner_id == socio)[:1]

    def action_abrir_buscar_producto(self):
        """Buscar el artículo en las listas de todos los proveedores (otro nombre, otra medida…)."""
        self.ensure_one()
        accion = self.env["ir.actions.act_window"]._for_xml_id("comercio_catalogo.action_buscar_producto")
        palabras = " ".join((self.descripcion or "").split()[:3])
        accion["context"] = {"search_default_buscar": palabras}
        accion["target"] = "current"
        return accion


class PurchaseOrder(models.Model):
    _inherit = "purchase.order"

    def create_document_from_attachment(self, attachment_ids):
        """«Subir» de Compras (pensado por Odoo para pedidos electrónicos en XML): si lo que se sube
        es la factura de un proveedor (PDF o foto con letra, código de comprobante o CAE), se crea la
        factura del proveedor, leída como en Facturas → Subir. Lo demás sigue como en Odoo."""
        adjuntos = self.env["ir.attachment"].browse(attachment_ids)
        Move = self.env["account.move"]
        leidas, otros = {}, self.env["ir.attachment"]
        for adjunto in adjuntos:
            factura = None
            if _tipo_de_archivo(adjunto.name, adjunto.mimetype):
                try:
                    factura = Move._comercio_leer(adjunto.raw, adjunto.name)
                except UserError as error:
                    _logger.info("«%s» no se leyó como factura: %s", adjunto.name, error)
            if factura and (factura.cae or factura.letra or factura.codigo_tipo):
                leidas[adjunto.id] = factura
            else:
                otros |= adjunto
        if not leidas:
            return super().create_document_from_attachment(attachment_ids)
        diario = self.env["account.journal"].search(
            [*self.env["account.journal"]._check_company_domain(self.env.company), ("type", "=", "purchase")], limit=1)
        if not diario:
            raise UserError(_("Falta el diario de compras para crear la factura del proveedor."))
        facturas = diario.with_context(default_move_type="in_invoice", comercio_facturas_leidas=leidas) \
            ._create_document_from_attachment(list(leidas))
        if otros:
            super().create_document_from_attachment(otros.ids)  # p. ej. un pedido en XML junto con la factura
        return facturas._get_records_action(name=_("Facturas de proveedor"))
