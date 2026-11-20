import { Dialog } from "@web/core/dialog/dialog";
import { _t } from "@web/core/l10n/translation";
import { patch } from "@web/core/utils/patch";
import BarcodeQuantModel from "@stock_barcode/models/barcode_quant_model";
import { Component, proxy, t, useProps } from "@odoo/owl";

const LINEA = "comercio.lista.importacion.linea";

export class AgregarDesdeConteoDialog extends Component {
    static components = { Dialog };
    static template = "comercio_conteo_catalogo.AgregarDesdeConteoDialog";

    props = useProps({
        datos: t.object(),
        onElegir: t.function([]),
        close: t.function([]),
    });

    elegir(esElParecido) {
        this.props.onElegir(esElParecido);
        this.props.close();
    }
}

export class CodigoDeUnNuestroDialog extends Component {
    static components = { Dialog };
    static template = "comercio_conteo_catalogo.CodigoDeUnNuestroDialog";

    props = useProps({
        codigo: t.string(),
        buscar: t.function([]),
        onElegir: t.function([]),
        close: t.function([]),
    });

    setup() {
        this.estado = proxy({ texto: "", resultados: null });
    }

    async onBuscar() {
        this.estado.resultados = await this.props.buscar(this.estado.texto);
    }

    onTecla(ev) {
        if (ev.key === "Enter") {
            ev.preventDefault();
            ev.stopPropagation(); // que la app de conteo no lo tome como un escaneo
            this.onBuscar();
        }
    }

    elegir(producto) {
        this.props.onElegir(producto.id);
        this.props.close();
    }
}

// Un código que no es nuestro: antes de decir «no existe», se busca en las listas (02/11)
patch(BarcodeQuantModel.prototype, {
    noProductToast(barcodeData) {
        if (!barcodeData.barcode || barcodeData.error) {
            return super.noProductToast(...arguments);
        }
        return this._comercioOfrecerAgregar(barcodeData);
    },

    async _comercioOfrecerAgregar(barcodeData) {
        const codigo = barcodeData.barcode;
        let datos = false;
        try {
            datos = await this.orm.call(LINEA, "comercio_buscar_para_conteo", [codigo]);
        } catch {
            datos = false;
        }
        if (!datos) {
            return this._comercioOfrecerPonerCodigo(barcodeData);
        }
        if (!datos.puede_agregar) {
            return this.notification(
                _t("«%(d)s» está en la lista de %(p)s, pero no es de nuestro catálogo: pedile a quien maneja las listas que lo agregue.", {
                    d: datos.descripcion,
                    p: datos.proveedores.join(", "),
                }),
                { type: "warning" }
            );
        }
        this.dialogService.add(AgregarDesdeConteoDialog, {
            datos,
            onElegir: (esElParecido) => this._comercioAgregar(codigo, esElParecido),
        });
    },

    /** No está en ninguna lista: quizás lo tenemos con otro código (o con el 20…). */
    async _comercioOfrecerPonerCodigo(barcodeData) {
        const codigo = barcodeData.barcode;
        let puede = false;
        try {
            puede = await this.orm.call(LINEA, "comercio_puede_agregar", []);
        } catch {
            puede = false;
        }
        if (!puede) {
            return super.noProductToast(barcodeData);
        }
        this.dialogService.add(CodigoDeUnNuestroDialog, {
            codigo,
            buscar: (texto) => this.orm.call("product.template", "comercio_buscar_para_codigo", [texto]),
            onElegir: async (productoId) => {
                const nuestro = await this.orm.call(
                    "product.template", "comercio_poner_codigo_desde_conteo", [[productoId], codigo]
                );
                await this._comercioContar(nuestro);
            },
        });
    },

    async _comercioAgregar(codigo, esElParecido) {
        const nuestro = await this.orm.call(LINEA, "comercio_agregar_desde_conteo", [codigo], {
            es_el_parecido: esElParecido,
        });
        await this._comercioContar(nuestro);
    },

    /** Suma al conteo el producto recién agregado o con su código nuevo. */
    async _comercioContar(nuestro) {
        if (!nuestro) {
            return;
        }
        // La app recuerda los códigos que no encontró: se olvida de este para volver a buscarlo
        for (const clave of [...this.cache.missingBarcodeKeyCache]) {
            if (clave.startsWith(JSON.stringify([nuestro]).slice(0, -1))) {
                this.cache.missingBarcodeKeyCache.delete(clave);
            }
        }
        this.cache.missingBarcodesCache.delete(nuestro);
        await this.processBarcode(nuestro);
    },
});
