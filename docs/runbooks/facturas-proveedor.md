# Facturas de proveedor: subirlas y agregar sus productos

Módulo `comercio_factura_proveedor` (ADR 0021). La factura la lee el comercio, **sin la
digitalización de Odoo** (que cobra créditos): un PDF del sistema del proveedor se lee
sin IA; una **foto** o un PDF escaneado los lee la IA (Gemini).

## Subir la factura

- *Compras → Órdenes → **Facturas de proveedor*** → **Subir** → elegir el PDF o la foto
  (es el mismo listado que *Contabilidad → Proveedores → Facturas*).
- O en *Compras → Órdenes* (solicitudes u órdenes de compra) → **Subir**: si el archivo es una
  factura, se crea la factura del proveedor y se abre.
- O desde la **orden de compra** confirmada: **Subir factura** (queda unida a esa orden).
- En una factura en borrador que ya tiene el archivo adjunto: **Leer factura**.

Se completa lo que esté vacío: proveedor (por su CUIT), tipo y número de comprobante, fecha
y vencimiento. Si el proveedor no tiene CUIT en Odoo se lo guarda, pero solo si sus
artículos están en su lista (si avisa «¿la factura es de otro proveedor?», revisar). Si ningún
proveedor tiene ese CUIT (por ejemplo, uno que vino de una lista sin CUIT, o uno nuevo), arriba
aparece el cartel **Elegir proveedor**: elegirlo de la lista o escribir el nombre para crearlo.
Se le guarda el CUIT y se lee la factura de nuevo.

**Si arriba aparece un cartel amarillo** («El CUIT de la factura es de …»): la factura se
subió en el proveedor equivocado. Tocar **Cambiar a ese proveedor y leer de nuevo**. Si venía
de una orden de compra de otro proveedor, borrar el borrador y subirla desde la orden correcta.

## Compras sin factura

Para cuando el proveedor **todavía no mandó la factura real**, o mandó un presupuesto, un remito
valorizado o una nota de pedido, y hay que registrar la compra y pagarla igual (ADR 0023).

- **Desde la orden de compra**, con la mercadería recibida: tocar **Sin factura**, al lado de
  «Subir factura». Arma la compra con lo recibido y a los precios de la orden, en el diario
  *Compras sin factura*.
- **Con el papel del proveedor:** *Compras → Órdenes → **Compras sin factura*** → **Subir**, y
  se lee igual que una factura. También se puede cargar a mano con **Nuevo**.
- **Sin IVA:** no va al libro IVA ni da crédito fiscal. Si el papel cobra IVA o percepciones,
  van como una línea más («IVA cobrado por el proveedor (sin crédito fiscal)»). Es costo, y el
  total da lo que se paga.
- **Pagarla:** como cualquier factura, con **Registrar pago**. Entra en «Se debe pagar» como las
  demás.
- **Verlas:** cada una tiene un cartel azul arriba. En el listado de facturas están los filtros
  **Sin factura** y **Con factura**, y la columna «Sin factura».
- **Cuando llega la factura real:** la administración la carga como siempre y anula a mano la
  compra sin factura, para que no quede dos veces.

## Los artículos

**Todos los artículos quedan anotados en la factura**, aunque no los tengamos: los que no
están en el catálogo van sin producto, con la descripción, la cantidad, el precio y la
bonificación de la factura (así el total ya da bien). En la pestaña **Leído de la factura**
se ve cada uno con su estado:

- **Con producto** (verde): ya lo tenemos; se cargó con la cantidad, el precio y la
  bonificación de la factura. Si la factura viene de una orden de compra, se completó esa
  línea (avisa si alguna línea de la orden no vino en la factura).
- **En la lista del proveedor, no lo tenemos**: elegir la **Categoría** y tocar **Agregar**
  (como en *Buscar producto*: toma el precio de venta del margen de la categoría).
- **No lo encontramos**: si ya lo tenemos con otro nombre, elegirlo en **Producto** y tocar
  **Es este** (la próxima vez se reconoce solo); si es nuevo, elegir la **Categoría** y
  **Crear producto** (con la descripción, el código y el precio de la factura). **Buscar**
  lo busca en las listas de todos los proveedores.
- **¿Es este?** (amarillo): se parece a uno de la lista del proveedor; confirmarlo con
  **Es este** o **Agregar**, o elegir otro.

