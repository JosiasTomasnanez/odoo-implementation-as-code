# 0037. Listas de clientes con descuentos por rubro y por producto, desde la administración

- Estado: aceptado (implementador, 10/11)
- Fecha: 2026-11-10
- Amplía: ADR 0036 (antes: una lista de cliente era solo «tal lista − X %» y no se podía cambiar).

## Contexto

En `/admin` se podía crear una lista «Mayorista − X %» y elegirla al aprobar un cliente. El
implementador pide algo más completo y a la vista: descuentos por **rubro** (categoría del PdV) o
por **producto**, elegir **a qué clientes** aplica una lista, y que el cliente vea sus condiciones
en su lista y en el Excel.

## Decisión

- Una **lista de clientes** hecha en la administración es: una lista base de Odoo + un descuento
  general + descuentos propios por rubro o por producto (0 a 60 %, de a medio punto). Todos se
  calculan **sobre la lista base** (no se acumulan): el del producto le gana al de su rubro, y el
  del rubro al general. La compra mínima es la que cada producto tiene en la lista base.
- La tienda guarda las **condiciones** (`listas_nuevas.reglas`, con `version` y `pendiente`); los
  **precios los sigue calculando Odoo**. El conector lleva la lista a Odoo
  (`tienda_sincronizar_clientes`), que guarda las condiciones en la lista
  (`comercio_tienda_reglas`) y **regenera sus reglas** (`_comercio_tienda_aplicar_reglas`), tocando
  solo lo que cambió. Los precios vuelven por la sincronización de siempre.
- **Rubros:** las reglas de las listas de Odoo no conocen las categorías del PdV (solo las
  categorías internas). El descuento de un rubro se **despliega en una regla por producto** de ese
  rubro (y sus subrubros). Cuando un producto cambia de rubro o se crea, las listas con descuentos
  por rubro se vuelven a desplegar solas.
- Las reglas de una lista hecha en la tienda **las maneja la tienda**: lo que se le agregue a mano
  en Odoo se pierde en el próximo cambio. Las listas armadas en Odoo (p. ej. «Mayorista») no se
  tocan desde la administración: ahí solo se ven sus clientes y se les pasan clientes.
- **Clientes:** en cada lista se ve quién la usa y se pasan clientes aprobados a ella (cambia su
  lista en la tienda y en su contacto de Odoo, como «Guardar lista»).
- **El cliente** ve «Tus condiciones» arriba de su lista y en el Excel, y en cada producto cuánto
  menos paga que el precio público.

## Consecuencias

- Una lista con descuento en un rubro grande tiene tantas reglas como productos del rubro. Con el
  catálogo real (miles de productos) hay que medirlo; si pesa, la alternativa es que el negocio
  ordene sus categorías internas como los rubros y usar reglas por categoría.
- Precio fijo por producto o escalas por cantidad siguen siendo de Odoo (en una lista de Odoo).
- Publicar primero la tienda (acepta la confirmación con o sin `version`) y después el módulo.
- Prueba: `make e2e-tienda-admin` (paso 3b).
