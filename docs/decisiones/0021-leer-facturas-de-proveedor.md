# 0021. Leer las facturas de proveedor nosotros (sin la digitalización de Odoo) y agregar sus productos al catálogo

- Estado: aceptado (pedido del cliente, 23/10)
- Fecha: 2026-10-23

## Contexto

En la charla del 23/10 con Daniel el cliente pidió que, al cargar la factura de un
proveedor (también la de una orden de compra), Odoo **detecte los productos, cargue los
datos y permita registrar en el catálogo los que no tenemos, desde la misma factura**.

Odoo 20 Enterprise ya trae la «digitalización de documentos» (`account_invoice_extract`):
al subir un PDF o una foto la manda a un servicio de Odoo (IAP) que la lee. **Cobra
créditos por cada factura** (en el lab, al subir la factura de FC descontó créditos y la
segunda quedó en «sin créditos suficientes»). Son unas 10 facturas por día (P-042), así
que es un costo fijo; además no busca los productos por el código del proveedor ni ofrece
crearlos desde su lista.

Las facturas que mandan los sistemas de los proveedores (FC, 13/10) son **PDF con texto**:
se pueden leer sin IA con las posiciones de las letras, igual que las listas en PDF
(`catalogo/pdf.py`). Las fotos o PDF escaneados necesitan IA; ya usamos Gemini con clave
propia (ADR 0018), mucho más barata.

## Decisión

Módulo **`comercio_factura_proveedor`** (On-Premise; depende de `comercio_catalogo`,
`comercio_precios`, `comercio_catalogo_ia` y `purchase`):

1. **Se apaga la digitalización de Odoo** (`config/onpremise/53-sin-digitalizacion-odoo.yaml`:
   «no digitalizar» en facturas de proveedor y de cliente).
2. **Lector propio** enchufado en el mecanismo nativo de Odoo para leer adjuntos
   (`_get_edi_decoder`, prioridad mayor que la de Odoo): corre al **subir** la factura
   (Compras/Contabilidad → Facturas → Subir, o «Subir factura» en la orden de compra) y con
   el botón **«Leer factura»** de una factura en borrador.
   - **PDF con texto: sin IA** (`factura/leer.py`): tabla de artículos (cantidad, código,
     descripción, precio, bonificación, importe, IVA), con el código al principio de la
     descripción o en el renglón de abajo, descripciones cortadas, varias páginas.
   - **Foto o PDF escaneado: Gemini** con la clave del servidor. Se manda solo la imagen de
     la factura. Lo leído con IA dice «leída con IA» y se revisa.
3. **Datos de la factura, solo si están vacíos:** proveedor por CUIT; el CUIT (y «Responsable
   Inscripto» si es factura A o M) se guarda en el proveedor **solo si sus artículos están
   en la lista de ese proveedor** (si se subió en otro proveedor, avisa y no lo pisa); tipo
   y número de comprobante, fecha y vencimiento.
4. **Artículos:** se buscan por el código del proveedor, el código de barras o la
   descripción exacta, en nuestros productos y en la **lista vigente** del proveedor.
   - Lo que tenemos se carga en la factura con la cantidad, el precio y la bonificación de
     la factura. Si la factura viene de una orden de compra, se completa esa línea en vez
     de duplicarla (y avisa qué líneas de la orden no vinieron).
   - **Lo demás también se anota en la factura** (23/10, pedido del cliente): sin producto,
     con la descripción, la cantidad, el precio, la bonificación y el IVA leídos, para que la
     factura quede completa. Además queda en la pestaña **«Leído de la factura»**: **Agregar** (está en su lista:
     se crea como en «Buscar producto», con la categoría elegida y su precio de venta por
     margen), **Crear producto** (no está en ninguna lista: con la descripción, el código y
     el precio de la factura) o **Es este** (ya lo tenemos con otro nombre: se elige y se le
     agrega este proveedor, así la próxima vez se reconoce solo). Lo parecido se sugiere
     («¿Es este?»), nunca se carga solo. Al agregarlo, la línea anotada toma el producto (no se
     duplica; si es de la orden de compra, se usa esa línea).
   - En Odoo 20 la app Compras no tiene menú de facturas (están en Contabilidad): se agrega
     *Compras → Órdenes → Facturas de proveedor*. El **«Subir»** de la lista de órdenes de
     compra (Odoo lo usa para importar pedidos electrónicos en XML, que acá no se usan) con una
     factura en PDF o foto crea la factura del proveedor (se lee una sola vez).
   - **Crear orden de compra** desde la factura (23/10, pedido del cliente): cuando llega la factura
     sin pedido en Odoo, crea y confirma la orden con sus productos, cantidades y precios (sale la
     recepción del stock) y une las líneas de la factura a ella (`purchase_line_id`).
   - Lo que no coincide por código se compara con **nuestros productos** (motor de similitud de
     las listas, desde 85 %) y queda «¿Es este?»; a pedido, **Verificar con IA** (como en las
     listas). Pantalla **«Artículos sin producto»** para resolverlos de a varios (**Agregar al
     catálogo** decide solo: desde la lista del proveedor o como producto nuevo). «Crear orden de
     compra» con faltantes no da error: abre esa pantalla (o crea la orden sin ellos).
   - Un producto que vino en la factura y no estaba en la lista del proveedor **se suma a su lista
     vigente** (fila «agregado desde la factura»): aparece en «Buscar producto» y «Lista del
     proveedor». Si la próxima lista no lo trae, se da de baja como cualquier otro.
   - **Diferencias con la orden** (factura subida desde la orden de compra): la factura manda en
     la factura; cada línea con otro precio, otra bonificación o más cantidad que lo recibido queda
     marcada («Diferencia con la orden»). Se instala el control nativo **`account_3way_match`**
     (Enterprise): «Se debe pagar» Sí / No / Excepción en cada factura de proveedor.
   - **Diferencia con su lista**: con o sin orden, cada artículo se compara con el precio vigente
     del proveedor (neto y bruto de la bonificación); avisa «¿lista vieja?» o «¿un descuento?». No
     cambia el costo (P-044); si conviene actualizarlo desde la factura, P-059.
   - Si el CUIT de la factura es de **otro proveedor** que el elegido (se subió en el equivocado),
     un cartel arriba de la factura ofrece cambiarlo y leerla de nuevo.
