import logging

from odoo import _, api, fields, models
from odoo.exceptions import AccessError, UserError

_logger = logging.getLogger(__name__)

TITULO_TRANSPARENCIA = "Régimen de Transparencia Fiscal al Consumidor (Ley 27.743)"
# Qué pasa con una venta con «Factura» marcado si ARCA no responde (config/valores.yaml, facturacion.arca_caido):
#   registradora     → el comprobante se hace en la registradora; Odoo no la factura después (doble comprobante).
#   facturar_despues → queda «Factura pendiente» y se factura con CAE sola cuando ARCA vuelve (sin registradoras).
PARAM_ARCA_CAIDO = "comercio_pos_ticket_ar.arca_caido"


class PosOrder(models.Model):
    _inherit = "pos.order"

    comercio_sin_factura_arca = fields.Boolean(
        "Sin factura: ARCA no respondió", readonly=True, copy=False,
        help="La caja intentó facturar y ARCA no respondió: la venta quedó cobrada sin factura de Odoo. "
             "Según facturacion.arca_caido, el comprobante se hizo en la registradora o la factura queda "
             "pendiente hasta que ARCA vuelva.")
    comercio_motivo_sin_factura = fields.Char("Motivo", readonly=True, copy=False)
    comercio_factura_pendiente = fields.Boolean(
        "Factura pendiente (ARCA)", readonly=True, copy=False, index=True,
        help="Se cobró con «Factura» marcado, ARCA no respondió y la factura con CAE se hace sola cuando ARCA "
             "vuelva (facturacion.arca_caido = facturar_despues). Las ventas cobradas sin «Factura» nunca "
             "quedan pendientes.")
    # Lo que va al pie del ticket (también lo lee la caja después de sincronizar)
    comercio_ticket_factura = fields.Char(compute="_compute_comercio_ticket")
    comercio_ticket_cae = fields.Char(compute="_compute_comercio_ticket")
    comercio_ticket_cae_vto = fields.Char(compute="_compute_comercio_ticket")
    comercio_ticket_qr = fields.Char(compute="_compute_comercio_ticket")
    comercio_ticket_transparencia = fields.Char(compute="_compute_comercio_ticket")

    @api.depends("account_move.state", "account_move.l10n_ar_afip_auth_code")
    def _compute_comercio_ticket(self):
        for pedido in self:
            factura = pedido.account_move
            valido = (factura and factura.state == "posted" and factura.journal_id.l10n_latam_use_documents
                      and factura.l10n_ar_afip_auth_code)
            if not valido:
                pedido.comercio_ticket_factura = pedido.comercio_ticket_cae = pedido.comercio_ticket_cae_vto = False
                pedido.comercio_ticket_qr = pedido.comercio_ticket_transparencia = False
                continue
            tipo = factura.l10n_latam_document_type_id
            nombre = f"{(tipo.report_name or tipo.name).capitalize()} {tipo.l10n_ar_letter or ''}".strip()
            pedido.comercio_ticket_factura = f"{nombre} Nº {factura.l10n_latam_document_number or factura.name}"
            pedido.comercio_ticket_cae = factura.l10n_ar_afip_auth_code
            vencimiento = factura.l10n_ar_afip_auth_code_due
            pedido.comercio_ticket_cae_vto = vencimiento.strftime("%d/%m/%Y") if vencimiento else False
            pedido.comercio_ticket_qr = factura.l10n_ar_afip_qr_code or False
            # Una línea por impuesto: «IVA Contenido $|1.640,95» (solo comprobantes B, RG 5614)
            resumen = factura._l10n_ar_get_invoice_custom_tax_summary_for_report()
            pedido.comercio_ticket_transparencia = "\n".join(
                f"{r['name']}|{r['formatted_tax_amount_currency']}" for r in resumen) or False

    # ------------------------------------------------------------ ARCA caído
    def _generate_order_invoice(self):
        """Si ARCA no responde, la venta no se traba: queda cobrada sin factura de Odoo y el comprobante
        va por la registradora.

        Antes de facturar se prueba la conexión con ARCA con el mismo método que usa l10n_ar_edi al
        validar (`_l10n_ar_get_connection` + `_get_client`). No se envuelve la factura en un savepoint:
        l10n_ar_edi hace commit al recibir el CAE y rollback de toda la transacción si ARCA rechaza el
        comprobante. Si ARCA responde pero lo rechaza (datos mal), sigue el error de siempre."""
        self.ensure_one()
        diario = self.config_id.journal_id
        empresa = self.company_id
        # Homologación sin certificado: Odoo valida sin ARCA (CAE inventado), no hay nada que probar
        sin_arca = empresa._get_environment_type() == "testing" and not empresa.sudo().l10n_ar_afip_ws_crt_id
        if not (self.to_invoice and self.state == "paid" and diario.l10n_ar_afip_ws) or sin_arca:
            return super()._generate_order_invoice()
        try:
            empresa._l10n_ar_get_connection(diario.l10n_ar_afip_ws)._get_client()
        except (UserError, ConnectionError, TimeoutError) as error:
            motivo = str(error.args[0] if error.args else error)[:500]
            _logger.warning("Venta %s sin factura de Odoo, ARCA no respondió: %s", self.name, motivo)
            despues = self._comercio_arca_caido() == "facturar_despues"
            self.write({"to_invoice": False, "comercio_sin_factura_arca": True,
                        "comercio_factura_pendiente": despues, "comercio_motivo_sin_factura": motivo})
            if despues:
                self.message_post(body=_("No se pudo facturar con CAE: ARCA no respondió. La venta quedó cobrada "
                                         "y la factura queda pendiente: se hace sola cuando ARCA vuelva. "
                                         "Motivo: %s", motivo))
            else:
                self.message_post(body=_("No se pudo facturar con CAE: ARCA no respondió. La venta quedó "
                                         "cobrada sin factura de Odoo; el comprobante se hace en la "
                                         "registradora. Motivo: %s", motivo))
            return None
        return super()._generate_order_invoice()

    @api.model
    def _comercio_arca_caido(self):
        modo = self.env["ir.config_parameter"].sudo().get_str(PARAM_ARCA_CAIDO, "registradora")
        return modo if modo in ("registradora", "facturar_despues") else "registradora"

    # ------------------------------------------------------------ facturas pendientes por ARCA
    def _comercio_facturar_con_cae(self):
        facturas = super()._comercio_facturar_con_cae()
        # Facturada a mano con «Facturar con CAE»: deja de estar pendiente
        self.filtered(lambda o: o.comercio_factura_pendiente and o.comercio_factura_odoo).write(
            {"comercio_factura_pendiente": False})
        return facturas

    def action_comercio_reintentar_facturas(self):
        """Botón «Reintentar facturas pendientes» (administración): lo mismo que hace la tarea automática."""
        if not self.env.user.has_group("account.group_account_invoice"):
            raise AccessError(_("Facturar ventas ya cobradas es tarea de la administración."))
        cuantas = self.sudo()._cron_comercio_facturar_pendientes()
        quedan = self.sudo().search_count([("comercio_factura_pendiente", "=", True)])
        mensaje = _("Facturadas: %(f)s. Siguen pendientes: %(q)s.", f=cuantas, q=quedan)
        if quedan:
            mensaje += " " + _("Si ARCA sigue sin responder, se reintenta sola cada 10 minutos.")
        return {"type": "ir.actions.client", "tag": "display_notification",
                "params": {"title": _("Facturas pendientes por ARCA"), "message": mensaje,
                           "type": "success" if not quedan else "warning", "sticky": False,
                           "next": {"type": "ir.actions.client", "tag": "soft_reload"}}}

    @api.model
    def _cron_comercio_facturar_pendientes(self, limite=100):
        """Factura con CAE las ventas pendientes por ARCA caído, si ARCA ya responde. Solo las que se cobraron
        con «Factura» marcado (comercio_factura_pendiente); nunca toca las cobradas sin «Factura».

        Idempotente: cada venta se confirma (commit) apenas tiene su CAE y deja de estar pendiente; una venta
        que ya tiene factura de Odoo solo se desmarca. Si ARCA vuelve a no responder, se corta y sigue en la
        próxima pasada. Si ARCA rechaza el comprobante (datos mal), deja de reintentarlo: queda en «Sin
        factura: ARCA no respondió» con el motivo, para facturarla a mano. Devuelve cuántas facturó."""
        pendientes = self.sudo().search([("comercio_factura_pendiente", "=", True)], order="id", limit=limite)
        facturadas = 0
        for empresa in pendientes.company_id:
            del_empresa = pendientes.filtered(lambda o: o.company_id == empresa).with_company(empresa)
            diario = del_empresa._comercio_diario_fiscal()
            if not del_empresa._comercio_arca_responde(empresa, diario):
                continue
            for pedido in del_empresa:
                if pedido.comercio_factura_odoo:
                    pedido.comercio_factura_pendiente = False
                    self.env.cr.commit()
                    continue
                try:
                    factura = pedido._comercio_facturar_con_cae()
                    pedido.comercio_factura_pendiente = False
                    pedido.message_post(body=_("ARCA volvió a responder: se emitió %s con CAE.", factura.name))
                    self.env.cr.commit()
                    facturadas += 1
                except Exception as error:  # noqa: BLE001 (cualquier error de ARCA o de la factura)
                    self.env.cr.rollback()
                    if not del_empresa._comercio_arca_responde(empresa, diario):
                        break  # se cayó de nuevo: sigue pendiente, se reintenta en la próxima pasada
                    motivo = str(error.args[0] if error.args else error)[:500]
                    _logger.warning("Venta %s: ARCA rechazó la factura al reintentar: %s", pedido.name, motivo)
                    pedido.write({"comercio_factura_pendiente": False,
                                  "comercio_motivo_sin_factura": _("ARCA la rechazó al reintentar: %s", motivo)})
                    pedido.message_post(body=_("No se pudo facturar al reintentar: ARCA rechazó el comprobante. "
                                               "Revisarla y facturarla a mano con «Facturar con CAE». Motivo: %s",
                                               motivo))
                    self.env.cr.commit()
        return facturadas

    @api.model
    def _comercio_arca_responde(self, empresa, diario):
        try:
            empresa._l10n_ar_get_connection(diario.l10n_ar_afip_ws)._get_client()
            return True
        except (UserError, ConnectionError, TimeoutError) as error:
            _logger.info("Facturas pendientes: ARCA sigue sin responder (%s)", error)
            return False
