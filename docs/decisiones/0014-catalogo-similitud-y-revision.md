# 0014. Catálogo: motor de similitud propio y pantalla de revisión en Odoo

- Estado: aceptado en parte (08/10/2026): M2, M3 y M4 decididos; el uso de IA (M1)
  queda abierto hasta probar con listas reales
- Fecha: 2026-10-08
- Cambia el rumbo de: P-021 («lo nativo antes que lo propio» para las listas de proveedores)

## Contexto

Los proveedores mandan listas en Excel con formatos distintos (más de 1000 productos).
El importador (`integrations/catalogo`, docs/areas/codigos.md) une productos solo por
coincidencia exacta: código de fábrica, o código del mismo proveedor. El mismo producto
en dos proveedores **sin código de fábrica en común** quedaría duplicado.

Investigado (docs/areas/matching-proveedores.md): la IA de Odoo 20 (Enterprise, créditos
IAP, datos a OpenAI/Gemini, sin clave propia) **no trae** una función para detectar el
mismo producto entre proveedores ni para importar listas; habría que programar la
herramienta igual. `odoo-product-matcher` (repo aparte) tiene un motor de comparación
sin IA, con tests, pero el resto está desactualizado (XML-RPC, sin XLSX, nunca probado
contra Odoo real).

## Decisión

- **Motor de similitud propio** en `integrations/catalogo`, portando el núcleo de
  `odoo-product-matcher` (normalización de nombres, unidades, abreviaturas, candidatos).
  Las filas sin coincidencia exacta pero con candidatos parecidos quedan como
  «posible duplicado» con los mejores candidatos, en lugar de crear un producto.
- **Pantalla de revisión en Odoo desde el principio (M2):** módulo `comercio_catalogo_revision`
  con una lista agrupada por proveedor y botones «Es el mismo» / «Es nuevo». Al confirmar
  «Es el mismo», el código de ese proveedor queda en el producto elegido y la próxima lista
  ya coincide exacto (confirmación de una sola vez). El cálculo de similitud corre afuera
  (integración por API JSON-2); el módulo solo muestra y registra las decisiones.
- **`odoo-product-matcher` se archiva** después de portar el núcleo (M3): un solo motor.
- **IA (M1, abierto):** el diseño deja un paso opcional para que un modelo de IA ordene
  o descarte candidatos de los casos dudosos, siempre con confirmación de una persona.
  Qué usar (agente de Odoo con créditos, o API externa como Gemini o Claude) se decide
  midiendo con listas reales anonimizadas: aciertos del motor sin IA, aciertos con IA y
  costo. Se prueba también un agente nativo con ~20 filas cuando esté Enterprise (M4).

## Alternativas consideradas

- Solo IA de Odoo: no existe la función; habría que programarla igual y pagar por uso.
- Revisión en planilla: más rápida de hacer, menos cómoda; el titular prefirió la pantalla.
- Studio para la pantalla: el botón igual requiere código y lo hecho hay que exportarlo (P-028).

## Consecuencias

- Trabajo estimado: motor y prueba con listas reales 3-4 días; pantalla en Odoo 3-5 días.
- Segundo módulo propio de backend (solo On-Premise); se prueba en el lab Community.
- Si se usa una API de IA externa: solo se envían nombres y códigos de productos (sin
  datos personales); la clave va en `.env`, nunca en git; el gasto se mide por lista.
