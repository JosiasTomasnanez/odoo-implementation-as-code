"""Cierre Z de una registradora cargado en Odoo (a mano o desde la foto con Gemini).

Al confirmarlo queda un comprobante «Tique» en el diario de esa registradora (controlador
fiscal externo: no va a ARCA), con una línea por alícuota y el IVA impreso en el Z, que entra
al Libro IVA Ventas con el rango de tiques del día; y un cobro por cada medio de pago, para
conciliar después el banco y las tarjetas (P-070).
"""

import base64
import copy
import logging
import time
from datetime import datetime, time as hora, timedelta

import pytz

from odoo import _, api, fields, models
from odoo.addons.comercio_catalogo_ia.ia import verificar as ia
from odoo.addons.comercio_catalogo_ia.models.importacion import _configuracion
from odoo.exceptions import UserError, ValidationError

from ..cierre import leer

_logger = logging.getLogger(__name__)

# Código de ARCA del grupo de IVA de cada alícuota (l10n_ar: account.tax.group.l10n_ar_vat_afip_code)
CODIGO_IVA = {"neto_21": "5", "neto_105": "4", "neto_27": "6", "exento": "2", "no_gravado": "1"}
NOMBRE_LINEA = {"neto_21": "Ventas al 21 %", "neto_105": "Ventas al 10,5 %", "neto_27": "Ventas al 27 %",
                "exento": "Ventas exentas", "no_gravado": "Ventas no gravadas"}
ZONA = "America/Argentina/Buenos_Aires"


def _pesos(valor):
    entero, decimales = f"{abs(valor or 0.0):,.2f}".split(".")
    return f"{'−' if (valor or 0) < 0 else ''}$ {entero.replace(',', '.')},{decimales}"


