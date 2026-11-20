# 0009. Módulo propio: pedido del puesto con QR, cobrado en la caja

- Estado: aceptado
- Fecha: 2026-10-07

## Contexto

En Comercio Ejemplo, una sola caja cobra. Los demás puestos arman el pedido del
cliente, le entregan un ticket y el cliente paga en la caja
(`docs/relevamiento/procesos/venta-mostrador.md`). El cliente llega a la caja con el
ticket y su pedido tiene que abrirse **al instante**, sin buscarlo en una lista.

Se investigó Odoo 20 estándar y se probó de punta a punta en el lab con un navegador
automatizado (`docs/areas/pos.md`). Ya resuelve:

- quien atiende entra con rol **supervisado** (`pos_hr`) y **no puede cobrar**;
- el botón «Cuenta» (`iface_printbill`) imprime un **proforma** antes de pagar;
- «Órdenes» abre un pedido puntual escaneando un QR con la **cámara**;
- al cobrarlo, Odoo mueve el pedido a la **sesión de la caja** y descuenta el stock
  **una sola vez**.

Lo que **no** hace:

1. imprimir el proforma **no sube el pedido al servidor** (se genera en el navegador
   del puesto), así que la caja no tiene qué abrir;
2. el proforma **no lleva ningún código** del pedido (el QR estándar solo sale en
   recibos pagados);
3. la caja solo puede abrirlo desde «Órdenes» y con la cámara (franja de lectura
   pensada para códigos de línea), no con el lector USB desde la pantalla principal;
4. en los puestos, el botón principal sigue siendo «Pago» (deshabilitado), cuando lo
   útil es imprimir el pedido.

Compartir pedidos entre puntos de venta («POS de confianza») hace que la caja vea y
cargue sola **todos** los pedidos de los puestos, lo que el negocio no quiere.

## Decisión

Un módulo propio chico, `comercio_pos_pedido_qr` (`addons/`), que se activa por punto de
venta con la opción **«Puesto que arma pedidos (no cobra)»**:

- **En el puesto:** el botón principal pasa a ser **«Imprimir pedido»**: sube el pedido
  al servidor, imprime el proforma con un **QR** y deja la pantalla lista para el
  siguiente cliente. «Pago» no se muestra.
- **En el proforma:** un QR con el identificador del pedido (`PED` + uuid sin guiones:
  solo letras y números, para que el lector no dependa de la distribución de teclado).
- **En la caja:** al escanear ese QR con el lector USB en la pantalla principal, se abre
  ese pedido listo para cobrar. Si ya se cobró o no existe, se avisa.

Todo lo demás (cobro, sesión, contabilidad, stock) queda en manos de Odoo estándar.

## Precisión (07/10/2026): son dos cajas

El relevamiento confirmó que **cobran 2 cajas** (no una). El módulo ya trata como caja a
todo POS sin «arma pedidos» y la regla de cierre usa la **última** caja abierta, pero
faltaba probar el caso de dos cajas (P-035). Resultado:

- Cualquier caja abre y cobra el pedido del puesto.
- Si las dos cajas abren el mismo pedido, Odoo ya impide cobrarlo dos veces (el servidor
  rechaza el segundo pago), pero la segunda caja mostraba «Importe pagado» tapado por un
  error técnico. El módulo ahora consulta el estado en el servidor antes de validar y,
  si otra caja ya lo cobró, avisa «Pedido ya cobrado» y deja la caja vacía.
- La cancelación de pendientes espera a la **última** caja.

Prueba: `tests/e2e/pos_dos_cajas.py` (parte de `make e2e-pos`).

## Precisión (07/10/2026): pedidos enviados a caja que nadie cobra

Odoo no deja cerrar una sesión con pedidos en borrador, y el puesto no ve los pedidos
que envió a caja. Regla acordada con el implementador (P-027):

- **El puesto cierra con la caja abierta:** sus pedidos pendientes **no se cancelan**; se
  desprenden del puesto (como hace Odoo con los pedidos programados) y la caja los sigue
  pudiendo cobrar. Resguardo para el cliente que todavía está en la fila.
- **Cierra la última caja:** se cancelan los pedidos pendientes que nadie cobró.
- **El puesto cierra con la caja ya cerrada:** se cancelan en ese momento.

En los puestos, quien atiende puede **abrir y cerrar** la sesión aunque su rol sea
supervisado (en Odoo abrir requiere cajero o gerente y cerrar, gerente; esos roles también
dan cobro, precios, descuentos o acceso al backend: demasiado para un puesto). Sin el
permiso de apertura (agregado el 08/10, módulo 20.0.1.5.0), a la mañana veía la nota de
apertura sin botón para abrir y «Descartar» lo sacaba. El resto de sus permisos no cambia.
En las cajas se mantienen los permisos de Odoo.

Además, una acción planificada cierra todas las noches (23:30) los puestos que quedaron
abiertos; la caja nunca se cierra sola porque su cierre lleva el conteo del efectivo.

Cada cancelación queda registrada en el pedido y en la sesión. Como un borrador no movió
stock ni dinero, cancelarlo no afecta inventario ni caja. Prueba: `tests/e2e/pos_cierre.py`.

## Alternativas consideradas

- **Solo estándar** (caja busca en «Órdenes» con la cámara): no cumple «al instante»,
  y el pedido ni siquiera llega al servidor al imprimir.
- **POS de confianza:** la caja ve y carga sola todos los pedidos de los puestos.
- **Presupuestos de la app Ventas cargados en el POS** (`pos_sale`): cambia la
  herramienta de los puestos a una interfaz de backend, más compleja para quien atiende.
- **Código de barras de línea (Code128) en vez de QR:** el identificador es largo y no
  entra bien en un ticket de 80 mm; con lectores 2D el QR no tiene costo extra.

## Consecuencias

- Requiere **On-Premise** (Odoo Online no instala módulos propios): coherente con el
  ADR 0007. En Online este flujo no se puede probar; se prueba en el lab (Community),
  donde funciona igual.
- Los **lectores tienen que ser 2D** (leen QR y códigos de producto).
- Hay que mantener el módulo en cada versión de Odoo: toca puntos chicos del POS
  (plantilla del recibo, botón de pago, lector de códigos). Se cubre con la prueba
  automatizada de punta a punta.
- El rol supervisado se sigue usando en los puestos como segunda barrera.
- El proforma no es comprobante fiscal: su leyenda se valida con el contador (P-025).
