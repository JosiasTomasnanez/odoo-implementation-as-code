/** Productos del punto de venta: favoritos primero y el resto por orden alfabético. */
import { patch } from "@web/core/utils/patch";
import { localeCompare } from "@web/core/l10n/utils";
import { PosStore } from "@point_of_sale/app/services/pos_store";
import { PosAccessRightPlugin } from "@point_of_sale/app/plugins/access_right_plugin";

// Odoo ordena por favoritos, después por la «secuencia del POS» (que al crear un producto
// lo pone al final: queda el orden de carga) y recién después por nombre. Con miles de
// productos eso parece desordenado: se deja favoritos (la estrellita) y nombre.
patch(PosStore.prototype, {
    orderProductBySequenceAndFav(products) {
        if (this.searchProductWord.trim()) {
            return super.orderProductBySequenceAndFav(...arguments);
        }
        return products.sort(
            (a, b) => b.is_favorite - a.is_favorite || localeCompare(a.name, b.name)
        );
    },
});

// Reordenar arrastrando no tendría efecto (no se usa la secuencia): no se ofrece.
patch(PosAccessRightPlugin.prototype, {
    get canSortProducts() {
        return false;
    },
});
