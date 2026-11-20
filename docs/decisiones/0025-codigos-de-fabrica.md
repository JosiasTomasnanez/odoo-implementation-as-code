# 0025. «Códigos de fábrica»: reemplazar rápido el código propio por el del envase

- Estado: aceptado (pedido del implementador, 26/10; P-058)
- Fecha: 2026-10-26

## Contexto

Cada producto que se crea sin código de barras recibe uno propio `20…` (P-007, `comercio_catalogo`).
Muchas listas de proveedor no traen el código de barras, pero el producto sí lo trae impreso en
el envase. Hay muchos productos de los dos tipos. El negocio no quiere dejar de crear el `20…`,
pero sí poder cambiarlo por el de fábrica rápido, sin abrir los productos de a uno.

Odoo 20 tiene un solo código de barras por producto, y además códigos por unidad
(`product.uom`, lo que antes era el empaque) que la caja también lee al escanear
(`point_of_sale` carga `product.uom` y busca por `barcode`). Verificado en el código de Odoo 20.

## Decisión

Módulo propio `comercio_codigos_fabrica` (depende de `comercio_catalogo`):

- **Pantalla «Códigos de fábrica»** (*Costos y precios → Listas de proveedores*): lista editable
  con los productos que tienen el `20…` y no se marcaron «sin código de fábrica». Se hace clic
  en «Escanear acá» y se escanea el envase; el lector manda Enter y pasa a la fila siguiente.
- **Al escanear:** el código de fábrica pasa a ser el código de barras y el `20…` queda como
  **código alternativo** (`product.uom` en la unidad del producto), así una etiqueta ya pegada
  sigue funcionando en la caja. Queda en el chatter.
- **No se acepta** un código inválido (dígito verificador), interno (empieza con 2) o que ya es
  de otro producto (principal o alternativo): avisa y sugiere «Fusionar» si es el mismo.
- **«No tiene código de fábrica»** (sueltos, pesables, fraccionados): sale de la lista sin tocar
  el código; «Volver» lo devuelve.
- **Numeración:** el próximo `20…` también mira los alternativos, para no repetir un número ya
  pegado.
- Lo usa el grupo «Costos y precios» sin ser administrador de productos (como los márgenes).

## Alternativas descartadas

- **No crear el `20…` hasta imprimir la etiqueta:** el negocio prefiere que se creen con código.
- **Abrir cada producto y escanear:** es lo que hay en Odoo estándar; lento con cientos.
- **Borrar el `20…` al reemplazarlo:** una etiqueta ya pegada dejaría de leerse en la caja.

## Consecuencias

- Falta probarlo con el lector real y la caja (que el alternativo se lea al escanear).
- Queda para más adelante: escanear al recibir la mercadería (P-058) y que la lista del
  proveedor que trae el código de fábrica lo aplique sola (hoy va a revisar).
- Validar con `make e2e-codigos-fabrica`.

## Actualización 20/11/2026: la lista del proveedor aplica sola el código de fábrica

Pedido del usuario: el código de barras de fábrica tiene prioridad. Si una lista nueva trae el
código de fábrica de un producto que tenía el propio (`20…`), se reemplaza al aplicar (con «Aplicar
todo» o la fila) y el propio queda como **alternativo** (la caja lo sigue leyendo, igual que en
«Códigos de fábrica»); «Deshacer» devuelve el propio y borra el alternativo. Salvaguardas:

- Si el código de fábrica ya es de otro producto, la fila va a revisar.
- Si varias filas de la misma lista traen códigos de fábrica **distintos** para el mismo producto
  (p. ej. guantes de cuatro marcas unidos a un guante genérico), son productos distintos: todas
  pasan a «¿Es el mismo?» con ese producto y nada se aplica solo.
- La IA no une sola una fila si otra de la misma lista también dice ser ese producto, ni si la fila
  trae un código de fábrica distinto del que el producto ya tiene.
- Si la ficha del proveedor no tenía columna de código de barras (la primera lista no los traía),
  se vuelve a buscar en cada lista nueva.
