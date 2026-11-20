# Listas de precios de proveedores

App **Costos y precios** en Odoo, sección **Listas de proveedores**.

**Buscar un producto** (sin abrir ninguna lista): *Buscar producto* → escribir palabras o
medidas en cualquier orden («fix 4x40», «cadena 40 galv») o un código (del proveedor, de
barras o nuestra referencia, también el propio 20…). Aparece cada
proveedor que lo tiene, con su costo; en verde, lo que ya tenemos. Para agregar uno que no
tenemos: elegir la **Categoría** (la columna **Precio de venta** muestra a cuánto se
vendería) y tocar **Agregar**. Para pedirlo: **Pedir** (carrito) lo suma a la solicitud
en borrador de ese proveedor; con varias casillas, **Agregar al pedido**. Si dice «Posible duplicado», **Es el
mismo** (ya lo tenemos con otro proveedor) o **Agregar como nuevo**. Para varios, marcar las casillas.

**El mismo producto en varias listas** (02/11): en *Buscar producto*, buscarlo (p. ej. «grampa
caño 3/8»), marcar las filas de **todos** los proveedores que lo venden, tocar **Agregar a
nuestro catálogo** y elegir **Son el mismo producto**: se crea uno solo con todos esos
proveedores (su código y su precio) y Odoo le compra al más barato. Si alguna fila ya es nuestra, se le suman las demás. Si se escapa un
proveedor: al agregar un producto, las filas parecidas de las otras listas pasan solas a «¿Es el
mismo?» (aviso «Se agregó … desde la lista de …»), y si se toca **Agregar** en una fila que
cambió así, no se agrega otro igual: se vuelve a calcular y avisa para elegir **Es el mismo**.
Con varias filas marcadas, **Agregar a nuestro catálogo** pregunta cómo: **Son el mismo
producto** (uno solo), **Son productos distintos** (uno por fila) o **Ya los tenemos** (cada una
al producto nuestro más parecido). Con una sola fila sin parecidos, la agrega directo.

