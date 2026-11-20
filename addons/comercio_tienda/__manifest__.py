{
    "name": "Comercio: tienda online",
    "summary": "Qué se publica en la tienda online y la cola de cambios que lee el conector del local "
    "(productos, precios de las listas, stock libre, fotos y rubros).",
    "description": """
Ver ADR 0031, 0032 y 0033 en el repositorio de la implementación.

- En el producto: «Publicar en la tienda» y «Consultar disponibilidad» (se vende igual y se
  confirma en el día); en Acciones de la lista de productos, de a muchos.
- En la lista de precios: «Sincronizar con la tienda» (la «Tienda online» y las mayoristas) y
  «Es la de la tienda» (la que ve todo el mundo).
- En la categoría: margen de stock para la tienda (unidades que no se ofrecen online).
- Cola de cambios (comercio.tienda.cambio): cada cambio de un producto publicado (datos, precio,
  stock libre, foto) o de un rubro del PdV deja una fila; el conector la lee en lotes
  (tienda_leer_cambios) y la confirma (tienda_confirmar). El local no publica ninguna API: el
  conector sale hacia la tienda.
- «Tienda: a reponer» (Compras y Inventario): lo publicado que llegó al mínimo. La tienda lo
  ofrece solo como «Consultar disponibilidad» y sale de la lista cuando se repone; acciones:
  Pedir al proveedor, Dejar siempre a consultar, No reponer por ahora, Quitar de la tienda.
- Pedidos de la tienda: el conector los trae pagos y los crea confirmados (tienda_crear_pedidos),
  con el cliente por su mail; nunca dos veces el mismo (comercio_tienda_ref único).
- Mayoristas y listas aprobados en la administración de la tienda (tienda_sincronizar_clientes):
  contacto por CUIT (o nuevo, con la etiqueta «Mayorista (tienda online)») con su lista; listas
  nuevas «otra lista − X %» con «Sincronizar con la tienda».
- El usuario del conector solo tiene el grupo «Tienda online: conector» (acceso a la cola).
""",
    "version": "20.0.1.11.0",
    "category": "Sales/Sales",
    "license": "LGPL-3",
    "depends": ["point_of_sale", "stock", "purchase", "sale_stock", "hr"],
    "data": [
        "security/grupos.xml",
        "security/ir.access.csv",
        "data/cron.xml",
        "views/product_views.xml",
        "views/pricelist_views.xml",
        "views/reponer_views.xml",
        "views/hr_employee_views.xml",
    ],
    "installable": True,
}
