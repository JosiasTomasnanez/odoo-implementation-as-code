# Demo de facturación (laboratorio)

Para entender la facturación de Odoo y mostrársela a la administración. Todo en el **lab**,
contra **ARCA homologación**: las facturas tienen CAE de prueba y **no valen** (nada llega a
ARCA de verdad). Duración: unos 20 minutos.

Cómo se cargan los datos reales (CUIT, certificado, bancos): `datos-fiscales-y-bancos.md`.

## Antes de empezar: 5 ideas

1. **La factura no es el papel.** La factura existe cuando ARCA la autoriza y devuelve un **CAE**
   (un número de autorización). El papel (ticket o A4) es solo una forma de mostrarla.
2. **¿Cuándo se hace?** Al cobrar en la caja con el botón **Factura** marcado: Odoo le pide el
   CAE a ARCA en ese momento, en un segundo. No hace falta escanear nada.
3. **¿A o B?** Odoo la elige solo según el cliente. Sin cliente (Consumidor Final) sale **B**.
   Con un cliente Responsable Inscripto con CUIT sale **A**.
4. **El QR del ticket** es el de ARCA: sirve para que cualquiera verifique que la factura existe.
   Escanearlo no factura nada.
5. **Odoo y la registradora conviven.** Con **Factura** desmarcado, la venta queda en Odoo
   (stock y caja) pero el comprobante lo hace la registradora. Odoo no la mete en su Libro IVA.

## Preparar (una vez)

