/** Balanza Systel Cuora en el POS: lectura del peso y pesaje automático. */
import { onMounted, onWillUnmount } from "@odoo/owl";
import { _t } from "@web/core/l10n/translation";
import { registry } from "@web/core/registry";
import { delay } from "@web/core/utils/concurrency";
import { useHotkey } from "@web/core/hotkeys/hotkey_hook";
import { patch } from "@web/core/utils/patch";
import { ScaleInterface } from "@point_of_sale/app/utils/scale/scale_interface";
import { ScaleScreen } from "@point_of_sale/app/screens/scale_screen/scale_screen";
import { NumberPopup } from "@point_of_sale/app/components/popups/number_popup/number_popup";
import { abrirBalanzaSystel } from "@comercio_pos_balanza_systel/lib/systel_cuora_scale";

// Pesaje automático: cada cuánto se pide el peso y cuántas lecturas iguales y estables
// hacen falta para agregarlo al pedido.
const INTERVALO_MS = 250;
const LECTURAS_ESTABLES = 2;

const ERRORES = {
    E4: _t("La balanza no reconoce el pedido de peso (¿protocolo distinto?)"),
};

export class SystelCuoraScaleInterface extends ScaleInterface {
    async connectToScale() {
        this.estable = false;
        this.scale = await abrirBalanzaSystel(this.pos.config.comercio_balanza_numero || 1);
        return Boolean(this.scale);
    }

    /** La tara se hace en la balanza: Odoo muestra solo el peso neto que manda. */
    get hardwareTare() {
        return true;
    }

    /**
     * Sin respuesta no se lanza un error: el error «grave» del POS cierra la pantalla de
     * peso y agrega el producto con cantidad 1, un peso que nadie midió. Se avisa una
     * vez, la pantalla sigue abierta y se reintenta.
     */
    async _readWeight() {
        let respuesta = null;
        try {
            respuesta = await this.scale.leerPeso();
        } catch {
            // Cable desconectado: igual que sin respuesta.
        }
        if (!respuesta) {
            this.estable = false;
            if (!this.sinRespuesta) {
                this.sinRespuesta = true;
                this.onError(
                    _t("La balanza no responde. Revisar el cable USB y que esté encendida."),
                    false
                );
            }
            return null;
        }
        this.sinRespuesta = false;
        if (respuesta.error) {
            this.estable = false;
            // Un aviso por error, no uno por lectura (se lee cada 250 ms)
            if (this.ultimoError !== respuesta.error) {
                this.ultimoError = respuesta.error;
                this.onError(ERRORES[respuesta.error] || _t("Error de la balanza: %s", respuesta.error), false);
            }
            return null;
        }
        this.ultimoError = null;
        this.estable = respuesta.estable;
        return respuesta.gramos / 1000;
    }

    get isWeightValid() {
        return super.isWeightValid && this.estable;
    }
}

registry
    .category("electronic_scales")
    .add("comercio_systel_cuora", SystelCuoraScaleInterface, { sequence: 50 });
// En el local solo hay Systel. Si la Cuora no contesta (apagada, número mal cargado), el POS
// probaba la balanza estándar por USB (Toledo) en el mismo puerto, y si esa prueba fallaba
// el POS no abría («¡Ups!», encontrado el 19/10). Sin ella, el puesto abre sin balanza.
registry.category("electronic_scales").remove("web_serial");

patch(ScaleScreen.prototype, {
    setup() {
        super.setup(...arguments);
        if (this.scale instanceof SystelCuoraScaleInterface) {
            // Cada producto se elige a propósito: la misma pesada que el anterior («un kilo
            // justo») tiene que valer. El estándar la rechaza hasta que la balanza vuelva a cero.
            this.scale.lastWeight = null;
            this.scale.ultimoError = null;
            this.scale.sinRespuesta = false;
        }
        if (this.scale instanceof SystelCuoraScaleInterface) {
            // Automático: se agrega solo al quedar estable. Si no (17/11: «a veces hay que ir
            // agregando o sacando hasta el peso que piden»), el peso se ve en vivo y se
            // agrega con «Pedido» o Enter.
            onMounted(() =>
                this.pos.config.comercio_pesaje_automatico
                    ? this.comercioPesajeAutomatico()
                    : this.comercioLecturaEnVivo()
            );
            onWillUnmount(() => {
                this.comercioPesando = false;
            });
            useHotkey("enter", () => this.scale.isWeightValid && this.comercioConfirmar(), {
                bypassEditableProtection: true,
            });
        }
    },

    /** Pide el peso todo el tiempo para mostrarlo en vivo; no agrega nada solo. */
    async comercioLecturaEnVivo() {
        this.comercioPesando = true;
        while (this.comercioPesando && this.scale.product) {
            await this.scale.readWeight();
            await delay(INTERVALO_MS);
        }
    },

    /** Pide el peso hasta que quede estable y lo agrega al pedido sin tocar «Pedido». */
    async comercioPesajeAutomatico() {
        this.comercioPesando = true;
        let anterior = null;
        let iguales = 0;
        while (this.comercioPesando) {
            await this.scale.readWeight();
            if (!this.comercioPesando || !this.scale.product) {
                break;
            }
            if (this.scale.isWeightValid && this.scale.weight === anterior) {
                iguales++;
            } else {
                anterior = this.scale.isWeightValid ? this.scale.weight : null;
                iguales = anterior === null ? 0 : 1;
            }
            if (iguales >= LECTURAS_ESTABLES) {
                this.comercioPesando = false;
                this.comercioConfirmar();
                break;
            }
            await delay(INTERVALO_MS);
        }
    },

    /**
     * «Escribir el peso» (pedido del 17/11): para los casos en que no conviene pesar (bolsa
     * con el peso impreso, balanza ocupada). Corta el pesaje automático, pide el peso con el
     * teclado y lo agrega al pedido. Sin restricción: la cantidad igual se puede cambiar
     * después en la línea.
     */
    comercioPesoManual() {
        this.comercioPesando = false;
        const unidad = this.scale.product?.unitOfMeasure || "kg";
        this.dialog.add(NumberPopup, {
            title: _t("Peso (%s)", unidad),
            placeholder: "0,000",
            getPayload: (valor) => {
                const peso = Number(String(valor ?? "").replace(",", "."));
                if (!(peso > 0) || !this.scale.product) {
                    return;
                }
                this.props.getPayload(peso);
                this.props.close();
                setTimeout(() => {
                    this.scale.setErrorCallback(null);
                    this.scale.product = null;
                });
            },
        });
    },

    /**
     * Como confirm(), pero vacía el producto de la balanza después de cerrar: fuera de un
     * clic, vaciarlo antes re-dibuja el diálogo sin producto y falla.
     */
    comercioConfirmar() {
        this.comercioPesando = false;
        this.props.getPayload(this.scale.confirmWeight());
        this.props.close();
        setTimeout(() => {
            this.scale.setErrorCallback(null);
            this.scale.product = null;
        });
    },
});
