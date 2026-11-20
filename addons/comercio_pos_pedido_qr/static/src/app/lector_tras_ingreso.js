/**
 * Arreglo temporal de un error de Odoo 20 (pos_hr, imagen odoo:20.0-20261015): la pantalla de
 * ingreso con PIN registra el lector de códigos «en exclusiva» para las tarjetas de cajero y
 * nunca lo suelta. Después de entrar, todo escaneo se toma como tarjeta de cajero y cualquier
 * producto da «Código de barras desconocido» (encontrado el 18/11 en Ferretería 1).
 *
 * Odoo ya lo corrigió en 20.0 (usa useBarcodeReader, que lo suelta al cerrar la pantalla).
 * Al actualizar la imagen, si pos_hr ya usa useBarcodeReader, borrar este archivo.
 */
import { patch } from "@web/core/utils/patch";
import { onWillDestroy } from "@odoo/owl";
import { LoginScreen } from "@point_of_sale/app/screens/login_screen/login_screen";

const soloCajero = (cbMap) => cbMap && Object.keys(cbMap).join() === "cashier";

patch(LoginScreen.prototype, {
    setup() {
        const lector = this.env.services.barcode_reader;
        const exclusivoAntes = lector?.exclusiveCbMap;
        const antes = new Set(lector?.cbMaps || []);
        super.setup(...arguments);
        if (!lector) {
            return;
        }
        const exclusivo =
            lector.exclusiveCbMap !== exclusivoAntes && soloCajero(lector.exclusiveCbMap)
                ? lector.exclusiveCbMap
                : null;
        const nuevos = [...lector.cbMaps].filter((m) => !antes.has(m) && soloCajero(m));
        onWillDestroy(() => {
            if (exclusivo && lector.exclusiveCbMap === exclusivo) {
                lector.exclusiveCbMap = null;
            }
            nuevos.forEach((m) => lector.cbMaps.delete(m));
        });
    },
});
