import { PaymentScreen } from "@point_of_sale/app/screens/payment_screen/payment_screen";
import { patch } from "@web/core/utils/patch";

// «Factura» desmarcado: la venta va sin factura de Odoo (la emite la registradora o 3C). ADR 0024.
patch(PaymentScreen.prototype, {
    get comercioSinFactura() {
        return (
            this.pos.isArgentineanCompany() &&
            !this.currentOrder.isToInvoice() &&
            !this.isForcedToInvoice
        );
    },
});
