# 0017. Primera etapa: solo alimento para animales, sin caja ni facturación en Odoo

- Estado: aceptado (alcance) · el registro de la venta: opción B, temporal (ADR 0019, 21/10) · rubro reemplazado por ADR 0022 (ferretería, 23/10)
- Fecha: 2026-10-19

## Contexto

El plan hasta el 14/10 arrancaba con puestos, **cajas que cobran y facturan en Odoo**
(factura electrónica con CAE) y stock de alimentos. El 19/10 el negocio pidió restringir
mucho más la primera etapa (`docs/relevamiento/charla-19-10.md`):

- no quieren todavía **nada fiscal** ni **cobrar en Odoo**: las 2 registradoras (Sam4s,
  punto de venta 8; Hasar, punto de venta 13) siguen cobrando y emitiendo el ticket;
- solo **alimento para animales**;
- solo **stock, compras, inventario y puestos que arman el pedido e imprimen el ticket**
  para pagar en la registradora, con códigos de barras, balanza y lectores.

Coincide con el principio de adopción gradual (CLAUDE.md).

## Decisión

La primera etapa en el local incluye:

1. Productos de **alimento para animales** (categorías con stock, `catalogo.categorias_con_stock`),
   con códigos de barras, código propio `20…` y etiquetas (`docs/areas/codigos.md`).
2. **Compras** a proveedores de alimento y **recepción** que suma stock; listas de
   proveedores y costos (ADR 0015).
3. **Inventario**: inventario inicial y recuentos.
4. **Puestos** del POS que arman el pedido (lector y balanza Systel, ADR 0012) e imprimen
   el ticket con QR (ADR 0009) que se paga en la registradora.

Queda **fuera** de la primera etapa:

- cobrar en Odoo, medios de pago, cierre de caja y arqueo;
- factura electrónica, punto de venta RECE, certificado, Libro IVA;
- conciliación bancaria y de tarjetas (P-045);
- los demás rubros (ferretería, veterinaria, etc.), mayoristas y ecommerce.

Lo ya hecho para esas partes **no se borra**: queda probado en el lab para la etapa
siguiente (`make e2e-factura`, `make e2e-pos`).

## Cómo se descuenta el stock (P-046) — decidido 21/10, temporal: opción B (ADR 0019)

En Odoo el stock de una venta del POS se descuenta cuando el pedido **se valida**. Si la
caja no cobra en Odoo, el pedido del puesto nunca se valida y el stock no baja. Opciones:

- **A. «Caja liviana» en la cabina (propuesta):** la cajera escanea el QR del ticket en
  Odoo y valida con un único medio de pago «Cobrado en registradora» (sin factura, sin
  manejo de dinero); después cobra en la registradora como hoy. Reusa `comercio_pos_pedido_qr`
  casi sin cambios. Solo baja el stock de lo que se pagó. Requiere PC y lector en la
  cabina, y un paso más para la cajera (un escaneo).
- **B. El puesto valida al imprimir:** el pedido se da por vendido al imprimir el ticket.
  No hace falta nada en la cabina, pero si el cliente no paga (se arrepiente, se va), el
  stock baja igual y hay que anular a mano.
- **C. Descontar por ajuste periódico:** el stock se corrige con recuentos. Descartada:
  pierde el sentido de controlar stock.

Además: si el cliente lleva alimento y productos de otros rubros, ¿el puesto los pone en
el mismo ticket (productos genéricos por rubro) o solo el alimento? Y el ticket podría
mostrar **subtotales por rubro** para que la cajera los tipee en la registradora.

## Alternativas consideradas

- Mantener el plan anterior (cajas facturando desde la puesta en marcha): descartado por
  el negocio; además depende del contador, del certificado y de la contingencia sin ARCA
  (P-029).

## Consecuencias

- La puesta en marcha deja de depender de lo fiscal (P-002, P-029, P-034) y del posnet
  (P-016): esos pendientes bajan de prioridad.
- La contabilidad de Odoo igual registra las ventas del POS y las compras (asientos
  internos), pero **no es la contabilidad fiscal** mientras la registradora y 3C sigan
  siendo los comprobantes válidos. Las facturas de proveedor en Odoo quedan a definir
  (P-047).
- En el futuro, al facturar desde Odoo: un solo punto de venta RECE para las 2 cajas
  (respuesta del 19/10); las dos pueden facturar a la vez (ver relevamiento).
- La regla de la «última caja» (ADR 0009) sigue valiendo si se elige la opción A.
