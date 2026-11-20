/**
 * Más productos a la vista (20/11, pedido del usuario): Odoo corta en 100 productos ANTES de
 * ordenar (los primeros 100 en orden de carga), así que el orden alfabético (orden.js) ordenaba
 * solo esos. Acá se ordena primero (favoritos y nombre, sin búsqueda; con búsqueda, el orden de la
 * búsqueda) y se muestran hasta 300.
 */
import { patch } from "@web/core/utils/patch";
import { localeCompare } from "@web/core/l10n/utils";
import { PosStore } from "@point_of_sale/app/services/pos_store";

const TOPE = 300;

patch(PosStore.prototype, {
    filterExcludedProducts(products) {
        let lista = [...products];
        if (!this.searchProductWord.trim()) {
            lista.sort((a, b) => b.is_favorite - a.is_favorite || localeCompare(a.name, b.name));
        }
        const excluidos = new Set(this.getExcludedProductIds());
        const categorias = new Set((this.config.iface_available_categ_ids || []).map((c) => c.id));
        const salida = [];
        for (const p of lista) {
            if (salida.length >= TOPE) {
                break;
            }
            if (excluidos.has(p.id) || !p.canBeDisplayed) {
                continue;
            }
            if (
                categorias.size &&
                !this.config._pos_special_display_products_ids?.includes(p.id) &&
                !p.pos_categ_ids.some((c) => categorias.has(c.id))
            ) {
                continue;
            }
            salida.push(p);
        }
        return salida;
    },
});
