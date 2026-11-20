"""Compras sin factura: la compra queda registrada y se paga aunque el proveedor
todavía no haya mandado la factura real (o mande un presupuesto, un remito valorizado, una
nota de pedido). Van en un diario de compras propio, sin documentos fiscales: no van al libro
IVA ni dan crédito fiscal, así que las líneas van sin IVA (el IVA que se paga es costo).
Cuando llega la factura real la carga la administración y anula esta a mano."""
from odoo import Command, _, api, fields, models
from odoo.exceptions import UserError


class AccountJournal(models.Model):
    _inherit = "account.journal"

    comercio_sin_factura = fields.Boolean(
        "Compras sin factura",
        help="Diario de compras para registrar y pagar lo que todavía no tiene factura real del proveedor. "
             "Sin documentos fiscales ni IVA: no va al libro IVA ni da crédito fiscal.")


class AccountMove(models.Model):
    _inherit = "account.move"

    comercio_provisoria = fields.Boolean(
        "Sin factura", related="journal_id.comercio_sin_factura", store=True,
        help="Compra registrada sin la factura real del proveedor: no va al libro IVA.")

    @api.model
    def _comercio_diario_sin_factura(self, empresa=None):
        empresa = empresa or self.env.company
        diario = self.env["account.journal"].search([
            *self.env["account.journal"]._check_company_domain(empresa),
            ("type", "=", "purchase"), ("comercio_sin_factura", "=", True)], limit=1)
        if not diario:
            raise UserError(_("No hay un diario de «Compras sin factura» (se crea con la configuración del servidor)."))
        return diario

    @api.model
    def action_comercio_provisorias(self):
        """Menú «Compras sin factura»: «Nuevo» y «Subir» van a ese diario."""
        diario = self._comercio_diario_sin_factura()
        accion = self.env["ir.actions.act_window"]._for_xml_id("account.action_move_in_invoice_type")
        accion.update({
            "name": _("Compras sin factura"),
            "domain": [("move_type", "in", ("in_invoice", "in_refund")), ("journal_id", "=", diario.id)],
            "context": {"default_move_type": "in_invoice", "default_journal_id": diario.id},
        })
        return accion

    def write(self, vals):
        res = super().write(vals)
        if "journal_id" in vals:
            self.filtered(lambda m: m.state == "draft")._comercio_impuestos_segun_diario()
        return res

    def _comercio_impuestos_segun_diario(self):
        """Al pasar al diario sin factura las líneas quedan sin IVA; al volver a uno con factura,
        con el IVA de cada producto."""
        for move in self:
            lineas = move.invoice_line_ids.filtered(lambda ml: ml.display_type == "product")
            if move.comercio_provisoria:
                lineas.filtered("tax_ids").tax_ids = [Command.clear()]
            else:
                lineas.filtered(lambda ml: ml.product_id and not ml.tax_ids)._compute_tax_ids()

    def _post(self, soft=True):
        for move in self.filtered("comercio_provisoria"):
            if move.invoice_line_ids.filtered("tax_ids"):
                raise UserError(_(
                    "«%s» es una compra sin factura: va sin IVA ni percepciones (no dan crédito fiscal). Sacale "
                    "los impuestos a las líneas; si el proveedor cobró IVA, sumalo en una línea aparte.",
                    move.display_name))
        return super()._post(soft=soft)


class AccountMoveLine(models.Model):
    _inherit = "account.move.line"

    @api.model_create_multi
    def create(self, vals_list):
        lineas = super().create(vals_list)
        lineas.filtered(lambda ml: ml.move_id.comercio_provisoria and ml.display_type == "product"
                        and ml.tax_ids).tax_ids = [Command.clear()]
        return lineas

    def _compute_tax_ids(self):
        super()._compute_tax_ids()
        for linea in self.filtered(lambda ml: ml.move_id.comercio_provisoria and ml.display_type == "product"):
            linea.tax_ids = False


class PurchaseOrder(models.Model):
    _inherit = "purchase.order"

    def action_comercio_factura_provisoria(self):
        """Como «Crear factura» (lo recibido, a los precios de la orden), pero en el diario sin factura:
        la compra queda registrada y se puede pagar hasta que llegue la factura real."""
        diario = self.env["account.move"]._comercio_diario_sin_factura(self.company_id[:1])
        antes = self.invoice_ids
        accion = self.with_context(default_journal_id=diario.id).action_create_invoice()
        (self.invoice_ids - antes).filtered(lambda m: m.journal_id != diario).write({"journal_id": diario.id})
        return accion
