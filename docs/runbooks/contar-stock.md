# Contar el stock

Para cuando ferretería empiece a contar (02/11: al principio no se cuenta). Hasta entonces, el
stock de los productos que se venden queda **en negativo**: no frena nada y se corrige solo al
contar. Solo llevan stock las categorías con la casilla **Controla stock** (ferretería).

## Con el lector (lo más fácil)

App **Código de barras** → **Contar inventario**. Anda en la PC con el lector USB y en el celular
con la cámara.

1. Escanear el producto: aparece en la lista con 1.
2. Cada vez que se vuelve a escanear, suma 1. Si hay muchos iguales, escanear una vez y
   tocar la cantidad para **escribir el número** (p. ej. 48).
3. Seguir con el próximo producto del estante.
4. Al terminar el estante (o la tanda): **Confirmar**. Recién ahí cambia el stock: queda lo
   contado, y la diferencia queda en el historial.

Lee el código de fábrica y también nuestro `20…` (el de la etiqueta), aunque el producto ya
tenga código de fábrica. Si un código **no es de un producto nuestro**:

- **Está en la lista de un proveedor:** cartel «No está en nuestro catálogo» → **Agregar a
  nuestro catálogo** (con su rubro y su margen; si varios proveedores lo tienen, queda uno solo
  con todos) y se suma al conteo. Si se parece a uno que ya tenemos, **Es ese**: se une a ese
  producto y el código escaneado pasa a ser su código de fábrica.
- **No está en ninguna lista:** cartel «Código que no tenemos» → buscar el producto por nombre
  y tocarlo: el código escaneado pasa a ser su código de fábrica (el `20…` queda como
  alternativo; si ya tenía uno de fábrica, el nuevo se suma como alternativo) y se cuenta.
  Si de verdad no lo tenemos: **No lo tenemos** y anotarlo.

Los carteles los ve quien tiene el permiso «Costos y precios»; los demás ven «Este producto no
existe». Un producto sin etiqueta ni código de fábrica: **Agregar producto** (abajo) y buscarlo
por nombre.

No hace falta tener todo «cargado sin número» antes: se cuenta lo que hay en el estante, y lo
que no se escanea queda como estaba. Se puede ir por partes (un estante por día).
**Confirmar al terminar cada estante, antes de cerrar la pestaña:** lo contado sin confirmar
puede perderse (probado el 02/11: al recargar la página, no quedó), y si se vende en el medio
el número ya no es el del estante.

## Desde la PC, en lista

*Inventario → Operaciones → Ajustes → Inventario físico*: buscar lo que se va a contar
(nombre, código o categoría; el lector también sirve en el buscador), columna **Contado** = lo
que hay (al lado, **A la mano** es lo que dice el sistema y **Diferencia**, lo que cambia),
marcar las filas → **Aplicar**. Un producto que nunca tuvo stock no aparece: **Nuevo** → el
producto → **Contado** → **Aplicar**.
