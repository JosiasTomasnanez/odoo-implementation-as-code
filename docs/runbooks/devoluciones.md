# Devoluciones en la caja

Estado: **probado en el lab** (08/10/2026, cuando el lab era Odoo 20 Community; hoy es Enterprise). Falta definir con el
contador el tratamiento fiscal y con el negocio quién autoriza (P-038).

## Qué hace el cajero

1. «Órdenes» → filtro «Activo» → **«Pagado»** → elegir la venta (buscar por número del
   ticket o por cliente).
2. Tocar cada producto que vuelve e indicar la cantidad.
3. **«Reembolso»**: se abre una venta nueva con importes **en negativo**.
4. Elegir cómo se devuelve la plata (efectivo, tarjeta…) y **«Validar»**.

## Qué pasa en Odoo (verificado en el lab)

| | Qué ocurre |
|---|---|
| **Venta original** | No se borra ni se modifica: queda «Pagado» y marca que tiene una devolución. |
| **Devolución** | Es una venta nueva, enlazada a la original, con cantidades e importe negativos. |
| **Plata** | Pago negativo en el medio elegido: si es efectivo, sale de la caja y el cierre lo tiene en cuenta. |
| **Stock** | Los productos **vuelven al depósito** automáticamente (movimiento «Clientes → Existencias»). |
| **Factura** | Si la venta tenía factura, se genera una **nota de crédito** que la anula (en el lab: «Reversión de …»). |

O sea: el stock vuelve, la plata sale y **los dos movimientos quedan registrados**
(venta y devolución), con trazabilidad completa.

## A definir

- **Fiscal (contador):** en el sistema real la nota de crédito es un comprobante
  electrónico ante ARCA (NC B o NC A, según la factura original). Confirmar el
  procedimiento y si se puede devolver en efectivo una venta pagada con tarjeta.
- **Quién autoriza (P-038):** en Odoo estándar cualquier cajero puede devolver, sin tope.
- **Mercadería dañada o vencida:** Odoo la devuelve al stock vendible; si no se puede
  volver a vender, hace falta un ajuste o un desecho después. Definir cómo se maneja.
