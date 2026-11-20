# 0038. Cierre Z de las registradoras en Odoo; los puestos sin efecto contable

- Estado: aceptado en el lab (implementador, 11/11); falta que lo aprueben la administración y el
  contador (P-070) y las fotos de un Z real de la Sam4s y de la Hasar
- Fecha: 2026-11-11
- Cambia: ADR 0019 (lo de «Cobrado en registradora» ya no queda en la contabilidad) y ADR 0024 (el
  Libro IVA de Odoo puede incluir lo de las registradoras, si el contador elige un solo libro)

## Contexto

Las registradoras (Sam4s PV 8, Hasar PV 13) siguen emitiendo los tiques. La administración quiere
que Odoo tenga lo que vendieron, para conciliar el banco y las tarjetas, ver compras contra ventas
y, si el contador lo elige, tener un solo Libro IVA (P-070, P-071). Odoo 20 no maneja controladores
fiscales: el Z no se puede leer de la registradora ni generar desde Odoo.

Además, en Odoo 20 cada cierre de sesión del punto de venta crea un comprobante de cierre (factura
interna del diario de cierre, sin documento fiscal) con ventas e IVA, y un cobro por medio de pago.
Los puestos «cobran» todo con «Cobrado en registradora» (ADR 0019): si además se carga el Z, la
venta y el IVA quedan dos veces en la contabilidad y en «Análisis de facturas».

## Decisión

- **Módulo `comercio_cierre_z`**, *Contabilidad → Clientes → Cierres Z*: un registro por Z con los
  números impresos (número, fecha, primer y último tique, neto e IVA por alícuota, exento, no
  gravado, TOTAL, cómo se cobró) y su foto. Se carga **a mano** o con **«Leer foto con IA»**
  (Gemini con la clave propia, como las facturas de proveedor, ADR 0018/0021): la IA solo completa,
  una persona revisa y confirma.
- **Controles:** no se confirma si las sumas no dan el TOTAL, si el IVA no corresponde a su neto
  (tolerancia: $ 2 o 0,5 %, por el redondeo por tique) o si los cobros no suman el TOTAL; el número
  no se repite. Avisa si falta un Z correlativo, la diferencia con lo que imprimieron los puestos ese
  día y si la caja de Odoo vendió sin factura ese día.
- **Confirmar** crea un comprobante **Tique (83)** en el diario de la registradora (tipo
  «Controlador fiscal externo» de `l10n_ar`, no va a ARCA), con el **IVA impreso en el Z** (no el
  recalculado), la foto adjunta y un cobro por medio de pago (diario configurable por medio en
  `config/onpremise/65-cierre-z-medios.yaml`). «Volver a borrador» anula comprobante y cobros.
- **Libro IVA Digital:** el comprobante del Z se informa del primer al último tique del día
  (Odoo pone siempre «hasta» = «desde»; se completa en `_vat_book_get_REGINFO_CV_CBTE`).
- **Puestos sin efecto contable:** apenas se hace la contabilidad de una sesión cuyos pagos son
  todos «Cobrado en registradora», se anulan esos cobros y el comprobante de cierre se revierte con
  su nota de crédito. El stock no cambia. Un pedido de esas sesiones no se puede facturar después
  con CAE (lo documenta el tique de la registradora). Las sesiones cerradas antes del módulo se
  procesan con `pos.session.comercio_anular_puestos_anteriores()`; las que tienen pedidos facturados
  después del cierre se dejan y se avisa para revisarlas a mano.

## Alternativas consideradas

- **Posición fiscal en los puestos** (impuestos y cuentas «de control»): sin código, pero cambia los
  impuestos en la pantalla del PdV y una cuenta de ingresos sin mapear duplicaría la venta sin aviso.
- **Cuenta transitoria** que el Z cancela: no alcanza en Odoo 20, donde el cierre es una factura
  interna con su IVA.
- **Importar el archivo del Z** de la registradora: depende de cada modelo; se evalúa con las fotos
  reales (P-070).

## Consecuencias

- La venta contable de lo que cobran las registradoras es el Z. Lo de los puestos sirve para stock,
  reportes del PdV y como control contra el Z.
- **Cobros de la caja de Odoo sin factura** (ADR 0024) y Z de la registradora a la vez: no está
  resuelto (quedarían dos veces); el Z avisa. Hoy la caja de Odoo no se usa (ADR 0017).
- «Tarjetas a liquidar» es provisorio hasta definir la conciliación de liquidaciones (P-045).
- Pruebas: `make test`, `make e2e-cierre-z`, `make e2e-pos` (cierre del puesto) y `make e2e-ia`
  (lectura de la foto con Gemini).
