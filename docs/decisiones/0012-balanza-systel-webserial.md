# 0012. Balanza Systel Cuora leída desde el navegador (WebSerial), sin IoT

- Estado: aceptado (probado con balanza simulada; falta probar con el equipo real)
- Fecha: 2026-10-08

## Contexto

El local tiene 8 balanzas **Systel Cuora** en los puestos. Hoy imprimen un ticket por
ítem. El negocio quiere que el puesto tome el peso directo, sin tickets (P-040).

- Odoo 20 lee balanzas por USB desde Chrome/Edge (**WebSerial**, Community) o con el
  **IoT** (Enterprise), pero en los dos casos solo con el protocolo **Toledo 8217**.
- La Cuora Max tiene un protocolo propio, oficial y documentado («Protocolo de
  comunicaciones MAX CUORA V7»): por USB (conversor FT232, puerto COM) la PC manda
  `[número][1][XOR]` y la balanza responde peso neto en gramos, estable/inestable y tara.
  No emula Toledo.

## Decisión

Módulo propio `comercio_pos_balanza_systel` (solo On-Premise) que:

- registra una balanza «Systel Cuora» en el POS (WebSerial), con prioridad sobre la
  estándar;
- pesa en forma **automática**: al elegir un producto pesable, lo agrega solo cuando
  el peso queda estable (dos lecturas iguales);
- si la balanza no responde, avisa una vez y **no agrega nada** (el POS estándar
  agregaría el producto con cantidad 1);
- en Ajustes del POS: número de la balanza, pesaje automático y botón «Conectar
  balanza Systel» (se autoriza el puerto una vez por computadora).

Se valida con `make e2e-pos` (`tests/e2e/pos_balanza_systel.py`), que simula la Cuora
según el protocolo oficial.

## Alternativas consideradas

- **IoT de Windows en cada PC + driver propio:** vía oficial, pero 8 instalaciones que
  mantener, certificado emitido por odoo.com y un mecanismo de drivers propios que no
  se pudo verificar en Odoo 20. Queda como alternativa si WebSerial falla.
- **Servicio propio en cada PC:** reinventa el IoT, con el mismo costo de mantenimiento.
- **Etiqueta con código de barras impresa por la balanza:** funciona sin código, pero
  mantiene el ticket por ítem que se quiere evitar.

## Consecuencias

- Requiere **HTTPS válido** en el servidor (P-012) y Chrome o Edge en los puestos
  (en el lab alcanza `localhost`).
- Solo sirve para la **Cuora Max con USB** (o Cuora 2). Con Ethernet/WiFi el navegador
  no puede hablarle directo; con Cuora Neo no hay protocolo de peso publicado.
- Falta probar con una balanza real: cable, driver FT232 en Windows, número de balanza
  y paridad (el ejemplo oficial usa 115200, 8 bits; se asume sin paridad).
- Riesgo legal a consultar: si el POS puede calcular el importe a partir del peso
  (Res. SIC 25/2025, OIML R76; P-040).
- Qendra y el POS no pueden usar el mismo puerto USB a la vez.
