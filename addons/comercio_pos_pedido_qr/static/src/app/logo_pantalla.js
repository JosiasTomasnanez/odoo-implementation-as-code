/** Pantalla de entrada del POS con el logo en color de la empresa. */
import { patch } from "@web/core/utils/patch";
import { LoginScreen } from "@point_of_sale/app/screens/login_screen/login_screen";

// Odoo muestra acá el logo del ticket, que en el local es el blanco y negro para la
// térmica (config/base/30-puntos-de-venta.yaml); en pantalla va el de la empresa.
patch(LoginScreen.prototype, {
    get logoUrl() {
        const empresa = this.pos.company?.id;
        return empresa ? `/web/binary/company_logo?company=${empresa}` : super.logoUrl;
    },
});
