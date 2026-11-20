# Código propio: inventario para mantener y actualizar

Todo lo que no es Odoo estándar y hay que **revisar al cambiar de versión de Odoo**
(p. ej. 20 → 21), al pasar a Enterprise o al tocar algo de Odoo de lo que dependemos.
Cada módulo o cambio de código nuevo se agrega acá en el mismo cambio que lo crea.

Relevado del código el 12/10/2026 (entonces Odoo 20.0 Community en el lab). Hoy el lab y el
servidor corren `odoo:20.0-AAAAMMDD` + Enterprise de GitHub de la misma fecha.

## Resumen

| Pieza | Tipo | Versión | Para qué | Decisión | Riesgo al actualizar | Prueba |
|---|---|---|---|---|---|---|
| `comercio_pos_pedido_qr` | módulo (Python + POS JS) | 20.0.1.13.0 | Puesto que arma el pedido con QR, caja que cobra, dos cajas, cierres | ADR 0009, P-035 | **Alto**: parchea 7 piezas internas del POS | `make e2e-pos` |
| `comercio_pos_balanza_systel` | módulo (POS JS + ajustes) | 20.0.1.3.0 | Peso de la Systel Cuora por USB (WebSerial) | ADR 0012 | **Alto**: parchea la pantalla de balanza y usa `iot_webserial` | `make e2e-pos` |
| `comercio_catalogo` | módulo (Python, app propia) | 20.0.1.53.0 | App «Costos y precios» (listas de proveedores), códigos automáticos y costo del producto | ADR 0014, 0015, P-007, P-044 | Medio: modelos propios, poco acople | `make e2e-catalogo`, `make listas-reales` (motor con las listas reales, sin lab) |
| `comercio_pos_categorias` | módulo (Python, integración externa) | 20.0.1.5.1 | «Categorizar con IA / a mano» la categoría del punto de venta (botones del POS) | ADR 0018 | Bajo: asistente propio, escribe el campo nativo `pos_categ_ids`; acciones en el menú de `product.template`; usa el cliente de Gemini de `comercio_catalogo_ia` | `make test`, `make e2e-ia` |
| `comercio_catalogo_ia` | módulo (Python, integración externa) | 20.0.1.14.0 | «Verificar con IA» (Gemini) en posibles duplicados, productos a agregar y lo ya unido (sugiere; une sola lo seguro, nunca agrega productos); lee listas en foto o PDF escaneado | ADR 0018, 0034 | Bajo: hereda filas e importación de `comercio_catalogo`; depende de la API de Gemini (nombres de modelos cambian) | `make test`, `make e2e-ia` |
| `comercio_carteles` | módulo (Python, app propia) | 20.0.1.1.1 | Carteles grandes de precio en A4 (1, 2, 4 u 8 por hoja), texto libre, precio de Odoo con IVA (redondeado o a mano), vista previa en vivo en la ficha y «Ver PDF», y «Para reimprimir» si cambió el precio. Estilos en `static/src/cartel.scss` (backend y reportes). En producción desde el 20/11 | ADR 0039 | Bajo: modelo y reporte propios; usa `taxes_id.compute_all`, el widget `barcode` de QWeb y el bloque `article` de los reportes (sin él no hay UTF-8) | `tests/test_carteles.py`; a mano en el lab |
| `comercio_precios` | módulo (Python + vistas) | 20.0.1.20.0 | Precio de venta sugerido por margen de la categoría; precios a actualizar y etiquetas | ADR 0016, P-030 | Medio: pisa `write`/`create` de productos y categorías; hereda el asistente «Importar lista» de `comercio_catalogo` (margen del rubro) | `make e2e-precios` |
| `comercio_compras_lista_vigente` | módulo (Python + vista) | 20.0.1.10.0 | Compras según la lista vigente del proveedor; avisos; «Agregar al pedido» desde las listas; «Enviar por WhatsApp» | ADR 0015, P-042, P-044 | **Alto**: usa métodos internos de Compras | `make e2e-catalogo` |
| `comercio_factura_proveedor` | módulo (Python + vistas, integración externa) | 20.0.1.9.2 | Leer la factura del proveedor (PDF sin IA, foto con Gemini) en vez de la digitalización paga de Odoo; cargar sus artículos y agregar al catálogo los que no tenemos | ADR 0021, P-047 | **Medio**: se engancha en el lector de adjuntos de Contabilidad (`_get_edi_decoder`, `_get_import_file_type`) | `make test`, `make e2e-factura-proveedor` |
| `comercio_pos_factura` | módulo (Python + vistas + JS del POS) | 20.0.1.1.6 | Caja: «Factura» marcado = factura de Odoo con CAE; desmarcado = la emite la registradora o 3C (franja de color al costado), separado para el contador | ADR 0024 | **Bajo-medio**: hereda plantillas del POS (`PaymentScreenDue`, `PaymentScreenButtons`) y usa `isToInvoice`/`isArgentineanCompany` de `l10n_ar_pos` | `make e2e-pos` (`pos_factura.py`) |
| `comercio_codigos_fabrica` | módulo (Python + vistas) | 20.0.1.1.0 | «Códigos de fábrica»: escanear el código del envase en lugar del propio 20…, que queda como alternativo | ADR 0025, P-058 | **Bajo**: campos nuevos en `product.template`; usa `product.uom` (códigos por unidad, que el POS lee) y hereda `_comercio_ultimo_numero` de `comercio_catalogo` | `make e2e-codigos-fabrica` |
| `comercio_etiquetas` | módulo (Python + plantilla ZPL) | 20.0.1.2.0 | Etiqueta ZPL «Comercio Ejemplo» (nombre en 2 líneas, Code 128 automático, «Rollo» a elegir al imprimir: modelo `comercio.etiqueta.rollo`, último por usuario con `ir.default`; Gerencia crea rollos nuevos desde el campo) para imprimir directo en la Zebra por la IoT | ADR 0030, P-062 | **Bajo-medio**: agrega una opción a `product.label.layout.zpl_template` y hereda `_get_label_template_xml_id` / `_prepare_report_data` / `_save_user_defaults` y la vista `product.product_label_layout_form` del asistente de etiquetas | a mano (`etiquetas-zebra.md`) |
| `comercio_conteo_catalogo` | módulo (Python + JS de la app Código de barras) | 20.0.1.0.0 | Al contar el stock, un código que no es nuestro se busca en las listas («¿Agregar a nuestro catálogo?» / «Es ese») o se le pone a un producto nuestro como código de fábrica | pedido del 02/11 | **Alto**: parchea `BarcodeQuantModel.noProductToast` de `stock_barcode` (Enterprise) y vacía su caché interna de códigos no encontrados (`cache.missingBarcodeKeyCache`, `missingBarcodesCache`) para volver a buscar el producto; OWL 3 (`proxy`, `t-model.proxy`) | a mano en el lab (Contar inventario: escanear un código de una lista, uno de nadie y uno parecido) |
| `comercio_factura_mail` | módulo (Python + plantilla de mail) | 20.0.1.0.0 | Mail con que se manda la factura: diseño propio sin botón «Ver Factura» al portal, sin firma del usuario ni «Powered by Odoo». El texto (asunto y cuerpo) está en `config/base/08-mail-factura.yaml` (adopta «Factura: Envío», `account.email_template_edi_invoice`) | 09/11, `docs/areas/facturacion-contabilidad.md` | **Medio**: pisa `account.move.send._get_mail_layout`; el diseño usa `mail.notification_preview` y las variables `message`, `company`, `lang` del render de mails; el texto usa `l10n_latam_document_type_id.report_name`, `l10n_ar_letter`, `l10n_latam_document_number` y `l10n_ar.par_cfa` | A mano: «Enviar» en una factura del lab → Mailpit (`localhost:8025`) |
| `comercio_cierre_z` | módulo (Python + vistas, integración externa) | 20.0.1.0.0 | Cierre Z de las registradoras a mano o leyendo la foto con Gemini: tique (83) en el diario de la registradora con el IVA impreso y cobros por medio; Libro IVA con el rango de tiques; puestos que cobran en la registradora sin efecto contable | ADR 0038, P-070 | **Medio-alto**: hereda `pos.session._validate_session_accounting` (Odoo 20: el cierre es una factura interna `sale_move_ids`/`refund_move_ids` y cobros `account.payment` con `pos_session_id`) y `pos.order._generate_invoice_after_session_closing`; usa `_reverse_moves(cancel=True)`, `account.payment.register`, `tax_totals` (inverso) y `price_include` de los impuestos; pisa `l10n_ar.tax.report.handler._vat_book_get_REGINFO_CV_CBTE` (posiciones 36-56 del TXT); lee la foto como `BinaryValue.content`; usa el cliente de Gemini de `comercio_catalogo_ia` | `make test`, `make e2e-cierre-z`, `make e2e-pos`, `make e2e-ia` |
| `comercio_libro_iva` | módulo (solo un menú) | 20.0.1.0.0 | Menú «Libro de IVA» en Facturación → Reportes → Impuestos y finanzas (Odoo 20 no lo trae) | 09/11 | **Bajo**: usa los xml_id `account.account_reports_taxes_and_fiscal_menu` y `account_reports.action_account_report_gt` | A mano: el menú abre la Declaración fiscal con «Libro de IVA (AR)» |
| `comercio_pos_ticket_ar` | módulo (Python + plantilla del ticket + JS del POS + tarea programada) | 20.0.1.1.0 | Ticket de la caja con factura, CAE, vencimiento, QR de ARCA y Ley 27.743; con ARCA caído la venta queda cobrada sin factura de Odoo y la caja avisa; con `facturacion.arca_caido: facturar_despues` queda «Factura pendiente» (leyenda en el ticket) y una tarea cada 10 minutos (o «Reintentar facturas pendientes») la factura cuando ARCA vuelve, solo si se cobró con «Factura» | 02/11, `docs/areas/facturacion-contabilidad.md` | **Alto**: hereda `point_of_sale.pos_order_receipt` (`before-footer`) y `pos.order.receipt.order_receipt_generate_data`; parchea `GeneratePrinterData.generateReceiptData` y `OrderPaymentValidation.afterOrderValidation`; pisa `pos.order._generate_order_invoice` y usa internos de `l10n_ar_edi` (`_l10n_ar_get_connection`, `_get_client`, `_l10n_ar_get_invoice_custom_tax_summary_for_report`, `l10n_ar_afip_qr_code`); el reintento usa `_comercio_facturar_con_cae` de `comercio_pos_factura` con `sudo` y hace commit por venta (como `l10n_ar_edi`); lee `ir.config_parameter.get_str` (Odoo 20) | `make e2e-factura` (punto 4: factura pendiente) |
| `comercio_tienda` | módulo (Python + vistas) | 20.0.1.11.0 | Tienda online (fotos WebP 400/800 con Pillow directo: registra `PIL.WebPImagePlugin`, que Odoo 20 no carga en `tools/image.py`): «Publicar en la tienda» / «Consultar disponibilidad», lista «Tienda online» y listas mayoristas (mínimo por regla, bulto por embalaje; ADR 0035), mayoristas aprobados en la administración de la tienda → contacto por CUIT con su lista y listas de clientes «otra − X %» con descuentos por rubro o por producto que se regeneran desde la tienda (`tienda_sincronizar_clientes`, `_comercio_tienda_aplicar_reglas`, ADR 0036/0037), margen de stock por categoría, «Tienda: a reponer» (bajo el mínimo → a consultar solo; Pedir al proveedor) y cola de cambios que lee el conector | ADR 0031, 0032, 0033, 0036, 0037 | **Medio**: pisa `create`/`write`/`unlink` de `product.template`, `product.product`, `stock.quant`, `product.pricelist(.item)` y `pos.category` para anotar cambios; usa `_compute_price_rule` de las listas, `_get_applicable_rules` y `_is_applicable_for` de las reglas (mínimo mayorista), `uom_ids` y `_compute_quantity` (embalajes de Odoo 20, bulto), `_get_filtered_sellers(quantity=None)` (Odoo 20: `_select_seller` devuelve un dict), `free_qty` con `warehouse_id`, `taxes_id.compute_all`, `image_1024.to_base64()` (Odoo 20: `BinaryValue`) y el checksum de `ir.attachment`; crea `sale.order` confirmados (`action_confirm`, `get_product_multiline_description_sale`, `sale_stock`; cada pedido en `cr.savepoint()`; la línea con `discount: 0` porque Odoo 20 calcula el descuento de las reglas `compute_price=discount` aunque se le pase el precio; compara `amount_total` con lo cobrado y, si no da, deja el presupuesto con `activity_schedule`); valida entregas (`move.quantity`, `picked`, `button_validate` con `skip_backorder`, `picking_ids_not_to_backorder`, `skip_sms`); `hr.employee.pin`; crea `res.partner` (Odoo 20: `is_company` se calcula por el CUIT, no se escribe), `property_product_pricelist`, `l10n_ar_afip_responsibility_type_id` y reglas `base=pricelist` + `compute_price=discount` (generales, `1_product` y `0_product_variant`; el orden de aplicación de Odoo hace que la del producto le gane a la general) | `make e2e-tienda-sync`, `make e2e-tienda-pedidos`, `make e2e-tienda-admin` |
| `integrations/tienda` (conector) + `compose.tienda.yml` + `crear-conector-tienda.sh` | servicio externo (Python, sin dependencias) | - | Lleva la cola de `comercio_tienda` a la tienda, firmado con HMAC; sube las fotos; trae en una sola consulta por vuelta (`/api/conector/pendientes`) pedidos, acciones del panel y mayoristas/listas aprobados en la administración; usuario portal con solo el grupo del conector | ADR 0033 | Bajo: solo llama a los métodos `tienda_*` por JSON-2; `res.users.apikeys._generate` y `group_ids` (Odoo 20) en el script | `make e2e-tienda-sync` |
| `web/tienda` sitio mayorista (`src/middleware.ts`, `servidor/sitio.ts`, `pages/mayoristas/`, `servidor/xlsx.ts`) | Worker (TypeScript) | - | Sitio mayorista por dominio, cantidades mínimas y bultos, Excel de la lista sin dependencias | ADR 0035 | Bajo: no toca Odoo; depende de `context.rewrite` del middleware de Astro | `npm test` (web/tienda) |
| `web/tienda` cuentas y administración (`servidor/claves.ts`, `servidor/google.ts`, `servidor/equipo.ts`, `pages/admin/`, `pages/api/admin/`, `pages/compra.astro`) | Worker (TypeScript) | - | Contraseñas PBKDF2, código atado al navegador, Google OIDC con PKCE, equipo con roles y registro, aprobar mayoristas y pedir listas (los lleva el conector a Odoo), pantalla de pago | ADR 0036 | Bajo: no toca Odoo directo (va por el conector); depende de WebCrypto (PBKDF2 ≤ 100.000 vueltas en Workers) | `npm test`, `make e2e-tienda-cuentas`, `make e2e-tienda-admin` |
| `web/tienda` buscadores, legales y operación (`pages/sitemap.xml.ts`, `robots.txt.ts`, `api/sugerir.ts`, `legales/`, `arrepentimiento.astro`, `servidor/limpieza.ts`, `servidor/pendientes.ts`, `infra/scripts/tienda-respaldo.sh`) | Worker (TypeScript) + script | - | Sugerencias del buscador, vista previa y datos estructurados, textos legales en borrador, botón de arrepentimiento, eliminar cuenta, limpieza horaria, respaldo de D1 tabla por tabla (D1 no exporta bases con FTS5) | auditoría 10/11 | Bajo: no toca Odoo | `npm run tipos`, `npm test`, e2e de la tienda |
| Tienda (`web/tienda/`) | sitio Astro 7 en Cloudflare Workers + D1 + R2 + Durable Object | - | Tienda online: páginas desde D1 (búsqueda FTS5), API del conector (firma, validación con zod, consultas preparadas), carrito | ADR 0032, 0033 | Bajo respecto de Odoo (solo el formato del lote); medio respecto de Astro y del adaptador de Cloudflare | `npm test` en `web/tienda`, `make e2e-tienda-sync` |
| `src/odoo_iac` | herramienta externa | - | Configuración como código (`config/`) | ADR 0002, 0003 | Medio: API JSON-2 y nombres de campos | `make test`, `make verify` |
| `integrations/catalogo` | script externo | - | Carga inicial de productos desde Excel | ADR 0014 | Bajo: comparte el motor con `comercio_catalogo` | `make test` |
| `integrations/balanza_systel` | script de diagnóstico | - | Probar una balanza real por USB | ADR 0012 | Bajo: no toca Odoo | a mano (`prueba-balanza-real.md`) |
| Monitoreo (`infra/docker/monitoreo/`) | configuración + SQL + Python | - | Tableros y alertas de Grafana; consultas del negocio sobre la base de Odoo | ADR 0028 | **Medio**: las SQL dependen de tablas y columnas de Odoo y de los módulos propios | `make verify-monitoreo` |
| Acceso remoto (`caddy/remoto.caddy`, `compose.acceso-remoto.yml`, `configurar-acceso-remoto.sh`) | configuración + script (API de Cloudflare) | - | `remoto.comercio-ejemplo.example` por túnel y Cloudflare Access | ADR 0020 | Bajo: bloquea rutas de Odoo (`/web/database`, `/xmlrpc`, `/jsonrpc`, `/json/2`, `/doc`) y cuenta con que `proxy_mode` tome la última IP de `X-Forwarded-For` (`ProxyFix(x_for=1)`); si Odoo agrega otra API, sumarla | `make test` (`test_acceso_remoto.py`); a mano (`instalar-servidor.md`, paso 12) |
| `config/` | configuración YAML | - | Estado deseado de Odoo | ADR 0003, 0010 | Medio: nombres de campos, xml_id y módulos | `make plan` / `verify` |

