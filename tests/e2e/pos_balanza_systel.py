"""Prueba de punta a punta del módulo comercio_pos_balanza_systel (P-040) en el laboratorio.

No hace falta la balanza: el navegador recibe una **Cuora simulada** (reemplaza
`navigator.serial`) que responde como indica el protocolo oficial de Systel
(«Protocolo de comunicaciones MAX CUORA V7», función 1). Lo que esta prueba no cubre
—el cable, el driver FT232 y la balanza real— se prueba aparte con el equipo.

Flujo verificado en el puesto:
1. El POS detecta la Cuora al abrir (115200 baudios, trama [número, 1, XOR]).
2. Producto pesable con peso **inestable**: espera, no agrega nada.
3. Peso **estable**: se agrega solo (pesaje automático), con el peso de la balanza.
4. Balanza que no responde: avisa una vez, no agrega nada y sigue esperando.
5. Cuando vuelve a responder, pesa y agrega.
6. La misma pesada dos veces seguidas se agrega igual.
7. Un error de la balanza (E1-E9) avisa una sola vez.
   «Escribir el peso»: el peso a mano se agrega sin esperar a la balanza.
8. El pedido llega al servidor con las cantidades pesadas.
10. Sin pesaje automático: el peso se ve en vivo y se agrega con Enter.

Uso: .venv/bin/python tests/e2e/pos_balanza_systel.py [carpeta_capturas]
No usar en producción: crea pedidos de prueba.
"""
import re
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from playwright.sync_api import expect, sync_playwright  # noqa: E402
from pos_pedido_qr import (  # noqa: E402
    PIN_ATENCION,
    VER,  # noqa: E402
    abrir_pos,
    asegurar_sesion,
    buscar_mas,
    forzar_qr,
    login,
    ultimo_borrador,
    xmlid,
)

from odoo_iac.client import connect  # noqa: E402
from odoo_iac.settings import load_environment  # noqa: E402

PRODUCTO = "Alimento perro suelto"  # [EJ] pesable, por kg (config/ejemplos/20-productos.yaml)

# Cuora simulada: un puerto serie falso que contesta la función 1 del protocolo.
# window.__balanza permite cambiar el peso, la estabilidad o dejarla muda.
BALANZA_SIMULADA = """
(() => {
    const balanza = { numero: 1, gramos: 0, estable: true, tara: 0, muda: false, error: "", pedidos: [] };
    window.__balanza = balanza;
    const xor = (bytes) => bytes.reduce((a, b) => a ^ b, 0);
    let salida = null;
    const puerto = {
        connected: true, readable: null, writable: null,
        async open(opciones) {
            balanza.opciones = opciones;
            this.readable = new ReadableStream({ start(c) { salida = c; } });
            this.writable = new WritableStream({ write(chunk) {
                const pedido = Array.from(chunk);
                balanza.pedidos.push(pedido);
                if (balanza.muda || pedido.length !== 3 || pedido[0] !== balanza.numero
                    || pedido[1] !== 1 || pedido[2] !== xor(pedido.slice(0, 2))) {
                    return;
                }
                const g = balanza.gramos;
                const peso = g < 0 ? "-" + String(-g).padStart(5, "0") : String(g).padStart(6, "0");
                const datos = balanza.error ||
                    peso + (balanza.estable ? "e" : "i") + String(balanza.tara).padStart(6, "0");
                const r = [balanza.numero, 1, ...Array.from(datos, (c) => c.charCodeAt(0))];
                r.push(xor(r));
                setTimeout(() => salida.enqueue(Uint8Array.from(r)), 5);
            } });
        },
        async close() { this.readable = null; this.writable = null; },
        async forget() {},
        getInfo() { return { usbVendorId: 0x0403, usbProductId: 0x6001 }; },
    };
    Object.defineProperty(navigator, "serial", { configurable: true, value: {
        getPorts: async () => [puerto], requestPort: async () => puerto,
        addEventListener() {}, removeEventListener() {},
    } });
})();
"""


def lineas(page) -> list[dict]:
    return page.evaluate(
        "posmodel.getOrder().lines.map(l => ({producto: l.product_id.display_name, qty: l.qty}))"
    )


def elegir_producto(page) -> None:
    page.fill("input[placeholder='Buscar productos...']", PRODUCTO)
    buscar_mas(page)
    page.locator("article.product").first.click()