En los tres casos la misma línea de la factura toma el producto: no se duplica.

Agregar o crear productos (y que «Es este» le sume el proveedor al producto) lo hace quien tiene **Costos y precios**; sin ese permiso, «Es este» carga la línea igual.

## Muchos artículos que no tenemos: de a varios

Botón **Artículos sin producto** (arriba en la factura): abre solo los que faltan, cada uno con su
estado y, si se le pidió, lo que opina la IA.
1. Si se cree que alguno ya lo tenemos con otro nombre: marcarlos → **Verificar con IA**. Los que
   la IA da por iguales quedan **¿Es este?** con nuestro producto; revisarlo y **Es este (el
   sugerido)**.
2. Los demás: marcarlos (tildar el primero, **Mayús** y tildar el último), cambiar la **Categoría**
   en uno (cambia en todos) y **Agregar al catálogo**: los que están en la lista del proveedor se
   agregan desde ahí; los que no, se crean y **se suman a su lista vigente** (así aparecen en
   «Buscar producto» y en «Lista del proveedor»).

## Llegó la factura y no hay orden de compra

Si el pedido no se hizo en Odoo (lo pidieron por teléfono, lo trajo el viajante): en la factura,
**Crear orden de compra**. Se crea y se confirma con los mismos productos, cantidades y precios,
sale la **recepción** para que entre el stock, y la factura queda unida a esa orden. Si hay
artículos que no tenemos, se abre la lista de los que faltan: agregarlos (arriba) y volver a
tocarlo, o **Crear la orden de compra** desde esa lista con lo que ya tiene producto (lo demás
queda afuera de la orden y sigue en la factura).

## La factura de una orden de compra: diferencias

Lo normal: orden → recepción → **Subir factura** desde la orden. La **factura manda** en la factura
(es lo que cobra el proveedor); la orden queda con lo pedido y la recepción con lo que entró.
- Cada artículo que la factura cobra distinto queda **en amarillo**, con la columna **Diferencia
  con la orden** («Precio: orden $ 1.000,00, factura $ 1.100,00 (+10 %)», «bonificación», «facturan
  3 y se recibió 2»), y arriba el resumen.
- Odoo marca solo cada factura de proveedor con **Se debe pagar** (pestaña *Otra información*):
  **Sí** (coincide con lo recibido), **No** (todavía no llegó la mercadería) o **Excepción** (precio
  o cantidad distintos, o artículos fuera de la orden). En la lista de facturas, filtro **Facturas
  en excepción**: revisar esas antes de pagar.
- Si es un error del proveedor: pedirle una **nota de crédito**. Si se acepta: confirmar la factura
  como está (y, si hace falta, cambiar «Se debe pagar» a mano).

## Precio distinto al de su lista

Aunque no haya orden, cada artículo se compara con el precio vigente de ese proveedor (el de su
lista). Si cobra distinto (antes y después de la bonificación), la columna **Diferencia con su
lista** lo dice: más caro → **¿lista vieja?** (pedile la nueva y subila: el costo y el precio de
venta salen de las listas); más barato → **¿un descuento?**. La factura se paga igual con su precio.

## Antes de confirmar

- **El total tiene que dar el de la factura del proveedor.** Se lee también el pie de la
  factura: el **flete** se carga como una línea con su IVA y cada **percepción** (IIBB de la
  provincia, IVA, Ganancias) con su impuesto. No pasan a la orden de compra, pero se pagan.
  El resumen de «Leído de la factura» muestra el pie y si el total coincide.
- Si no coincide, arriba de la factura hay un **cartel rojo** con la diferencia y «Se debe
  pagar» queda en **Excepción**. Hay que ver qué falta (otro tributo, una percepción de una
  provincia sin impuesto en Odoo, un número mal leído) y cargarlo, o tocar **Leer factura**
  para que lo vuelva a cargar. Unos centavos de diferencia son redondeo línea por línea.
- Si después se cambia una línea a mano, Odoo vuelve a calcular la percepción a $ 1. El cartel
  rojo lo avisa; **Leer factura** la vuelve a poner.
- Si fue leída con IA, revisar cantidades y precios contra la foto.
- La factura no cambia los costos ni los precios de venta: eso lo hacen las listas.