Los módulos están en `addons/` (convenciones en `addons/README.md`), son **Community**
(sirven igual con Enterprise) y solo corren **On-Premise** (ADR 0011).

**Riesgo** = cuánto se apoya en piezas internas de Odoo que pueden cambiar entre versiones.
Lo que se hereda «por las buenas» (campos nuevos, herencia de vistas con xpath, `super()`)
suele sobrevivir; los **parches de JS del POS** y los **métodos privados** (`_algo`) son lo
primero que se rompe.

---

## `comercio_pos_pedido_qr`

Depende de `point_of_sale`, `pos_hr`. Instalado desde `config/onpremise/00-modulos.yaml`.

- **Campos propios:** `pos.config.comercio_arma_pedidos` (lo usan los puestos en
  `config/onpremise/40-puestos.yaml` y `config/ejemplos`), `pos.order.comercio_en_caja`;
  `pos.config.comercio_cobro_en_registradora` y `comercio_metodo_registradora_id` (ADR 0019).
- **Cobro en la registradora** (1.6.0, ADR 0019): `pos.order.comercio_cobrar_en_registradora`
  agrega el pago (`add_payment`) y llama a `_process_saved_order(False)` de Odoo (pagado +
  `_set_product_qty_available` → picking de `pos_stock`). Si Odoo cambia ese camino, el
  stock deja de bajar: lo detecta `tests/e2e/pos_cobro_registradora.py`.
- **Python que pisa a Odoo:**
  - `pos.order._load_pos_data_domain` (qué pedidos carga la caja).
  - `pos.session.close_session_from_ui` (regla de la última caja: anula los no cobrados).
- **Tarea programada:** «Comercio: cerrar puestos abiertos por la noche».
- **Ticket:** hereda la plantilla `point_of_sale.pos_order_receipt_header` (xpath sobre
  el bloque de pedido en borrador) y, en el ticket del puesto, oculta el subtotal (`pos_order_receipt`,
  `td[@name='subtotal']`), el CUIT (`company_info_receipt`, `td[@name='company_info_vat']`) y
  «Con la tecnología de Odoo» (`pos_order_receipt_footer`, `div[strong='Odoo']`); precio unitario opcional por puesto (`pos.config.comercio_ticket_unitario`: no / siempre / si suma; muestra el `standard-unit-price` estándar de Odoo), la tabla de `company_info_receipt` (17/11: el puesto va arriba, `span[@t-out=formated_date_order]` + «Puesto: …»; logo `div[@name='logo']/img` en `w-30`; al imprimir 390 px (6 px de margen izquierdo) y letras al 76 % (ancho útil medido ~400 px) (con `zoom` salía en blanco en Chrome de Windows) para que entre en los 72 mm de la TM-T88V); en el
  encabezado, «Recibo proforma», `cashier_name` y `partner_info`; en las líneas, el precio
  por unidad (`standard-unit-price`) y la cantidad (`span.qty`, kilos debajo del nombre si
  es pesable); `@page { margin: 0 }` en `pos_order_receipt_style`.
