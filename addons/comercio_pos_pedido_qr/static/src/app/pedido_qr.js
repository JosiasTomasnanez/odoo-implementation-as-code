/** Pedido del puesto con QR, cobrado en la caja (ADR 0009). */
import { _t } from "@web/core/l10n/translation";
import { patch } from "@web/core/utils/patch";
import { PosStore } from "@point_of_sale/app/services/pos_store";
import { BarcodeReader } from "@point_of_sale/app/services/barcode_reader_service";
import { GeneratePrinterData } from "@point_of_sale/app/utils/printer/generate_printer_data";
import { TextInputPopup } from "@point_of_sale/app/components/popups/text_input_popup/text_input_popup";
import { makeAwaitable } from "@point_of_sale/app/utils/make_awaitable_dialog";
import DevicesSynchronisation from "@point_of_sale/app/utils/devices_synchronisation";
import { Domain } from "@web/core/domain";
import { PosAccessRightPlugin } from "@point_of_sale/app/plugins/access_right_plugin";
import OrderPaymentValidation from "@point_of_sale/app/utils/order_payment_validation";
import { AlertDialog } from "@web/core/confirmation_dialog/confirmation_dialog";

// Código del QR: "PED" + uuid sin guiones. Solo letras y números, para que el lector
// USB lo envíe igual sin importar la distribución de teclado configurada.
const PREFIJO = "PED";
const CODIGO_RE = /^PED([0-9a-f]{32})$/i;
const UUID_RE = /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i;

export function codigoDePedido(uuid) {
    return PREFIJO + uuid.replace(/-/g, "");
}

function uuidDeCodigo(codigo) {
    const match = CODIGO_RE.exec(codigo);
    if (!match) {
        return null;
    }
    const h = match[1].toLowerCase();
    return `${h.slice(0, 8)}-${h.slice(8, 12)}-${h.slice(12, 16)}-${h.slice(16, 20)}-${h.slice(20)}`;
}

patch(PosStore.prototype, {
    async setup() {
        await super.setup(...arguments);
        // Solo la caja abre pedidos escaneados; el puesto los ignora.
        this.barcodeReader.comercioPedidoHandler = (codigo) =>
            !this.config.comercio_arma_pedidos && this.comercioAbrirPedido(codigo);
    },

    /** Puesto: sube el pedido al servidor, imprime el proforma con QR y deja la pantalla libre. */
    async comercioImprimirPedido() {
        const order = this.getOrder();
        if (!order || order.isEmpty()) {
            return;
        }
        this.addPendingOrder([order.id]);
        await this.syncAllOrders({ orders: [order], force: true, throw: true });
        const registradora = this.config.comercio_cobro_en_registradora;
        if (registradora) {
            // Se cobra en la registradora (P-046, temporal): queda cobrado en el servidor
            // (baja el stock) antes de imprimir; si falla, el pedido sigue en pantalla.
            await this.data.call("pos.order", "comercio_cobrar_en_registradora", [[order.id]]);
        } else {
            // Marcado como enviado a caja: el puesto no lo vuelve a cargar al reabrir.
            await this.data.write("pos.order", [order.id], { comercio_en_caja: true });
        }
        await this.ticketPrinter.printOrderReceipt({ order, printBillActionTriggered: true });
        this.notification.add(
            registradora
                ? _t("Pedido %s impreso: se cobra en la caja", order.pos_reference)
                : _t("Pedido %s listo para cobrar en caja", order.pos_reference),
            { type: "success" }
        );
        this.setOrder(this.getEmptyOrder());
        // Se quita solo de este navegador; en el servidor queda para la caja.
        this.removeOrder(order, false);
    },

    /** Caja: busca el pedido escaneado o tipeado y lo deja listo para cobrar. */
    async comercioAbrirPedido(entrada) {
        const texto = (entrada || "").trim();
        if (!texto) {
            return false;
        }
        const uuid = uuidDeCodigo(texto) || (UUID_RE.test(texto) ? texto : null);
        const dominio = uuid ? [["uuid", "=", uuid]] : [["pos_reference", "=", texto]];
        const pedidos = await this.data.loadServerOrders([...dominio, ["state", "=", "draft"]]);
        const pedido = pedidos[0];
        if (!pedido) {
            this.notification.add(
                _t("No se encontró un pedido pendiente de cobro con «%s». Puede que ya esté cobrado.", texto),
                { type: "warning" }
            );
            return false;
        }
        this.setOrder(pedido);
        this.navigateToOrderScreen(pedido);
        return true;
    },

    /** Caja: respaldo si el lector falla, tipear el número impreso en el ticket. */
    async comercioPedirNumeroPedido() {
        const numero = await makeAwaitable(this.dialog, TextInputPopup, {
            title: _t("Abrir pedido"),
            placeholder: _t("Número impreso en el ticket, p. ej. 2610-2-000001"),
        });
        if (numero) {
            await this.comercioAbrirPedido(numero);
        }
    },
});

