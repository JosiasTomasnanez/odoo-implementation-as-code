# Runbook: probar la balanza Systel real

Objetivo: confirmar con una Cuora de verdad lo que ya pasa con la balanza simulada
(`make e2e-pos`, ADR 0012). Tiempo estimado: 30 minutos con la balanza en la mano.

## ¿Hace falta HTTPS?

**No para esta prueba**, si la balanza se enchufa a la notebook que corre el lab y se
abre Odoo en `http://localhost:8069`: Chrome considera seguro a `localhost`.

Solo hace falta si el POS se abre **desde otra PC** (p. ej. una PC del local apuntando a
la notebook). Para una prueba puntual alcanza, en esa PC, con
`chrome://flags/#unsafely-treat-insecure-origin-as-secure` → agregar
`http://<IP de la notebook>:8069` → reiniciar Chrome. En producción va HTTPS real (P-012).

## Dejar listo antes (una vez)

- [ ] `sudo usermod -aG dialout $USER` y cerrar y abrir la sesión (sin esto, ni el
      diagnóstico ni Chrome pueden abrir el USB). Comprobar con `id` que aparece `dialout`.
- [ ] `.venv/bin/pip install -e '.[balanza]'` (pyserial para el diagnóstico).
- [ ] Lab al día y probado: `make lab-up`, `make apply`, `make e2e-pos`.
- [ ] Llevar un cable **USB A-B** (el común de impresora): la balanza tiene un USB-B abajo
      (foto del 10/10). Por las dudas, uno de repuesto.

## En el local, con la balanza

1. **Datos de la placa**: código de modelo (CM15…/CM30… = Cuora Max; «Neo» = no sirve
   este camino) y qué conector tiene abajo (USB, Ethernet o WiFi). Foto de la placa.
   Si no tiene placa visible (09/10 no se vio), identificarla por el frente: «cuora Max»
   con íconos o «cuora» con teclas «+V1…+V4». **Probar al menos una de cada frente**: el
   diagnóstico prueba solo velocidades, paridades y números, así que alcanza con
   enchufarla y correrlo.
2. **Número de balanza**: menú USUARIO → clave → 11. Config. equipo → 3. Conectividad →
   1. Identificación. Anotar el número (hace falta la clave de supervisor; pedírsela a Daniel).
   No cambiarlo si Qendra la usa.
3. Cerrar **Qendra** si está abierto en la PC a la que está conectada (no comparten el puerto).
4. Enchufar la balanza a la notebook y correr el diagnóstico:

   ```bash
   .venv/bin/python integrations/balanza_systel/diagnostico.py
   ```

   Tiene que decir «✓ Balanza encontrada» y mostrar el peso al poner algo en la bandeja.
   Si encuentra otros parámetros que no sean 115200 8N1, avisa: hay que cambiarlos en
   `addons/comercio_pos_balanza_systel/static/src/lib/systel_cuora_scale.js`.
5. **En Odoo** (lab, Chrome, `localhost:8069`): Ajustes → Punto de venta → elegir el
   puesto → «Número de la balanza Systel» con el número del paso 2 → Guardar →
   «Conectar balanza Systel» → elegir el puerto (FT232). Tiene que avisar «Balanza conectada (N g)».
6. Abrir el POS del puesto, elegir el producto pesable de ejemplo y poner peso en la
   bandeja: tiene que entrar solo cuando el peso se estabiliza. Probar también:
   tara hecha en la balanza, desenchufar el cable con la pantalla de peso abierta
   (avisa y no agrega nada) y volver a enchufar.
7. Comparar el importe del POS con el de la balanza para el mismo peso.

## Si Odoo dice que la balanza no respondió

Visto el 14/10 en Linux: si antes se usó un programa con pyserial (p. ej. una versión
vieja del diagnóstico), el puerto queda con `min = 0` y Chrome toma la balanza como
desconectada. Comprobar con `stty -F /dev/ttyUSB0 -a` y arreglar con
`stty -F /dev/ttyUSB0 min 1 time 0`. El diagnóstico actual lo restaura solo al terminar.
Usar **Chrome o Edge**: Firefox no tiene WebSerial.

## Registrar

Resultado, modelo, conector, número y parámetros en `docs/relevamiento/hardware.md`,
P-040 y la bitácora de la guía. Si algo falla, guardar la salida del diagnóstico.