- **JS del POS (parches, lo más frágil):**

  | Pieza de Odoo | Qué se cambia |
  |---|---|
  | `PosStore` (`@point_of_sale/app/services/pos_store`) | `setup` + acciones propias (imprimir/abrir pedido) |
  | `BarcodeReader._scan` | leer el QR del pedido |
  | `GeneratePrinterData.generateReceiptData` | QR y número en el ticket (sin QR si se cobra en la registradora); en el puesto, sin IVA (`extra_data.prices.taxes`) ni CUIT ni marca de Odoo; cantidades y kilos (`lines[i].comercio_cantidad` / `comercio_pesada`) |
  | `DevicesSynchronisation.constructOrdersDomain` | qué pedidos sincroniza cada caja |
  | `PosAccessRightPlugin.canOpenRegister` / `canCloseSession` | quien atiende el puesto puede abrir y cerrar |
  | `OrderPaymentValidation.validateOrder` | «Pedido ya cobrado» con dos cajas |
  | `LoginScreen.logoUrl` | logo en color de la empresa (`/web/binary/company_logo`) en la pantalla de entrada |
  | `LoginScreen.setup` + `BarcodeReader.exclusiveCbMap` / `cbMaps` | **temporal**: suelta el lector que `pos_hr` dejaba tomado para las tarjetas de cajero después de entrar con el PIN (error de la imagen `20.0-20261015`, ya corregido en 20.0 con `useBarcodeReader`). Al actualizar la imagen, si `pos_hr/…/login_screen.js` usa `useBarcodeReader`, borrar `lector_tras_ingreso.js`. Prueba: `tests/e2e/pos_escaneo_producto.py` |
  | Plantillas `point_of_sale.ActionpadWidget` y `point_of_sale.ProductScreen` | botón «Imprimir pedido» en lugar de «Pago» (xpath por clases `pay-order-button`, `pay-button`) |

  También usa `TextInputPopup`, `makeAwaitable`, `Domain`, `AlertDialog`.

## `comercio_pos_balanza_systel`

Depende de `point_of_sale` (y por ella de `iot_webserial`, que en Odoo 20 trae el
manejo de WebSerial; **si cambia o deja de venir con el POS, este módulo se rompe**).

- **Campos propios:** `pos.config.comercio_balanza_numero`, `comercio_pesaje_automatico`
  (y sus espejos `pos_…` en `res.config.settings`).
- **Ajustes:** hereda `point_of_sale.res_config_settings_view_form`, ubicándose después
  del ajuste `iot_webserial.connect_web_serial_scale`.
- **JS del POS:** parche de `ScaleScreen` (`setup`, pesaje automático) y una interfaz
  propia sobre `ScaleInterface` (`connectToScale`, `_readWeight`, `hardwareTare`,
  `isWeightValid`); usa `WebSerialDevice` de `@iot_webserial/web_serial_device`.
  **Saca del registro `electronic_scales` la balanza estándar `web_serial`** (Toledo) del
  POS (19/10): si la Cuora no contestaba, el POS probaba esa en el mismo puerto y una
  falla ahí no lo dejaba abrir. Depende de esa clave del registro; si Odoo la renombra,
  vuelve a probarse la Toledo (no se rompe, pero vuelve el riesgo).
- **Sin pesaje automático** (17/11): lectura en vivo cada 250 ms (`scale.readWeight`) sin agregar;
  «Pedido» o Enter (`useHotkey` de `@web/core/hotkeys/hotkey_hook`) confirman.
- **«Escribir el peso»** (17/11): botón en la pantalla de la balanza (hereda la plantilla Owl
  `point_of_sale.ScaleScreen`, `//t[@t-set-slot='footer']/div`) que abre `NumberPopup`
  (`@point_of_sale/app/components/popups/number_popup/number_popup`) y entrega el peso con
  `props.getPayload`, como `confirm()`.
- **Backend:** widget propio «Conectar balanza Systel» (registro `view_widgets`).
- **Fuera de Odoo:** protocolo de la Cuora (115200 8N1, trama `[1, 1, XOR]`); requiere
  HTTPS en el local (ADR 0013).

## `comercio_catalogo`

Depende de `product`, `mail`, `account`. App «Costos y precios» (antes «Listas de proveedores»), sección «Listas de proveedores».

- **Modelos propios:** `comercio.lista.proveedor`, `comercio.lista.importacion`,
  `comercio.lista.importacion.linea`, asistente `comercio.importar.lista.wizard`.
  Permisos en `security/ir.access.csv` (formato de Odoo 20) y grupos propios.
- **Herencias:** `product.category.comercio_controla_stock` (+ vista
  `product.product_category_form_view`); `product.template.create` (código de barras `20…`
  y referencia interna automáticos, P-007; el último número usado se busca con SQL en
  `product_product` **y** `product_template`, porque al archivar una variante Odoo 20 le borra los
  códigos y la plantilla los conserva) y `product.template.write` (costo manual, P-044).
- **Odoo que usa:** `mail.thread`, `mail.alias.mixin.optional` (recibir listas por
  correo: `_alias_get_creation_values`, `message_update`), `product.supplierinfo`
  (precios por proveedor con fechas: historial).
- **Costo del producto** (P-044): `catalogo.odoo_api.actualizar_costos` escribe
  `product.template.standard_price` con el precio por unidad (`price_discounted`,
  `min_qty` ≤ 1) vigente más barato de `product.supplierinfo` al aplicar o deshacer, y en
  la tarea «Listas de proveedores: costo de los productos». Campo propio
  `product.template.comercio_costo_manual` (vista heredada de
  `product.product_template_form_view`, xpath `//div[@name='standard_price_uom']`).
  **Pisa `product.template.write`:** escribir `standard_price` sin la marca lo vuelve
  manual. Depende de que Odoo guarde el costo de un producto nuevo con un `write` interno
  dentro de `create` (por eso el contexto `comercio_creando`); si eso cambia, revisar. Depende de esos dos campos y del método de
  costo «estándar»: con valuación automática del stock, cambiar el costo genera asientos
  de revalorización (revisar con el contador si se activa).
- **Dos precios del proveedor:** campos propios en `product.supplierinfo`
  (`comercio_precio_mayor`, `comercio_cantidad_mayor`, `comercio_escala_de_id`); pisa
  `create`/`write` de `product.supplierinfo` para mantener una segunda fila nativa con
  `min_qty` = cantidad por mayor. Depende de que Compras elija el precio por `min_qty`
  (`_select_seller`). Las vistas y búsquedas propias excluyen esas filas.
- **Listas en partes y `.xls`** (19/10, 20.0.1.4.0): campo propio
  `product.supplierinfo.comercio_lista_id` (qué lista cargó cada precio; las bajas de una
  lista solo miran sus precios cuando el proveedor tiene varias) y `parte` en la lista.
  Los `.xls` se leen con **`xlrd`**, que viene en la imagen de Odoo 20 (2.0.1; lo usa
  `base_import`): si una imagen futura no lo trae, el `.xls` da error al leerse.
- **Catálogo del proveedor** (19/10, 20.0.1.5.0, P-048): campos propios en la fila
  (`registrado`, `categoria_id`) y en la importación (`cant_catalogo`); orden de filas
  «lo nuestro primero». **Pisa `product.category.create`**: quien no es administrador de
  productos solo crea con nombre y madre (permiso `cr` propio sobre `product.category`), y
  nadie (salvo `su`) crea una categoría con el mismo nombre que otra bajo la misma madre.
- **Buscar producto** (19/10, 20.0.1.6.0): menú sobre las filas de la última lista de
  cada proveedor (`de_lista_vigente`, búsqueda calculada con `_vigente_de`); texto
  normalizado guardado en la fila (`texto_busqueda`, `catalogo/busqueda.py`) para buscar
  palabras por su comienzo y números enteros en cualquier orden.
- **Editar filas desde la importación** (19/10, 20.0.1.7.0): el formulario guarda la
  categoría o la decisión de una fila escribiendo la importación con comandos `UPDATE`
  sobre `linea_ids`; `ComercioListaImportacion.write` solo acepta eso y lo pasa al `write`
  de la fila (con sus controles). Un «nuevo» también se puede unir a un producto («Es el
  mismo que»; `_coincide` espera vincular/actualizar con la decisión «es_el_mismo»).
- **Listas en PDF** (19/10, 1.8.0): `catalogo/pdf.py` lee el texto con `pdfminer` (viene con
  Odoo) y arma la tabla por posición; `lista_proveedor._tabla_de_documento` la convierte en
  CSV (`convertir.tabla_a_csv`) y el original queda en `archivo_original`. `leida_con_ia`
  saca las filas de lo automático. PDF y foto solo a mano (no por correo ni link).
- **Excel con varias hojas** (20/10, 1.11.0): `convertir.hojas` cuenta las filas con datos
  de cada hoja; el asistente (`_onchange_hojas`, modelo transitorio
  `comercio.importar.lista.hoja`) las ofrece, reconoce la parte existente por hoja o
  nombre de parte y `_importar_hojas` crea las que faltan y simula una importación por hoja.
- **Unidad de compra del proveedor** (20/10, 1.10.0, P-053): se apoya en las unidades de
  Odoo 20 (`uom.uom.relative_uom_id` / `relative_factor`, `parent_path`) y en
  `product.supplierinfo.uom_id`. `odoo_api.unidades` arma la familia de cada unidad («u»,
  «kg», «m», «l») subiendo a la raíz; `sacar_foto` marca `unidad_propia` en los precios
  cuya unidad no es la del producto. El motor guarda ese precio tal cual (sin dividir la
  caja) y conserva `uom_id` en el historial, el vínculo, deshacer y la fila por mayor
  (`COPIADOS`); si la unidad de la lista no es de la familia del producto, la fila va a
  revisar con el producto, y la línea tiene `unidad_compra_id` (se crea desde el
  desplegable; permiso de creación de `uom.uom` para «Costos y precios»). Supuesto de
  Odoo: `price_discounted` del precio del proveedor ya viene convertido a la unidad del
  producto (lo usa el costo, verificado en el lab).
- **Asistente de importación:** la propia empresa (`ref_company_ids`) no se ofrece ni se
  acepta como proveedor.
- **Tareas programadas:** «Listas de proveedores: actualización automática», «… aplicar
  en segundo plano», «… costo de los productos» y «… recalcular las listas en dólares»
  (1.24.0).
- **Del precio de la lista al costo (1.24.0, ADR 0029):** `catalogo/costo.py` (Python puro);
  modelo `comercio.lista.regla` (descuentos por familia y por producto). Dólar: lee
  `res.currency.rate` del USD (`res.currency._convert`) y, si falta la del día, llama a
  `res.company.update_currency_rates()` de `currency_rate_live` (Enterprise, proveedor
  «[AR] ARCA» de `l10n_ar_edi`, que necesita el certificado). IVA del producto:
  `product.template.supplier_taxes_id`. Productos nuevos con el IVA de la columna: `odoo_api.aplicar`
  busca los `account.tax` «IVA N%» de venta y compra de la localización (por nombre y alícuota).
  «Recalcular costos» reimporta el último archivo.
  «Corregir» una fila con problema (1.26.0): `_corregir` reescribe su `datos` y `_replanificar`
  vuelve a simular solo esa fila con el mismo motor (`_plan` con `lista_entera`).
  Pantalla «Dólar» (1.25.0): lista de `res.currency.rate` del USD (`inverse_company_rate` =
  pesos por dólar) con permiso para «Costos y precios» y el botón «Recalcular listas en
  dólares».