patch(BarcodeReader.prototype, {
    async _scan(code) {
        if (this.comercioPedidoHandler && CODIGO_RE.test(code || "")) {
            return this.comercioPedidoHandler(code);
        }
        return super._scan(...arguments);
    },
});

patch(GeneratePrinterData.prototype, {
    generateReceiptData() {
        const data = super.generateReceiptData(...arguments);
        if (this.config.comercio_arma_pedidos && this.order.state === "draft" && this.order.uuid) {
            if (this.config.comercio_cobro_en_registradora) {
                data.conditions.comercio_pagar_en_registradora = true; // sin QR: la caja no lo abre
            } else {
                data.image.comercio_pedido_qr = this.generateQrCode(codigoDePedido(this.order.uuid));
            }
        }
        if (this.config.comercio_arma_pedidos) {
            // Ticket del puesto sin nada de IVA (ni impuestos ni subtotal sin IVA, solo el
            // total), sin CUIT y sin «Con la tecnología de Odoo».
            data.extra_data.prices.taxes = [];
            data.conditions.comercio_ticket_puesto = true;
            // Sin precio por unidad: la cantidad a la izquierda y, si se pesó, «1,250 kg»
            // debajo del nombre (con la cantidad de la izquierda vacía).
            const unitario = this.config.comercio_ticket_unitario || "no";
            this.order.lines.forEach((linea, i) => {
                const cantidad = linea.getQuantityStr().qtyStr;
                const pesada = linea.product_id.to_weight;
                const unidad = linea.product_id.uom_id?.name || "";
                data.lines[i].comercio_cantidad = pesada ? "" : cantidad;
                data.lines[i].comercio_pesada = pesada ? `${cantidad} ${unidad}`.trim() : false;
                // Precio unitario como lo muestra Odoo («$ 450,00 / Unidades», 17/11)
                data.lines[i].comercio_unitario =
                    unitario === "siempre" ||
                    (unitario === "si_suma" && (pesada || linea.getQuantity() !== 1));
            });
        }
        return data;
    },
});

// Puesto: la sincronización entre dispositivos tampoco trae los pedidos ya enviados a caja
// (la carga inicial los filtra en el servidor: pos_order._load_pos_data_domain).
patch(DevicesSynchronisation.prototype, {
    constructOrdersDomain() {
        const result = super.constructOrdersDomain(...arguments);
        const dominio = result?.domain?.["pos.order"];
        if (this.pos.config.comercio_arma_pedidos && dominio) {
            result.domain["pos.order"] = Domain.and([
                new Domain(dominio),
                new Domain([["comercio_en_caja", "=", false]]),
            ]).toList();
        }
        return result;
    },
});

// Puesto: quien atiende (aunque sea rol supervisado) puede cerrar su sesión. El puesto no
// maneja plata; el resto de los permisos (precios, descuentos, backend) sigue restringido.
// Depende de pos_hr para aplicarse después de su versión de este permiso.
// Puestos: no manejan plata, así que quien atiende (rol supervisado) puede abrir y cerrar
// la sesión del puesto. Sin esto, a la mañana veía la nota de apertura sin botón para
// abrir y «Descartar» lo sacaba del punto de venta. En las cajas se mantiene el permiso
// de Odoo (abrir: cajero o encargado; cerrar: encargado).
patch(PosAccessRightPlugin.prototype, {
    get canOpenRegister() {
        return this.config?.comercio_arma_pedidos || super.canOpenRegister;
    },
    get canCloseSession() {
        return this.config?.comercio_arma_pedidos || super.canCloseSession;
    },
});

// Caja: cobran dos cajas (P-035). Si las dos abrieron el mismo pedido, la segunda no lo
// puede cobrar (Odoo lo rechaza), pero mostraba «Importe pagado» con un error técnico.
// Antes de validar se consulta el servidor y se avisa con claridad.
patch(OrderPaymentValidation.prototype, {
    async validateOrder(isForceValidate) {
        const order = this.order;
        if (!this.pos.config.comercio_arma_pedidos && order.isSynced) {
            const estado = await this.pos.data.call("pos.order", "comercio_estado_pedido", [order.uuid]);
            if (estado && estado !== "draft") {
                this.pos.dialog.add(AlertDialog, {
                    title: _t("Pedido ya cobrado"),
                    body: _t(
                        "El pedido %s ya fue cobrado (o cancelado) en otra caja. No lo cobres de nuevo: si el cliente ya pagó, no hay nada más que hacer.",
                        order.pos_reference
                    ),
                });
                this.pos.removeOrder(order, false);
                const nueva = this.pos.getEmptyOrder();
                this.pos.setOrder(nueva);
                this.pos.navigateToOrderScreen(nueva);
                return false;
            }
        }
        return await super.validateOrder(...arguments);
    },
});
