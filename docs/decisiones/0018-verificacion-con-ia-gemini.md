# 0018. Verificación con IA (Gemini) de los posibles duplicados, a pedido y solo como sugerencia

- Estado: aceptado
- Fecha: 2026-10-19

## Contexto

El ADR 0014 dejó el motor de similitud propio para detectar «posibles duplicados» al
cargar listas de proveedores y abrió la puerta a sumar IA para los casos dudosos, a
decidir midiendo con listas reales. Con FC y Gas del Sur (19/10) quedó claro que el motor
marca muchos parecidos que una persona tiene que mirar uno por uno: la misma medida
escrita distinto, o medidas parecidas que son otro producto. P-021 ya planteaba una
doble verificación con Gemini.

La IA nativa de Odoo 20 no sirve para esto: no admite clave propia, cobra con créditos
IAP y necesita pgvector (P-020). El titular generó una clave de la API de Gemini (Google
AI Studio) para el proyecto.

## Decisión

Módulo aparte **`comercio_catalogo_ia`** (depende de `comercio_catalogo`) con:

- **Botón «Verificar con IA»** en las filas «posible duplicado» marcadas, y «Verificar
  dudosos con IA» para todas las de una lista. La IA da su **sugerencia**: «es el mismo»
  (y cuál), «es otro» o «dudoso», con confianza y un motivo corto. **No aplica nada.**
- **«Aceptar sugerencia de la IA»**: una persona confirma. «Es el mismo» vincula y «Es
  otro» crea el producto; las dudosas quedan para decidir a mano. Con confianza ≥ 0,8
  se deja preseleccionado «Es el mismo que».
- **Qué se manda a Google:** descripción, código y unidad de la fila del proveedor, más
  nombre y descripciones de otros proveedores de hasta 3 productos nuestros parecidos.
  **Nada de clientes, ventas, costos ni márgenes.**
- **Clave fuera de la base y del repo:** variable de entorno `GEMINI_API_KEY` del
  contenedor de Odoo. En el lab sale del `.env` del repo (ignorado por git, permisos 600)
  vía `infra/scripts/lib.sh`; en el servidor, del `onprem.env`. Sin clave, el botón no
  aparece. Así la clave no viaja en los backups ni se ve desde Odoo.
- **Modelo:** `GEMINI_MODEL` (por defecto `gemini-3.5-flash-lite`, el más barato que
  respondió bien) y `GEMINI_MODEL_RESPALDO` (`gemini-3.8-flash`). Si Google responde
  «alta demanda» (429/503) se reintenta y se pasa al respaldo; un modelo retirado (404)
  pasa directo al respaldo. Respuesta en **JSON con esquema** y temperatura 0.
- **Costo controlado:** solo a pedido (nunca automático ni en la tarea programada), filas
  de a 20 por pedido, y cada verificación deja en la importación cuántos pedidos y
  tokens usó.
- Núcleo sin Odoo (`ia/verificar.py`) con tests sin red (`tests/test_catalogo_ia.py`) y
  prueba real `make e2e-ia`.

### Ampliación (19/10, después de la primera prueba manual)

El motor puede equivocarse también en lo que da por seguro, y eso no lo veía nadie. La IA
se puede pedir además sobre:

- **Un producto antes de agregarlo** (fila «nuevo»): se le muestran los 3 productos nuestros
  más parecidos con un umbral más bajo que el del motor (0,35 en vez de 0,50). Si no hay
  ninguno, «Es otro» sin consultar. «Es el mismo» une la fila a ese producto en vez de crear
  uno repetido.
- **Lo ya unido** (por código del proveedor o confirmado antes): «Revisar lo nuestro con IA»
  pregunta si la descripción del proveedor sigue siendo ese producto (caso: el proveedor
  reusa un código para otro artículo). Solo avisa (filtro «La IA duda»); no deshace nada.

Sigue siendo a pedido (hasta 200 filas por clic): revisar toda una lista de 10 000 filas en
cada actualización gastaría tokens en filas que nadie mira. Próximo paso posible: revisar
solo lo nuestro cuya descripción cambió respecto de la lista anterior.

### Ampliación: listas en foto o PDF escaneado (19/10)

Algunos proveedores mandan la lista en PDF o en foto. Un **PDF con texto se lee sin IA**
(`pdfminer`, por la posición de cada letra: exacto y gratis). Una **foto o un PDF
escaneado** los transcribe Gemini, página por página (hasta 10 por archivo), con la orden
de copiar los números tal cual y poner «?» si un dígito no se lee. Lo leído sigue el
camino de siempre (simulación contra la lista anterior) y **nunca se aplica solo**, ni los
cambios chicos: un dígito mal leído aparece como suba o baja grande. A Google va la imagen
de la lista del proveedor (no hay datos del negocio). Medido con una foto de 42 filas:
42 iguales a lo impreso. Por correo o link solo se aceptan Excel y CSV (un PDF de factura
o el logo de una firma se leerían como lista). Falta probar con una foto real.

### Ampliación: categorizar productos del punto de venta (22/10)

Módulo `comercio_pos_categorias`. Los botones de arriba del POS son las **categorías del
punto de venta** (`pos.category`), distintas de los rubros. En el menú Acciones de Productos
(también en *Punto de venta → Productos*, junto a «Fusionar»): **«Categorizar con IA»**
(Gemini elige, entre las categorías del POS que existen, la que más se acerca a cada
producto, o ninguna) y **«Categorizar a mano»** (agregar o reemplazar). La IA saltea los que
ya tienen categoría, solo **sugiere** (las de confianza ≥ 0,8 vienen marcadas) y nada se
escribe hasta «Aplicar». A Google va el nombre del producto, su rubro y los nombres de las
categorías del POS: nada de costos, precios, clientes ni ventas. Reutiliza el cliente de
Gemini y la clave de `comercio_catalogo_ia`. Hasta 500 productos por clic (tandas de 50 en
paralelo). Medido el 22/10 con productos de ejemplo: ~500 tokens por 2 productos, bien
categorizados. Validar con `make e2e-ia`.

## Alternativas consideradas

- **IA nativa de Odoo:** sin clave propia, créditos IAP y pgvector (P-020). Descartada
  para esto.
- **Que la IA decida sola:** más rápido, pero una vinculación equivocada mezcla los
  precios de dos productos. Las automatizaciones no modifican datos críticos sin control
  (CLAUDE.md).
- **Verificar toda la lista al importar:** gasta tokens en filas que nadie va a mirar.
  Con el catálogo (P-048) se agregan pocos productos por vez: alcanza a pedido.
- **Guardar la clave en Odoo (parámetro del sistema):** viajaría en cada backup y la vería
  cualquier administrador. Descartada.

## Consecuencias

- Hay una dependencia externa (Google) solo para una ayuda opcional: sin internet o sin
  clave, todo sigue funcionando a mano.
- La clave quedó escrita en el chat del implementador: conviene restringirla en Google
  Cloud (solo API de Gemini, tope de gasto) y, para producción, usar una a nombre del
  negocio en el `onprem.env`.
- Revisar cada tanto el consumo (mensajes en las importaciones y la consola de Google).
- Los nombres de los modelos cambian seguido: si uno se retira, se cambia
  `GEMINI_MODEL` en el `.env` u `onprem.env` sin tocar código.
