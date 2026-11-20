import { GeneratePrinterData } from "@point_of_sale/app/utils/printer/generate_printer_data";
import OrderPaymentValidation from "@point_of_sale/app/utils/order_payment_validation";
import { AlertDialog } from "@web/core/confirmation_dialog/confirmation_dialog";
import { _t } from "@web/core/l10n/translation";
import { patch } from "@web/core/utils/patch";

const TITULO_TRANSPARENCIA = "Régimen de Transparencia Fiscal al Consumidor (Ley 27.743)";

// Copia en JS de receipt/pos_order_receipt.py: los datos de la factura al pie del ticket
patch(GeneratePrinterData.prototype, {
    generateReceiptData() {
        const data = super.generateReceiptData(...arguments);
        const pedido = this.order;
        if (pedido.comercio_ticket_cae) {
            data.conditions.comercio_factura_ar = true;
            // Ya está facturada: sin el «¿Necesita factura?» de Odoo (otro QR, que confunde con el de ARCA)
            data.conditions.use_self_invoicing = false;
            data.extra_data.comercio_factura_ar = {
                factura: pedido.comercio_ticket_factura,
                cae: pedido.comercio_ticket_cae,
                vto: pedido.comercio_ticket_cae_vto,
                titulo: TITULO_TRANSPARENCIA,
                impuestos: (pedido.comercio_ticket_transparencia || "")
                    .split("\n")
                    .filter(Boolean)
                    .map((linea) => linea.split("|")),
            };
            if (pedido.comercio_ticket_qr) {
                data.image.comercio_qr_arca = this.generateQrCode(pedido.comercio_ticket_qr);
            }
        } else if (pedido.comercio_factura_pendiente) {
            data.conditions.comercio_factura_pendiente = true;
            data.conditions.use_self_invoicing = false;
        }
        return data;
    },
});

// ARCA no respondió: el servidor dejó la venta cobrada sin factura de Odoo; la caja lo avisa claro
patch(OrderPaymentValidation.prototype, {
    async afterOrderValidation() {
        const resultado = await super.afterOrderValidation(...arguments);
        if (this.order.comercio_factura_pendiente) {
            this.pos.dialog.add(AlertDialog, {
                title: _t("ARCA no respondió: factura pendiente"),
                body: _t(
                    "La venta quedó cobrada. La factura se hace sola cuando ARCA vuelva a responder; el ticket lo aclara."
                ),
            });
        } else if (this.order.comercio_sin_factura_arca) {
            this.pos.dialog.add(AlertDialog, {
                title: _t("ARCA no respondió: venta sin factura"),
                body: _t(
                    "La venta quedó cobrada, pero sin factura de Odoo. Hacé el comprobante en la registradora."
                ),
            });
        }
        return resultado;
    },
});