class ComercioCierreZ(models.Model):
    _name = "comercio.cierre.z"
    _description = "Cierre Z de una registradora"
    _inherit = ["mail.thread"]
    _order = "fecha desc, journal_id, numero desc"

    name = fields.Char("Cierre", compute="_compute_name", store=True)
    company_id = fields.Many2one("res.company", "Empresa", required=True, default=lambda s: s.env.company)
    currency_id = fields.Many2one(related="company_id.currency_id")
    journal_id = fields.Many2one(
        "account.journal", "Registradora", required=True, tracking=True,
        domain="[('type', '=', 'sale'), ('l10n_ar_afip_pos_system', '=', 'CF'), ('company_id', '=', company_id)]",
        default=lambda s: s.env["account.journal"].search(
            [("type", "=", "sale"), ("l10n_ar_afip_pos_system", "=", "CF"),
             ("company_id", "=", s.env.company.id)], limit=1),
        help="El diario de la registradora (controlador fiscal externo), con su punto de venta.")
    fecha = fields.Date("Fecha del Z", required=True, default=fields.Date.context_today, tracking=True)
    numero = fields.Integer("N.º de Z", tracking=True)
    tique_desde = fields.Integer("Primer tique", help="El primer tique del día que figura en el Z.")
    tique_hasta = fields.Integer("Último tique", help="El último tique del día que figura en el Z.")
    documento_tipo_id = fields.Many2one(
        "l10n_latam.document.type", "Tipo de comprobante",
        domain="[('code', 'in', ['81', '82', '83'])]",
        default=lambda s: s.env.ref("l10n_ar.dc_t", raise_if_not_found=False),
        help="Tique (83) para consumidor final; tique factura A o B si la registradora los emite.")

    neto_21 = fields.Monetary("Neto 21 %")
    iva_21 = fields.Monetary("IVA 21 %")
    neto_105 = fields.Monetary("Neto 10,5 %")
    iva_105 = fields.Monetary("IVA 10,5 %")
    neto_27 = fields.Monetary("Neto 27 %")
    iva_27 = fields.Monetary("IVA 27 %")
    exento = fields.Monetary("Exento")
    no_gravado = fields.Monetary("No gravado")
    total = fields.Monetary("TOTAL del Z", tracking=True, help="El TOTAL impreso en el Z.")
    suma = fields.Monetary("Suma de lo cargado", compute="_compute_suma")

    cobro_ids = fields.One2many("comercio.cierre.z.cobro", "cierre_id", "Cómo se cobró")
    cobrado = fields.Monetary("Suma de los cobros", compute="_compute_suma")

    foto = fields.Binary("Foto del Z", attachment=True)
    foto_nombre = fields.Char("Nombre de la foto")
    leido_con_ia = fields.Boolean("Leído con IA", readonly=True, copy=False)
    dudas_ia = fields.Text("Dudas de la IA", readonly=True, copy=False)

    state = fields.Selection([("borrador", "Borrador"), ("confirmado", "Confirmado")],
                             "Estado", default="borrador", required=True, tracking=True, copy=False)
    move_id = fields.Many2one("account.move", "Comprobante", readonly=True, copy=False)

    problemas = fields.Text("Para corregir", compute="_compute_controles")
    avisos = fields.Text("Para revisar", compute="_compute_controles")
    puestos_dia = fields.Monetary("Pedidos de los puestos ese día", compute="_compute_controles",
                                  help="Lo que imprimieron los puestos con «Cobrado en registradora» ese día "
                                  "(todas las registradoras juntas).")
    z_del_dia = fields.Monetary("Z de ese día (todas las registradoras)", compute="_compute_controles")

    @api.depends("journal_id", "numero", "fecha")
    def _compute_name(self):
        for z in self:
            partes = [_("Z %s", z.numero) if z.numero else _("Z")]
            if z.journal_id:
                partes.append(z.journal_id.name)
            if z.fecha:
                partes.append(z.fecha.strftime("%d/%m/%Y"))
            z.name = " — ".join(partes)

    @api.depends("neto_21", "iva_21", "neto_105", "iva_105", "neto_27", "iva_27", "exento", "no_gravado",
                 "cobro_ids.importe")
    def _compute_suma(self):
        for z in self:
            z.suma = leer.suma_comprobante(z._valores())
            z.cobrado = sum(z.cobro_ids.mapped("importe"))

    def _valores(self):
        self.ensure_one()
        v = {campo: self[campo] for campo in (
            "neto_21", "iva_21", "neto_105", "iva_105", "neto_27", "iva_27", "exento", "no_gravado")}
        v.update(numero_z=self.numero, fecha=self.fecha, tique_desde=self.tique_desde,
                 tique_hasta=self.tique_hasta, total=self.total if self.total or self.suma else None)
        return v

    # ------------------------------------------------------------ controles
    @api.depends("journal_id", "numero", "fecha", "tique_desde", "tique_hasta", "total", "neto_21", "iva_21",
                 "neto_105", "iva_105", "neto_27", "iva_27", "exento", "no_gravado", "cobro_ids.importe", "state")
    def _compute_controles(self):
        for z in self:
            problemas = leer.errores(z._valores(), z.cobro_ids.mapped("importe"))
            if z.numero and z.journal_id and z._otros_del_mismo_numero():
                problemas.append(_("El Z %(n)s de %(r)s ya está cargado.", n=z.numero, r=z.journal_id.name))
            z.problemas = "\n".join(problemas) or False
            avisos = []
            if not z.cobro_ids and z.total:
                avisos.append(_("No se cargó cómo se cobró: el comprobante queda sin cobrar (se puede cargar después "
                                "con «Registrar pago»)."))
            anterior = z._z_anterior_faltante()
            if anterior:
                avisos.append(anterior)
            z.puestos_dia, z.z_del_dia = z._puestos_y_z_del_dia()
            if z.fecha and z.puestos_dia:
                diferencia = z.z_del_dia - z.puestos_dia
                avisos.append(_(
                    "Ese día los puestos imprimieron %(p)s y los Z cargados de ese día suman %(z)s (diferencia "
                    "%(d)s). Si falta el Z de la otra registradora, la diferencia es normal.",
                    p=_pesos(z.puestos_dia), z=_pesos(z.z_del_dia), d=_pesos(diferencia)))
            caja = z._caja_sin_factura_del_dia()
            if caja:
                avisos.append(_(
                    "Ese día la caja de Odoo cobró %s en ventas sin factura de Odoo: si las facturó esta registradora, "
                    "con el Z quedarían dos veces en la contabilidad (P-070, todavía sin resolver).", _pesos(caja)))
            if z.dudas_ia and z.state == "borrador":
                avisos.append(_("La IA no está segura de: %s", z.dudas_ia))
            z.avisos = "\n".join(avisos) or False

    def _otros_del_mismo_numero(self):
        return self.search_count([("id", "!=", self.id or 0), ("journal_id", "=", self.journal_id.id),
                                  ("numero", "=", self.numero)])

    def _z_anterior_faltante(self):
        """Los Z de una registradora son correlativos: avisa si falta el anterior (y hay alguno antes)."""
        if not (self.numero and self.journal_id):
            return False
        anteriores = self.search([("journal_id", "=", self.journal_id.id), ("numero", "<", self.numero),
                                  ("id", "!=", self.id or 0)], order="numero desc", limit=1)
        if anteriores and anteriores.numero != self.numero - 1:
            faltan = self.numero - anteriores.numero - 1
            if faltan == 1:
                return _("Falta cargar el Z %(n)s de %(r)s.", n=self.numero - 1, r=self.journal_id.name)
            return _("Faltan cargar %(c)s Z de %(r)s (del %(d)s al %(h)s).", c=faltan, r=self.journal_id.name,
                     d=anteriores.numero + 1, h=self.numero - 1)
        return False

    def _rango_del_dia(self):
        zona = pytz.timezone(self.env.user.tz or ZONA)
        inicio = zona.localize(datetime.combine(self.fecha, hora.min)).astimezone(pytz.utc).replace(tzinfo=None)
        return inicio, inicio + timedelta(days=1)

    def _metodos_registradora(self):
        if "comercio_metodo_registradora_id" not in self.env["pos.config"]._fields:
            return self.env["pos.payment.method"]
        return self.env["pos.config"].sudo().with_context(active_test=False).search([]).mapped(
            "comercio_metodo_registradora_id")

    def _puestos_y_z_del_dia(self):
        if not self.fecha:
            return 0.0, 0.0
        inicio, fin = self._rango_del_dia()
        metodos = self._metodos_registradora()
        puestos = 0.0
        if metodos:
            pagos = self.env["pos.payment"].sudo().search([
                ("payment_method_id", "in", metodos.ids), ("pos_order_id.state", "in", ["paid", "done"]),
                ("pos_order_id.date_order", ">=", inicio), ("pos_order_id.date_order", "<", fin),
                ("company_id", "=", self.company_id.id)])
            puestos = sum(pagos.mapped("amount"))
        del_dia = self.search([("fecha", "=", self.fecha), ("company_id", "=", self.company_id.id)])
        return puestos, sum(del_dia.mapped("total"))

    def _caja_sin_factura_del_dia(self):
        """Ventas de la caja de Odoo (no de los puestos) cobradas sin factura de Odoo ese día (ADR 0024)."""
        Pedido = self.env["pos.order"].sudo()
        if not self.fecha or "comercio_factura_odoo" not in Pedido._fields:
            return 0.0
        inicio, fin = self._rango_del_dia()
        metodos = self._metodos_registradora()
        pedidos = Pedido.search([
            ("state", "in", ["paid", "done"]), ("comercio_factura_odoo", "=", False),
            ("date_order", ">=", inicio), ("date_order", "<", fin), ("company_id", "=", self.company_id.id)])
        pedidos = pedidos.filtered(lambda p: p.payment_ids and not all(
            pago.payment_method_id in metodos for pago in p.payment_ids))
        return sum(pedidos.mapped("amount_total"))

    @api.constrains("journal_id", "numero")
    def _check_numero_unico(self):
        for z in self:
            if z.numero and z._otros_del_mismo_numero():
                raise ValidationError(_("El Z %(n)s de %(r)s ya está cargado.", n=z.numero, r=z.journal_id.name))

    # ------------------------------------------------------------ foto
    def action_leer_foto(self):
        self.ensure_one()
        if self.state != "borrador":
            raise UserError(_("El Z ya está confirmado."))
        if not self.foto:
            raise UserError(_("Primero subí la foto del Z."))
        contenido = self._foto_bytes()
        mime = leer.tipo_de_imagen(contenido)
        if not mime:
            raise UserError(_("La foto tiene que ser JPG, PNG, WEBP, HEIC o PDF."))
        clave, modelos = _configuracion()
        if not clave:
            raise UserError(_("Para leer la foto hace falta la IA (GEMINI_API_KEY en el servidor), que no está "
                              "configurada. Cargá los números a mano."))
        partes = [{"inline_data": {"mime_type": mime, "data": base64.b64encode(contenido).decode()}},
                  {"text": leer.INSTRUCCIONES_IA}]
        consumo = ia.Consumo()
        try:
            respuesta = ia.pedir(
                lambda modelo: ia.llamar_gemini(partes, clave, modelo, esquema=leer.ESQUEMA_IA),
                modelos, consumo, time.sleep)
            datos = ia._texto_de(respuesta)
        except ia.ErrorIA as error:
            raise UserError(_("No se pudo leer la foto con la IA: %s", error)) from error
        _logger.info("IA: cierre Z %s leído (%s tokens, %s)", self.id, consumo.tokens, consumo.modelo)
        self._cargar_leido(leer.desde_ia(datos if isinstance(datos, dict) else {}))
        self.message_post(body=_("Foto leída con IA (%(m)s). Revisá cada número contra el Z antes de confirmar.",
                                 m=consumo.modelo))
        return True

    def _foto_bytes(self):
        """La foto como bytes (Odoo 20 devuelve un BinaryValue; antes, base64)."""
        valor = self.foto
        if hasattr(valor, "content"):
            return valor.content
        return base64.b64decode(valor) if valor else b""

    def _cargar_leido(self, leido):
        """Completa el formulario con lo leído (reemplaza lo que había) y los cobros por medio."""
        v = leido.valores
        valores = {"leido_con_ia": True, "dudas_ia": "\n".join(leido.dudas) or False}
        if v.get("numero_z"):
            valores["numero"] = v["numero_z"]
        if v.get("fecha"):
            valores["fecha"] = v["fecha"]
        for campo in ("tique_desde", "tique_hasta"):
            if v.get(campo):
                valores[campo] = v[campo]
        for campo in ("neto_21", "iva_21", "neto_105", "iva_105", "neto_27", "iva_27", "exento", "no_gravado",
                      "total"):
            valores[campo] = v.get(campo) or 0.0
        pv = v.get("punto_de_venta")
        if pv:
            diario = self.env["account.journal"].search([
                ("type", "=", "sale"), ("l10n_ar_afip_pos_system", "=", "CF"),
                ("l10n_ar_afip_pos_number", "=", pv), ("company_id", "=", self.company_id.id)], limit=1)
            if diario:
                valores["journal_id"] = diario.id
        if leido.medios:
            cobros = [(5, 0, 0)]
            for medio, monto in leido.medios:
                cobros.append((0, 0, {"medio": medio, "importe": monto}))
            valores["cobro_ids"] = cobros
        self.write(valores)

    # ------------------------------------------------------------ confirmar
    def action_confirmar(self):
        for z in self:
            if z.state != "borrador":
                continue
            z._compute_controles()
            if z.problemas:
                raise UserError(_("No se puede confirmar %(z)s:\n%(p)s", z=z.name, p=z.problemas))
            sin_diario = z.cobro_ids.filtered(lambda c: not c.journal_id)
            if sin_diario:
                raise UserError(_(
                    "Falta el diario de «%s»: elegilo en la línea o configuralo en Ajustes (parámetro "
                    "comercio_cierre_z.diario_<medio>).", ", ".join(sin_diario.mapped("medio"))))
            move = z._crear_comprobante()
            z._registrar_cobros(move)
            z.write({"state": "confirmado", "move_id": move.id})
            z.message_post(body=_("Confirmado: %s", move._get_html_link()))
        return True

    def _impuesto(self, codigo):
        impuesto = self.env["account.tax"].search([
            *self.env["account.tax"]._check_company_domain(self.company_id), ("type_tax_use", "=", "sale"),
            ("tax_group_id.l10n_ar_vat_afip_code", "=", codigo)], limit=1)
        if not impuesto:
            raise UserError(_("No se encontró el impuesto de venta de IVA con código de ARCA %s.", codigo))
        return impuesto

    def _crear_comprobante(self):
        self.ensure_one()
        diario = self.journal_id
        if not diario.l10n_ar_afip_pos_number:
            raise UserError(_("El diario %s no tiene punto de venta.", diario.name))
        cuenta = diario.default_account_id
        lineas = []
        for campo, codigo in CODIGO_IVA.items():
            neto = self[campo]
            if not neto:
                continue
            impuesto = self._impuesto(codigo)
            # Con «precios con IVA incluido» (la empresa vende así) el precio de la línea lleva el IVA:
            # neto × (1 + alícuota) da de vuelta el neto exacto; el IVA impreso se pone después.
            precio = neto
            if impuesto.price_include and impuesto.amount_type == "percent":
                precio = round(neto * (1 + impuesto.amount / 100.0), 2)
            lineas.append((0, 0, {
                "name": _("%(l)s — Z %(n)s", l=NOMBRE_LINEA[campo], n=self.numero),
                "quantity": 1, "price_unit": precio, "account_id": cuenta.id,
                "tax_ids": [(6, 0, impuesto.ids)],
            }))
        cliente = self.env.ref("l10n_ar.par_cfa")
        move = self.env["account.move"].create({
            "move_type": "out_invoice", "journal_id": diario.id, "partner_id": cliente.id,
            "invoice_date": self.fecha, "date": self.fecha, "company_id": self.company_id.id,
            "l10n_latam_document_type_id": self.documento_tipo_id.id,
            "l10n_latam_document_number": f"{diario.l10n_ar_afip_pos_number:05d}-{self.tique_desde:08d}",
            "comercio_tique_hasta": self.tique_hasta, "comercio_cierre_z_id": self.id,
            "ref": _("Cierre Z %s", self.numero), "invoice_line_ids": lineas,
        })
        self._ajustar_iva(move)
        if self.foto:
            self.env["ir.attachment"].create({
                "name": self.foto_nombre or f"cierre-z-{self.numero}.jpg", "raw": self._foto_bytes(),
                "res_model": "account.move", "res_id": move.id})
        move.action_post()
        return move

    def _ajustar_iva(self, move):
        """El IVA del comprobante es el impreso en el Z (la registradora redondea ticket por ticket):
        se pone en el resumen de impuestos (`tax_totals`, como a mano en la pantalla)."""
        impreso = {}
        for neto, iva, _alicuota in leer.ALICUOTAS:
            if self[neto]:
                grupo = self._impuesto(CODIGO_IVA[neto]).tax_group_id
                impreso[grupo.id] = self[iva]
        totales = copy.deepcopy(move.tax_totals)
        cambio = False
        for subtotal in totales.get("subtotals", []):
            for grupo in subtotal.get("tax_groups", []):
                importe = impreso.get(grupo["id"])
                if importe is not None and move.currency_id.compare_amounts(grupo["tax_amount_currency"], importe):
                    grupo["tax_amount_currency"] = importe
                    cambio = True
        if cambio:
            move.tax_totals = totales
            move.invalidate_recordset(["tax_totals"])
        netos = sum(self[campo] for campo in CODIGO_IVA)
        if move.currency_id.compare_amounts(move.amount_untaxed, netos) or \
                move.currency_id.compare_amounts(move.amount_total, self.suma):
            raise UserError(_(
                "El comprobante da neto %(n)s y total %(c)s, y el Z neto %(zn)s y total %(z)s: no se pudo cargar "
                "tal cual.", n=_pesos(move.amount_untaxed), c=_pesos(move.amount_total), zn=_pesos(netos),
                z=_pesos(self.suma)))

    def _registrar_cobros(self, move):
        for cobro in self.cobro_ids:
            asistente = self.env["account.payment.register"].with_context(
                active_model="account.move", active_ids=move.ids).create({
                    "journal_id": cobro.journal_id.id, "amount": cobro.importe, "payment_date": self.fecha,
                    "communication": _("%(m)s — Z %(n)s", m=cobro._nombre_medio(), n=self.numero),
                    "payment_difference_handling": "open",
                })
            asistente._create_payments()

    def action_volver_a_borrador(self):
        """Para corregir un Z mal cargado: anula sus cobros y su comprobante (quedan anulados, a la vista)."""
        for z in self.filtered(lambda r: r.state == "confirmado"):
            move = z.move_id
            if move:
                pagos = move._get_reconciled_payments()
                if pagos:
                    pagos.action_draft()
                    pagos.action_cancel()
                if move.state == "posted":
                    move.button_draft()
                if move.state == "draft":
                    move.button_cancel()
            z.write({"state": "borrador", "move_id": False})
            z.message_post(body=_("Vuelto a borrador para corregirlo; el comprobante %s quedó anulado.",
                                  move.name if move else "-"))
        return True

    def unlink(self):
        if any(z.state == "confirmado" for z in self):
            raise UserError(_("Un Z confirmado no se borra: volvelo a borrador primero."))
        return super().unlink()

    # ------------------------------------------------------------ para revisar y probar
    def comercio_renglones_libro_iva(self):
        """Los renglones del Libro IVA Digital (TXT de ventas y de alícuotas) del comprobante del Z,
        tal como salen en la exportación de Odoo."""
        self.ensure_one()
        if not self.move_id:
            return {}
        libro = self.env["l10n_ar.tax.report.handler"]
        alicuotas = libro._vat_book_get_REGINFO_CV_ALICUOTAS({}, "sale", self.move_id)
        comprobante = libro._vat_book_get_REGINFO_CV_CBTE({}, alicuotas, "sale", self.move_id)
        return {"comprobante": comprobante, "alicuotas": [r for v in alicuotas.values() for r in v]}


