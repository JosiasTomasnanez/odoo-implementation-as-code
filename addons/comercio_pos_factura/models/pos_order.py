from collections import Counter

from odoo import _, api, fields, models
from odoo.exceptions import AccessError, UserError


class PosOrder(models.Model):
    _inherit = "pos.order"

    comercio_factura_odoo = fields.Boolean(
        "Con factura de Odoo", compute="_compute_comercio_factura_odoo", store=True,
        help="La venta tiene factura de Odoo con comprobante fiscal (va al Libro IVA Ventas de Odoo). Si no, "
             "el comprobante lo emitió la registradora o 3C y le llega al contador por ese lado.")

    @api.depends("account_move.state", "account_move.journal_id.l10n_latam_use_documents")
    def _compute_comercio_factura_odoo(self):
        for pedido in self:
            factura = pedido.account_move
            pedido.comercio_factura_odoo = bool(
                factura and factura.state == "posted" and factura.journal_id.l10n_latam_use_documents)

    # ------------------------------------------------------------ facturar después, con CAE
    def _prepare_invoice_vals(self):
        vals = super()._prepare_invoice_vals()
        diario = self.env.context.get("comercio_diario_fiscal")
        # El contexto lo puede mandar cualquiera por la API: solo vale el diario electrónico y para la administración
        # (o el reintento automático de comercio_pos_ticket_ar, que corre con sudo)
        if diario and (self.env.su or self.env.user.has_group("account.group_account_invoice")) \
                and diario == self._comercio_diario_fiscal().id:
            vals["journal_id"] = diario  # el de factura electrónica, no el del punto de venta (ADR 0024)
        return vals

    @api.model
    def _comercio_diario_fiscal(self):
        """El diario de factura electrónica: el de las cajas que facturan con comprobante (el más usado) o,
        si no, el único diario de ventas por web service de la empresa."""
        cajas = self.env["pos.config"].search(
            [("company_id", "=", self.env.company.id), ("journal_id.l10n_latam_use_documents", "=", True)])
        if cajas:
            return Counter(caja.journal_id for caja in cajas).most_common(1)[0][0]
        diarios = self.env["account.journal"].search([
            *self.env["account.journal"]._check_company_domain(self.env.company), ("type", "=", "sale"),
            ("l10n_latam_use_documents", "=", True), ("l10n_ar_afip_pos_system", "=", "RAW_MAW")])
        if len(diarios) != 1:
            raise UserError(_("No se encontró el diario de factura electrónica para facturar con CAE: configurá el "
                              "diario de las cajas (Punto de venta → Configuración)."))
        return diarios

    def action_comercio_facturar_con_cae(self):
        """«Facturar con CAE» (administración): ventas que quedaron sin factura de Odoo y no se hicieron en la
        registradora. Una factura por venta, siempre en el diario de factura electrónica (el «Factura» de Odoo
        usa el diario del punto de venta y en un puesto hace un comprobante interno, sin CAE)."""
        if not self.env.user.has_group("account.group_account_invoice"):
            raise AccessError(_("Facturar ventas ya cobradas es tarea de la administración."))
        facturas = self._comercio_facturar_con_cae()
        if len(facturas) == 1:
            return {"type": "ir.actions.act_window", "res_model": "account.move", "res_id": facturas.id,
                    "view_mode": "form", "views": [(False, "form")], "name": facturas.name}
        return {"type": "ir.actions.act_window", "res_model": "account.move", "name": _("Facturas con CAE"),
                "domain": [("id", "in", facturas.ids)], "view_mode": "list,form", "views": [(False, "list"), (False, "form")]}

    def _comercio_facturar_con_cae(self):
        """Lo que hace «Facturar con CAE», sin el control de permisos (lo usa también el reintento automático
        cuando ARCA vuelve, comercio_pos_ticket_ar). Devuelve las facturas."""
        pedidos = self.filtered(lambda o: o.state in ("paid", "done") and not o.comercio_factura_odoo)
        if not pedidos:
            raise UserError(_("Las ventas elegidas ya tienen factura de Odoo (o no están cobradas)."))
        if pedidos.filtered(lambda o: o.amount_total < 0):
            raise UserError(_("Las devoluciones no se facturan desde acá."))
        diario = self._comercio_diario_fiscal()
        facturas = self.env["account.move"]
        for pedido in pedidos:
            interna = pedido.account_move
            if pedido.is_singly_invoiced and interna.move_type == "out_invoice" \
                    and not interna.journal_id.l10n_latam_use_documents:
                pedido._comercio_pasar_a_factura_fiscal(diario)
            else:
                pedido.with_context(comercio_diario_fiscal=diario.id).action_pos_order_invoice()
            facturas |= pedido.account_move
        return facturas

    def _comercio_pasar_a_factura_fiscal(self, diario):
        """La venta ya tiene un comprobante interno (factura en un diario sin documentos, p. ej. hecha con el
        «Factura» de Odoo desde un puesto): pasa al diario de factura electrónica y se confirma (pide el CAE).
        Mantiene el cobro y la contabilidad de la venta."""
        self.ensure_one()
        factura = self.account_move
        factura.button_draft()
        # Sin el número interno (va a otro diario) y con la fecha de hoy: la factura con CAE se emite hoy, y ARCA
        # rechaza una fecha anterior a la última que autorizó (error 10016)
        hoy = fields.Date.context_today(self)
        factura.write({"name": "/", "journal_id": diario.id, "invoice_date": hoy, "invoice_date_due": hoy})
        tipo = factura.l10n_latam_available_document_type_ids.filtered(lambda t: t.internal_type == "invoice")[:1]
        if not tipo:
            raise UserError(_("No hay un tipo de factura posible para %s (revisá el cliente).", self.name))
        factura.l10n_latam_document_type_id = tipo
        factura.action_post()
