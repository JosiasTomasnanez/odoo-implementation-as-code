{
    "name": "Comercio: compras según la lista vigente del proveedor",
    "summary": "El catálogo de la orden de compra muestra solo lo que el proveedor tiene en su lista "
    "vigente, avisa si se agrega un producto que no está y sugiere al más barato.",
    "description": """
Complemento de comercio_catalogo para la app Compras (P-042).

- Catálogo de la orden de compra: el filtro por proveedor muestra solo los productos con
  precio vigente de ese proveedor (sin los cerrados, p. ej. «ya no lo tiene»).
- Línea de la orden con un producto fuera de la lista vigente: se marca en amarillo, con
  el motivo, y avisa al elegirlo. No bloquea: a veces se compra igual algo fuera de lista.
- Si la cantidad no llega al mínimo de la lista del proveedor, la línea se marca en
  amarillo («Mínimo 10 Unidades: sin precio de lista») y avisa al cambiar la cantidad: por
  debajo del mínimo Odoo no tiene precio de lista y pone el costo del producto.
- Si otro proveedor tiene un precio vigente menor para esa cantidad, un cartel lo sugiere
  (solo precio de lista con descuento: no incluye flete ni condiciones, P-004).
- Si en una recepción llegan productos fuera de la lista vigente o por debajo de su mínimo
  (Odoo les pone el costo general del producto), queda una nota y una tarea en la orden para revisar el precio
  antes de facturar. No bloquea la recepción.
- «Agregar al pedido» desde «Buscar producto» y desde los productos del proveedor: suma el
  producto a la solicitud de cotización en borrador de ese proveedor (o la crea), con la
  cantidad mínima de su lista.
- «Enviar por WhatsApp» en la orden: abre WhatsApp (Web o la aplicación) con el chat del
  proveedor y el pedido escrito (antes se muestra el mensaje para corregirlo); sin la
  API de WhatsApp Business.
  Cada producto va con el código y la descripción del proveedor (de su lista), no con
  nuestra referencia interna.
- En la recepción, botón «Orden de compra» que lleva a su orden (solo para Compras, como el
  de la factura del proveedor).
""",
    "version": "20.0.1.10.0",
    "category": "Inventory/Purchase",
    "license": "LGPL-3",
    "depends": ["purchase_stock", "comercio_catalogo"],
    "data": ["security/ir.access.csv", "views/purchase_order_views.xml", "views/lista_views.xml"],
    "installable": True,
}