5. **No cambia costos ni precios de venta por su cuenta**: el costo lo siguen moviendo las
   listas (P-044). Crear un producto o agregarle el proveedor sí recalcula su costo, como
   cualquier precio de proveedor nuevo.
6. **El pie de la factura** (23/10, probando el circuito completo con FC: se pagaban $ 62.153
   de menos). Se lee el subtotal, el flete, el neto, el IVA, las percepciones y el TOTAL:
   - en el PDF, por la posición de cada importe debajo de su título o con «Título: importe»;
   - en la foto, lo lee la IA.
   
   El **flete** va como una línea con su IVA. Cada **percepción** va con su impuesto de
   `l10n_ar`, que es fijo de $ 1: se pone el importe en el resumen de impuestos, como se haría a
   mano en la pantalla (`tax_totals`). Viaja en una línea sin importe con IVA «No gravado»,
   porque la validación argentina pide un IVA por línea. Ni el flete ni las percepciones pasan a
   la orden de compra, y no ponen la factura en excepción. Si el total de Odoo no da el impreso
   (más de $ 1 de diferencia), aparece un cartel rojo y «Se debe pagar» queda en **Excepción**.
   En el lab, las percepciones de compra van «sin incluir», como el IVA
   (`config/ejemplos/06-iva-compras.yaml`). La cuenta contable de cada percepción la confirma el
   contador (P-034).

## Alternativas consideradas

- **Digitalización de Odoo (IAP):** nativa, pero cobra por factura y no resuelve lo que
  pidió el cliente (buscar por código del proveedor y crear desde su lista). Descartada.
- **Todo con Gemini (también los PDF):** más simple, pero paga por cada factura algo que se
  lee bien sin IA. Queda solo para fotos y escaneados.
- **Un lector por proveedor (plantillas):** más preciso con formatos raros, pero hay que
  mantener una plantilla por proveedor. Se empieza genérico; si un proveedor no se lee
  bien, se evalúa.

## Consecuencias

- En el lab, «precios con IVA incluido» (de venta, P-030) hacía que Odoo tomara también los
  precios de compra con IVA incluido y achicara el neto de la factura: los IVA de compra van
  «sin incluir» (`config/ejemplos/06-iva-compras.yaml`; a confirmar con el contador, P-034).

- Probado con la factura real de FC (26 artículos, 2 páginas): el PDF se lee completo
  sin IA y los artículos suman exactamente el subtotal; como foto (Gemini) lee bien la
  página en ~9 s. `make e2e-factura-proveedor` lo prueba con una factura ficticia.
- La factura de proveedor en Odoo sigue siendo decisión de la administración (P-047): esto
  la hace práctica, no la vuelve obligatoria.
- Depende de piezas de Odoo que pueden cambiar al actualizar (`_get_edi_decoder`,
  `_get_import_file_type`, `create_document_from_attachment`): anotado en
  `docs/codigo-propio.md`.
- Si se desinstala `account_invoice_extract`, las fotos se siguen reconociendo (el módulo
  identifica JPG/PNG por su cuenta).