- **Motor:** `addons/comercio_catalogo/catalogo/` (Python puro, sin Odoo; lo comparte
  `integrations/catalogo`). Tests en `make test`.

## `comercio_pos_categorias`

Depende de `point_of_sale` y `comercio_catalogo_ia`. Asistente transitorio
`comercio.pos.categorizar` (+ `.linea` con las sugerencias) y dos `ir.actions.server` con
`binding_model_id = product.template` («Categorizar con IA», «Categorizar a mano»; grupo
`point_of_sale.group_pos_manager`). Escribe solo `product.template.pos_categ_ids` (campo de
`point_of_sale`), con `sudo` porque el encargado del POS solo lee productos; queda el
usuario en el chatter. Antes del `sudo`, `check_access("read")` con los permisos del usuario
sobre productos y categorías, y las sugerencias tienen que ser de los productos del asistente
(revisión de seguridad del 22/10).

- **Núcleo:** `ia/categorizar.py` (sin Odoo; tests en `make test` cargando
  `comercio_catalogo_ia/ia/verificar.py` con el nombre `odoo.addons…`). Reutiliza de ahí
  `llamar_gemini` (con su `ESQUEMA`), `pedir`, `Consumo`, `ErrorIA` y `_clave`, y la
  configuración `_configuracion()` de `comercio_catalogo_ia/models/importacion.py`.
- El asistente se abre con `context.dialog_size = extra-large`.
- Vistas (1.1.0): hereda `point_of_sale.product_template_tree_view_point_of_sale` (mueve
  `pos_categ_ids` al lado de `name`, `position="move"`, y la deja visible) y
  `point_of_sale.product_template_search_view_pos` (filtro «Sin categoría del PdV» después de
  `filter_to_availabe_pos`, en grupo propio).
- **JS del POS** (1.2.0, `static/src/app/orden.js`): `PosStore.orderProductBySequenceAndFav`
  (sin búsqueda: favoritos y después nombre con `localeCompare`, sin `pos_sequence`) y
  `PosAccessRightPlugin.canSortProducts` → `false` (sin reordenar arrastrando).

## `comercio_catalogo_ia`

Depende de `comercio_catalogo`. Campos propios en `comercio.lista.importacion.linea`
(`ia_veredicto`, `ia_producto_id`, `ia_confianza`, `ia_motivo`) y botones en sus vistas
(herencia de `importacion_linea_list` e `importacion_form`). Usa `_aplicar_por_importacion`,
`_exigir_vigente` y las decisiones «es_el_mismo»/«es_nuevo» del módulo base.

- **Fuera de Odoo:** API de Gemini (`generativelanguage.googleapis.com/v1beta`,
  `generateContent` con `responseSchema`), por `urllib`. Clave y modelos por variables de
  entorno del contenedor (`GEMINI_API_KEY`, `GEMINI_MODEL`, `GEMINI_MODEL_RESPALDO`).
- **Núcleo:** `ia/verificar.py` (sin Odoo; tests en `make test`).
- **Qué revisa** (20.0.1.2.0): posibles duplicados (sus candidatos), filas «nuevo» (los
  3 productos nuestros más parecidos con un umbral más bajo que el motor:
  `similitud.Buscador` con `UMBRAL_AMPLIO`; sin ninguno, «Es otro» sin consultar) y filas
  ya unidas (`producto_id`: ¿es el mismo?). Hasta `MAXIMO_POR_VEZ` filas por clic, en
  tandas de `TANDA` mandadas en paralelo (`EN_PARALELO`, 1.3.2: cada pedido tarda ~25 s). Filtros
  «La IA duda» y «La IA dice que ya lo tenemos».
- **Lee listas en foto o PDF escaneado** (1.3.0): `ia/leer.py` manda cada página (PDF partido
  con `pypdf`, viene con Odoo) a Gemini con un esquema «filas de celdas» y las une; pisa
  `comercio.lista.proveedor._tabla_de_documento`. Reintentos compartidos: `verificar.pedir`.

## `comercio_precios`

Depende de `comercio_catalogo` (usa su `costo_por_unidad`) y `account`. Instalado desde
`config/onpremise/00-modulos.yaml`.

- **Campos propios:** en `product.category`: `comercio_margen`, `comercio_base`,
  `comercio_proveedor_base_id`, `comercio_iva_venta_id`, `comercio_redondeo`; en
  `product.template`: `comercio_precio_calculado`, `comercio_precio_detalle`,
  `comercio_precio_manual`, `comercio_precio_desactualizado` (guardado),
  `comercio_etiqueta_pendiente`.
- **Pisa:** `product.template.create`/`write` (precio manual y recálculo al cambiar costo,
  categoría o impuestos), `product.category.write` (recalcula su rama) y
  `product.supplierinfo.create`/`write`/`unlink` (recalcula el sugerido).
- **Odoo que usa:** `res.company.account_price_include` (precio con o sin IVA),
  `account.tax.amount`, `product.template.action_open_label_layout` (etiquetas).
- **Vistas:** página en `product.product_category_form_view` (dentro de `//notebook`);
  campos después de `//div[@name='list_price_per_uom_id']` en
  `product.product_template_form_view`; listas y menús propios en la sección «Precios de venta» de la app «Costos y precios».
- **Permisos:** `security/ir.access.csv` da leer y modificar (`ru`) `product.category` al
  grupo «Costos y precios», limitado en `ProductCategory.write` a los campos de la regla de
  precio (`CAMPOS_REGLA`): nombre, madre, cuentas y método de costo siguen siendo del
  administrador de productos (lo marcó la revisión de seguridad del 12/10). Las acciones de precios controlan el grupo y escriben como
  sistema (`sudo`), así no hace falta ser administrador de productos.
- **Pantalla «Márgenes por categoría»:** lista editable de `product.category` ordenada por
  `parent_path` (en Odoo 20 `complete_name` no se guarda y no sirve para ordenar).
- **Tarea programada:** «Precios de venta: recalcular los sugeridos».
- **Agregar desde una lista** (19/10, 20.0.1.3.0): pisa
  `comercio.lista.importacion._aplicar_o_encolar` para no crear productos en una categoría
  sin margen (quedarían a $1 en la caja) ni sin categoría.
- **Margen especial por producto** (19/10, 1.5.0): `comercio_margen_especial` y
  `comercio_margen_propio` en `product.template` reemplazan el margen de la regla de la
  categoría en `_comercio_calcular_precio`; el `write` deja cambiar solo esos dos campos al
  grupo «Costos y precios» (con `sudo`, mensaje en el chatter). Pantalla «Márgenes especiales»
  con «Agregar producto» (1.6.0, asistente `comercio.margen.especial.wizard`: elige los
  productos y el margen, y escribe esos dos campos por el mismo `write`). 1.8.0 (22/10):
  también la base, como en las categorías (`comercio_base_especial`,
  `comercio_proveedor_especial_id`; vacío = la del rubro), en `CAMPOS_MARGEN`. 1.9.0: al
  marcarlo arranca con lo de su rubro (onchange en la ficha y en «Agregar producto»; en el
  `write`, `_comercio_base_del_rubro` completa la base vacía; migración para los que ya
  existían).
- **Precio de venta en las filas** (1.4.0): `precio_venta` calculado en
  `comercio.lista.importacion.linea` (lo nuestro: `list_price`; lo demás: costo de la lista
  + regla de la categoría de la fila, con `calculo.precio_final`). Columna en «Buscar
  producto» y en las filas.
- **Cálculo puro:** `addons/comercio_precios/calculo.py` (tests en `make test`).

## `comercio_compras_lista_vigente`

Depende de `purchase_stock` y (desde 1.2.0) `comercio_catalogo`. Va junto con Compras.

- **Recepción → orden de compra** (22/10, 1.6.0): botón en `stock.view_picking_form`
  (`button_box`), grupo `purchase.group_purchase_user` como el de la factura del proveedor;
  `stock.picking.comercio_compra_nombre` y `action_comercio_ver_compra` desde
  `move_ids.purchase_line_id.order_id` (en Odoo 20 no existe `get_formview_action`: la acción
  se arma a mano).

- **«Enviar por WhatsApp»** (19/10, 1.3.0): `purchase.order.action_comercio_enviar_whatsapp`
  devuelve un `act_url` a `https://wa.me/<número>?text=…` (sin la API de WhatsApp Business);
  el número sale del teléfono del proveedor con `phonenumbers` (viene con Odoo) y en
  Argentina se le agrega el 9 de celular. Pasa la solicitud a «enviada».
  Desde 1.5.0 (21/10) primero abre el asistente `comercio.whatsapp.pedido` con el mensaje
  editable (como el mail); «Abrir WhatsApp» (`action_abrir`) arma el link con ese texto.
- **«Agregar al pedido»** (19/10, 1.2.0): `comercio.lista.importacion.linea.action_agregar_a_pedido`
  suma el producto a la última `purchase.order` en borrador del proveedor (o la crea) con
  la cantidad mínima vigente; el precio lo calcula Compras al crear la línea. Botones en
  `comercio_catalogo.catalogo_busqueda_list` e `importacion_linea_list` (grupo Compras).
  Desde 1.4.0 la línea sale en la unidad del proveedor (`uom_id` del precio vigente: 1 caja,
  no 1 kg).

- **Campos calculados:** en `purchase.order.line`: `comercio_aviso_lista`,
  `comercio_aviso_minimo`, `comercio_mas_barato`; en `purchase.order`:
  `comercio_mas_barato_resumen`.
- **Métodos de Odoo que usa o pisa (internos, revisar primero):**
  - `product.product._search_sold_by_vendor` (filtro «Proveedor» del catálogo de compras).
  - `product.product._get_filtered_sellers` y `purchase.order.line._get_seller_info`,
    `_get_select_sellers_params` (cómo elige Odoo el precio del proveedor).
  - `stock.picking._action_done` (tarea al recibir algo fuera de lista o bajo el mínimo).
- **Supuesto de Odoo 20 del que depende:** sin precio de proveedor para la cantidad, la
  línea toma el costo del producto (`purchase.order.line._compute_price_unit_and_date_planned_and_name`).
- **Vista:** hereda `purchase.purchase_order_form` (xpath sobre `//notebook` y las
  columnas de `order_line` después de `price_total`).

## `comercio_factura_proveedor`

Depende de `purchase`, `comercio_catalogo`, `comercio_precios` y `comercio_catalogo_ia`.
Modelo propio `comercio.factura.linea` (lo leído de cada factura, pestaña «Leído de la
factura» en el formulario de `account.move`) y botón «Leer factura».

