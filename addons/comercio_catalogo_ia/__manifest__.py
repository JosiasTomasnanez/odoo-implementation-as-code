{
    "name": "Comercio: listas de proveedores con verificación por IA",
    "summary": "Segunda opinión de Gemini sobre los posibles duplicados de una lista de proveedor.",
    "description": """
Ver ADR 0018 en el repositorio de la implementación.

- Un solo botón «Verificar con IA» en cada pantalla (30/10): abre «¿Qué querés revisar?»
  (filas marcadas, posibles duplicados, lo que ya tenemos, filas con problemas, aceptar).
- Filas con problemas (sin precio, repetidas…): la IA explica qué pasó y qué hacer.
- La IA solo **sugiere** (es el mismo / es otro / dudoso, con confianza y motivo); una
  persona confirma con «Aceptar sugerencia de la IA» o decide a mano.
- Se manda a Google solo la descripción y el código de la fila del proveedor y los
  nombres de nuestros productos parecidos. Nada de clientes, ventas ni costos.
- La clave va en el servidor (variable de entorno GEMINI_API_KEY), no en la base.
""",
    "version": "20.0.1.14.0",
    "category": "Inventory/Purchase",
    "license": "LGPL-3",
    "depends": ["comercio_catalogo"],
    "data": [
        "security/ir.access.csv",
        "views/importacion_views.xml",
    ],
    "installable": True,
}
