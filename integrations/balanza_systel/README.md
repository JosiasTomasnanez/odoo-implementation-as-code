# Balanza Systel Cuora: diagnóstico por USB

`diagnostico.py` busca una Systel Cuora en los puertos USB, prueba velocidades,
paridades y números de balanza, y muestra la firma del equipo y el peso en vivo. No
usa Odoo ni modifica la balanza: sirve para confirmar los parámetros del módulo
`comercio_pos_balanza_systel` (ADR 0012) con el equipo real.

- **Hardware:** Cuora Max (o Cuora 2) con USB: conversor FTDI FT232 (Linux `ftdi_sio`,
  `/dev/ttyUSB*`; Windows: driver FTDI, puerto COM).
- **Protocolo:** «Protocolo de comunicaciones MAX CUORA V7» (Systel), funciones 1
  (peso, estabilidad y tara) y 2 (firma digital).
- **Dependencias:** `pip install -e '.[balanza]'` (pyserial). En Linux, el usuario en el
  grupo `dialout`.
- **Limitaciones:** no sirve para la Cuora Neo ni para balanzas conectadas por
  Ethernet/WiFi. No puede usar el puerto si Qendra lo tiene abierto.

Paso a paso de la prueba: `docs/runbooks/prueba-balanza-real.md`.
