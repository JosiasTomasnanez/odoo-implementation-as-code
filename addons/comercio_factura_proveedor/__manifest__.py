{
    "name": "Comercio: leer la factura del proveedor y cargar sus productos",
    "summary": "Al subir la factura de un proveedor (PDF o foto) la lee el comercio, sin la digitalización "
    "paga de Odoo: completa los datos, carga los artículos y permite agregar al catálogo los que no tenemos.",
    "description": """
Ver ADR 0021 en el repositorio de la implementación.

- Reemplaza la digitalización de Odoo (cobra créditos IAP por factura): un PDF con texto
  se lee sin IA (posición de las letras) y una foto o un PDF escaneado los lee Gemini con
  la clave propia del comercio (comercio_catalogo_ia).
- Funciona al subir la factura (Compras → Facturas, o «Subir factura» en la orden de
  compra) y con el botón «Leer factura» de una factura en borrador.
- Completa lo que esté vacío: proveedor (por CUIT), su CUIT y condición de IVA, tipo y
  número de comprobante, fecha y vencimiento.
- Cada artículo se busca por el código del proveedor, el código de barras o su
  descripción exacta, en nuestros productos y en la lista vigente del proveedor. Los
  encontrados se cargan en la factura (cantidad, precio y bonificación de la factura;
  las líneas que vienen de la orden de compra se completan en vez de duplicarse).
- Los que no tenemos también quedan anotados en la factura (sin producto, con la
  descripción y el precio de la factura) y en la pestaña «Leído de la factura» para agregarlos a
  nuestro catálogo: desde la lista del proveedor (como en «Buscar producto») o como
  producto nuevo, con su categoría (de ella sale el precio de venta), o para elegir a
  mano cuál de nuestros productos es.
- El precio de la factura no cambia costos ni precios de venta: los siguen moviendo las listas (P-044).
- El pie de la factura también se carga: el flete como una línea con su IVA y cada percepción con su
  impuesto de l10n_ar (no pasan a la orden de compra). Si el total de Odoo no da el TOTAL impreso,
  avisa arriba de la factura y «Se debe pagar» queda en excepción.
- Compras sin factura: un diario de compras sin documentos fiscales para registrar
  y pagar lo que todavía no tiene la factura real del proveedor (presupuesto, remito valorizado).
  Sin IVA (no va al libro IVA); botón «Sin factura» en la orden de compra y menú
  Compras → Órdenes → Compras sin factura.
""",
    "version": "20.0.1.11.0",
    "category": "Accounting/Accounting",
    "license": "OPL-1",
    "depends": ["purchase", "account_3way_match", "comercio_catalogo", "comercio_precios", "comercio_catalogo_ia"],
    "data": [
        "security/ir.access.csv",
        "views/account_move_views.xml",
    ],
    "installable": True,
}
