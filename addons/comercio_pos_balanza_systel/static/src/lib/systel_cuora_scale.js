/**
 * Balanza Systel Cuora Max por USB (WebSerial).
 *
 * Protocolo oficial «Protocolo de comunicaciones MAX CUORA V7» (Systel):
 * - Pedido PC → balanza: [número de balanza][función][datos ASCII][XOR de los anteriores].
 * - Respuesta: misma estructura. El fin de trama se detecta por silencio (~5 ms).
 * - Función 1 (peso, estabilidad y tara): sin datos; responde peso neto en gramos
 *   (6 dígitos, o «-» y 5 dígitos), «e» (estable) o «i» (inestable) y la tara en gramos.
 * - Errores: datos «E1»…«E9».
 * El USB de la balanza es un conversor serie FT232 (115200 baudios, 8 bits).
 */
import { _t } from "@web/core/l10n/translation";
import { WebSerialDevice } from "@iot_webserial/web_serial_device";

const FUNCION_PESO = 1;
// número + función + 13 datos + XOR
const LARGO_RESPUESTA_PESO = 16;
const ESPERA_RESPUESTA_MS = 600;  // la lectura termina apenas llega la trama: no agrega demora
const PESO_RE = /^(-\d{5}|\d{6})([ei])(\d{6})$/;
const ERROR_RE = /^E\d$/;

/** @param {number[]} bytes */
export function xor(bytes) {
    return bytes.reduce((acumulado, byte) => acumulado ^ byte, 0);
}

/**
 * Arma la trama de un pedido a la balanza.
 * @param {number} numero número de la balanza (1 a 99)
 * @param {number} funcion
 * @param {string} [datos]
 */
export function armarPedido(numero, funcion, datos = "") {
    const bytes = [numero, funcion, ...Array.from(datos, (c) => c.charCodeAt(0))];
    return Uint8Array.from([...bytes, xor(bytes)]);
}

/**
 * Busca en lo recibido una respuesta válida a la función 1.
 * @param {number[]} recibido bytes leídos del puerto (puede traer restos anteriores)
 * @param {number} numero
 * @returns {{gramos: number, estable: boolean, taraGramos: number} | {error: string} | null}
 */
export function leerRespuestaPeso(recibido, numero) {
    for (let inicio = 0; inicio < recibido.length - 2; inicio++) {
        if (recibido[inicio] !== numero || recibido[inicio + 1] !== FUNCION_PESO) {
            continue;
        }
        for (const largo of [LARGO_RESPUESTA_PESO, 5]) {
            const trama = recibido.slice(inicio, inicio + largo);
            if (trama.length !== largo || xor(trama.slice(0, -1)) !== trama.at(-1)) {
                continue;
            }
            const datos = String.fromCharCode(...trama.slice(2, -1));
            const peso = PESO_RE.exec(datos);
            if (peso) {
                return {
                    gramos: parseInt(peso[1], 10),
                    estable: peso[2] === "e",
                    taraGramos: parseInt(peso[3], 10),
                };
            }
            if (ERROR_RE.test(datos)) {
                return { error: datos };
            }
        }
    }
    return null;
}

export class SystelCuoraScale extends WebSerialDevice {
    /**
     * @param {import("@iot_webserial/web_serial_device").SerialPort} serialPort
     * @param {number} [numero] número de la balanza configurado en su menú
     */
    constructor(serialPort, numero = 1) {
        super(serialPort);
        this.numero = numero;
    }

    get serialPortOptions() {
        return { baudRate: 115200, dataBits: 8, parity: "none", stopBits: 1 };
    }

    /** Es una Cuora si responde a la función 1 (aunque sea con un error). */
    async supported() {
        try {
            return Boolean(await this.leerPeso());
        } catch {
            return false;
        }
    }

    /** @param {Uint8Array} bytes */
    async escribir(bytes) {
        if (!this._serialPort.writable) {
            throw new Error(_t("The device has been disconnected"));
        }
        const writer = this._serialPort.writable.getWriter();
        try {
            await writer.write(bytes);
        } finally {
            writer.releaseLock();
        }
    }

    /**
     * Lee hasta obtener una respuesta válida o hasta que pase el tiempo de espera.
     * @returns {Promise<ReturnType<typeof leerRespuestaPeso>>}
     */
    async leerHastaRespuesta() {
        if (!this._serialPort.readable) {
            throw new Error(_t("The device has been disconnected"));
        }
        const reader = this._serialPort.readable.getReader();
        const recibido = [];
        // Liberar el lector corta la lectura pendiente (mismo criterio que WebSerialDevice)
        const espera = setTimeout(() => reader.releaseLock(), ESPERA_RESPUESTA_MS);
        try {
            while (true) {
                const { value, done } = await reader.read();
                if (done) {
                    break;
                }
                recibido.push(...value);
                const respuesta = leerRespuestaPeso(recibido, this.numero);
                if (respuesta) {
                    return respuesta;
                }
            }
        } catch {
            // Tiempo de espera agotado: se devuelve lo que haya.
        } finally {
            clearTimeout(espera);
            reader.releaseLock();
        }
        return leerRespuestaPeso(recibido, this.numero);
    }

    /** Pide el peso (función 1). Devuelve null si la balanza no responde. */
    async leerPeso() {
        await this.escribir(armarPedido(this.numero, FUNCION_PESO));
        return this.leerHastaRespuesta();
    }
}

/**
 * Abre la primera balanza Cuora entre los puertos ya autorizados en este navegador.
 * @param {number} numero
 * @returns {Promise<SystelCuoraScale | null>}
 */
export async function abrirBalanzaSystel(numero) {
    if (!navigator.serial) {
        return null;
    }
    const puertos = (await navigator.serial.getPorts()).filter((puerto) => puerto.connected);
    for (const puerto of puertos) {
        const balanza = new SystelCuoraScale(puerto, numero);
        try {
            if (await balanza.open()) {
                return balanza;
            }
        } catch {
            // Puerto ocupado o desconectado: se prueba el siguiente.
        }
    }
    return null;
}
