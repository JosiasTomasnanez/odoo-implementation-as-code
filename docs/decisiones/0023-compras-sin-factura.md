# 0023. Compras sin factura en un diario aparte

- Estado: aceptado (pedido del implementador para la puesta en marcha, 23/10)
- Fecha: 2026-10-23

## Contexto

Hoy muchas compras se pagan sin tener la factura real del proveedor. A veces el proveedor manda
un presupuesto, un remito valorizado o una nota de pedido, y la factura llega después o la
recibe la administración. Si en Odoo solo se pudiera registrar la factura real, esas compras
quedarían afuera: no se podrían pagar ni controlar contra la orden y la recepción.

Para que el cambio no sea brusco se las registra y se las paga como «sin factura»; la real la
carga después la administración.

## Decisión

- **Un diario de compras propio, «Compras sin factura»** (código `PROV`,
  `config/onpremise/54-compras-sin-factura.yaml`; el nombre está en `config/valores.yaml`).
  - **No usa documentos fiscales** (`l10n_latam_use_documents: false`): no hay tipo ni número
    de comprobante, no va al libro IVA y no da crédito fiscal.
  - Se marca con la casilla `comercio_sin_factura` del diario.
- **Sin IVA.** El módulo `comercio_factura_proveedor` saca los impuestos de las líneas de ese
  diario: al crearlas, al elegir el producto y al pasar la factura a ese diario. Al confirmar,
  no deja pasar líneas con impuestos.
  - Si el papel cobra IVA o percepciones, van como líneas comunes («IVA cobrado por el proveedor
    (sin crédito fiscal)»). Son costo de la compra, y el total da lo que se paga.
- **Cómo se carga:**
  - el botón **«Sin factura»** en la orden de compra (lo recibido, a los precios de la orden);
  - el menú *Compras → Órdenes → **Compras sin factura***, donde «Nuevo» y «Subir» van a ese
    diario. El papel se lee igual que una factura.
- Se paga, se concilia y entra en el control pedido ↔ recibido ↔ facturado («Se debe pagar»)
  como cualquier factura.
- En el listado hay filtros «Sin factura» y «Con factura», y cada una lleva un cartel azul.

## Cuando llega la factura real

Por ahora se hace a mano (decidido 23/10): la administración carga la factura real como siempre
y anula la compra sin factura, para que no quede dos veces. Cómo se contabiliza lo que todavía no
tiene factura (cuenta, cierre de mes) lo confirma el contador (P-034).

## Consecuencias

- Las compras sin factura quedan registradas, con su pago y su stock, en vez de quedar fuera de
  Odoo.
- Riesgo: que nunca se cargue la factura real. El filtro «Sin factura» muestra las que quedan.
- No sirve para ocultar compras ni ventas: registra compras reales que de otra forma no
  estarían en el sistema.
