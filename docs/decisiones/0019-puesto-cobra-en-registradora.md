# 0019. El puesto da el pedido por cobrado al imprimirlo (temporal, mientras cobran las registradoras)

- Estado: aceptado (temporal: hasta que la caja cobre en Odoo)
- Fecha: 2026-10-21

## Contexto

En la primera etapa (ADR 0017) las registradoras cobran y Odoo no. El stock de una venta
del POS baja cuando el pedido **se valida**, así que el pedido del puesto (ADR 0009) nunca
bajaba el stock (P-046). El negocio no quiere sumar trabajo en la caja.

## Decisión

Opción B de ADR 0017: en los puestos, **«Imprimir pedido» además da el pedido por
cobrado** con un medio de pago propio, **«Cobrado en registradora»** (diario tipo banco
`REGI`, separado del resto), sin pedir medio de pago. El ticket sale igual, como proforma
y **sin QR** («Presentar en caja para pagar» y el número). El stock baja en el momento.

Es una **opción por puesto** (`pos.config.comercio_cobro_en_registradora`, módulo
`comercio_pos_pedido_qr` 20.0.1.6.0) que se prende desde `config/valores.yaml`
(`puestos_cobran_en_registradora`). El flujo del QR que abre y cobra la caja de Odoo
**no se borra**: con `false` y `make apply` vuelve tal cual (para cuando la caja cobre).

## Alternativas consideradas

- **A. «Caja liviana» en la cabina** (la cajera escanea el QR y valida): solo baja lo que
  se pagó, pero suma un paso en la caja y hace falta PC y lector ahí. Descartada por ahora.
- **C. Ajustar el stock con recuentos:** pierde el sentido de controlar stock.

## Consecuencias

- Baja el stock de lo que se imprimió, aunque el cliente después no pague o cambie de idea.
  Si pide otra cosa, es **otro ticket**. Lo que no se llevó se corrige con una devolución
  del pedido o con los recuentos; cuánto pasa en la práctica se mira en los primeros días.
- Las ventas quedan en Odoo con «Cobrado en registradora»: sirven para stock y reportes
  internos, **no son la contabilidad fiscal** (los comprobantes siguen siendo los de la
  registradora y 3C). El diario `REGI` se revisa o reclasifica cuando entre lo fiscal.
- El cierre nocturno de los puestos sigue igual: cierran solos (no hay efectivo que contar).
- Validación: `make e2e-pos` (`tests/e2e/pos_cobro_registradora.py`; las pruebas del QR
  apagan la opción mientras corren).