- **Piezas de Odoo que usa:** `account.move._get_edi_decoder` (el decodificador de adjuntos
  de Contabilidad; prioridad 20, más que la digitalización de Odoo) y
  `_get_import_file_type` (reconoce JPG/PNG/WEBP aunque no esté `account_invoice_extract`).
  Corre al subir con `account.journal.create_document_from_attachment` y con «Subir factura»
  de la orden de compra (`purchase.order.action_create_invoice` con adjuntos). Campos
  `l10n_latam_document_type_id` / `l10n_latam_document_number` (localización argentina),
  `l10n_ar_afip_responsibility_type_id` del proveedor y la referencia
  `l10n_ar.res_IVARI`.
- **Núcleo sin Odoo:** `factura/leer.py` (tabla de artículos de un PDF con texto, datos
  generales, respuesta de la IA) y `factura/cuit.py`; tests en `make test`. Usa el lector
  posicional de las listas (`comercio_catalogo/catalogo/pdf.py`) y, para fotos, el cliente
  de Gemini de `comercio_catalogo_ia` (`verificar.pedir`, `llamar_gemini`).
- **Productos:** «Agregar» usa `comercio.lista.importacion.linea.action_aplicar` (el
  mismo camino que «Buscar producto»); «Crear producto» crea `product.template` con
  `seller_ids` y llama a `_comercio_actualizar_costo`.
- **Config:** `config/onpremise/53-sin-digitalizacion-odoo.yaml` apaga la digitalización de
  Odoo (`extract_*_digitalization_mode`, campos de `account_invoice_extract`, Enterprise).
- **Pie de la factura (1.8.0):**
  - Las percepciones se ponen editando `account.move.tax_totals` (su inverso
    `_inverse_tax_totals`, el mismo de la pantalla) sobre los impuestos fijos de percepción de
    `l10n_ar`. Se eligen por `account.tax.group.l10n_ar_tribute_afip_code`: 07 = IIBB, buscado
    por el nombre de la provincia; 06 = IVA; 09 = Ganancias.
  - El IVA «No gravado» se elige por `l10n_ar_vat_afip_code = 1`; hace falta por la validación
    `_check_argentinean_invoice_taxes`.
  - `_compute_release_to_pay` de `account_3way_match` (ahora dependencia del módulo) se extiende:
    ignora las líneas `comercio_extra` y pone Excepción si el total no da el del proveedor.
  - `_compute_is_purchase_matched` de `purchase` («Coincidencia de órdenes de compra») tampoco
    cuenta las líneas `comercio_extra`.
  - Lee los renglones con posiciones de `comercio_catalogo/catalogo/pdf.py`
    (`renglones_desde_pdf`).
- **Compras sin factura (1.9.0, ADR 0023, `models/sin_factura.py`):**
  - Campo `account.journal.comercio_sin_factura`.
  - Saca los impuestos en el diario sin factura con overrides de `account.move.line.create` y
    `_compute_tax_ids`, `account.move.write` (cambio de diario) y `_post` (no deja confirmar con
    impuestos).
  - El botón «Sin factura» llama a `purchase.order.action_create_invoice` con `default_journal_id`.
  - El menú es una acción de servidor que abre `account.action_move_in_invoice_type` con
    `default_journal_id`, para que «Subir» (`account_file_uploader`) y «Nuevo» usen ese diario.
- **Ajuste de percepciones:** después de editar `tax_totals` se invalida y se recalcula
  `_compute_amount`. Si no, el «Cantidad por pagar» (`amount_residual`) del borrador quedaba con
  la percepción en $ 1.

## `comercio_codigos_fabrica`

Depende de `comercio_catalogo` (ADR 0025).

- **Piezas de Odoo que usa:** `product.uom` (código de barras por producto y unidad; en Odoo 20
  reemplaza al empaque y el POS lo carga y lo busca al escanear: `product_screen.js`,
  `pos_store.js`). El `20…` viejo se guarda ahí con la unidad del producto; primero se cambia el
  `barcode` del producto (Odoo no deja que un alternativo repita el principal).
- **Backend:** `product.template.comercio_codigo_fabrica` (calculado con `inverse`, para escanear en
  la lista editable), `comercio_sin_codigo_fabrica`, `comercio_codigos_alternativos`. Valida con
  `normalizar` del motor. `write` como sistema para el grupo «Costos y precios» si solo toca esos
  campos.
- **Numeración:** extiende `_comercio_ultimo_numero` de `comercio_catalogo` para mirar
  `product_uom.barcode`.

## `comercio_cierre_z`

Depende de `l10n_ar_reports`, `comercio_pos_pedido_qr` y `comercio_catalogo_ia` (ADR 0038).

- **Cierre Z** (`comercio.cierre.z`, `comercio.cierre.z.cobro`): los cálculos y controles están en
  `cierre/leer.py` (sin Odoo, `tests/test_cierre_z.py`). Al confirmar crea un `out_invoice` con
  documento 83 en un diario `l10n_ar_afip_pos_system = CF`, número `PPPPP-<primer tique>`; con
  impuestos «IVA incluido» (la empresa vende así) el precio de la línea es neto × (1 + alícuota)
  para que la base dé el neto exacto, y el IVA impreso se pone por `tax_totals` (el inverso de
  Odoo solo toca la línea de impuesto). Cobros con `account.payment.register`.
- **Libro IVA:** `account.move.comercio_tique_hasta` y la herencia de
  `_vat_book_get_REGINFO_CV_CBTE`, que reemplaza las posiciones 36–56 (número hasta) del renglón.
  Si Odoo cambia el formato del TXT, la prueba `make e2e-cierre-z` lo detecta.
- **Puestos:** después de `_validate_session_accounting`, si todos los pagos de la sesión son de
  un `comercio_metodo_registradora_id`, anula sus `account.payment` (`pos_session_id`) y revierte
  `sale_move_ids`/`refund_move_ids` con `_reverse_moves(cancel=True)` (sin copiar
  `pos_session_sales_id`). Bloquea `_generate_invoice_after_session_closing` en esas sesiones.
- **Foto:** `fields.Binary(attachment=True)` en Odoo 20 se lee como `BinaryValue` (`.content`).

## `comercio_pos_factura`

Depende de `point_of_sale` y `l10n_ar_pos` (ADR 0024).

- **Piezas de Odoo que usa:**
  - En la pantalla de pago, el botón nativo `js_invoice` (`toggleIsToInvoice`); `l10n_ar_pos` lo
    marca al montar la pantalla.
  - Hereda `point_of_sale.PaymentScreenDue`: un marcador oculto `comercio-sin-factura` y SCSS con
    `:has()` que pone una franja de color al costado de `.payment-screen`.
  - Hereda `point_of_sale.PaymentScreenButtons`: el texto «Factura».
  - El getter usa `pos.isArgentineanCompany()` e `isForcedToInvoice`.
- **Backend:** `pos.order.comercio_factura_odoo` (guardado; depende de `account_move.state` y de
  `journal_id.l10n_latam_use_documents`). Filtros y columna en `point_of_sale.view_pos_order_filter`
  y `view_pos_order_tree`; acción y menú «Ventas sin factura de Odoo» en
  `point_of_sale.menu_point_of_sale`.
- **Facturar con CAE (1.1.0):**
  - Extiende `pos.order._prepare_invoice_vals`: con el contexto `comercio_diario_fiscal`, usa el
    diario electrónico en vez de `config_id.journal_id`. Llama a `action_pos_order_invoice`, que
    también cubre la caja cerrada (`_generate_invoice_after_session_closing`).
  - Si la venta ya tiene una factura en un diario sin documentos: `button_draft`, `name = "/"`,
    cambio de diario, `l10n_latam_document_type_id` y `action_post` (pide CAE).
  - Oculta `action_pos_order_invoice` (formulario) y `action_create_invoices` (lista, asistente
    `pos.make.invoice`): los dos usan el diario del punto de venta. En su lugar, el botón propio.
  - Al pasar un comprobante interno a factura fiscal, fecha y vencimiento quedan en hoy. ARCA rechaza
    una fecha anterior a la última autorizada (error 10016).
- **Libro IVA:** no se toca. `l10n_ar_reports` ya filtra por `l10n_latam_use_documents`.
- **Lab:** `infra/scripts/lab-arca-homologacion.py` pone `journal_id` de `iac.pos_caja_1/2` en el
  diario FE1. En Odoo 20 el POS factura en `config.journal_id`; no hay `invoice_journal_id`.

## Fuera de los módulos

- **`src/odoo_iac`:** habla con Odoo por **JSON-2** (`/json/2/<modelo>/<método>`, Odoo
  19+). Usa `fields_get`, `search_read`, `create`, `write`, `default_get`/`execute` de
  `res.config.settings`, `ir.module.module.button_immediate_install` y `ir.model.data`
  (los xml_id `iac.*`). Los campos imagen/binarios se leen como `{'content': base64,
  'size': …}` y se escriben con el base64 en texto (`{archivo: …}` en `config/`).
- **`config/`:** depende de nombres de campos (incluidos los propios `comercio_*`),
  xml_id de Odoo (`base.ARS`, `l10n_ar.res_IVARI`, `uom.product_uom_unit`…) y nombres de
  módulos. Si Odoo renombra algo, `make plan` falla con el campo o la referencia.
- **`infra/scripts/lab-arca-homologacion.py`** (`make lab-arca`, solo lab Enterprise):
  usa `res.company.set_demo_random_cert` y los archivos `l10n_ar_edi/demo/` (clave y
  certificados de prueba de Odoo), y los campos `l10n_ar_afip_ws_*` y
  `l10n_ar_afip_pos_*`. Si Odoo los cambia, falla al correr; se prueba con
  `make e2e-factura`.
- **Imagen y scripts del servidor** (`infra/docker/`, `infra/servidor/instalar-odoo.sh`,
  `infra/scripts/fijar-enterprise.sh`): imagen oficial `odoo:20.0-AAAAMMDD` + clon de
  `odoo/enterprise` de la misma fecha; dependen de que la imagen corra como el usuario 100 y
  PostgreSQL como el 999 (dueños de los archivos de `/etc/odoo-comercio`) y del comando
  `odoo db init`. Se prueban en una máquina virtual Debian 13 limpia.
