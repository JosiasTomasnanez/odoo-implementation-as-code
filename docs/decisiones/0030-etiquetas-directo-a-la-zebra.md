# 0030. Etiquetas directo a la Zebra con la IoT de Odoo y una etiqueta ZPL propia

- Estado: propuesto (pedido del cliente, 30/10; P-062). Falta probarlo en la PC Windows del local
- Fecha: 2026-10-30

## Contexto

La Zebra ZD420 (203 dpi, ZPL) funciona (28/10), pero «Imprimir etiquetas» de Odoo descarga un
archivo (PDF o `.zpl`) que después hay que mandar a la impresora: Odoo sin IoT no imprime en
una impresora USB. Además, la etiqueta ZPL de Odoo corta el nombre en una línea con letra fija
y el código de barras sale ancho: en un rollo más chico que 57 × 32 mm queda cortado y el
lector no lo lee.

Lo que trae Odoo 20 (verificado en el código):

- **IoT (Enterprise, módulo `iot`)**: la «IoT de Windows» se descarga desde Odoo, se instala en
  la PC con la impresora y queda emparejada. Cualquier informe vinculado a esa impresora se
  imprime directo (`iot/models/ir_actions_report.py`); el driver de Windows manda el ZPL en
  crudo a una impresora Zebra instalada.
- **`printer` (Community, nuevo en 20)**: manda ZPL a una impresora **por red** (`http://IP/pstprnt`);
  la ZD420 del local es USB, y desde una página HTTPS el navegador bloquea un `http://`.
- Nada para USB desde el navegador sin IoT.

## Decisión

- **Imprimir con la IoT de Windows** (nativa, incluida en el plan Custom): se instala `iot`
  (`config/onpremise/00-modulos.yaml`), se baja e instala la IoT en la PC Windows donde esté la
  Zebra (con su driver ZDesigner) y se vincula la etiqueta ZPL a esa impresora
  (`docs/runbooks/etiquetas-zebra.md`).
- **Etiqueta ZPL propia** (módulo `comercio_etiquetas`): plantilla «Comercio Ejemplo» en el
  asistente de Odoo, con el nombre en hasta dos líneas, Code 128 en modo automático (los números
  van de a pares: la mitad de ancho), referencia y precio. La **medida del rollo** va en
  `config/valores.yaml` (`etiquetas`) y la etiqueta se acomoda a ella.

## Consecuencias

- Hay que probarlo en el local: emparejar la IoT por HTTPS (`odoo.comercio-ejemplo.example`), que la PC
  quede prendida y que la IoT detecte la Zebra. Falta medir el rollo (P-062).
- La IoT de Windows es un programa más en esa PC (servicio de Windows); se documenta su
  reinstalación.
- Si la IoT no funciona con el plan o con HTTPS, la alternativa es un módulo propio que mande el
  ZPL por WebUSB desde Chrome (como la balanza con WebSerial, ADR 0012), con otro ADR.

## Alternativas descartadas

- **Placa de red en la Zebra + módulo `printer`:** hardware extra y el bloqueo de `http://`
  desde HTTPS.
- **Seguir descargando el PDF:** es lo que el cliente pidió cambiar (y en Linux el visor elegía
  mal el papel, 28/10).