class ComercioCierreZCobro(models.Model):
    _name = "comercio.cierre.z.cobro"
    _description = "Medio de pago de un cierre Z"

    cierre_id = fields.Many2one("comercio.cierre.z", required=True, ondelete="cascade")
    currency_id = fields.Many2one(related="cierre_id.currency_id")
    medio = fields.Selection([
        ("efectivo", "Efectivo"), ("debito", "Débito"), ("credito", "Crédito"),
        ("transferencia", "Transferencia / QR"), ("otro", "Otro"),
    ], "Medio", required=True, default="efectivo")
    journal_id = fields.Many2one(
        "account.journal", "Diario", compute="_compute_journal_id", store=True, readonly=False,
        domain="[('type', 'in', ('cash', 'bank'))]",
        help="Dónde entra la plata: se configura por medio (comercio_cierre_z.diario_<medio>) y se puede cambiar.")
    importe = fields.Monetary("Importe")

    @api.depends("medio")
    def _compute_journal_id(self):
        parametros = self.env["ir.config_parameter"].sudo()
        for cobro in self:
            codigo = parametros.get_str(f"comercio_cierre_z.diario_{cobro.medio}")
            cobro.journal_id = codigo and self.env["account.journal"].search(
                [("code", "=", codigo), ("type", "in", ("cash", "bank"))], limit=1)

    def _nombre_medio(self):
        return dict(self._fields["medio"]._description_selection(self.env)).get(self.medio, self.medio)
