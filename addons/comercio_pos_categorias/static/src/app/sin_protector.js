/**
 * Sin protector de pantalla (20/11, pedido del usuario). Odoo a los 3 minutos sin tocar muestra
 * el protector y, al volver, borra la cajera (pos_store `firstPage` → `resetCashier`): había que
 * poner el usuario y el PIN de nuevo. Sin pasos de inactividad no hay protector ni vuelta al PIN;
 * para dejar el puesto, el botón de bloquear de siempre.
 */
import { patch } from "@web/core/utils/patch";
import { PosStore } from "@point_of_sale/app/services/pos_store";

patch(PosStore.prototype, {
    get idleTimeout() {
        return [];
    },
});