- **Monitoreo** (`infra/docker/monitoreo/`, ADR 0028): las consultas del tablero «Negocio
  (Odoo)» (`grafana/generar_tableros.py`) y de las alertas de negocio
  (`reglas-negocio.yaml`) leen directo la base. Dependen de:
  - tablas y columnas de Odoo: `pos_order`, `pos_order_line`, `pos_config`, `purchase_order`,
    `account_move` (`release_to_pay` de `account_3way_match`), `stock_*`,
    `product_supplierinfo`, `res_users`;
  - campos de los módulos propios: `comercio_en_caja`, `comercio_precio_desactualizado`,
    `comercio_precio_variacion`, `comercio_etiqueta_pendiente`, `comercio_sin_codigo_fabrica`,
    `comercio_total_factura`, `comercio_sin_factura`, `comercio_escala_de_id`,
    `comercio_lista_*`;
  - el formato de la referencia del ticket (`pos_reference` = `AAA-<pos.config>-NNNNNN`), del
    que se saca el puesto que armó el pedido.

  El usuario `grafana_lector` solo puede leer las columnas listadas en `usuarios.sql`. Una
  columna renombrada o borrada se saltea al dar permisos, y su consulta falla en
  `make verify-monitoreo`. El tablero «PostgreSQL» depende de los nombres de métricas de
  `postgres_exporter` (fijado en v0.20.1). Con PostgreSQL 17 o más, los checkpoints pasan a
  `stat_checkpointer`.
- **Pruebas e2e** (`tests/e2e/`): usan Playwright sobre el POS y la API; dependen de
  textos y clases de la pantalla, así que también hay que ajustarlas.

---

## Al cambiar de versión de Odoo

1. Leer las notas de la versión nueva de Odoo (POS, Compras, `product.supplierinfo`,
   permisos, API) buscando cada pieza de este documento.
2. Cambiar la imagen (`lab.env`, `onprem.env.example`) y el clon de Enterprise
   (`infra/scripts/fijar-enterprise.sh`), y levantar el lab desde cero: `make lab-completo`.
   Corregir lo que falle en `config/` (campos o xml_id renombrados).
3. Por módulo, en el orden de riesgo de la tabla: subir la versión del manifiesto
   (`21.0.x.y.z`), revisar cada pieza listada arriba contra el código nuevo de Odoo y
   correr su prueba.
4. `make test lint`, `make e2e-pos`, `make e2e-catalogo`, `make lab-monitoreo verify-monitoreo` y la prueba visual
   (`docs/runbooks/prueba-visual.md`).
5. Restaurar una copia de producción en el lab (neutralizada) y probar la migración de
   datos antes de tocar el servidor.
6. Actualizar este documento (versión de Odoo y lo que cambió).

## Al cambiar un módulo

- Subir la versión del manifiesto (`20.0.x.y.z`) y actualizarlo en el lab:
  *Aplicaciones* → el módulo → **Actualizar** (o por API `button_immediate_upgrade`).
- Correr su prueba y anotar acá lo nuevo que dependa de Odoo.
- En el servidor, `make apply` no actualiza los módulos ya instalados: después del
  `git pull` va `-u all` (`docs/runbooks/instalar-servidor.md`, «Actualizar Odoo»).

## Historial

