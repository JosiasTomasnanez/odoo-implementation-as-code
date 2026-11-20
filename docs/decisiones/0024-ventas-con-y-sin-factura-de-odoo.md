# 0024. Ventas de la caja con y sin factura de Odoo, mientras siguen las registradoras

- Estado: aceptado en el lab (pedido del implementador, 24/10); el uso real depende de adelantar la
  caja de Odoo y de la administración (ADR 0017, P-002, P-029)
- Fecha: 2026-10-24

## Contexto

Las 2 registradoras (puntos de venta 8 y 13) y 3C (punto de venta 12) van a seguir emitiendo los
comprobantes fiscales un tiempo, a la vez que Odoo. Se quiere registrar **todas** las ventas en
Odoo y pasar de a poco algunas a la factura de Odoo, para que el cambio no sea brusco.

El contador necesita lo de Odoo y lo de las registradoras **por separado, sin que se pisen**:

- el Libro IVA Ventas;
- el detalle de compras;
- los archivos TXT del Libro IVA Digital que se cargan en ARCA.

Si una venta de la registradora estuviera también en el libro de Odoo, el IVA se informaría dos
veces.

## Decisión

- **En la caja, el botón «Factura» que ya trae Odoo**, marcado por defecto (la localización
  argentina lo marca). Se renombra «Factura» (Odoo lo traducía «Recibo/Factura»).
  - **Marcado:** Odoo factura en el momento, con CAE, en el diario de factura electrónica.
  - **Desmarcado:** la venta queda en Odoo (stock, caja, contabilidad) **sin factura de Odoo**; el
    comprobante lo emite la registradora o 3C.
  - Lo único que cambia en pantalla es una **franja de color al costado** de la pantalla de pago,
    sin carteles ni leyendas (pedido del implementador: que no sea vistoso; 26/10 reemplazó al
    importe en gris, que no le gustaba en el precio). El ticket no agrega texto.
- **Por detrás, separado:**
  - El Libro IVA de Odoo (`l10n_ar_reports`, con su exportación ZIP de TXT para ARCA) toma solo
    los comprobantes con documento fiscal. Verificado en el código: dominio
    `l10n_latam_use_documents`. Las ventas sin factura de Odoo quedan afuera solas.
  - Campo `pos.order.comercio_factura_odoo` (con factura de Odoo con comprobante, confirmada).
  - En los pedidos del punto de venta, filtros «Con / Sin factura de Odoo» y el listado
    *Punto de venta → Órdenes → **Ventas sin factura de Odoo***, agrupado por día y caja, con
    totales. Es el «lado registradora», para controlar contra el resumen diario de cada
    registradora y para el contador.
- **Facturar después con CAE** (24/10): para lo que se cobró sin factura por error y no se hizo en la
  registradora. Es el botón **«Facturar con CAE»** (solo el grupo Facturación), en la venta o con
  varias marcadas en la lista, y siempre usa el diario de factura electrónica.
  - Si la venta es de otro día, la factura sale con fecha de hoy: ARCA no acepta una fecha anterior a la
    última que autorizó.
  - El «Factura» de Odoo en el pedido y el «Crear facturas» de la lista se ocultan: usa el diario del punto de venta, y en un puesto (o
    cualquier punto de venta con diario no fiscal) hacía un comprobante interno «pagado» sin CAE.
  - Si la venta ya tenía ese comprobante interno, pasa al diario electrónico y se confirma (pide CAE),
    sin tocar el cobro.
  - Si la caja ya cerró, Odoo saca la venta del asiento del cierre, para que no cuente dos veces.
- **Compras:** lo equivalente ya existe con el diario «Compras sin factura» (ADR 0023): no va al
  Libro IVA Compras.
- **Lab:** `make lab-arca` deja Caja 1 y Caja 2 facturando con el diario electrónico de
  homologación. Las cajas de ejemplo de las pruebas no dependen de ARCA.

## Límite

«Sin factura de Odoo» significa que **la factura la hace la registradora o 3C**, no que la venta no
lleve comprobante. Lo confirmó el implementador: no quedan ventas sin facturar. No se implementa
nada para ocultar ventas: todas quedan registradas en Odoo y el listado de las que no facturó Odoo
sirve justamente para controlarlas.

## Consecuencias

- Mientras dure la transición, una venta «sin factura de Odoo» se registra dos veces a mano: en
  Odoo y en la registradora. Es trabajo extra en la caja; se conversa con la administración antes
  de usarlo (P-046).
- Si ARCA no responde, la venta con «Factura» marcado no se cierra (P-029); desmarcado, sigue por
  la registradora.
- En producción, las cajas facturan con el punto de venta RECE nuevo (P-002); hoy la primera etapa
  no tiene caja de Odoo (ADR 0017).
- Uso: `docs/runbooks/ventas-con-y-sin-factura.md`. Validar con `make e2e-pos` (`tests/e2e/pos_factura.py`). La venta con CAE se prueba a mano en
  Caja 1 o 2 después de `make lab-arca`.