def main() -> int:
    client = connect(load_environment("lab"))
    puesto_id = xmlid(client, "ej_pos_puesto")
    forzar_qr(client, puesto_id)
    # La balanza simulada es la número 1; el puesto puede haber quedado con el número de una
    # balanza real probada a mano (14/10: la Cuora del local, número 70). Se restaura al final.
    numero = client.read("pos.config", [puesto_id], ["comercio_balanza_numero"])[0]["comercio_balanza_numero"]
    client.write("pos.config", [puesto_id], {"comercio_balanza_numero": 1})
    try:
        return probar(client, puesto_id)
    finally:
        client.write("pos.config", [puesto_id], {"comercio_balanza_numero": numero})


def probar(client, puesto_id: int) -> int:
    out = Path(sys.argv[1] if len(sys.argv) > 1 else tempfile.mkdtemp(prefix="e2e_balanza_"))
    out.mkdir(parents=True, exist_ok=True)
    asegurar_sesion(client, puesto_id)

    with sync_playwright() as p:
        browser = p.chromium.launch(**VER)
        contexto = browser.new_context(viewport={"width": 1366, "height": 768}, locale="es-AR")
        contexto.add_init_script(BALANZA_SIMULADA)
        page = contexto.new_page()
        errores: list[str] = []
        page.on("console", lambda m: m.type == "error" and errores.append(m.text))
        login(page)
        abrir_pos(page, puesto_id, PIN_ATENCION)

        escala = page.evaluate("posmodel.scale && posmodel.scale.constructor.name")
        assert escala == "SystelCuoraScaleInterface", f"el POS no tomó la Cuora: {escala}"
        opciones = page.evaluate("window.__balanza.opciones")
        assert opciones["baudRate"] == 115200 and opciones["dataBits"] == 8, opciones
        assert page.evaluate("window.__balanza.pedidos[0]") == [1, 1, 0], "trama de pedido incorrecta"
        print("1. El POS detecta la Cuora por USB (115200 8N1, trama [1, 1, XOR]) ✓")

        if not page.evaluate("posmodel.getOrder().isEmpty()"):
            page.evaluate("posmodel.addNewOrder()")
        page.evaluate("Object.assign(window.__balanza, {gramos: 1250, estable: false})")
        elegir_producto(page)
        page.wait_for_timeout(2000)
        dialogo = page.locator(".modal .computed-price")
        expect(dialogo).to_be_visible()
        page.screenshot(path=str(out / "1_inestable.png"))
        assert lineas(page) == [], "agregó el producto con el peso inestable"
        print("2. Peso inestable: la pantalla de peso espera ✓")

        page.evaluate("window.__balanza.estable = true")
        expect(dialogo).to_have_count(0, timeout=5000)
        page.screenshot(path=str(out / "2_agregado.png"))
        assert not page.locator(".modal").count(), f"quedó un diálogo abierto: {errores}"
        agregadas = lineas(page)
        assert len(agregadas) == 1 and abs(agregadas[0]["qty"] - 1.25) < 1e-6, agregadas
        print("3. Peso estable: se agrega solo, 1,250 kg ✓")

        page.evaluate("Object.assign(window.__balanza, {gramos: 0, muda: true})")
        elegir_producto(page)
        aviso = page.locator(".modal").get_by_text("La balanza no responde")
        expect(aviso).to_be_visible(timeout=5000)
        page.wait_for_timeout(1500)
        page.screenshot(path=str(out / "3_sin_respuesta.png"))
        assert len(lineas(page)) == 1, f"agregó un producto sin peso: {lineas(page)}"
        assert page.get_by_text("La balanza no responde").count() == 1, "repite el aviso"
        page.locator(".modal").get_by_role("button", name="De acuerdo").click()
        print("4. Balanza sin respuesta: avisa una vez, no agrega nada y espera ✓")

        page.evaluate("Object.assign(window.__balanza, {gramos: 800, estable: true, muda: false})")
        expect(page.locator(".modal")).to_have_count(0, timeout=5000)
        cantidades = [round(linea["qty"], 3) for linea in lineas(page)]
        assert cantidades == [1.25, 0.8], cantidades
        page.screenshot(path=str(out / "4_recuperada.png"))
        print("5. La balanza vuelve a responder: pesa 0,800 kg y lo agrega ✓")

        # Misma pesada que la anterior («un kilo justo» dos veces): también se agrega sola
        page.evaluate("Object.assign(window.__balanza, {gramos: 800, estable: true})")
        elegir_producto(page)
        page.wait_for_function("posmodel.getOrder().lines.length === 3", timeout=8000)
        assert [round(linea["qty"], 3) for linea in lineas(page)] == [1.25, 0.8, 0.8], lineas(page)
        print("6. La misma pesada dos veces seguidas se agrega igual ✓")

        # Error de la balanza (E3): un solo aviso, no uno por lectura
        page.evaluate("Object.assign(window.__balanza, {error: 'E3'})")
        elegir_producto(page)
        page.wait_for_timeout(3000)
        avisos = page.get_by_text("Error de la balanza: E3").count()
        assert avisos == 1, f"{avisos} avisos de error"
        page.locator(".modal").get_by_role("button", name="De acuerdo").click()
        page.evaluate("Object.assign(window.__balanza, {error: '', gramos: 500})")
        page.wait_for_function("posmodel.getOrder().lines.length === 4", timeout=8000)
        print("7. Error E3 de la balanza: un solo aviso; al resolverse, pesa y agrega ✓")

        # «Escribir el peso»: con la balanza inestable, se escribe el peso a mano
        page.evaluate("Object.assign(window.__balanza, {gramos: 300, estable: false})")
        elegir_producto(page)
        page.locator(".modal button.comercio-peso-manual").click()
        page.wait_for_timeout(800)
        page.keyboard.type("2,5")
        page.screenshot(path=str(out / "5_peso_manual.png"))
        page.keyboard.press("Enter")
        page.wait_for_function("posmodel.getOrder().lines.length === 5", timeout=8000)
        expect(page.locator(".modal")).to_have_count(0, timeout=5000)
        assert round(lineas(page)[-1]["qty"], 3) == 2.5, lineas(page)
        print("7b. «Escribir el peso»: 2,5 kg a mano, sin esperar a la balanza ✓")

        page.evaluate(
            """() => { posmodel.ticketPrinter.printWithFallback = async ({ iframe }) => {
                window.__ticket = iframe.contentDocument.documentElement.outerHTML; return true; }; }"""
        )
        page.fill("input[placeholder='Buscar productos...']", "")
        page.locator("button.comercio-imprimir-pedido").click()
        page.wait_for_timeout(3000)
        pedido = ultimo_borrador(client, puesto_id)
        renglones = client.search_read("pos.order.line", [("order_id.uuid", "=", pedido["uuid"])], ["qty"])
        assert sorted(round(r["qty"], 3) for r in renglones) == [0.5, 0.8, 0.8, 1.25, 2.5], renglones
        print(f"8. Pedido {pedido['pos_reference']} en el servidor con todas las pesadas ✓")
        ticket = page.evaluate("window.__ticket || ''")
        texto = re.sub(r"\s+", " ", re.sub(r"<style.*?</style>|<[^>]+>", " ", ticket, flags=re.S))
        assert "1,25 kg" in texto and "0,80 kg" in texto, f"el ticket no muestra lo pesado: {texto}"
        assert "/ kg" not in ticket, "el ticket del puesto muestra el precio por kilo"
        print("9. Ticket: cada pesada con sus kilos («1,25 kg»), sin precio por kilo ✓")

        # Sin pesaje automático: peso en vivo, se agrega solo con Enter (ir sumando hasta el peso pedido)
        client.write("pos.config", [puesto_id], {"comercio_pesaje_automatico": False})
        try:
            page.reload()
            abrir_pos(page, puesto_id, PIN_ATENCION)
            if not page.evaluate("posmodel.getOrder().isEmpty()"):
                page.evaluate("posmodel.addNewOrder()")
            page.evaluate("Object.assign(window.__balanza, {gramos: 400, estable: true})")
            elegir_producto(page)
            neto = page.locator(".modal").get_by_text("0,40 kg")
            expect(neto).to_be_visible(timeout=5000)
            page.wait_for_timeout(2000)
            assert lineas(page) == [], f"agregó solo sin pesaje automático: {lineas(page)}"
            page.evaluate("window.__balanza.gramos = 650")
            expect(page.locator(".modal").get_by_text("0,65 kg")).to_be_visible(timeout=5000)
            page.screenshot(path=str(out / "6_en_vivo.png"))
            page.keyboard.press("Enter")
            page.wait_for_function("posmodel.getOrder().lines.length === 1", timeout=8000)
            expect(page.locator(".modal")).to_have_count(0, timeout=5000)
            assert round(lineas(page)[0]["qty"], 3) == 0.65, lineas(page)
            print("10. Sin pesaje automático: el peso se ve en vivo (0,40 → 0,65 kg) y se agrega con Enter ✓")
        finally:
            client.write("pos.config", [puesto_id], {"comercio_pesaje_automatico": True})
        browser.close()

    print(f"Todo OK. Capturas en {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