| Fecha | Cambio |
|---|---|
| 19/11/2026 | `comercio_catalogo` 1.48.1: el recordatorio diario de listas atrasadas crea la actividad sin el mail «Te asignaron…» (contexto `mail_activity_quick_update` de `mail.activity.create`); eran ~50 mails por día y agotaban Resend; 1.48.2: tampoco se crean actividades por lista atrasada (lo avisa Grafana por Discord con el total); en Odoo solo el error de una descarga automática. |
| 19/11/2026 | `comercio_catalogo` 1.49.0: botón único **Aplicar todo** (lo pendiente de productos que ya tenemos, sin tope, y lo marcado; nunca agrega productos) en lugar de «Aplicar automáticos» y «Aplicar todo lo marcado»; el tope del 10 % sale de la pantalla (queda para las listas que se bajan solas). Descuento de la lista en el asistente de importar, antes de simular (1.49.2: sin la casilla del IVA, que se revisa en la ficha). «Buscar producto»: descripción ancha y lo secundario oculto. `comercio_catalogo_ia` 1.11.0: «Revisar con IA» suma «Lo que no tenemos» (marcado si son hasta 600 filas) y sus columnas en «Buscar producto» quedan ocultas. |
| 20/11/2026 | `comercio_catalogo_ia` 1.12.0: «Agregar» revisa con la IA los productos nuevos antes de crearlos (override de `comercio.lista.importacion._aplicar`): lo seguro se une solo, lo que la IA cree que ya tenemos queda retenido (filtro «Retenidas por la IA») y un segundo «Agregar» lo agrega; lo dudoso se agrega. Sin internet (prueba de conexión de 3 s), sin clave o si la IA falla: se agrega como siempre, sin carteles (solo el log). Medido: ~13 s de IA cada 200 filas (agregarlas, ~50 s). Sale la casilla «Lo que no tenemos» de «Revisar con IA». Las e2e de listas corren con `sin_revision_ia`. |
| 20/11/2026 | `comercio_catalogo` 1.49.3: en «Importar lista», el descuento vacío no borra el que la lista ya tenía (con varias partes, como FC, el campo aparece vacío hasta elegir la parte y aceptar así lo borraba). |
| 20/11/2026 | `comercio_catalogo` 1.50.0: el código de fábrica de la lista reemplaza al propio (20…), que queda como alternativo en `product.uom` (como `comercio_codigos_fabrica`); «Deshacer» lo devuelve. Varias filas con códigos de fábrica distintos para el mismo producto pasan a «¿Es el mismo?»; un código de fábrica de otro producto va a revisar; la columna de código de barras se vuelve a buscar si la ficha no la tenía (ADR 0025, actualización). `comercio_catalogo_ia` 1.13.0: la IA no une sola dos filas de la misma lista a un producto ni una fila con otro código de fábrica. |
| 20/11/2026 | `comercio_catalogo` 1.50.1: «Importar lista» no deja usar un proveedor recién creado con el mismo nombre que otro (sin mirar mayúsculas ni espacios): avisa y usa el existente, con su ficha (caso «RHO»/«Rho»). |
| 20/11/2026 | `comercio_catalogo` 1.50.2: si la descripción se repite, una columna de presentación, envase, contenido, peso, volumen, variedad, modelo o color se suma sola a la descripción (vivero: «Tierra Mejorada» 5/10/25 dm³; también LUMINA y Chi por el color). |
| 20/11/2026 | `comercio_catalogo_ia` 1.14.0: un PDF con texto cuyas columnas no se reconocen (sin títulos, títulos repetidos por productos lado a lado, o precios que no son números) lo lee la IA en modo «productos» (código, descripción completa y precio, con títulos fijos; une nombres partidos y antepone el rubro), con las páginas en paralelo y un plazo de 2 minutos: si Google no responde, queda la lectura del texto. |
| 20/11/2026 | `comercio_catalogo` 1.50.3: «DISC.», «discontinuado», «fuera de línea» en la columna del precio = el proveedor ya no lo vende: la fila no se carga (si lo teníamos, sale como baja); «sin stock» y «consultar» siguen a revisar (Xi). |
| 20/11/2026 | `comercio_catalogo` 1.51.0: ofertas en la columna de promociones: «OFERTA: N %» es un descuento más; «NETO $ X» reemplaza el precio de lista y solo lleva los «descuentos que valen también sobre los netos» (campo nuevo de la ficha; Omega: 10 % por pago). Verificado al centavo contra la columna «Netos −10 % pago» de Omega de septiembre. |
| 20/11/2026 | `comercio_catalogo` 1.52.0: estilo del «Cargando…» de Odoo (`web.LoadingIndicator`, `.o_loading_indicator_wrap`) al medio, grande y con fondo que bloquea los clics mientras carga. `comercio_pos_categorias` 1.3.0: botones de categorías del PdV más bajos (2,75rem) y el bloque a dos filas (`.category-list`, `.category-button` de `point_of_sale`). Riesgo al actualizar Odoo: si cambian esas clases, el estilo deja de aplicarse (no rompe nada). |
| 20/11/2026 | `comercio_carteles` 1.0.0 (nuevo, solo lab): carteles de precio en A4 (ADR 0039). |
| 20/11/2026 | `comercio_precios` 1.20.0: «Redondeo por tramos» en el rubro (`comercio_redondeo_tramos`, p. ej. «10; 1000:100; 10000:500»): el múltiplo depende del precio; manda sobre «Redondear a» y se hereda de la madre. En producción: todos los rubros con esos tramos (pedido del usuario: $ 100, y $ 500 desde $ 10.000; los de menos de $ 1.000 a $ 10 para no subirlos de golpe). |
| 20/11/2026 | `comercio_pos_categorias` 1.4.0: al cambiar precio, nombre, código, categoría del PdV, IVA o disponibilidad de un producto, se avisa a las cajas y puestos abiertos con `pos.config._notify_synchronisation` (el aviso que Odoo usa para los agotados): lo toman sin recargar. Un aviso por transacción (precommit). Riesgo al actualizar Odoo: si cambia ese método, vuelve a hacer falta recargar. Prueba: `tests/e2e/pos_precio_en_vivo.py` (en `make e2e-pos`). |
| 20/11/2026 | `comercio_pos_categorias` 1.5.0 (lab; producción a decidir): parches de `PosStore` en `static/src/app/`: `sin_protector.js` (`idleTimeout` vacío: sin protector ni vuelta al PIN por inactividad), `busqueda.js` (`getProductsBySearchWord` por palabras en cualquier orden; `searchProductsFromDBDomain` con un AND de ilike por palabra; `searchProductsFromDB` sin el aviso «No se encontraron otros productos» si hay resultados en pantalla), `grilla.js` (`filterExcludedProducts`: ordena antes de cortar y muestra hasta 300) y `grilla.scss` (tarjetas sin foto más chicas). Riesgo al actualizar Odoo: son getters internos; si cambian, vuelve el comportamiento de Odoo. Prueba: `tests/e2e/pos_busqueda.py` (en `make e2e-pos`). |
| 20/11/2026 | `comercio_catalogo` 1.53.0 (lab; producción pendiente): planillas con productos lado a lado con los mismos títulos («DESCRIPCION | PRECIO | DESCRIPCION | PRECIO…», Nu) se apilan como una lista común (`apilar_lado_a_lado`); con «familia en la descripción», «LINEA X» se antepone sin la palabra «LINEA» y sin repetirla si el producto ya la trae. |
| 18/11/2026 | `comercio_pos_pedido_qr` 1.13.0: después de entrar con el PIN, el lector vuelve a agregar productos (error de Odoo 20 en `pos_hr`: todo escaneo daba «Código de barras desconocido»); prueba `pos_escaneo_producto.py` en `make e2e-pos`. |
| 11/11/2026 | `comercio_cierre_z` 1.0.0 (ADR 0038): cierre Z de las registradoras (a mano y con foto), Libro IVA con el rango de tiques, puestos sin efecto contable. |
| 27/10/2026 | Acceso desde afuera (ADR 0020): `compose.acceso-remoto.yml` (cloudflared con versión fija, `ACCESO_REMOTO=1` en `lib.sh`), `caddy/remoto.caddy` (segundo nombre: solo desde cloudflared, 404 en el gestor de bases y las API, IP real por `Cf-Connecting-IP`), `trusted_proxies` en el Caddyfile (solo la IP de cloudflared) y `configurar-acceso-remoto.sh` + `acceso_remoto_cloudflare.py`. Rutas verificadas en Odoo 20 (`rpc`, `api_doc`, `http/router.py`). |
| 27/10/2026 | Monitoreo (ADR 0028): `compose.monitoreo.yml` (Prometheus, node_exporter, postgres_exporter, blackbox, cAdvisor, Grafana, relay a Discord), `infra/docker/monitoreo/` (umbrales, reglas, tableros generados, `usuarios.sql` con permisos por columna), `pg_stat_statements` en el servicio `db` de `compose.yml`, `verificar-monitoreo.py` (`make verify-monitoreo`) y `configurar-monitoreo.sh`. Las SQL del negocio leen tablas de Odoo y campos `comercio_*`: revisarlas al actualizar Odoo. `avisar.sh` arma la tarjeta de Discord con `formato_avisos.py` (compartida con el relay); `backup-nocturno.sh` y `revisar-servidor.sh` escriben métricas para node_exporter. |
| 27/10/2026 | `infra/scripts/restore-test.sh`: valida los adjuntos con `ir.attachment._full_path(store_fname)` (método interno; en Odoo 20 `_file_read()` ya no recibe la ruta y la prueba fallaba siempre). Nuevos `infra/servidor/` de backups y avisos (ADR 0027): restic, systemd, msmtp; no tocan Odoo salvo por `backup.sh`/`restore-test.sh`. |
| 27/10/2026 | `comercio_catalogo` 1.23.6: «Buscar producto» sin la columna «Lo tenemos» (lo que tenemos ya sale en verde; el campo queda oculto para el color y el botón «Agregar»). |
| 26/10/2026 | Enterprise desde GitHub (`odoo/enterprise` 20.0, fijado a la fecha de la imagen con `fijar-enterprise.sh`) en el lab y en la imagen del servidor; `instalar-odoo.sh` arma el servidor. Probadas todas las e2e. |
| 26/10/2026 | `comercio_pos_factura` 1.1.5: sin factura de Odoo, franja de color al costado de `.payment-screen` (`box-shadow` con `:has()`) en lugar del importe en gris. |
| 26/10/2026 | `comercio_catalogo_ia` 1.3.5 y `comercio_pos_categorias` 1.2.1: los pedidos de texto a Gemini (verificar, categorizar) se cortan a los 45 s (`llamar_gemini_texto`; fotos y PDF siguen en 90 s) y cada reintento queda en el registro. Gemini tarda ~20 s aunque sea un producto; un intento colgado hacía tardar «Categorizar con IA» 130 s con un solo producto. |
| 26/10/2026 | `comercio_codigos_fabrica` 1.0.0 (ADR 0025): pantalla «Códigos de fábrica». |
| 26/10/2026 | `comercio_catalogo` 1.23.5 (motor): la sugerencia de columnas no toma como descripción una columna casi toda de números («desc» = descuento en LUMINA; en Bazar Alfa «Producto» casi vacía hacía perder 38 filas sin aviso). |
| 26/10/2026 | `comercio_precios` 1.12.0: un producto todavía en $1 (sin «Precio manual») toma el sugerido apenas lo tiene, también si el costo llegó después de crearlo («Crear producto» desde la factura del proveedor quedaba en $1). `comercio_catalogo` 1.23.4 (motor): código GS1 completo («01» + GTIN-14 + vencimiento/lote, Rho) → el código de barras de adentro; fila con código pero sin descripción ni precio = título de familia (Tau: «Adhesivo de contacto | SUPRABOND»). |
| 26/10/2026 | `comercio_precios` 1.11.0: «Diferencia chica» en «Precios a actualizar» (`res.company.comercio_diferencia_chica`, asistente `comercio.diferencia.chica.wizard`; `comercio_precio_variacion` pasa a guardarse para filtrar; `comercio_precio_cambio_chico` con búsqueda propia; vista de búsqueda con filtro por defecto «Para cambiar»). |
| 26/10/2026 | `comercio_factura_proveedor` 1.11.0: si ningún proveedor tiene el CUIT de la factura, cartel «Elegir proveedor» (asistente `comercio.factura.elegir.proveedor`: uno de la lista o uno nuevo; se le guarda el CUIT y la condición de IVA aunque sus artículos no estén en una lista, contexto `comercio_proveedor_elegido`); no se adivina por los artículos (pedido del implementador); los tipos de comprobante se recalculan después de guardarle la condición de IVA (salía «Despacho de importación» y sin número); el cartel rojo del total compara contra `comercio_total_odoo` (suma de líneas + importe de cada percepción), que cambia sin guardar (`amount_total` y las percepciones de `tax_totals` recién se actualizan al guardar). `comercio_compras_lista_vigente` 1.8.0: «Lista del proveedor» abre la lista entera, sin el filtro «Lo tenemos» (eso lo hace «Catálogo»); aviso al cambiar el proveedor de una orden con productos que no están en su lista (`purchase.order._onchange_comercio_aviso_lista`). |
| 24/10/2026 | `comercio_pos_factura` 1.1.4: el diario que llega por contexto (`comercio_diario_fiscal`) solo se usa si es el electrónico y el usuario es del grupo Facturación (revisión de seguridad). |
| 24/10/2026 | `comercio_pos_factura` 1.1.3: «Facturar con CAE» de una venta de otro día sale con fecha de hoy (daba 10016 en ARCA); en la lista reemplaza al «Crear facturas» de Odoo (asistente con el diario del punto de venta). |
| 24/10/2026 | `comercio_factura_proveedor` 1.9.2: en una factura de una orden de compra, lo que se cobra y no se pidió queda marcado «No está en la orden de compra» (antes solo bajaba la coincidencia). `infra/scripts/factura-ejemplo.py` genera la factura ficticia de la prueba visual (`data/ejemplos/facturas/`). |
| 24/10/2026 | `comercio_pos_factura` 1.1.0: «Facturar con CAE» (administración) para ventas cobradas sin factura de Odoo por error. Siempre usa el diario electrónico; también convierte el comprobante interno que hacía el «Factura» de Odoo en un puesto. Se oculta el «Factura» nativo del pedido. |
| 24/10/2026 | `comercio_pos_factura` 1.0.0 (ADR 0024): ventas de la caja con y sin factura de Odoo; `make lab-arca` deja Caja 1 y 2 con el diario electrónico FE1; `tests/e2e/pos_factura.py` en `make e2e-pos`. |
| 23/10/2026 | `comercio_factura_proveedor` 1.9.1: «Coincidencia de órdenes de compra» (`purchase_matched_ratio` de `purchase`, `_compute_is_purchase_matched` extendido) sin contar flete ni percepciones; textos «Sin factura». |
| 23/10/2026 | `comercio_factura_proveedor` 1.9.0: compras sin factura (ADR 0023). Diario con `comercio_sin_factura` (`config/onpremise/54-compras-sin-factura.yaml`), líneas sin impuestos, botón en la orden, menú, filtros y cartel. Corrige el «Cantidad por pagar» del borrador con percepciones (`amount_residual`). |
| 23/10/2026 | `comercio_factura_proveedor` 1.8.0: el pie de la factura. `factura/leer.py` tiene `Totales`, `totales_desde_renglones` y `percepciones_del_texto`, también en la respuesta de la IA. El flete va como línea con IVA y las percepciones con su impuesto `l10n_ar`, ajustado en `tax_totals`; las dos líneas llevan `account.move.line.comercio_extra`. `account.move.comercio_total_factura` guarda el TOTAL del proveedor y aparece un cartel si no coincide. `_compute_release_to_pay` extendido; depende de `account_3way_match`. `comercio_catalogo` 1.23.3: `pdf.renglones_desde_pdf`. `config/ejemplos/06-iva-compras.yaml`: las percepciones de compra van sin incluir. |
| 23/10/2026 | `comercio_factura_proveedor` 1.7.2: la orden creada desde la factura lleva la fecha de hoy (con la de la factura, anterior a la última lista, cada línea decía «No está en su lista»). |
| 23/10/2026 | Rendimiento de «Agregar» con listas grandes: `comercio_catalogo` 1.23.2 lee las filas en bloque (`_filas` con `search_read`) y busca las bajas a corregir y `_revisada` en la base en vez de recorrer las 10 000 filas; `comercio_factura_proveedor` 1.7.1 aplica todos los artículos de la factura en una sola pasada por lista. 22 artículos de FC desde la factura: de varios minutos a ~9 s. |
| 23/10/2026 | `comercio_factura_proveedor` 1.7.0: «Diferencia con su lista» (precio de la factura, bruto y neto de la bonificación, contra el `product.supplierinfo` vigente de ese proveedor en la misma unidad). |
| 23/10/2026 | `comercio_factura_proveedor` 1.6.0: «Diferencia con la orden» por línea (precio, bonificación y cantidad contra `purchase.order.line` y `qty_received`). `config/onpremise/00-modulos.yaml`: `account_3way_match` (nativo, «Se debe pagar»). |
| 23/10/2026 | `comercio_catalogo` 1.23.0: sin el cartel de Mayús + clic (se borró la vista JS `comercio_buscar_producto`; molestaba). |
| 23/10/2026 | `comercio_factura_proveedor` 1.5.0: compara lo que no coincide con nuestros productos (`similitud.Buscador`, desde 0,85) y «Verificar con IA» (`comercio_catalogo_ia.ia.verificar`); pantalla «Artículos sin producto» (`action_revisar_articulos`) con «Agregar al catálogo» en lote; «Crear orden de compra» con faltantes abre esa pantalla (o «Crear la orden igual»); lo creado desde la factura se suma a la importación vigente del proveedor (fila `vincular` aplicada, `supplierinfo.comercio_lista_id`). |
| 23/10/2026 | `comercio_factura_proveedor` 1.4.0: «Crear orden de compra» desde la factura (crea y confirma `purchase.order`, escribe `account.move.line.purchase_line_id`). `comercio_catalogo` 1.21.0/1.22.2: «Buscar producto» agrupa por producto en general, lo tengamos o no (campos guardados `clave_producto` con `busqueda.clave_producto` y `producto_general`; migración que los recalcula). |
| 23/10/2026 | `comercio_factura_proveedor` 1.3.0: menú *Compras → Órdenes → Facturas de proveedor*; el «Subir» de las órdenes de compra (`purchase.order.create_document_from_attachment`, para pedidos XML) con una factura en PDF/foto crea la factura del proveedor (contexto `comercio_facturas_leidas` para no leerla dos veces). `comercio_compras_lista_vigente` 1.7.0: botón «Lista del proveedor» junto a «Catálogo» en las líneas de la orden (`purchase.order.line.action_comercio_lista_proveedor`, hereda el `<control>` de `purchase.purchase_order_form`); «Pedir» suma a esa orden (contexto `comercio_pedido_id`). |
| 23/10/2026 | `comercio_factura_proveedor` 1.1.0: cartel «el CUIT es de otro proveedor» con botón para cambiarlo y leer de nuevo; 1.2.0: todos los artículos quedan anotados en la factura (sin producto los que no tenemos, campo `account.move.line.comercio_anotada`) y al agregarlos al catálogo la misma línea toma el producto. `config/ejemplos/06-iva-compras.yaml`: IVA de compras sin incluir (`price_include_override`). |
| 23/10/2026 | `comercio_factura_proveedor` 1.0.0 (ADR 0021). `comercio_catalogo` 1.19.0: «Buscar producto» con el cartel de Mayús + clic (vista JS `comercio_buscar_producto`, hereda `web.ListView`); 1.20.0: motor de listas probado con las 36 listas reales de ferretería (precio 0 a revisar, « + » en títulos, títulos repetidos, familias, columnas por letra, envases y cantidades con texto, monedas, sugerencia de columnas por contenido, corte de filas vacías) y «Del precio de la lista al costo» (descuentos, recargo, cotización, IVA incluido) en la lista del proveedor. `comercio_compras_lista_vigente` 1.6.1: «Pedir» sin ícono (Odoo 20 no trae `fa-shopping-cart`). |
| 22/10/2026 | `odoo_iac`: en el plan de una base nueva, una referencia a un registro de un módulo que se instala en el mismo apply (p. ej. `product.model_product_template` de «Fusionar») queda pendiente en vez de cortar (`_modules_pending`). Probado con `make lab-completo` desde cero. |
| 22/10/2026 | `comercio_compras_lista_vigente` 1.6.0: botón «Orden de compra» en la recepción (solo Compras). `config/base/06-deposito.yaml`: el depósito principal se llama como la empresa. |
| 22/10/2026 | `comercio_compras_lista_vigente` 1.5.1: «Enviar por WhatsApp» escribe cada producto con el código y la descripción del proveedor (`product._select_seller(...)["supplierinfo"]`; en Odoo 20 devuelve un dict y la descripción de la línea viene vacía), nunca con nuestra referencia interna; 1.5.2: los botones de WhatsApp sin ícono (Odoo 20 ya no trae `fa-whatsapp` y mostraba un «-»). |
| 22/10/2026 | `comercio_pos_categorias` 1.1.0: columna «Categoría del PdV» al lado del nombre en Punto de venta → Productos y filtro «Sin categoría del PdV»; 1.1.1: «Categorizar a mano» con «Reemplazar» y sin categorías las quita; 1.2.0: en el POS, favoritos primero y el resto por orden alfabético. |
| 22/10/2026 | `comercio_pos_categorias` 1.0.0: «Categorizar con IA» y «Categorizar a mano» la categoría del punto de venta desde el menú Acciones de Productos. |
| 22/10/2026 | `comercio_precios` 1.8.0: el margen especial elige también la base (costo o precio de un proveedor), como los márgenes por categoría; 1.9.0: al marcarlo arranca con el margen, la base y el proveedor de su rubro (también los que ya existían); 1.9.1: la casilla «Especial» pasa a la primera columna de «Márgenes especiales»; 1.10.0: aviso (onchange) si el proveedor de referencia no tiene el producto en su lista vigente (`_comercio_precio_de`), en el margen especial, «Agregar producto» y la categoría; «Cómo se calculó» dice «costo (X no lo tiene en su lista)». |
| 19/10/2026 | `comercio_catalogo` 1.9.0: precio por caja («24 u.») → por unidad con mínimo; «Buscar producto» con las filas sin precio al final y columna «Problema» (`sin_costo`). `comercio_catalogo_ia` 1.3.1: mensajes que explican para qué sirve la IA. |
| 20/10/2026 | `comercio_catalogo` 1.12.0: «Es otra parte» al importar; sin bajas si casi nada coincide (`MINIMO_COINCIDENCIAS`). |
| 21/10/2026 | `comercio_catalogo` 1.12.1: «Elegir varias filas» abre en «No los tenemos» si no hay nada nuestro para revisar (antes abría vacía); 1.12.2: un posible duplicado aplicado se ve verde, no naranja; 1.13.0: la columna «Categoría» muestra la del producto en lo nuestro y cambiarla cambia el producto (`categoria_mostrada_id`, con `sudo`); 1.14.0: productos con costo manual marcados en la fila («Cambio» + «· costo manual», «Costo nuevo» en azul); 1.15.0: un producto dado de baja que vuelve a la lista con el mismo código se reconoce («vuelve a la lista», `Foto.cerrados`), no sale como posible duplicado de sí mismo; 1.15.1: las filas «Sin cambios» se ven verdes (están al día), no grises; 1.16.0: la fila que vuelve se guarda como «Vuelve a la lista» (`VUELVE`, para el motor sigue siendo VINCULAR con `Accion.vuelve`), con filtro y columna «Vuelven» en las importaciones; 1.17.0: «Quitar de nuestro catálogo» (menú Acciones de las filas y de «Buscar producto»: archiva el producto, antes lo saca del POS); un producto archivado cuenta como «No los tenemos» (`registrado` depende de `producto_id.active`) y «Agregar» lo reactiva en vez de crear otro; 1.17.1: la columna «Qué pasa» se llama «Novedad»; 1.17.2: «Buscar producto» encuentra también por el código de barras y la referencia de nuestro producto (`texto_busqueda`, recalculado en `migrations/20.0.1.17.2`); 1.18.0: «Más fotos» al importar una lista en fotos: se juntan con la primera en un PDF (`fotos_a_pdf`, Pillow) que lee la IA; 1.18.1: «Más fotos» solo acepta adjuntos recién subidos por la misma persona en esa ventana y los borra sin `sudo`; hasta 10 fotos, solo JPEG/PNG/WEBP y hasta ~50 MP, mirado antes de descomprimir (revisión de seguridad). `comercio_catalogo_ia` 1.3.2: las tandas a Gemini van en paralelo; 1.3.3: el botón pasa a «Verificar posibles duplicados con IA»; 1.3.4: los errores de Gemini (cupo agotado, clave inválida, sin conexión, modelo retirado) se muestran en castellano con qué hacer (`mensaje_claro`), el detalle técnico va al registro. `comercio_compras_lista_vigente` 1.5.0: «Enviar por WhatsApp» muestra antes el mensaje para corregirlo (asistente `comercio.whatsapp.pedido`). `comercio_pos_pedido_qr` 1.6.0: «Se cobra en la registradora» (ADR 0019, P-046 temporal): el puesto da el pedido por cobrado al imprimir con «Cobrado en registradora», sin QR; baja el stock; 1.7.0: el ticket del puesto no muestra nada del IVA (ni impuestos ni subtotal), solo el total; 1.8.0: tampoco el CUIT ni «Con la tecnología de Odoo». `odoo_iac`: `{archivo: ruta}` para campos imagen (logo del ticket de los puestos, `config/imagenes/logo-ticket.png`). `comercio_pos_pedido_qr` 1.9.0: ticket del puesto sin cliente, cajero, «Recibo proforma», precio por unidad ni número repetido; kilos en lo pesado; sin encabezado/pie de Chrome; 1.10.0: la pantalla de entrada del POS muestra el logo de la empresa (`LoginScreen.logoUrl`). |
| 20/10/2026 | `comercio_catalogo` 1.11.0: Excel con varias hojas → elegir cuáles importar, una parte por hoja. |
| 20/10/2026 | `comercio_catalogo` 1.10.0 y `comercio_compras_lista_vigente` 1.4.0: las listas respetan la unidad de compra del proveedor (P-053). |
| 19/10/2026 | `comercio_precios` 1.7.0: manda el IVA del producto; el de la categoría es el IVA por defecto (`_comercio_iva`, `create`). |
| 19/10/2026 | `comercio_precios` 1.6.0: «Agregar producto» en «Márgenes especiales». |
| 19/10/2026 | `comercio_precios` 1.5.0: margen especial por producto (excepción al rubro). |
| 19/10/2026 | `comercio_catalogo` 1.8.0: listas en PDF (texto). `comercio_catalogo_ia` 1.3.0: listas en foto o PDF escaneado. `comercio_compras_lista_vigente` 1.3.0: «Enviar por WhatsApp». |
| 19/10/2026 | `comercio_precios` 1.4.0: precio de venta (o el que tendría) en las filas de las listas. `comercio_compras_lista_vigente` 1.2.0: «Agregar al pedido». `make lab-completo` e `infra/scripts/lab-listas-reales.py`. |
| 19/10/2026 | `comercio_catalogo` 1.7.0: categoría editable desde la pestaña «Filas» (arreglo), propia empresa fuera del asistente, «Agregar como nuevo», un «nuevo» se puede unir. `comercio_catalogo_ia` 1.2.0: IA también para productos a agregar y lo ya unido. `comercio_precios` 1.3.0: no se agrega a una categoría sin margen. |
| 14/10/2026 | `integrations/balanza_systel/diagnostico.py`: restaura VMIN=1 al terminar (con VMIN=0 Chrome no lee la balanza). |
| 14/10/2026 | Lab Enterprise: `lab-arca-homologacion.py` y `tests/e2e/factura_electronica.py` (CAE en homologación). |
| 12/10/2026 | `comercio_precios` 1.2.0: pantalla «Márgenes por categoría» y permisos para el grupo «Costos y precios». |
| 12/10/2026 | `comercio_catalogo` 1.3.0: la app pasa a llamarse «Costos y precios» (secciones «Listas de proveedores» y «Precios de venta»). |
| 12/10/2026 | `comercio_precios` 1.1.0: un producto nuevo sin precio toma el sugerido al crearse. |
| 12/10/2026 | `comercio_precios` 1.0.0 (ADR 0016). `comercio_catalogo` 1.2.0: dos precios del proveedor (unidad y por mayor). `odoo_iac`: los ajustes se leen con un asistente nuevo (incluye los de la empresa). |
| 12/10/2026 | `comercio_catalogo` 1.1.0: el costo del producto lo mantienen las listas (precio por unidad más barato) salvo «Costo manual» (P-044). |
| 12/10/2026 | Inventario inicial. `comercio_compras_lista_vigente` 1.1.0: aviso de cantidad mínima. `odoo_iac`: ajustes generales (`settings:`). |
