# 0015. Listas de proveedores dentro de Odoo, con actualización automática

- Estado: aceptado (08/10/2026)
- Fecha: 2026-10-08
- Precisa a: [0014](0014-catalogo-similitud-y-revision.md) (el motor ya no corre solo afuera)

## Contexto

El importador de catálogo (`integrations/catalogo`) corría desde la terminal del
implementador. El titular pidió (08/10):

- que importar sea cómodo para un usuario común, sin terminal;
- actualización automática de cada proveedor cada tanto tiempo (configurable), sabiendo
  que el proveedor puede cambiar su Excel y agregar o quitar productos;
- que se compre por defecto al proveedor más barato.

Las listas llegan de formas distintas: unas se suben a mano (páginas con usuario),
otras tienen un link fijo, otras llegan por correo.

## Decisión

Módulo `comercio_catalogo` (On-Premise), app «Listas de proveedores» (desde el 12/10 la app se llama **«Costos y precios»**, porque también tiene los precios de venta del ADR 0016; las listas son una sección):

- **Una «lista» por proveedor:** de dónde llega (a mano, link fijo o correo con alias de
  Odoo), cada cuántos días, responsable, y qué columna del Excel es cada dato. Las
  columnas y la fila de títulos **se sugieren solas** con el primer archivo.
- **Importar = simular primero:** cada importación guarda la lista entera fila por fila
  (costo anterior, nuevo, variación, qué pasa) y queda como historial.
- **Qué se aplica solo** (decidido 08/10): cambios de costo hasta un tope configurable
  por lista (10 % por defecto), con historial (se cierra el precio anterior). Lo nuevo,
  las subas grandes, las bajas, los posibles duplicados y lo dudoso esperan.
- **Revisión:** botones por fila o por varias filas seleccionadas: Aplicar, Ignorar,
  «Es el mismo» (une a un producto existente, una sola vez) y «Es nuevo».
- **Bajas** (decidido 08/10): si un producto ya no está en la lista completa, se cierra
  su precio con ese proveedor (sigue en venta y con sus otros proveedores).
- **Proveedor más barato:** Odoo 20 ya elige al comprar el proveedor vigente de menor
  precio (verificado en el código y en el lab, `_select_seller`); la importación avisa
  cuando otro proveedor quedó más barato.
- **Tarea diaria:** baja e importa las listas con link y aplica lo automático; a las
  que se suben a mano o llegan por correo les deja un recordatorio si están vencidas.
  Toda lista con algo para revisar genera una actividad al responsable.
- **Solo la lista vigente se toca** (09/10): por proveedor, la importación más nueva que no
  esté descartada ni con error (ni reemplazada sin nada aplicado). Además, nunca se deshace
  una lista si una más nueva tiene filas aplicadas. Las anteriores son historial de solo lectura: no se
  aplican, deshacen, ignoran ni vuelven a simular. Para volver a una anterior: deshacer y
  descartar la más nueva. Las importaciones y sus filas no se borran (solo el
  administrador). El historial de costos de Odoo (`product.supplierinfo`) sigue siendo
  editable como en Odoo estándar.
- **Compras según la lista vigente** (09/10, módulo aparte `comercio_compras_lista_vigente`,
  depende de `purchase`): el «Catálogo» de la orden de compra filtrado por proveedor muestra
  solo sus precios vigentes (Odoo mostraba también los cerrados y todo lo comprado alguna
  vez; lo comprado se sigue mostrando si nunca tuvo precio cargado de ese proveedor). Una
  línea con un producto fuera de la lista vigente se marca en amarillo con el motivo y
  avisa; no bloquea. Si otro proveedor tiene precio vigente menor para esa cantidad
  (respetando su mínimo), la línea lo muestra y un cartel arriba de los productos lo
  resume con la salvedad «solo precio de lista; no incluye flete ni condiciones» (P-004).
  Si en una recepción llegan productos fuera de la lista vigente (Odoo deja agregarlos y
  les pone el costo general del producto, verificado 09/10), queda una nota y una tarea en
  la orden para revisar el precio antes de facturar; no se bloquea la recepción.
  Aparte para que `comercio_catalogo` no dependa de Compras (P-042).
- **Formato cambiado:** si faltan columnas, se vuelven a detectar solas (como la primera
  vez: fila de títulos y columnas por sus nombres habituales). Si aparecen el costo y el
  código o la descripción, se guardan, la importación avisa qué cambió y **no se aplica
  nada automáticamente** en esa lista (precisión del 09/10). Solo se guarda si la lista
  la subió una persona a mano: una que llegó por correo o link se procesa con el formato
  detectado pero no cambia la configuración del proveedor (el «De:» se puede falsificar). Si no, queda en error con los
  títulos encontrados. Para títulos que no se reconocen se podría sumar IA (P-020), a
  decidir midiendo con listas reales.
- **Correo:** solo se aplica algo solo si el remitente coincide **exacto** con «Correos del
  proveedor». El «De:» de un correo se puede falsificar: por eso, aun así, lo automático
  se limita a los cambios de costo chicos (tope) y lo demás se revisa.