**Nuestro nombre, no el de la lista:** el nombre del producto se toma de la lista solo al
crearlo. Se puede cambiar en el producto («Llave francesa 10"» en vez de «LLAVE FRANCESA 10»):
las listas siguientes **no lo pisan**. Cada proveedor queda unido por su código (o, si no trae
código, por su descripción), que se guarda aparte en el producto (pestaña *Compra*), así que al
reimportar se sigue reconociendo y solo se actualizan su precio y su descripción. La orden de
compra y el WhatsApp al proveedor usan su código y su descripción; la caja, nuestro nombre.

**Si la lista viene con un error:** en la fila, **Corregir** (precio o descripción) o **Ignorar**;
en el producto ya agregado se puede cambiar todo a mano (nombre, categoría, IVA, **Costo manual**
y **Precio manual**, que las listas no pisan).

**La primera vez con un proveedor:** se sube su lista y el sistema propone las columnas. Si
alguna no es la que corresponde (p. ej. la descripción sin título, o un «neto» del proveedor que
conviene más que su precio de lista), se elige una vez en la ficha de la lista, junto con sus
opciones (descuentos, moneda, sumar la familia o la medida al nombre, el precio por el envase
de la descripción). Queda guardado: **las listas siguientes se suben tal como vienen**.

**Los 24 proveedores de ferretería ya revisados** traen esa ficha armada desde el repositorio
(`integrations/catalogo/proveedores/*.yaml`). En una base nueva (producción), una sola vez,
desde el servidor:

```bash
cd /opt/odoo-implementation
.venv/bin/python infra/scripts/configurar-listas-proveedores.py onpremise            # muestra qué haría
.venv/bin/python infra/scripts/configurar-listas-proveedores.py onpremise --aplicar  # lo hace
```

Crea cada proveedor y la ficha de su lista (una por parte: LUMINA, LTX, Aluminio Phi y Bazar Alfa
tienen varias), sin importar nada y sin rubro. Una ficha que ya existe no se toca. JN y Chi
no hacen falta: sus columnas se reconocen solas.

**Al cambiar el motor de las listas** (`addons/comercio_catalogo/catalogo/`, para el implementador):
`make listas-reales` pasa todas las listas reales de `data/privado/` por el motor (con su YAML y
con las columnas que sugeriría solo) y muestra qué cambió contra la última foto: filas nuevas o
que ya no salen, costos, descripciones, códigos de barras, columnas sugeridas. No necesita el
lab (~1 min). Si los cambios son los buscados, `make listas-reales-foto` guarda la foto nueva
(`data/privado/foto-motor-listas.json`, fuera de git). Al sumar una lista o un YAML nuevo: revisar
lo que sale y guardar su foto (`.venv/bin/python infra/scripts/probar-listas-reales.py <nombre> --guardar`).

**Ver un producto con todos sus proveedores juntos** (lo tengamos o no): en *Buscar producto*,
buscar (p. ej. «cadena») y en el menú del buscador **Agrupar por → Producto**. Junta a los
proveedores por nuestro producto, por el mismo código de barras o por la misma descripción
(sin importar mayúsculas, acentos ni el orden: «4x40» = «4 X 40»). Si dos proveedores escriben
muy distinto el mismo artículo, quedan separados hasta que se une a nuestro producto («Es el
mismo» o la IA); desde ahí ya van juntos.

**Marcar muchas filas de una vez** (en cualquier lista de Odoo): tildar la primera, mantener
apretada **Mayús** (⇧ Shift) y tildar la última: se marcan todas las del medio. La casilla
del título marca toda la página (y arriba aparece «Seleccionar todos» para los demás).

**Desde una orden de compra:** con el proveedor elegido, debajo de las líneas, **Lista del
proveedor** (al lado de *Catálogo*): su última lista, primero lo que tenemos. Sacando el
filtro «Lo tenemos» se ve el resto: **Agregar** lo suma a nuestro catálogo y **Pedir** lo suma
a esa misma orden (se puede seguir eligiendo; al volver, la orden ya lo tiene).

**Quitar un producto de nuestro catálogo:** marcar su fila (en *Buscar producto* o en las
filas de una lista) → menú **Acciones** (⚙) → **Quitar de nuestro catálogo**. Se archiva,
no se borra: deja de verse en la caja y en Compras, pero queda su historial. En las listas
pasa a «No lo tenemos»; **Agregar** vuelve a poner el mismo producto, no crea otro.

**Subir una lista nueva**

1. *Importar lista* → elegir el proveedor (o escribir uno nuevo y **Crear**) → elegir el
   **Rubro por defecto** (se recuerda para la próxima; si no existe, escribirlo y **Crear**)
   → debajo, el **Margen del rubro**: si está vacío, cargarlo ahí mismo (se guarda en el rubro
   al simular; sin margen no se puede agregar nada de ese rubro) → subir el Excel tal como llegó
   (`.xlsx`, `.xls` viejo o CSV) → **Descuento de la lista** (p. ej. `10` o `10+10`; se guarda
   para la próxima; **vacío no cambia el que ya tenía**: para sacarlo, en la ficha del proveedor) → **Simular**. El IVA se revisa en la ficha del proveedor.
   Todavía no cambia nada.
2. Arriba aparecen los números: nuevos, cambios de costo, bajas y **para revisar**.
3. **Aplicar todo** (un solo botón, 19/11): aplica todo lo de los productos que ya tenemos
   (cambios de costo de cualquier tamaño, lo que el proveedor dejó de traer, proveedor que se
   agrega o vuelve) y lo que se haya marcado. **Nunca agrega productos que no tenemos**: así una
   lista entera no llena el catálogo. Los posibles duplicados sin decidir y las filas a corregir
   quedan para el paso 4. (Antes eran «Aplicar automáticos», con un tope de variación del 10 %,
   y «Aplicar todo lo marcado».)
4. Abrir **Para revisar** y decidir cada fila:
   - **Aplicar** (producto nuevo, suba grande, producto que ya no está) o **Ignorar**.
   - Si dice *Posible duplicado*: elegir en «Es el mismo que» y tocar **Es el mismo**,
     o tocar **Agregar como nuevo**. Se pregunta una sola vez.
   - Para muchas filas: botón **Para revisar** → marcar las casillas de la izquierda (o la
     del título, para todas) → arriba aparecen **Aplicar**, **Agregar como nuevo**, **Ignorar**…

**Agregar productos de la lista** (los que no tenemos no se crean solos; si la IA está
configurada, **«Agregar» primero los revisa con la IA**, 20/11: lo que seguro ya tenemos con otro
nombre se une solo a ese producto, y lo que la IA cree que ya tenemos **no se agrega**: queda en
amarillo, filtro **Retenidas por la IA**, con el motivo en «Motivo IA»; si no es el mismo, se marca y
**Agregar** de nuevo, y ahí se agrega. Lo dudoso se agrega. Sin internet o si la IA falla, se agrega
igual, sin avisos): botón **No los
tenemos** → buscar → en **Categoría** viene el rubro; cambiarlo si hace falta (para varios:
marcar las casillas y cambiar la categoría en uno) → **Agregar a nuestro catálogo**. Si
falta una categoría, escribirla en el desplegable y **Crear**. Una categoría **sin margen**
no deja agregar (el producto saldría a $1 en la caja): cargarle el margen en *Precios de
venta → Márgenes por categoría* y volver a tocar **Agregar**. La categoría también se puede
cambiar en la pestaña **Filas** de la importación.

**Categoría de lo que ya tenemos:** en las filas de productos nuestros, **Categoría** muestra
la del producto; cambiarla ahí cambia el producto (también con varias filas marcadas). El
precio de venta no cambia solo: el producto pasa a *Precios a actualizar* si el nuevo margen
da otro precio.

Muchas filas (más de 400) se aplican en segundo plano: llega un aviso cuando termina.
Si llega una lista más nueva del mismo proveedor, la anterior queda «reemplazada».

**Producto que vuelve a la lista** (se había dado de baja y vuelve con el mismo código):
la fila dice **Vuelve a la lista**, con el último precio que tuvo como costo anterior; se
aplica como cualquier otra. En *Importaciones*, la columna **Vuelven** los cuenta.

**Dos productos que eran el mismo** (se agregó uno nuevo y ya lo teníamos con otro nombre):
si es de la última lista, **Deshacer** esa fila y elegirlo en «Es el mismo que». Si ya es
de una lista vieja, **fusionarlos** (solo un administrador): en *Buscar producto* (o en
*Productos*) marcar los dos → **Acciones → Fusionar productos** → elegir cuál queda («Principal») → **Fusionar**. Proveedores, stock,
ventas e historial pasan al que queda; el otro se archiva. El costo se corrige esa noche
(o con la próxima lista). Si los dos tenían precio del **mismo** proveedor, quitar el que sobra.

**Volver atrás:** lo aplicado se puede **Deshacer** (por fila o *Deshacer todo lo
aplicado*); **Descartar** deja la lista sin aplicar.

**Una lista que se cargó mal** (columnas equivocadas, sin el descuento, el dólar mal):
1. En la importación, **Deshacer todo lo aplicado**: los costos vuelven a como estaban y los
   productos que se agregaron desde esa lista se borran (o se archivan, si ya se vendieron o
   tienen stock).
2. **Descartar**. La lista descartada queda en el historial, pero ya no cuenta: vuelve a
   mandar la anterior de ese proveedor, como si esta no hubiera llegado.
3. Corregir lo que estaba mal en *Proveedores* (columnas, descuentos, moneda) e **Importar
   lista** de nuevo con el mismo archivo.

No hace falta borrarla: descartada no ensucia nada (no se aplica, no se busca en «Buscar
producto» y no es la vigente). Borrar importaciones solo puede un administrador y se pierde
el registro de qué pasó. Deshacer no se puede si después ya se aplicó una lista más nueva de
ese proveedor (hay que deshacer primero la más nueva). Si la lista todavía no se aplicó, alcanza
con corregir y **Recalcular costos**, o con descartarla.

**Si el proveedor cambió el formato:** las columnas se reconocen solas y arriba aparece el
aviso **Formato cambiado**; nada se aplica solo hasta revisarlo. **Si da error** (no se
encontró la descripción o el precio): en *Proveedores* corregir las columnas con los
títulos que muestra el error y tocar **Volver a simular**.

**Si el Excel del proveedor es tan raro que no hay forma** (columnas mezcladas, precios en
el medio del texto, varias tablas en una hoja): copiar sus productos a la **planilla
modelo** `data/plantillas/lista-proveedor-modelo.xlsx` (una fila por producto; la hoja
«Cómo llenarla» explica cada columna) y subir esa planilla en *Importar lista*. Sus
columnas se reconocen solas. Tiene que ir la lista **completa**: lo que falta se toma como
baja.

**El mismo producto en otra presentación** (Chi: «display box x 20», «quarter pallet»): se carga la
primera fila y las otras quedan como **«Otra presentación de …»**, a la vista, sin corregir. La orden de compra nombra
esas presentaciones en el aviso del bulto («De a 100 (también: … display box x 20 …)»). **El mismo
código de barras en dos productos distintos** (un error de la lista, p. ej. dos colores): el primero se
queda con el código de fábrica y el otro se carga solo, como producto aparte con código propio `20…`.
**Código de barras incompleto o mal escrito**: el producto recibe uno propio. En los dos casos el
código de la lista queda como pista («La lista decía») en **Costos y precios → Códigos de fábrica**,
para escanear el del envase.

**Filas con problemas** (sin precio, precio 0, «Consultar», mal copiadas): botón **Corregir** en
la fila → se carga el **precio de la lista** (pasa al costo con los descuentos, el IVA y el dólar
de la lista) o se arregla la descripción, y la fila se vuelve a simular (queda «corregida a
mano»). Si el proveedor no lo vende más, **Ignorar**. Para verlas todas juntas: botón **Para corregir** arriba en la
importación (o el filtro **Para corregir** en **Elegir varias filas**).

**Revisar con IA** (si está configurada; 06/11): **un solo botón** en la importación, en sus filas y
en «Buscar producto». Abre una ventana con **casillas, todas marcadas**, y con cuántas filas falta
revisar de cada cosa; **Revisar con IA** hace todo junto (solo lo que todavía no tiene sugerencia,
hasta 200 por vez y en paralelo):
- **Las filas marcadas** (si se entró con filas elegidas).
- **Posibles duplicados:** ¿ya lo tenemos con otro nombre?
- **Lo que ya tenemos:** ¿la descripción del proveedor sigue siendo ese producto? Lo dudoso queda
  en el filtro **La IA duda** (sirve si un proveedor reusa un código para otro artículo).
- **Filas con problemas:** qué pasó y qué hacer (corregir, ignorar, preguntarle al proveedor).

**Aceptar lo que sugirió la IA** es un botón aparte en la misma ventana (aparece cuando hay
sugerencias): «Es el mismo» une, «Es otro» agrega; lo dudoso no se toca. La IA solo sugiere: lo que
dijo queda en el **detalle de la fila** («Lo que dijo la IA»); nada cambia hasta aceptar o corregir.

**Revisar las filas** (06/11): arriba de cada importación, los contadores (Para revisar, Para
corregir, Cambios de costo, No los tenemos, Toda la lista) abren la lista completa, con casillas y
barra para moverse. La lista muestra solo lo que hace falta para decidir:

| Novedad | Descripción del proveedor | Nuestro producto | Categoría | Costo | Por mayor | Botones |

- **Nuestro producto**: el producto unido o, entre «¿?», el más parecido. Si pasó la IA, al lado dice
  «IA: es el mismo» (verde), «IA: es otro» (gris) o «IA: duda» (naranja).
- **Costo**: el nuevo y cuánto cambió («72.633,00 ▲ +5,2 %», rojo si sube, verde si baja).
- **Por mayor**: el precio y desde cuántas unidades («7.780,00 ×12»).

**La lupa** al principio de cada fila abre el detalle para comparar: el producto de la lista y el
nuestro lado a lado (código de barras, costo actual), lo que dijo la IA con su motivo, el cálculo del
costo, los parecidos, los avisos y los mismos botones. Código, costo anterior, precio de venta, estado
y las demás columnas siguen en el menú de columnas (ícono a la derecha de los títulos).

**La IA une sola lo seguro** (ADR 0034): al tocar «Revisar con IA» (y sola en las listas que llegan
por correo o enlace), si dice «es el mismo» con 90 % o más, a un producto que ya tenemos y con un costo
que no salta más que el tope de la ficha, la fila se une y aplica sola. **Nunca agrega productos**: lo
que es otro queda en «No los tenemos» para decidir si lo queremos vender. Filtro **«Unidas por la IA»**
para revisarlas; se deshacen como cualquier fila.

**Descuentos por familia y por producto** (06/11): en la ficha del proveedor ya no hace falta escribirlos
de memoria. *Descuentos por familia*: en «Familia» escribí parte del nombre y elegí de las familias que
trae la lista (con cuántas filas tiene cada una); si la lista no trae familias, escribí el texto que
aparece en la descripción. *Descuentos por producto*: buscalo por código o por palabras de la descripción
(«autopolish clasico») y poné el descuento. En los dos, **Filas** dice a cuántas filas de la última lista
les toca y **Ver** las muestra. Las familias aparecen con la próxima lista o con «Recalcular costos».

**Moneda de la lista** (06/11): al subir el **primer** archivo de un proveedor se detecta sola (por el
título de la columna del precio, el texto de arriba o el formato de las celdas: «US$», «$»). En una
lista que ya tiene moneda **nunca se cambia sola**: si el archivo parece de otra, la ficha muestra un
aviso para cambiarla a mano.

**Del precio de la lista al costo** (ADR 0029). Si el precio de la columna elegida no es lo
que le cuesta al comercio, en la lista del proveedor (*Proveedores* → abrirla), bloque **Del
precio de la lista al costo** (todo opcional; vacío = el precio de la lista es el costo):
- **Moneda de la lista**: Pesos o **Dólares**. En dólares se usa la última cotización de la
  pantalla **Costos y precios → Dólar**: ahí se carga a mano (**Nuevo** → fecha y **pesos por
  dólar**, Banco Nación vendedor) y **Recalcular listas en dólares** aplica el cambio enseguida.
  Si no, a las 7 se recalculan solas las listas cuyo dólar se movió más de 0,5 % (los cambios
  grandes esperan revisión). Cuando el servidor tenga el certificado de ARCA, la cotización del
  día aparece sola cada mañana en esa pantalla. **Cotización fija**: solo si una lista va con
  otro dólar (p. ej. el del proveedor).
- **Descuentos del proveedor**: para toda la lista, en cadena: «30+10+10» (30 %, después 10 %
  sobre lo que queda y después otro 10 %).
- **Descuentos por familia** (pestaña): un descuento extra para la parte de la lista cuya
  descripción o código tiene ese texto («BULON, TUERCA» → 10). Vale la primera que coincide.
- **Descuentos por producto** (pestaña): por el código del proveedor, para un acuerdo puntual.
- **Columna «descuento»**: solo si el proveedor trae su descuento por fila. **Nunca** elegir
  una columna que agregó el comercio (precio final, con IVA, margen…): no se sugiere sola.
- **Columna «promociones»**: las promociones que el proveedor escribe en texto (FC:
  «Descuentos y Promociones Vigentes»). «5% DTO. X UNIDAD» **baja el costo**; «10% DTO. X 2
  ROLLOS» es el **precio por mayor** desde esa cantidad (si hay varios escalones, el primero; el
  texto entero queda como aviso en la fila). Lo que no es un descuento («va sin cargo…») solo
  se muestra. Cuando la promoción **se termina**, la lista siguiente avisa «Sube porque se
  terminó la promoción del proveedor» y ese cambio no se aplica solo.
- **Recargo**: p. ej. el flete que suma la factura (2,5).
- **Columna «unidades por bulto»** (UxB, unidades por caja): el proveedor vende de a bultos enteros. La
  orden de compra avisa si se pide una cantidad que no es un bulto entero («De a 100: pedir 100 o 200»).
  No es la compra mínima (esa va en «cantidad mínima», si la lista la trae). Si la lista da además un
  precio por bulto, esa columna es la del precio por mayor y no un bulto obligatorio.
- **Columna «stock»**: las filas que dicen NO, agotado o 0 **no se cargan** (decidido 30/10: si otro
  proveedor lo tiene, aparece en su lista). Un producto nuestro que se queda sin stock sale como
  «ya no está en la lista»; cuando vuelve, vuelve.
- **Columna «IVA»**: si la lista dice la alícuota de cada producto (FC: «Precio con I.V.A», que
  es el %: 21 o 10,5). Los productos **nuevos** que se agregan desde la lista toman ese IVA, de
  venta y de compra. En los que **ya tenemos manda el del producto**: si la lista dice otro, la
  fila avisa «La lista dice IVA 10,5 % y el producto tiene 21 %» y no se cambia nada.
- **La lista trae el IVA incluido**: se saca con el IVA del producto (si ya lo tenemos), si no
  con el de la columna «IVA», si no con «IVA si no se sabe» (21).

Todos los descuentos se suman en cadena, en ese orden. Abajo se ve **un ejemplo** con filas de
la última lista y, en la importación, la columna opcional **Cálculo del costo** de cada fila
(«$ 120,00 · −5 % (lista) · +2,5 % recargo → $ 116,85»). Después de cambiar algo:
**Recalcular costos** (arriba): vuelve a leer la última lista con los valores nuevos y se
revisa y aplica como una lista nueva.

**Precio 0, «SIN STOCK», «Consultar»:** no es un costo; la fila queda **a revisar** con «la
lista trae precio 0» y no se carga.

**Familias en una fila aparte** («CANDADO BRONCE» arriba y debajo «40 mm», «50 mm»): esas
filas nunca se leen como productos. Para que la descripción quede «CANDADO BRONCE 40 mm»,
marcar **Sumar la familia a la descripción** en la lista del proveedor. Si la lista no tiene
columna de descripción (solo código, potencia, color…), la descripción se arma sola con la
familia y esas columnas.

**Columna sin título o que cambia de título cada mes** (p. ej. «LISTA Nº 194 DE SETIEMBRE»):
en la lista del proveedor escribir la columna por su letra, como en Excel: «Columna A»,
«Columna B». Se lee por posición y no da «formato cambiado» el mes siguiente.

**Precio por caja** («24 u.», «100 U.», «12 par», «100», «Docena» en la unidad): se guarda por unidad, con la
caja como compra mínima (media caja si el mínimo es 0,5); lo dice el aviso de la fila.

**Producto que se vende suelto** (p. ej. tornillos por kg) **y el proveedor lo vende en
caja:** el producto va en kg y la caja es su **unidad de compra** («Caja 1000 = 2,5 kg»).
Si la lista lo trae por caja y el producto todavía no tiene la unidad, la fila queda **a
revisar** («se vende por kg y la lista lo trae por unidad o por caja»): en la columna
**Unidad de compra** elegir o crear la caja (*Crear y editar*: nombre, **Contiene** 2,5,
unidad de referencia **kg**) → **Aplicar**. Desde ahí cada lista actualiza el precio de la
caja tal cual, **Pedir** pide cajas y al recibir entran los kg.

**Lista en PDF o foto:** se sube igual. Un PDF con texto se lee solo, sin IA. Una foto o un
PDF escaneado los lee la IA (hasta 10 páginas; si son varias fotos, la primera en
**Archivo** y las demás en **Más fotos**, en orden: se juntan solas en un PDF); en ese caso **nada se aplica solo**: comparar las subas y bajas grandes con el
**Archivo original**. Por correo o link solo se aceptan Excel y CSV.

**Proveedor que manda la lista en partes** (p. ej. FC: una hoja general y otra de
bulones): una lista por parte. Si vienen en **hojas del mismo Excel**, al subirlo en
*Importar lista* aparecen las hojas con cuántas filas tiene cada una: marcar las que
tienen productos y **Simular**. Cada hoja marcada queda como una parte («Parte» y
«Hoja» con su nombre, creada sola la primera vez) con su rubro, y se simula aparte. Si
vienen en **archivos separados**: la primera vez, en *Importar lista* tildar **Es otra
parte** y ponerle nombre («Bulones»); se crea con sus columnas y la que ya tenía pasa a
llamarse «General». Las veces siguientes se elige en **Parte** a cuál va el archivo. Si
por error se sube a la parte equivocada (casi nada coincide con lo que tenía), la
simulación no da de baja nada y avisa «¿Es otra parte?». Lo que
falta en una parte no da de baja lo de la otra. Si la descripción viene en dos columnas, se juntan con « + »
(«Detalle + Descripción del producto»).

**Qué vende un proveedor:** *Proveedores* → abrirlo → botón **Productos**: abre lo nuestro;
quitando el filtro «En nuestro catálogo» se ve toda su lista.

**Ver la historia:** *Importaciones* (cada lista con sus cambios) e *Historial de costos*
(cada costo de cada proveedor con «Desde» y «Hasta»; «Hasta» vacío = vigente).


## De qué proveedor sale el costo (06/11)

El costo de un producto sale solo, con cada lista, del proveedor **más barato** (precio por unidad
vigente). Si conviene tomarlo de otro (el que siempre se le compra, el de mejor calidad), en el producto
elegí **«Costo de»** o, para varios a la vez, marcalos en la lista de productos y *Acciones → Tomar el
costo de…*. El costo sigue actualizándose solo, pero de ese proveedor (si deja de tener precio vigente,
vuelve al más barato). «Del más barato (normal)» lo deshace. Distinto de **«Costo manual»**, que congela
el costo. El precio de venta nuevo queda, como siempre, en *Precios a actualizar*.

En *Márgenes por proveedor*, además del margen se puede elegir **sobre qué** se calcula: el costo del
producto o el precio de un proveedor (como en «Margen especial»). Vacío: como su rubro.
