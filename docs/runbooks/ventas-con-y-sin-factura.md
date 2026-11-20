# Caja: ventas con y sin factura de Odoo

Mientras se sigan usando las registradoras (ADR 0024).

## En la caja

1. Se arma la venta y se toca **Pago**.
2. El botón **Factura** viene **marcado**: Odoo hace la factura (con CAE).
3. Si esa venta la factura la **registradora** (o 3C): se toca **Factura** para desmarcarlo. El
   costado de la pantalla aparece una **franja de color**: así se nota que esta venta no la factura Odoo. Se cobra igual, y el
   comprobante se hace en la registradora.

Si al volver a la pantalla de pago aparece marcado otra vez, es lo normal: siempre arranca marcado.

## Se cobró sin factura por error (y no se hizo en la registradora)

Lo arregla la administración:

1. Entrar a *Punto de venta → Órdenes → **Ventas sin factura de Odoo***.
2. Abrir la venta y tocar **Facturar con CAE**. Si son varias: marcarlas en la lista y tocar
   **Facturar con CAE** arriba.
3. Confirmar la pregunta. Sale la factura con CAE, la venta queda cobrada igual y sale de la lista.

**Solo si de verdad no se hizo el ticket en la registradora.** Si se hizo, quedarían dos
comprobantes por la misma venta.

## ARCA no responde al cobrar con «Factura»

La venta queda **cobrada** y la caja avisa. Qué pasa después lo decide `facturacion.arca_caido`
en `config/valores.yaml`:

- **`registradora`** (hoy): el comprobante se hace en la registradora. La venta queda marcada
  «Sin factura: ARCA no respondió» y **no** se factura después en Odoo.
- **`facturar_despues`** (cuando no haya registradoras): el ticket dice **FACTURA PENDIENTE** y la
  venta queda en el filtro «Factura pendiente (ARCA)». Cada 10 minutos Odoo prueba ARCA y, si
  responde, la factura con CAE (fecha del día en que se emite). Para no esperar: *Punto de venta →
  Órdenes* → **Reintentar facturas pendientes**. Si ARCA rechaza una (datos mal), deja de
  reintentarla: queda con el motivo para facturarla a mano con **Facturar con CAE**.

**Solo se reintentan las ventas cobradas con «Factura» marcado.** Las cobradas sin «Factura» nunca
se facturan solas.

## Para el contador

Lo de Odoo y lo de las registradoras van **por separado**:

| Qué pide | De Odoo | De las registradoras / 3C |
|---|---|---|
| **Libro IVA Ventas** (todas las facturas y tickets emitidos, con su IVA) | *Facturación → Reportes → Impuestos y finanzas → **Libro de IVA***, tipo de impuesto **Ventas** (ventas): solo lo que facturó Odoo | Como hoy: el resumen de cada registradora y lo de 3C |
| **Detalle de compras** (todas las facturas de proveedores) | El mismo **Libro de IVA** (compras): solo las facturas reales; las «Compras sin factura» no entran | — |
| **TXT para ARCA** (los archivos del Libro IVA Digital que se suben a la página de ARCA) | En el **Libro de IVA**, con **Ventas** o **Compras** elegido, ⚙ → **Libro de IVA (ZIP)**: trae los TXT | Como hoy |

Para controlar lo de las registradoras: *Punto de venta → Órdenes → **Ventas sin factura de Odoo***,
por día y por caja, con el total. Tiene que coincidir con lo que dio cada registradora ese día.
