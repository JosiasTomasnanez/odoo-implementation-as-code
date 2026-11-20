# 0016. Precio de venta sugerido por margen de la categoría, revisado antes de aplicarlo

- Estado: aceptado (implementado en el lab; márgenes reales a definir con el negocio, P-030)
- Fecha: 2026-10-12

## Contexto

El negocio quiere margen automático sobre el costo, quizás distinto por rubro, con
redondeo (P-030). El costo ya lo mantienen las listas de proveedores (P-044: precio por
unidad más barato entre sus proveedores, salvo «Costo manual»). El precio de venta tiene
que coincidir en la ficha, la caja y la etiqueta de góndola.

## Decisión

Módulo `comercio_precios` (On-Premise):

- **Regla en la categoría** (la carga el negocio en Odoo, no en `config/`): margen (%),
  base (costo del producto o precio de un proveedor en particular), IVA de venta y
  redondeo. Una subcategoría sin dato usa el de su madre.
- **Precio sugerido** = base × (1 + margen) × (1 + IVA), redondeado **para arriba** al
  múltiplo de la categoría. Se recalcula solo; el **precio de venta no cambia solo**.
  Excepción (decidida 12/10): un producto **nuevo sin precio de venta** (p. ej. creado desde
  una lista, que lo deja en $1) toma el sugerido al crearse y queda para imprimir su etiqueta.
- **«Precios a actualizar»**: los productos cuyo precio de venta difiere del sugerido. Se
  aplican (todos o algunos) y pasan a **«Etiquetas a reimprimir»**.
- **«Precio manual»**: escribir el precio a mano lo saca de las sugerencias hasta
  desmarcarlo (mismo criterio que «Costo manual»).
- **Precios con IVA incluido** en la empresa (`account_price_include = tax_included`): el
  precio de venta es el que paga el cliente y se redondea ese. En el lab está en
  `config/ejemplos`; pasa a `config/base` cuando lo confirme el contador.

## Alternativas consideradas

- **Lista de precios nativa con recargo sobre el costo (en vivo):** sin código, pero el
  precio de la caja cambia en el momento en que se importa una lista, sin revisión, y las
  etiquetas quedan viejas. Se puede usar para mayoristas o pilotos.
- **Márgenes en `config/valores.yaml` (ADR 0010):** versionados, pero obligan a pasar por
  el implementador para cambiar un margen. El titular eligió que los cargue el negocio.
- **Precio sugerido del proveedor (PVP de su lista):** queda para cuando haya listas reales
  que lo traigan (P-014).

### Ampliación: margen especial por producto (19/10)

Pedido del titular: además del margen por rubro, **excepciones para ciertos productos**.
Cada producto puede tener «Margen especial» y su porcentaje (puede ser 0): reemplaza solo
el margen de la categoría; la base (costo o proveedor) y el redondeo siguen saliendo de
la categoría (el IVA, del producto: ver la ampliación siguiente), así el producto sigue al costo como los demás. Se diferencia de
«Precio manual» (precio fijo que no sigue al costo). Pantalla «Márgenes especiales» y campo
en la ficha; lo cambia el grupo «Costos y precios» sin administrar productos (solo esos
dos campos) y queda en el chatter.

**22/10:** el margen especial también puede elegir su **base**, como las categorías:
«Calcular sobre» costo del producto o precio de un proveedor (con su proveedor de
referencia). Vacío = la base del rubro. El IVA y el redondeo siguen saliendo de la categoría.

### Ampliación: manda el IVA del producto (19/10)

Antes el IVA de la categoría le ganaba al del producto: un producto al 10,5 % en un rubro
del 21 % se calculaba con 21 % y al aplicar el precio volvía a 21 %. Ahora **manda el IVA
del producto** (el que cobra la caja) y el de la categoría pasa a ser el **IVA por
defecto**: se pone a los productos nuevos del rubro y a los que no tienen IVA (al crearlos
o al aplicar el precio). Cambiar el IVA de un producto recalcula su sugerido y lo manda a
«Precios a actualizar»; *Cómo se calculó* dice de dónde salió el IVA. Exento: «IVA Exen»
o «IVA 0 %» (vacío = el del rubro). Cambiar el IVA por defecto de una categoría no toca
los productos que ya tienen el suyo. Quién puede cambiar el IVA de un producto: hoy
quien administra productos (es un dato fiscal); a definir con administración (P-034).

## Consecuencias

- Un módulo más que mantener (inventario en `docs/codigo-propio.md`), con prueba
  `make e2e-precios`.
- El IVA de cada rubro pasa a ser un dato de la categoría: lo define el contador (P-034).
- Pendiente con el negocio: margen y redondeo de cada rubro, quién aplica los precios y
  cada cuánto, y si el mayorista usa una lista sobre el mismo costo (P-015).