1. `make lab-up` y `make lab-arca` (deja la empresa ficticia lista para pedir CAE de prueba).
2. Entrar al lab (<http://localhost:8069>, usuario `admin`).
3. Tener a mano dos pestañas: **Punto de venta** y **Facturación**.
4. Para ver el Libro de IVA (paso 8), el usuario necesita **funciones contables completas**:
   *Ajustes → Usuarios → (el usuario) → Contabilidad*: «Mostrar características de contabilidad
   completas» (o «solo lectura» para quien solo mira). Sin eso, *Facturación → Reportes* muestra
   solo «Reportes del contacto» y «Gestión». En el lab, `admin` ya lo tiene (09/11).

## La demo

### 1. Lo que se usa hoy (sin facturar en Odoo)

*Punto de venta* → **Mostrador 1** → PIN **1111** → agregar un producto → **Imprimir pedido**.

- Sale el ticket del pedido, con su número. El cliente paga en la **registradora**, que hace el
  ticket fiscal como siempre.
- En Odoo la venta queda como «Cobrado en registradora»: sirve para el **stock**, no es una
  factura.

### 2. Factura B en la caja (consumidor final)

*Punto de venta* → **Caja 1** → PIN **2222** → agregar un producto → **Pago**.

- El botón **Factura** viene **marcado**. Elegir **Efectivo** → **Validar**.
- Sale el ticket con, al pie: **Factura B Nº …**, **CAE**, vencimiento del CAE, el **QR de ARCA**
  y el **IVA contenido** (Ley 27.743).
- En *Facturación → Clientes → Facturas* está la misma factura (**FA-B**), «aceptada en ARCA».
  Abrirla → **Imprimir**: es la versión **A4**, la «profesional». Es la misma factura en otro
  formato.

### 3. Factura A (cliente con CUIT)

En la caja, otra venta → tocar **Cliente** → elegir «[EJ] Veterinaria Los Robles (mayorista)»
(Responsable Inscripto, CUIT ficticio) → **Pago** → **Validar**.

- Sale **Factura A**, con el IVA discriminado. Nadie elige la letra: la pone Odoo por el cliente.
- Para mandarla: desde la factura en *Facturación*, **Enviar** (PDF A4 por mail; en el lab
  llega a <http://localhost:8025>).

### 4. Venta que factura la registradora (Factura desmarcado)

Otra venta → **Pago** → tocar **Factura** para **desmarcarlo**.

- Aparece una **franja de color** al costado: avisa que esta venta no la factura Odoo.
- Cobrar. No hay CAE: el comprobante se hace en la registradora.
- *Punto de venta → Órdenes → **Ventas sin factura de Odoo***: está ahí, por día y caja, con el
  total. Sirve para controlar contra el cierre de cada registradora.

### 5. «Me olvidé de facturar» (facturar después)

En **Ventas sin factura de Odoo** abrir la venta del punto 4 → **Facturar con CAE** → confirmar.

- Sale la factura con CAE (con fecha de **hoy**: ARCA no acepta fechas pasadas) y la venta sale
  de la lista.
- **Solo si no se hizo el ticket en la registradora**: si no, habría dos comprobantes.

### 6. Devolución (nota de crédito)

En la caja: *Órdenes* → filtro **Pagado** → elegir la venta del punto 2 → **Devolución** →
cantidad → cobrar en negativo (devolver el efectivo).

- Odoo hace la **nota de crédito B**, que anula la factura, y le pide su propio CAE (la nota de
  crédito con CAE está probada con `make e2e-factura`; desde la caja, mirarla en *Facturación →
  Clientes → Facturas* y anotar acá si sale distinto).

### 7. ARCA no responde

En una terminal: `make lab-arca-cortar` (simula que ARCA está caído).

- En la caja, una venta con **Factura** marcado → **Validar**. La caja avisa: «ARCA no respondió:
  venta sin factura. Hacé el comprobante en la registradora.»
- La venta queda cobrada, **sin factura de Odoo**, marcada «ARCA no respondió». El cliente no
  espera y el comprobante sale de la registradora.
- Al terminar: `make lab-arca-volver`.
- **Cuando ya no haya registradoras** (`facturacion.arca_caido: facturar_despues` en
  `config/valores.yaml`): la caja avisa «factura pendiente», el ticket dice **FACTURA PENDIENTE**
  y la factura se hace sola con CAE cuando ARCA vuelve (cada 10 minutos, o *Punto de venta →
  Órdenes* → **Reintentar facturas pendientes**). Solo las cobradas con **Factura** marcado: las
  cobradas sin «Factura» nunca se facturan solas.

### 8. Lo que se le pasa al contador

*Facturación → Reportes → Impuestos y finanzas → **Libro de IVA*** (menú agregado por
`comercio_libro_iva`: Odoo 20 no lo trae; el de «Reporte fiscal» abre otro informe, vacío). Abre la
«Declaración fiscal» con **Reporte: Libro de IVA (AR)**.

- **El período arranca en el mes anterior**: en el botón del calendario, pasar a **este mes**
  (flechita de «Mes») o elegir **Año**.
- **Tipo de impuesto**: **Ventas** o **Compras** (todo junto se ve, pero no se exporta).
- En la **ruedita ⚙**: **Libro de IVA (ZIP)** trae los **TXT del Libro IVA Digital** que se suben a
  ARCA. Ventas: `Ventas.txt` (comprobantes) e `IVA_Ventas.txt` (alícuotas); compras: los mismos de
  compras. Solo lo que facturó Odoo. Lo de las registradoras y 3C se le sigue mandando como hoy.
  También **Libro IVA (PDF)**, XLSX y **Reporte de IVA Simple (ZIP)** (el formato de «IVA Simple»
  de ARCA: cuál usa, lo dice el contador).
- *Reportes → Informes Argentinos → **Resumen IVA*** es otra cosa: un resumen del IVA por alícuota y
  por mes, para mirar. No reemplaza al Libro de IVA ni exporta los TXT.

## Si algo falla

- **«Code 10016»** (numeración de prueba desfasada: el CUIT de prueba lo usan muchas bases):
  probar de nuevo; si sigue, `make lab-arca` y volver a abrir la caja.
- **La caja no deja cerrar**: hay una venta que quedó a medias; ver *Órdenes* en la caja.
- Detalle técnico: `ventas-con-y-sin-factura.md`, `devoluciones.md`,
  `docs/areas/facturacion-contabilidad.md`.

## Qué le falta al ticket antes de usarlo de verdad (P-029)

- **Encabezado fiscal**: razón social, domicilio, «IVA Responsable Inscripto», Ingresos Brutos e
  inicio de actividades. Hoy solo sale el logo y el CUIT al final.
- Que diga **«Factura B Nº …» arriba**, no «Recibo …» (ese es el número interno de la venta).
- **IVA discriminado o no** en la B: según el modelo que use hoy la registradora.
- Plan: copiar el modelo de un **ticket de la registradora** (B) y de una **factura A de 3C**.






odoo manda a arca para facturar el importe o todos los productos y demas
