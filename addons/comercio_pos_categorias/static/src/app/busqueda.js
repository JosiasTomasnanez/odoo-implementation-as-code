/**
 * Búsqueda de productos por palabras (20/11, pedido del usuario): Odoo busca la frase entera como
 * texto seguido («cepillo acero» no encontraba «CEPILLO DE ACERO»). Acá cada palabra tiene que
 * estar, en cualquier orden y aunque sea el principio («cep acer»). Una sola palabra o un código
 * siguen como en Odoo.
 */
import { patch } from "@web/core/utils/patch";
import { normalize } from "@web/core/l10n/utils";
import { _t } from "@web/core/l10n/translation";
import { PosStore } from "@point_of_sale/app/services/pos_store";

const palabras = (texto) => normalize(texto || "").split(/\s+/).filter(Boolean);

patch(PosStore.prototype, {
    getProductsBySearchWord(searchWord, products) {
        const buscadas = palabras(searchWord);
        if (buscadas.length <= 1) {
            return super.getProductsBySearchWord(...arguments);
        }
        const coincidencias = [];
        for (const product of products) {
            const texto = product.searchString;
            if (!buscadas.every((p) => texto.includes(p))) {
                continue;
            }
            const nombre = product.normalizedName;
            const delNombre = nombre.split(/\s+/);
            coincidencias.push({
                product,
                nombre,
                // Primero las que tienen todas las palabras en el nombre (no solo en el código)
                enNombre: buscadas.filter((p) => nombre.includes(p)).length,
                // Después, las que tienen palabras del nombre que empiezan con lo buscado
                empiezan: buscadas.filter((p) => delNombre.some((n) => n.startsWith(p))).length,
            });
        }
        coincidencias.sort(
            (a, b) =>
                b.enNombre - a.enNombre ||
                b.empiezan - a.empiezan ||
                (a.nombre < b.nombre ? -1 : a.nombre > b.nombre ? 1 : 0)
        );
        return coincidencias.map((c) => c.product);
    },

    // «Buscar más» / Enter en el servidor: el mismo criterio (cada palabra, en cualquier orden)
    searchProductsFromDBDomain(searchProductWord) {
        const buscadas = (searchProductWord || "").trim().split(/\s+/).filter(Boolean);
        if (buscadas.length <= 1) {
            return super.searchProductsFromDBDomain(...arguments);
        }
        const dominio = [];
        for (const p of buscadas) {
            dominio.push(
                "|", "|", "|", "|", "|",
                ["name", "ilike", p],
                ["product_variant_ids.name", "ilike", p],
                ["default_code", "ilike", p],
                ["product_variant_ids.default_code", "ilike", p],
                ["barcode", "ilike", p],
                ["product_variant_ids.barcode", "ilike", p]
            );
        }
        return [...dominio, ["available_in_pos", "=", true], ["sale_ok", "=", true]];
    },

    /**
     * Enter en el buscador: Odoo va al servidor a buscar productos que todavía no cargó y, si no hay
     * más, avisa «No se encontraron otros productos», aunque en pantalla haya resultados (parecía una
     * falla). Con resultados en pantalla no se avisa nada; sin ninguno, un aviso claro.
     */
    async searchProductsFromDB() {
        const buscado = (this.searchProductWord || "").trim();
        if (!buscado) {
            return;
        }
        const enPantalla = this.productsToDisplay.length;
        const avisar = this.notification.add.bind(this.notification);
        this.notification.add = (mensaje, ...resto) => {
            if (!enPantalla) {
                return avisar(_t('No hay productos con "%s" en el catálogo.', buscado), ...resto);
            }
        };
        try {
            return await super.searchProductsFromDB(...arguments);
        } finally {
            this.notification.add = avisar;
        }
    },
});
