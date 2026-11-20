# Funciones Enterprise: qué trae y qué se probó en el lab

- Estado: investigado el 08/10/2026 (P-017). **El lab corre Enterprise** desde el 13/10 y,
  desde el 26/10, con el código de GitHub de la misma fecha que la imagen (ver «Lab
  Enterprise» abajo). Ya se probó la factura electrónica con CAE en homologación (14/10).
- Contexto: el lab y el servidor usan `odoo:20.0-AAAAMMDD` + Enterprise de GitHub; producción
  es Odoo 20 **Enterprise** On-Premise (plan Custom, P-010). La tabla y el «Hallazgo
  principal» se escribieron con el lab Community (08/10): la columna «En el lab hoy» quedó
  vieja para lo Enterprise.

## Cómo se verificó

- **Lab:** si el módulo está en `/usr/lib/python3/dist-packages/odoo/addons/` del
  contenedor `odoo-lab-odoo-1`, es Community (licencia LGPL-3 en su manifiesto). Si no
  está, es Enterprise o no existe.
- **Marca de Odoo:** en Community, Ajustes muestra con la etiqueta «Enterprise» los
  módulos cuyo campo usa `widget="upgrade_boolean"` (verificado en las vistas del lab).
- **Documentación 20.0:** [localización Argentina](https://www.odoo.com/documentation/20.0/applications/finance/fiscal_localizations/argentina.html),
  [IoT](https://www.odoo.com/documentation/20.0/applications/general/iot.html).
- El repositorio Enterprise es privado: lo que no está en el lab y no tiene marca ni
  documentación queda como **supuesto**.

## Hallazgo principal

**La factura electrónica argentina (CAE por web service) es Enterprise.** El módulo
`l10n_ar_edi` no está en el lab, y en Community el diario solo ofrece los sistemas de
punto de venta ARCA «Factura preimpresa», «Factura en línea», bonos, exportación y
«Controlador fiscal externo»; la opción **web service** (`RAW_MAW`) la agrega
`l10n_ar_edi` (verificado en `l10n_ar/models/account_journal.py`). En el lab las
facturas A/B se validan con número local, **sin CAE ni QR de ARCA**. Tampoco está el
**Libro IVA Digital** (`l10n_ar_reports`). _(08/10, lab Community. Con Enterprise las dos
cosas ya están en el lab; la facturación quedó para la etapa siguiente, ADR 0017.)_

En cambio, **lo propio del local no depende de Enterprise**: los módulos
`comercio_pos_pedido_qr` y `comercio_pos_balanza_systel` (balanza por WebSerial, ADR 0012)
usan solo Community, y los lectores USB funcionan como teclado.

## Tabla

Leyenda de «Edición»: **C** = Community, **E** = Enterprise. «Verif.»: *lab* (presente o
ausente en el lab), *marca* (etiqueta «Enterprise» en Ajustes), *doc*, *supuesto*.

| Función | Módulo | Edición (verif.) | ¿La usamos? | En el lab hoy | Queda para Enterprise | Alternativa Community |
|---|---|---|---|---|---|---|
| Localización AR: plan de cuentas, tipos de documento, letra A/B, responsabilidad ARCA | `l10n_ar`, `l10n_latam_invoice_document` | C (lab) | Sí, facturación (P-002) | Todo, sin CAE | — | — |
| **Factura electrónica ARCA (CAE, web service wsfev1, certificado, homologación)** | `l10n_ar_edi` | **E** (lab: ausente; doc) | **Sí, crítico** (P-029, P-034) | Nada contra ARCA; solo la factura sin CAE | Certificado de homologación, CAE en factura y en POS, QR ARCA, notas de crédito, rechazos | No hay en 20.0 (los de terceros llegan a 18.0, ver P-029) |
| POS argentino: cliente CF por defecto, A/B según cliente, botón «Factura» | `l10n_ar_pos` | C (lab) | Sí, cajas (P-003) | Flujo y letra del comprobante | Que la caja obtenga el CAE al validar | — |
| Autofacturación por QR del ticket | `point_of_sale` + `l10n_ar_pos` | C (lab) | Propuesto (P-037) | Pantalla y factura sin CAE | Factura con CAE | — |
| **Libro IVA Digital (ZIP), resumen de IVA** | `l10n_ar_reports` (sobre `account_reports`) | **E** (lab: ausente; doc) | Sí, contador | No | Exportar el ZIP y validarlo con el contador | Exportar facturas a planilla (manual) |
| Retenciones en pagos | `l10n_ar_withholding` | C (lab) | A definir con el contador | Sí | — | — |
| Ecommerce AR (tipo de documento y responsabilidad en el checkout) | `l10n_ar_website_sale` | C (lab) | Futuro (P-009) | Sí | Factura con CAE de la venta web | — |
| App Contabilidad completa (conciliación bancaria, cierre, activos) | `account_accountant` | **E** (lab: ausente) | Sí, administración/contador | Solo Facturación (`account`): facturas, pagos, extractos | Conciliación bancaria, asientos de cierre | Conciliar a mano (pagos contra extracto) |
| Reportes contables (balance, resultados, mayor, reporte de impuestos) | `account_reports` | **E** (lab: ausente; los menús de reportes vienen vacíos) | Sí | «Análisis de facturas» y tablas dinámicas | Todos los reportes legales | Tablas dinámicas, exportar a planilla |
| Seguimiento de cobros (follow-ups, cuenta corriente) | `account_followup` | **E** (lab: ausente) | Mayorista, etapa posterior (P-015) | No | Recordatorios de deuda | Filtro de facturas vencidas |
| Importar extractos bancarios CSV/OFX, OCR de facturas de proveedor | `account_bank_statement_import_*`, `account_invoice_extract` | **E** (marca); OCR además consume créditos IAP | A evaluar | No | Probar con extractos reales anonimizados | Carga manual |
| **IoT (caja IoT o IoT de Windows)**, impresoras/balanzas/pagos por IoT en el POS | `iot`, `pos_iot` | **E** (lab: ausentes; doc: requiere suscripción de IoT box) | **No por ahora** (ADR 0012 eligió WebSerial) | — | Solo si se cambia de camino | `iot_webserial` (C, en el lab) + módulo propio |
| Balanza por USB desde el navegador | `iot_webserial` + `comercio_pos_balanza_systel` | C (lab) | Sí (P-040) | Todo, con balanza simulada | — | — |
| Impresoras de tickets por red (Epson ePOS) y etiquetas ZPL por IP | `point_of_sale`, `printer` | C (lab) | A definir (P-006) | Sí, si la impresora es ePOS/ZPL de red | Impresora USB por IoT | Impresión del navegador (modo kiosco) |
| Empleados en el POS con PIN y roles (supervisado, cajero) | `pos_hr` | C (lab) | Sí, puestos y cajas (P-005) | Todo (ya probado) | Confirmar licencia «Light User» (P-005) | — |
| Mercado Pago (terminal POS / pago web) | `pos_mercado_pago`, `payment_mercado_pago` | C (lab) | A evaluar (P-016) | Con credenciales de prueba | — | — |
| Autoservicio / pantalla de preparación | `pos_self_order` (C) / `pos_enterprise` (E, supuesto) | C / E | No | — | — | — |
| Promociones, cupones, 2x1 | `loyalty`, `pos_loyalty` | C (lab) | Sí, gradual (P-030) | Todo | — | — |
| Listas de precios, margen por categoría | `product` | C (lab) | Sí (P-030) | Todo | — | — |
| Inventario, ubicaciones, lotes/vencimientos, reposición | `stock`, `product_expiry` | C (lab) | Sí | Todo | — | — |
| Nomenclatura de códigos con peso/precio y GS1 | `barcodes`, `barcodes_gs1_nomenclature` | C (lab) | Plan B pesables | Todo | — | — |
| Etiquetas de producto (A4, Dymo, ZPL) | `product` | C (lab) | Sí (P-007, D8) | Todo | — | — |
| **App Código de barras** (recepción, conteos, transferencias con lector) | `stock_barcode` | **E** (lab: ausente; marca) | Probable: recepción y conteos | No | Recepción de compras y conteo con lector o celular | Inventario normal con lector como teclado |
| Datos de producto por código de barras (barcodelookup) | `product_barcodelookup` | **E** (marca); usa servicio externo | A evaluar (carga de catálogo) | No | Ver costo y calidad para productos argentinos | Importador propio `integrations/catalogo/` |
| **Fusionar productos repetidos** (proveedores, stock e historial pasan al que queda; el otro se archiva) | `data_cleaning`, `data_merge_product` (+ `data_merge_stock_account`) | **E** (lab Enterprise, probado 21/10) | Sí, para duplicados que se escaparon de las listas | Todo (`config/onpremise/50-…`, `51-…`) | — | Quitar el repetido del catálogo y unir la fila en la próxima lista |
| Compras, varios proveedores por producto | `purchase`, `purchase_stock` | C (lab) | Sí | Todo | — | — |
| Acuerdos de compra y pedidos alternativos | `purchase_requisition`, `purchase_alternative` | C (lab) | A evaluar (P-004) | Todo | — | — |
| Ventas mayoristas (presupuestos, pedidos) | `sale_management` | C (lab) | Etapa posterior (P-015) | Todo, salvo follow-ups | — | — |
| Sitio web y ecommerce | `website`, `website_sale` | C (lab) | Futuro (P-009) | Todo | — | — |
| **Studio** (campos, vistas, informes, automatizaciones sin código) | `web_studio` | **E** (lab: ausente) | Propuesto para backend (P-028) | No | Probar y **probar la exportación** a módulo | Módulo en `addons/` o `config/` + `base_automation` (C) |
| Automatizaciones (acciones automáticas) | `base_automation` | C (lab) | Sí | Todo | — | — |
| **Funciones de IA** (app IA, agentes, «Preguntar a IA», crear registros desde PDF) | `ai` y derivados | **E** (lab: ausente); consumen créditos IAP (P-020) | A evaluar (P-020, P-021) | No | Agentes para listas de proveedores (P-021) | `odoo-product-matcher`, importador propio |
| Tableros (spreadsheet dashboards) de solo lectura | `spreadsheet_dashboard*` | C (lab) | Probable (reportes) | Ver tableros estándar | — | — |
| Editar hojas de cálculo y tableros propios, Documentos | `spreadsheet_edition`, `documents` | **E** (supuesto; no están en el lab) | A evaluar | No | Tableros propios | Tablas dinámicas, exportar |
| Calidad (controles) | `quality_control` | **E** (marca) | No | — | — | — |

## Lab Enterprise (13/10; desde GitHub el 26/10)

- **Código (desde el 26/10):** el repositorio `github.com/odoo/enterprise`, rama `20.0`, solo
  los módulos Enterprise. Se accede con la cuenta de GitHub **CasaEjemplo**, que Odoo agregó
  por la suscripción. Community sale de la imagen oficial con fecha `odoo:20.0-AAAAMMDD`, y
  `infra/scripts/fijar-enterprise.sh` deja el clon en el último cambio de ese día, así las dos
  partes son de la misma fecha. El clon vive **fuera del repo** (en la PC,
  `/mnt/datos1/odoo-enterprise-git`; en el servidor, `/opt/odoo-enterprise`) y no se versiona.
  Antes (13/10) se usaba el tarball de odoo.com (`ODOO_ENTERPRISE_SRC`, todavía soportado).
- **Cómo lo usa el lab:** `ODOO_ENTERPRISE_ADDONS=<clon>` en `.env`. `infra/scripts/lib.sh`
  suma `infra/docker/compose.enterprise-git.yml`, que lo monta en `/mnt/enterprise-addons`
  (primero en el `addons_path` de `odoo.lab.conf`). Sin la variable, ahí queda un volumen vacío
  y el stack es Community. **El servidor** lo copia adentro de la imagen al construirla
  (`compose.onprem.yml`, `additional_contexts`; `Dockerfile` con `RUN --mount`).
- **Actualizar Odoo:** cambiar la fecha de la imagen, correr `fijar-enterprise.sh`, rearmar el
  lab y pasar las e2e; recién después, el servidor (`docs/runbooks/instalar-servidor.md`).
- **Base:** `web_enterprise` se instala solo con `web`, así que toda base nueva del lab
  es Enterprise. La base `lab` existente se pasó con `-i web_enterprise`. **No se
  registra con el código de suscripción:** una base sin registrar funciona unos 30 días
  desde su creación (a confirmar con Odoo, P-010); al vencer, `make lab-destroy lab-init`.
- **Dependencias:** la imagen ya trae `zeep` (web service de ARCA). Faltan `PyPDF2`
  (usa `pypdf` en su lugar), `rl-renderPM` y `pypiwin32` (Windows): no hacen falta.
- **Probado el 13/10 sobre Enterprise:** `make test lint`, `make e2e-pos` (puesto, dos
  cajas, cierre, balanza), `make e2e-catalogo`, `make e2e-precios`, `make apply`/`verify`.
  Única diferencia encontrada: el texto del campo del PIN («Escriba su NIP» en lugar de
  «Ingresa tu NIP»), ya contemplado en la prueba.
- **Probado el 26/10 con Enterprise de GitHub** (`odoo:20.0-20261015` + Enterprise del mismo
  día): todas las e2e (catálogo, precios, códigos de fábrica, factura de proveedor, POS,
  factura con CAE, IA) y `make verify`. El código de suscripción se registra solo en la base
  de producción del servidor.

## Qué sirve de Enterprise (investigado el 14/10 en el código 20.0+e)

Leído en `/mnt/datos1/odoo-enterprise/.../odoo/addons/` (licencia `OEEL-1` = Enterprise).
**V** = verificado en el código; **S** = supuesto.

**Factura electrónica (`l10n_ar_edi`)**
- **Probado el 14/10:** CAE real de ARCA **homologación** para una factura B a Consumidor
  Final, una A a un Responsable Inscripto y una nota de crédito. Se repite con
  `make lab-arca e2e-factura`.
- **Certificado de prueba:** Odoo trae 10 certificados de homologación (`demo/cert*.crt`,
  CUIT de prueba de Odoo, vencen en 09/2027) que funcionan con el CUIT ficticio de su
  empresa demo (30111111118). Sirven para el lab. Para homologar con el CUIT real de Casa
  Ejemplo hace falta un certificado propio: alguien con clave fiscal nivel 3 lo saca en
  ARCA (servicio «WSASS – Autogestión Certificados Homologación», S: nombres de menú sin
  verificar); en Odoo, Ajustes → «Generar solicitud» crea la clave y el pedido (CSR).
- **Pide el CAE en el momento de validar (V):** si ARCA rechaza o no responde, la factura
  no se valida. **No hay cola, reintento ni CAEA para emitir (V).** En el POS, el pedido
  vuelve a borrador y la caja no puede terminar la venta (V,
  `point_of_sale/.../order_payment_validation.js`). Hace falta un plan de contingencia
  (P-029).
- **El POS argentino factura cada venta (V):** `l10n_ar_pos` marca «Factura» por defecto,
  con Consumidor Final anónimo. Cada venta sería una factura B con su CAE.
- **El ticket térmico no muestra CAE ni QR de ARCA (V):** solo el PDF de la factura. Hay
  que diseñar el comprobante que se entrega en la caja.
- **No hay consulta de padrón por CUIT (V).** Sí trae: «Consultar comprobante en ARCA»,
  sincronizar la numeración con ARCA y verificar facturas de proveedor (wscdc).
- «Verificar el PdV de ARCA disponible» no anda en homologación (V).

**Contabilidad:** `account_accountant` y `l10n_ar_reports` se instalan solos con Enterprise.
Libro IVA Digital (ZIP), SICORE (retenciones de Ganancias) y percepciones de Córdoba en el
plan de cuentas (V); **no hay SIRCAR ni padrones de IIBB Córdoba** (V). Extractos CSV/OFX.
Bancos argentinos en la sincronización bancaria: no se puede saber del código (S). El POS
no maneja analítica: los 6 rubros irían por categoría en las líneas de factura (S, P-031).

**POS, stock y compras**
- **`stock_barcode` (app Código de barras): alta utilidad** para recibir y contar mercadería
  con lector o con la cámara del celular; vencimientos con `stock_barcode_product_expiry`.
  Su usuario es **«ligero»** (V).
- `pos_settle_due`: cobrar deudas desde la caja (etapa mayorista). `stock_enterprise` y
  tableros listos de POS, stock y compras (`spreadsheet_dashboard_*`).
- `pos_enterprise` es la pantalla de preparación (cocinas): **no reemplaza**
  `comercio_pos_pedido_qr`. IoT solo trae balanzas Adam: **sigue haciendo falta**
  `comercio_pos_balanza_systel`.
- `data_merge_product`: duplicados de productos por coincidencia exacta o sin acentos (V).
  No reemplaza el motor de similitud (ADR 0014); sirve como control periódico (P-021).
- `product_barcodelookup`: completa productos por EAN con barcodelookup.com (clave y costo
  propios, no IAP); cobertura argentina dudosa (S).

**Licencias (V en `mail/models/update.py` y `base/models/res_users.py`):** Odoo informa los
usuarios internos activos y aparte los «ligeros» (todos sus grupos son ligeros: Código de
barras, opciones de stock, ausencias). **Los empleados del POS sin usuario (`pos_hr`) no
cuentan.** Pero **el usuario que abre el POS en cada navegador cuenta como usuario normal**
(`group_pos_user` no es ligero), y el usuario de la API de `odoo-iac` también. Con 1 usuario,
hoy todo saldría con el administrador: hay que definirlo (P-005).

**Studio, IA, web y otros**
- **Studio** exporta un módulo de solo datos (`studio_customization`, XML sin Python) que se
  puede versionar en `addons/` (V, P-028).
- **IA: no acepta clave propia (V).** Todo pasa por el servicio de Odoo con créditos IAP y
  el modelo lo elige Odoo. Además **necesita la extensión pgvector** en PostgreSQL (V); el
  lab usa `postgres:16`, que no la trae, así que hoy no se instala. Ojo: si algún día se
  agrega pgvector, `ai_auto_install` instala la IA sola. La doble verificación con Gemini
  de P-021 tiene que ser una integración propia.
- Ecommerce: `website_sale_enterprise`, `l10n_ar_website_sale`, retiro en el local
  (`website_sale_collect`), Mercado Pago, envíos con Envia (no hay Andreani, OCA ni Correo
  Argentino) y el tema de mascotas `theme_pawtastic`.
- **Veterinaria:** no hay módulo nativo (V). `appointment` para turnos, más una ficha de
  mascota hecha con Studio, cuando se releve.
- WhatsApp (`whatsapp_pos`, tickets y facturas): cuenta propia de Meta, tarifa por mensaje.
  `knowledge` sirve para las guías cortas del personal.
- **Interfaz mínima:** varios módulos Enterprise se instalan solos (`pos_enterprise`,
  `product_barcodelookup`, `account_accountant`…). Hay que revisar qué menús ve el personal.

## Qué probar primero en Enterprise

Ordenado por importancia para cuando se facture desde Odoo (etapa siguiente, ADR 0017). Siempre en
**homologación** de ARCA y con datos ficticios (regla de `docs/areas/facturacion-contabilidad.md`).

1. **Factura electrónica (`l10n_ar_edi`) en homologación:** _Hecho el 14/10 desde Ventas
   (B, A y nota de crédito, `make e2e-factura`)._ Falta: desde la caja del POS, ARCA caído,
   comprobante en la impresora térmica. Certificado de prueba, diario
   de punto de venta «web service», factura B a Consumidor Final y A a Responsable
   Inscripto **desde la caja del POS** con el flujo real (`make e2e-pos` con
   `comercio_pos_pedido_qr`), CAE y QR en el ticket, nota de crédito, qué pasa si ARCA
   no responde. Confirmar que los módulos propios conviven con Enterprise.
2. **Comprobante de cierre de sesión** (ventas sin factura individual): ver si
   `l10n_ar_edi` lo emite ante ARCA y cómo (P-003), y «facturar después» con CAE.
3. **Libro IVA Digital (`l10n_ar_reports`)**: exportar el ZIP de un mes de prueba y
   validarlo con el contador (pregunta 7 del área de facturación).
4. **Contabilidad completa:** reportes de impuestos, conciliación bancaria y cierre de
   caja contra el banco, con el contador.
5. **Instalación y actualización Enterprise On-Premise:** el código ya se obtiene y
   `odoo-iac` anda igual (13/10, «Lab Enterprise»). La imagen del servidor con Enterprise
   está resuelta (26/10, GitHub). Falta probar la restauración de un backup en el servidor (ADR 0027).
6. **Código de barras (`stock_barcode`)** para recepción de compras y conteos; decidir si
   entra en el arranque o después (adopción gradual).
7. **Studio** con un caso concreto y la **exportación** versionable (P-028).
8. **IA** (P-020, P-021): solo con una necesidad concreta (listas de proveedores) y
   midiendo el consumo de créditos IAP.
9. Después del arranque: follow-ups y cuenta corriente para mayoristas (P-015),
   tableros propios.

## Pendientes que siguen abiertos

- Confirmar con Odoo que se pueden usar bases de prueba sin registrar y cómo se pasa el
  código de suscripción a otra base (P-010). La descarga ya está resuelta (13/10).
- Licencia de los empleados que solo entran al POS con PIN («Light User», P-005).
- El código Enterprise ya está en el lab (clon de GitHub): lo marcado *supuesto* se confirma
  mirando ese clon cuando haga falta, y se actualiza esta tabla.
