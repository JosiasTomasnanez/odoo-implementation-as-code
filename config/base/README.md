# Capa `base`

Visión funcional común a Online y On-Premise. Cada archivo corresponde a algo que el
negocio ya confirmó (ver `docs/relevamiento/` y `docs/pendientes.md`).

| Archivo | Qué declara | Origen |
|---------|-------------|--------|
| `00-modulos.yaml` | Punto de venta y empleados con PIN | P-008, P-005 |
| `05-empresa.yaml` | La empresa: nombre (`empresa.nombre` en `valores.yaml`) y logo en color (`config/imagenes/logo.png`) | P-001 |
| `06-deposito.yaml` | Nombre del depósito principal de Odoo = el de la empresa | P-032 |
| `10-diarios-efectivo.yaml` | Un efectivo por caja (Caja 1 y Caja 2) | 2 cajas confirmadas (07/10) |
| `20-medios-de-pago.yaml` | Efectivo, débito, crédito, transferencia | P-016. Las cuentas contables quedan pendientes del contador (P-034) |
| `30-puntos-de-venta.yaml` | 9 puestos y 2 cajas, con el logo en blanco y negro en el ticket | P-008 |

Los nombres y opciones que pueden cambiar no están en estos archivos sino en
`config/valores.yaml` (ADR 0010).

Lo que solo existe en el servidor propio (puestos que imprimen el pedido con QR) está en
`config/onpremise/`. Los empleados reales todavía no se cargan (P-005).
