# 0039. Carteles de precio en A4 con un módulo propio aparte

- **Estado:** vigente; en producción desde el 20/11/2026 (probado antes en el lab)
- **Pedido:** el usuario, 20/11: hoy los carteles grandes de precio se hacen a mano (fibrón y cartulina).

## Contexto

Las etiquetas de góndola salen por la Zebra (ADR 0030), pero para algunos productos hace falta un
cartel grande y llamativo, con el texto que se quiera y el precio de Odoo. Odoo no trae carteles de
precio en A4 (solo etiquetas con código de barras en hojas de etiquetas).

## Decisión

Módulo propio separado, `comercio_carteles` (solo `product`, `account` y `mail`):

- Cada cartel es un registro (`comercio.cartel`): título libre (el nombre del producto por defecto),
  aclaración, precio (el de Odoo **con IVA**, redondeado hacia arriba, o a mano), «antes» tachado,
  código de barras opcional, copias, tamaño (1, 2, 4 u 8 por A4) y estilo (Clásico u Oferta, sobre
  blanco por la tinta en cartulina).
- PDF con el motor de reportes de Odoo (QWeb + wkhtmltopdf), con líneas de corte; las letras se
  calculan para que entren (`medidas.py`, probado en `tests/test_carteles.py`).
- Al imprimir se guarda el precio impreso: si después cambia el precio de venta, el cartel pasa a
  «Para reimprimir» (como las etiquetas con `comercio_etiqueta_pendiente`).

## Descartado

- **Plantilla de etiquetas de Odoo** (`product.label.layout`): pensada para etiquetas con código en
  hojas de etiquetas, no para texto libre grande.
- **Un documento de texto o planilla aparte:** no sabe el precio de Odoo ni avisa cuando cambia.

## Pendiente

- Ver con Daniel en el uso real: tamaños, estilos, si hace falta «precio por kilo» de la ley de góndolas.
