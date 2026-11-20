/** Ajustes del POS: autorizar en esta computadora el puerto USB de la balanza Systel. */
import { Component, signal, usePlugin, useProps } from "@odoo/owl";
import { _t } from "@web/core/l10n/translation";
import { NotificationPlugin } from "@web/core/notifications/notification_plugin";
import { registry } from "@web/core/registry";
import { standardWidgetProps } from "@web/views/widgets/standard_widget_props";
import { SystelCuoraScale } from "@comercio_pos_balanza_systel/lib/systel_cuora_scale";

export class ConectarBalanzaSystel extends Component {
    static template = "comercio_pos_balanza_systel.ConectarBalanzaSystel";

    props = useProps(standardWidgetProps);

    setup() {
        this.notification = usePlugin(NotificationPlugin);
        this.cargando = signal(false);
    }

    avisar(mensaje, tipo) {
        this.notification.add(mensaje, { type: tipo });
    }

    async onClick() {
        if (!window.isSecureContext) {
            this.avisar(_t("Para conectar la balanza hay que entrar a Odoo por HTTPS."), "danger");
            return;
        }
        if (!navigator.serial) {
            this.avisar(_t("Este navegador no permite conectar la balanza: usar Chrome o Edge."), "danger");
            return;
        }
        this.cargando.set(true);
        try {
            await this.conectar();
        } finally {
            this.cargando.set(false);
        }
    }

    async conectar() {
        let puerto;
        try {
            puerto = await navigator.serial.requestPort();
        } catch {
            this.avisar(_t("No se eligió ningún dispositivo."), "warning");
            return;
        }
        const numero = this.props.record.data.pos_comercio_balanza_numero || 1;
        const balanza = new SystelCuoraScale(puerto, numero);
        try {
            if (await balanza.open()) {
                const peso = await balanza.leerPeso();
                await balanza.close();
                const detalle = peso && !peso.error ? ` (${peso.gramos} g)` : "";
                this.avisar(
                    _t("Balanza conectada%s. Volver a abrir el POS en esta computadora.", detalle),
                    "success"
                );
            } else {
                this.avisar(
                    _t("La balanza número %s no respondió en ese puerto. Revisar el número configurado en la balanza.", numero),
                    "danger"
                );
            }
        } catch {
            this.avisar(_t("No se pudo abrir el puerto (¿lo está usando otro programa, como Qendra?)."), "danger");
        }
    }
}

registry.category("view_widgets").add("comercio_pos_balanza_systel.conectar", {
    component: ConectarBalanzaSystel,
});