- **Link:** solo http/https a direcciones **públicas** (se rechazan localhost, la red del
  local, link-local y metadatos de nube). El link se lee con el mismo analizador que la
  descarga (urllib3) y se rechazan los que tienen `@`, `\` o espacios. Además se revisa
  la dirección a la que **realmente** se conectó antes de leer (por si el DNS cambia
  después de validar); si no se puede saber, no se descarga. Cada redirección se
  revalida y hay tamaño máximo. En el lab se habilita la red local con el parámetro de
  sistema `comercio_catalogo.permitir_red_local` (nunca en producción). Pendiente:
  probar una descarga https pública real (el lab no tiene salida a Internet).
- El motor (`addons/comercio_catalogo/catalogo/`, Python puro) es **el mismo** que usa la
  herramienta de línea de comandos para la carga inicial masiva.

## Ajustes tras las pruebas adversariales (08/10)

- El proveedor se identifica por su **id** (no por nombre: puede haber homónimos).
- Una fila a revisar de un producto existente **no** cuenta como baja; si la «lista
  completa» trae menos de la mitad de los productos que el proveedor tiene hoy, no se
  calculan bajas (archivo cortado o columnas mal elegidas).
- Al llegar una lista nueva, las anteriores sin aplicar quedan **reemplazadas** (aplicarlas
  volvería atrás los precios). Al aplicar se compara con lo simulado: si algo cambió
  (otra lista o un cambio a mano), esa fila no se aplica y avisa.
- Costo vacío → revisar; si no hay columna de costo, la importación queda en error.
  Números de Excel y CSV de Windows (cp1252) se leen bien.
- Más de 400 filas se aplican **en segundo plano**, en tandas, con aviso al terminar
  (3000 productos nuevos: ~112 s en tandas; una fila: <1 s; simular 3000: ~3 s).
- Las columnas sugeridas se guardan solo si el archivo se leyó bien; ya aplicada una
  importación no se vuelve a simular (se conserva el registro de lo hecho).

## Ajustes tras las pruebas a mano del titular (08/10)

- **Proveedor que cambia sus códigos:** si un producto «nuevo» se parece a uno que ese
  mismo proveedor tenía y que no vino en la lista, sale como posible duplicado con el
  aviso «¿cambió el código?». «Es el mismo» actualiza el código (con historial de precio)
  y la baja del código viejo se resuelve sola.
- **Volver atrás:** Deshacer por fila o todo lo aplicado, y Descartar una importación.
  No se deshace una lista si después se aplicó una más nueva.
- **Seguridad:** de una fila, un usuario solo puede escribir la decisión y el producto
  elegido; el resto (estado, datos para deshacer) lo escribe solo el módulo. Si no, por
  API se podría armar una fila que al deshacerla cambie cualquier producto o precio.

## La lista es el catálogo del proveedor (19/10, P-048)

Probado con listas reales (FC ~10 500 filas, Gas del Sur 3246): crear un producto por fila
llena Odoo de productos que no se venden, imposibles de categorizar; con dos proveedores,
la mitad de las filas salía «posible duplicado», y el POS de Odoo 20 carga solo 5000
productos al abrir. Desde la versión 20.0.1.5.0:

- Lo que no tenemos es **catálogo del proveedor**: se ve en la lista (con su costo), no
  cuenta «para revisar» y no se crea solo. Se **agrega** a pedido («Agregar a nuestro
  catálogo»), con la **categoría** de la fila: por defecto el **rubro** elegido al importar
  (queda guardado en la lista del proveedor), cambiable fila por fila o en varias a la vez.
- Las categorías se pueden crear desde el desplegable (solo nombre y madre; se avisa si ya
  existe una igual escrita distinto).
- En las filas, lo nuestro aparece primero. «Productos» del proveedor abre su última lista
  filtrada en lo nuestro; sin el filtro, el catálogo entero.
- **Buscar producto**: una sola pantalla busca en la última lista de todos los
  proveedores a la vez (palabras en cualquier orden, números enteros), muestra quién lo
  vende y a cuánto, si ya lo tenemos, y lo agrega ahí mismo.
- Una importación queda «Aplicada» cuando no queda nada pendiente de lo nuestro; mientras
  sea la vigente, se siguen pudiendo agregar productos de su catálogo.

## Unidad de compra del proveedor (20/10, P-053)

Lo que se vende suelto se lleva en la unidad de venta (kg) y la presentación del
proveedor es una unidad de Odoo relacionada («Caja 1000 tornillos» = 2,5 kg) en su precio
de proveedor: Odoo pide en cajas y recibe en kg. Las listas lo respetan: si el precio de
ese proveedor tiene unidad propia, la lista trae el precio de esa unidad y se guarda tal
cual (no se divide la caja), también en el historial, deshacer y el precio por mayor. Si
la unidad de la lista no se puede convertir a la del producto (lista por unidad o caja de
unidades, producto en kg), la fila va a revisar y se elige ahí la unidad de compra
(creándola si hace falta); cambiar la unidad nunca es automático. Los productos nuevos se
siguen creando con la unidad de la lista.

## Alternativas consideradas

- Seguir con la terminal: no lo puede usar el personal.
- Importador estándar de Odoo: no simula, no compara, no tiene historial ni similitud.

## Consecuencias

- Segundo módulo de backend propio; probado con `make e2e-catalogo`.
- Las listas por correo necesitan el dominio y el correo entrante de Odoo (P-022).
- Páginas de proveedores con usuario y contraseña: se suben a mano (no se guardan
  credenciales de terceros).
- Antes de producción: relevar el origen real de cada proveedor y su frecuencia (P-021).
