# Prueba visual del lab (paso a paso)

**Guía única para probar todo a mano**, en el orden del día a día de la **primera etapa**:
ferretería (ADR 0022), sin caja ni facturación en Odoo (ADR 0017). Las registradoras cobran
y el puesto, al imprimir el pedido, lo da por cobrado con «Cobrado en registradora» (ADR 0019,
`puestos_cobran_en_registradora: true` en `config/valores.yaml`). Lo de las etapas siguientes
(QR y caja de Odoo, factura con CAE, mayorista) está al final, en la sección 10.

Cada paso dice **dónde** hacerlo y **qué tendría que pasar** (✔). Si algo no coincide,
anotarlo (sección 13). Todo es laboratorio: datos ficticios «[EJ]» más las listas reales de
los proveedores, que no salen del lab.

Cada sección cierra con un recuadro **«En el día a día»**: quién lo hace, cuándo, y los
**huecos a mirar** (lo que el flujo todavía no contempla). Sirve para enseñarlo y para llevar
preguntas al negocio.

| Sección | Detalle o versión para el personal |
|---|---|
| 0. Preparación | `laboratorio.md` |
| 1. Productos y códigos | `codigos-fabrica.md`, `docs/areas/codigos.md` |
| 2. Listas de proveedores · 3. Buscar producto | `listas-proveedores.md` |
| 4. Precios de venta | ADR 0016 |
| 5. Pedir al proveedor · 6. Recepción y stock | `listas-proveedores.md` |
| 7. Facturas de proveedor | `facturas-proveedor.md` |
| 8. Venta en el puesto | `categorias-pos.md` |
| 9. Balanza | `prueba-balanza-real.md` |
| 10. Etapas siguientes | `demo-puesto-caja.md`, `cierre-de-caja.md`, `devoluciones.md`, `ventas-con-y-sin-factura.md`, `listas-de-precios.md` |
| 11. Backup | `backup-restauracion.md` |

Quedan afuera los que solo aplican al servidor del local (`https-servidor.md`,
`instalar-servidor.md`).

---

## 0. Preparación (15 min)

- [ ] **Lab desde cero** (borra todo y lo rearma; unos 10 minutos):

      ```bash
      make lab-completo
      ```

      Hace, en orden: borrar el lab, crear la base, aplicar `config/` (capas `base`,
      `onpremise` y `ejemplos`), cargar los productos de ejemplo
      (`data/plantillas/productos.csv`), dejar ARCA homologación lista (`make lab-arca`) y
      cargar las **listas reales** de `data/privado/listas-proveedores/`
      (`make lab-listas-reales`). En otra PC, sin esos archivos, se saltean.
- [ ] Listas reales que carga (`infra/scripts/lab-listas-reales.py`): **24 proveedores**.
      - Ferretera Central, en dos partes (General y Bulones). De la General quedan
        agregados a nuestro catálogo 30 tornillos Fix y 10 cadenas, como haría el negocio.
      - Gas del Sur.
      - Nortex, PLASTIMET y Clorosur, con su mapeo de columnas (no se reconocen solas).
      - Otros 19 con las columnas **detectadas solas**, como cuando el negocio sube una lista
        nueva: C. Kappa, Lambda, Theta, Zeta, Pinturas Beta, Omega, Rho, LUMINA, LTX…
        Los que tienen varias hojas (LUMINA, LTX, Chi, Aluminio Phi, Bazar Alfa) quedan con
        una parte por hoja.
- [ ] Si el lab ya estaba armado: `make lab-up`.
- [ ] Abrir <http://localhost:8069> en Chrome → usuario `admin`, contraseña `admin`. Es
      administrador: ve todas las apps. El lab no trae usuarios por rol; los roles
      propuestos están en `docs/areas/roles-y-tareas.md`.
- [ ] En el punto de venta se entra como **empleado con PIN** (empleados ficticios de
      `config/ejemplos/25-empleados.yaml`): **1111** «[EJ] Atención mascotas» (arma pedidos,
      no cobra), **2222** «[EJ] Cajero», y «[EJ] Encargado», que es el usuario `admin`.
- [ ] Abrir también <http://localhost:8025> (buzón de prueba: ahí llegan todos los mails;
      nada sale a Internet).
- [ ] Tener a mano `data/ejemplos/listas/ferretera-ejemplo-2.xlsx` y la factura ficticia
      `data/ejemplos/facturas/factura-ejemplo-distribuidora-norte.pdf` (se regenera con
      `.venv/bin/python infra/scripts/factura-ejemplo.py`).
- [ ] Para la IA (listas en foto, verificar, categorizar, facturas en foto): `GEMINI_API_KEY`
      en el `.env`. Sin clave, esos botones no aparecen o avisan. Si se cambia la clave:
      `make lab-up` (recrea el contenedor).
- Para probar desde el celular u otra PC: `make lab-red` y entrar a
  `http://<IP de la notebook>:8069` (solo en una red de confianza; al terminar, `make lab-local`).

Si ya probaste antes, algunos resultados cambian (productos que ya existen). Para seguir el
recorrido exacto, empezar de cero con `make lab-completo`.

> **Precio de venta:** un producto nuevo toma solo el precio sugerido por el margen de su
> categoría (sección 4). Sin margen quedaría en $1; por eso desde una lista no se deja
> agregar a una categoría sin margen. El lab carga los precios **con IVA incluido**.

> **En el día a día:** el servidor del local se arma igual, sin clics a mano
> (`infra/servidor/instalar-odoo.sh` + `make apply ENV=onpremise`). Si el lab se rompe, se
> rearma: es la idea central del proyecto.

---

## 1. Productos y códigos (15 min)

**1.1 Un producto con dos proveedores.** *Inventario → Productos → Productos* → abrir
«[EJ] Alimento gato castrado 7,5 kg».
- [ ] ✔ Código de barras `7790000001017` (el de fábrica, tal cual).
- [ ] ✔ Categoría «[EJ] Mascotas / [EJ] Alimento».
- [ ] Pestaña **Compras**: ✔ dos proveedores con su código, precio y cantidad mínima:
      Distribuidora Norte (A-100, 25.000, mín. 1) y Mayorista Sur (Z-9, 24.500, mín. 10).

**1.2 Un producto de ferretería.** Abrir «[EJ] Cinta métrica 5 m».
- [ ] ✔ Código de barras `7790000002021`, categoría «[EJ] Ferretería», proveedor
      «[EJ] Bulonera Oeste» (B-3).
- [ ] Abrir «[EJ] Tornillo T1 aguja (por kg)»: ✔ unidad **kg** y código propio `20…`
      (no trae código de fábrica).

**1.3 Producto sin código de fábrica.** Abrir «[EJ] Correa nylon 1,5 m roja».
- [ ] ✔ Código de barras propio que empieza con `20…` y **Referencia** con el mismo número corto.
- [ ] ✔ Categoría «[EJ] Mascotas»: **no** controla stock (ver 1.7).

**1.4 Crear un producto a mano.** *Inventario → Productos → Productos* → **Nuevo** → solo el
nombre → guardar.
- [ ] ✔ Recibe solo una **Referencia** (número) y un **Código de barras** `20…` con ese número.
- [ ] Otro producto escribiendo un código de fábrica en *Código de barras*: ✔ se respeta.

**1.5 Códigos de fábrica** (ADR 0025). *Costos y precios → Listas de proveedores →
Códigos de fábrica*.
- [ ] ✔ Están los productos con código propio `20…`. Clic en **Escanear acá** de la primera
      fila → escribir `7798310622823` + Enter (o escanear un envase real): ✔ pasa a la fila
      de abajo y el producto sale de la lista. En su ficha: ese código, y el `20…` viejo
      queda como alternativo (se ve en el historial de la ficha).
- [ ] Escanear el mismo código en otra fila: ✔ avisa «El código … ya es de …». Con un
      dígito cambiado (`7798310622824`): ✔ «no es un código de barras de fábrica válido».
- [ ] **No tiene** en otra fila: ✔ sale de la lista. Filtro «Marcados sin código de
      fábrica» → **Volver**: ✔ vuelve a la lista.
- [ ] En el puesto (sección 8): tipear en la búsqueda el `20…` viejo: ✔ encuentra el
      producto. Las etiquetas ya pegadas siguen sirviendo.

**1.6 Precio a mano.** En el alimento del 1.1: *Precio de venta* → por ejemplo `45000` →
guardar. ✔ Se tilda **Precio manual** (abajo del precio): el margen no lo va a cambiar
(se usa en el 4.3).

**1.7 Etiquetas y categorías.**
- [ ] En el producto: **Imprimir etiquetas** → elegir formato (hoja o ZPL para la Zebra) y
      cantidad → ✔ PDF con el código de barras legible. Destildando **Imprimir con
      precio**: ✔ sale solo con nombre y código.
- [ ] *Inventario → Configuración → Productos → Categorías* → «[EJ] Ferretería»: ✔ casilla
      **Controla stock** marcada (primera etapa = ferretería). En el lab también la tiene
      «[EJ] Alimento» (ejemplos viejos); «[EJ] Mascotas», no.

> **En el día a día** (a validar con el negocio):
> - **Cuatro códigos que no se mezclan** (P-007, `docs/areas/codigos.md`): código de
>   barras de fábrica tal cual; si no trae, uno propio `20…`; referencia interna = el mismo
>   correlativo; el código de cada proveedor va en su fila de la pestaña Compras.
> - **Quién:** administración o depósito. Casi todos los productos entran desde las listas
>   (sección 2); a mano, lo que no viene en ninguna.
> - **Códigos de fábrica:** con el lector en la mano, recorrer la góndola y escanear los
>   envases que tienen código; lo suelto o fraccionado, **No tiene**.
> - **Huecos a mirar:** ¿hay impresora de etiquetas en el depósito y quién pega? ¿Cómo se
>   manejan las **presentaciones** (caja cerrada y suelto: ¿un producto o dos?)? ¿Quién
>   decide la categoría de un producto dudoso?

---

## 2. Listas de proveedores (30 min)

App **Costos y precios**: en la barra, *Buscar producto*, *Listas de proveedores* y *Precios
de venta*. En *Listas de proveedores* están *Proveedores*, *Importar lista*, *Importaciones*,
*Historial de costos* y *Códigos de fábrica*.

> **Idea central (P-048):** la lista del proveedor es su **catálogo**. Subirla no crea
> productos: solo se crean los que se agregan a pedido («Agregar a nuestro catálogo»), con
> la categoría de la fila. Lo que ya tenemos se actualiza (costos, bajas). Importar es
> siempre **simular → revisar → aplicar**.

`make lab-completo` deja cargada la lista ficticia **«[EJ] Ferretera Ejemplo»**, parecida a
la de FC, en tres partes: **General**, **Bulones** e **Importados** (en dólares). De cada
parte ya se agregaron algunos productos a nuestro catálogo. Los Excel están en
`data/ejemplos/listas/` (qué trae cada uno: su `README.md`). Es la lista para mostrarle a
Daniel cómo se lee una lista y cómo se llega al costo.

**2.1 Cómo se lee la lista.** *Proveedores* → «[EJ] Ferretera Ejemplo (General)».
- [ ] ✔ **Columnas del archivo:** código «Código», descripción «Detalle + Descripción del
      producto» (dos columnas juntas), código de barras, costo «Precio de lista» y descuento
      «Desc. %». La columna «PRECIO FINAL (cálculo interno)» **no** está elegida: es una cuenta
      del comercio, no del proveedor.
- [ ] Botón **Productos** → sacar el filtro: ✔ las filas sin precio («SIN STOCK», «Consultar»,
      0) están **a revisar** y no se cargan; las familias («ABRAZADERAS») no son productos; el
      EJ-4002 repetido avisa «aparece dos veces».
- [ ] ✔ Los productos agregados recibieron un código propio `20…` (la lista no trae el de
      fábrica). La **cinta métrica** sí lo trae (`7791234000013`) y sale como **Posible
      duplicado** de «[EJ] Cinta métrica 5 m»: elegirlo en **Es el mismo que** → **Es el
      mismo**. ✔ La cinta queda también con este proveedor.

**2.2 Del precio de la lista al costo.** En la misma lista, bloque **Del precio de la lista
al costo**:
- [ ] ✔ Pesos, **Descuentos** `5`, **Recargo** `2,5`; pestaña **Descuentos por familia**:
      «TORNILLO» `10`; **Descuentos por producto**: «EJ-4001» (Martillo carpintero) `3`.
- [ ] ✔ Debajo, **el ejemplo**, una fila por caso, p. ej. «$ 120,00 · −5 % (lista) · +2,5 %
      recargo → $ 116,85» y el tornillo con «−10 % (TORNILLO)».
- [ ] En la importación, columna **Cálculo del costo** (y, opcional, **Precio de la lista** con el
      ícono al final de la fila de títulos): ✔ cada fila dice cómo se llegó al costo. Abrazadera 16-25 mm: ✔
      «−10 % (columna de la lista)» (oferta del proveedor). Martillo: ✔ «−3 % (producto)» y
      «−5 % (promoción del proveedor)» (columna «Promociones vigentes», en texto como FC).
      Destornillador: ✔ «por mayor desde 6: −10 % (promoción)» y el aviso con el texto entero.
- [ ] Cambiar el descuento de «TORNILLO» a `15` y guardar: ✔ el ejemplo cambia al instante,
      pero **todavía no** el costo.
- [ ] **Recalcular costos** (arriba): ✔ se abre una importación nueva del mismo archivo, con
      los tornillos en **Cambios de costo** (▼ −5,6 %). **Aplicar automáticos** → ✔ el costo
      del tornillo baja. Volver la regla a `10` y recalcular de nuevo.

> **En el día a día:** ¿el descuento del proveedor es igual para todo, o cambia por familia
> o por producto? ¿Quién avisa cuando cambia un acuerdo? (P-056)

**2.3 Dos precios: suelto y por caja.** *Proveedores* → «… (Bulones)».
- [ ] ✔ Se reconocieron solas «Precio Unit. sin IVA», «Precio x caja (c/u)» y «Unidades x
      caja». Familia «TUERCA» con `10` extra.
- [ ] Abrir un bulón agregado → pestaña **Compras**: ✔ dos filas del mismo proveedor, mínimo 1
      y mínimo 100 (más barato). ✔ **Costo** = el de la unidad suelta.

**2.4 Lista en dólares con IVA incluido.** *Proveedores* → «… (Importados)».
- [ ] ✔ **Moneda** Dólares, sin cotización fija: **Dólar del día** con su fecha (en el lab, la
      de ARCA homologación: de prueba, no la real). **La lista trae el IVA incluido**, columna
      **IVA** «IVA %».
- [ ] ✔ En la importación, **Dólar usado** y, en el cálculo de cada fila, «US$ 85 × … » y
      «sin IVA 21 % (columna)»; la cinta de embalar «sin IVA 10,5 % (columna)».
- [ ] *Costos y precios → **Dólar***: ✔ la cotización de hoy. Cambiarla (p. ej. `1450`) →
      **Recalcular listas en dólares** → ✔ aviso «Se recalcularon 1 listas» y en
      *Importaciones* una nueva de Importados (origen «Recálculo») con los cambios de costo: si
      superan el tope de la lista, esperan revisión.
- [ ] Poner **Cotización fija** `1500` en la lista → **Recalcular costos**: ✔ todos cambian.
      Volver a 0 y recalcular.
- [ ] ✔ La columna «Precio U$S c/IVA» **no** se sugirió sola (dice «c/IVA»): se eligió a mano.
- [ ] Agregar la **cinta de embalar** (IVA 10,5 % en la lista) → abrir el producto: ✔ IVA de
      venta y de compra **10,5 %** (no el 21 % del rubro) y el precio de venta calculado con ese IVA.

> Todos los días a las 7, las listas en dólares se recalculan solas si el dólar se movió más
> de 0,5 % (lo chico se aplica solo; lo grande espera revisión).

**2.5 La lista siguiente (subas, bajas, nuevos, formato cambiado).** *Importar lista* →
«[EJ] Ferretera Ejemplo» → `ferretera-ejemplo-2.xlsx` → ✔ tabla de hojas con las tres partes
→ **Simular**.
- [ ] General: ✔ aviso **Formato cambiado** («Precio de lista» → «P. Lista $»), y por eso nada
      se aplica solo.
- [ ] ✔ Martillo «▲» con el aviso **«Sube porque se terminó la promoción del proveedor»** (y no
      se aplica solo), tornillos «▲ +4 %», candado de 40 mm «▲ +25 %»; cinta métrica **Ya
      no está en la lista**; llave francesa en **No los tenemos**; el candado de 50 mm ahora
      tiene precio.
- [ ] **Aplicar automáticos** → ✔ no aplica nada (formato cambiado). Elegir las filas chicas
      y **Aplicar**; el candado de 40 mm queda para decidir.
- [ ] Bulones: ✔ todos «▲ +8 %», se aplican con **Aplicar automáticos** si el tope de la
      lista es 10 %.

**2.6 Categoría nueva y sin margen.** En la General, fila de la llave francesa, columna
**Categoría**:
- [ ] Escribir «[EJ] Llaves» → **Crear "[EJ] Llaves"**. ✔ Se crea y queda elegida. En otra
      fila «[EJ]  LLAVES» → Crear: ✔ avisa que ya existe.
- [ ] **Agregar como nuevo** → ✔ aviso de que «[EJ] Llaves» no tiene margen (quedaría a $1) y
      no crea nada. *Márgenes por categoría* → margen `35` → volver y agregar: ✔ con precio.

**2.7 Historial y volver atrás.**
- [ ] *Proveedores* → la General → **Productos**: ✔ su última lista con el filtro **En nuestro
      catálogo**; sin el filtro, todo su catálogo con **Agregar**.
- [ ] *Historial de costos* → el proveedor: ✔ cada costo con **Desde** y **Hasta** («Hasta»
      vacío = vigente).
- [ ] Escribir otro **Costo** a mano en el martillo → ✔ **Costo manual**. En la importación de
      la lista 2: **Deshacer todo lo aplicado** → ✔ vuelven los costos anteriores, salvo el
      del martillo. Destildar **Costo manual** → ✔ vuelve a seguir las listas.

**2.8 Varias hojas y varias partes.**
- [ ] `.xls` viejo: *Importar lista* → «[EJ] Proveedor XLS» → `tests/datos/lista_ficticia.xls`
      → **Simular**. ✔ Se lee como un `.xlsx`: 3 productos que no tenemos.
- [ ] Armar un Excel con hojas «General» y «Bulones» (cada una con `Cód.`, `Descripción`,
      `Precio` y unas filas) y una «Notas» con texto. Subirlo para un proveedor nuevo.
      ✔ Tabla de hojas: General y Bulones marcadas, Notas no, **Parte** = «Nueva parte».
      Elegir otro **Rubro por defecto** para Bulones → **Simular**. ✔ Dos importaciones y,
      en *Proveedores*, dos listas «(General)» y «(Bulones)».
- [ ] Otro Excel del mismo proveedor, de una hoja, con otros productos: ✔ aparece **Es otra
      parte** → tildarlo, nombre «Herramientas» → **Simular**. ✔ Parte nueva, sin comparar
      con las otras (nada «Ya no está en la lista»).
- [ ] Error a propósito: subir ese Excel en la parte «General». ✔ La simulación avisa que
      vienen pocos productos y pregunta si es otra parte; no da de baja nada. **Descartar**.

**2.9 Filas con problemas y ayuda de la IA** (la IA necesita `GEMINI_API_KEY`; **solo sugiere**).
- [ ] En la General, fila «Candado bronce 50 mm» (SIN STOCK) → **Corregir** → precio `6100` →
      **Corregir y volver a simular la fila**. ✔ Pasa a «Producto nuevo» con su costo y
      «Cálculo del costo … (precio corregido a mano)».
- [ ] En la importación: **Verificar con IA** (un solo botón) → ✔ ventanita «¿Qué querés revisar
      con la IA?» con cuántas filas hay de cada cosa. **Las filas con problemas** → **Revisar** →
      ✔ en **Motivo IA**, qué pasó y qué hacer (corregir, ignorar, preguntarle al proveedor).
- [ ] **Verificar con IA** → **Los posibles duplicados** → ✔ cada uno con su sugerencia; después
      **Aceptar lo que sugirió la IA** → ✔ «Es otro» se agrega, «Es el mismo» une, lo dudoso no.
- [ ] **Lo que ya tenemos** → ✔ aviso con el resultado; filtro **La IA duda**: ✔ vacío.
- [ ] *Buscar producto* → `llave francesa` → marcarla → **Verificar con IA** → **Las filas
      marcadas** → ✔ columna **Sugerencia** y **Motivo**.

**2.10 Lista en PDF o en foto.**
- [ ] «[EJ] Proveedor PDF» → `tests/datos/lista_ficticia.pdf` → **Simular**. ✔ 60 productos
      leídos **sin IA** (el PDF tiene texto). En **Archivo original** queda el PDF.
- [ ] «[EJ] Proveedor foto» → `tests/datos/lista_ficticia_foto.png` → **Simular** (tarda
      unos segundos). ✔ Aviso «Lista leída con IA…» y 42 productos. Comparar dos o tres
      precios con la foto. **Aplicar automáticos**: ✔ no aplica nada (lo leído con IA lo
      revisa siempre una persona).
- Varias fotos: juntarlas en un PDF con el escáner del celular (hasta 10 páginas).

**2.11 Comprar por caja, vender suelto** (P-053).
- [ ] *Inventario → Productos → Nuevo*: «[EJ] Tornillo 6x1 suelto», unidad `kg`, categoría
      «[EJ] Ferretería», pestaña **Compra**: la Distribuidora con código `T1` y precio `10`.
- [ ] Excel con `Cód.`, `Descripción`, `Unidad`, `Precio` y la fila `T1` · `TORNILLO 6X1` ·
      `1000 u` · `25000` → *Importar lista* → la Distribuidora. ✔ La fila T1 queda **a
      revisar**: se vende por kg y la lista lo trae por 1000 u.
- [ ] Pestaña **Filas** → columna **Unidad de compra** → «Caja 1000 tornillos» → **Crear y
      editar…** → contiene `2,5` kg → guardar → **Aplicar**. ✔ En el producto: $ 25.000 por
      «Caja 1000 tornillos»; **Costo** $ 10.000 (por kg).
- [ ] En *Buscar producto* → **Pedir**: ✔ la solicitud dice **1 Caja 1000 tornillos**. Al
      recibirla (sección 6): ✔ entran **2,5 kg**.

**2.12 Las listas reales de ferretería.** *Costos y precios → Listas de proveedores →
Importaciones*.
- [ ] ✔ Una importación por proveedor (o por parte). Abrir la de uno detectado solo (por
      ejemplo Lambda): ✔ código, descripción y precio reconocidos; el precio al público, el
      margen o «con IVA» **no** se toman como costo.
- [ ] Filtro **Para revisar**: ✔ lo que viene sin precio, con precio 0 o «sin stock» queda
      a revisar con su motivo. **Nunca** entra un costo 0.
- [ ] Abrir la ficha de una lista (*Proveedores*): ✔ sección **Del precio de la lista al
      costo** (descuentos en cadena como `30+10+10`, recargo, cotización del dólar, IVA
      incluido). Vacía por defecto: los valores de cada proveedor los confirma el negocio
      (P-056; tabla en `docs/relevamiento/proveedores-costos.md`).
- [ ] Probar en una lista sin nada aplicado (por ejemplo Lambda): descuento `10` → guardar →
      en su importación, **Volver a simular** → ✔ los costos bajan 10 %. Dejarlo vacío y
      volver a simular.

> **En el día a día** (a validar con el negocio):
> - **Quién:** administración, cuando llega una lista (mail o WhatsApp); cada proveedor
>   cada 2 a 4 semanas.
> - **Rutina (5 a 15 minutos):** *Importar lista* → subir el archivo tal como llega →
>   **Simular** → **Aplicar automáticos** (cambios chicos) → revisar **Para revisar** (subas
>   grandes, **Ya no está en la lista**) → listo. Lo que no tenemos queda como catálogo.
> - **Descuentos o dólares** del proveedor: se cargan una vez en su lista y después se
>   aplican solos.
> - **Huecos a mirar:** proveedores **sin lista** (se cargan a mano en el producto);
>   bonificaciones y flete que la lista no dice (P-056); Beta repite códigos (P-061);
>   planillas internas del comercio (P-057: no se usan); para producción se piden listas
>   actualizadas; quién cubre si la persona de administración no está.

---

## 3. Buscar producto (10 min)

*Costos y precios → Buscar producto*: busca en la **última lista de todos los proveedores**
a la vez, por palabras en cualquier orden, código del proveedor o código de barras. Lo que ya
tenemos sale **en verde** y primero.

- [ ] `martillo carpintero 27` → Enter. ✔ Primero, en verde, la fila de la Ferretera Ejemplo
      con nuestro martillo en **Producto**. Con las listas reales (`LISTAS_REALES=1`), debajo,
      de la más barata a la más cara, los martillos de otros proveedores que no tenemos.
- [ ] `27 carpintero martillo` encuentra lo mismo; `martillo carpintero 270` **no** (los números
      tienen que coincidir enteros).
- [ ] Filtros **Lo tenemos** y **No lo tenemos**: ✔ separan una cosa de la otra.
- [ ] `fix 4x40` (con las listas reales): ✔ el tornillo en Ferretera Central (en verde,
      lo tenemos) y en Gas del Sur (caja de 250, otro precio).
- [ ] *Agrupar por → Producto*: ✔ cada grupo es **un mismo artículo**, lo tengamos o no
      (junta por nuestro producto, código de barras o misma descripción): se ve quién lo da
      más barato.
- [ ] Filas **sin precio** (Gas del Sur lista algunas): ✔ van al final, con la columna
      **Problema**.
- [ ] Columna **Precio de venta**: ✔ en lo que tenemos, su precio; en lo que no, **a cuánto
      se vendería** con el margen de la categoría de la fila (cambiar la categoría → cambia).
      Vacío si la categoría no tiene margen.
- [ ] Algo que no tenemos: elegir la categoría → **Agregar**. ✔ Pasa a verde, con su
      precio de venta.
- [ ] **Pedir** (solo en lo que tenemos): ✔ abre una **solicitud de cotización en borrador**
      a ese proveedor con el producto, a su precio de lista. Otra vez **Pedir**: ✔ la misma
      solicitud. Varios: marcar casillas → **Agregar al pedido** (una solicitud por
      proveedor). Cancelar la solicitud después (*Compras*).
- [ ] Marcar una fila, mantener **Mayús** y marcar otra más abajo: ✔ se marcan las del medio.

> **En el día a día:** un cliente pide algo que no hay, o hay que comparar precios:
> *Buscar producto* → ver quién lo tiene y a cuánto → si no lo tenemos, elegir categoría
> (mirar el **Precio de venta** que tendría) → **Agregar** → **Pedir**. Responde «¿quién lo
> vende, a cuánto y lo tenemos?» sin abrir ninguna lista.

---

## 4. Precios de venta por margen (20 min)

*Costos y precios → Precios de venta*. Márgenes **ficticios** del lab: Mascotas 35 %,
Alimento 25 %, Ferretería 45 % (redondeo $5), Veterinaria 40 %; IVA 21 %.

**4.1 La regla.** *Márgenes por categoría*.
- [ ] ✔ Tabla con todas las categorías: margen, base («Costo del producto»), IVA, redondeo,
      la columna **Regla que se usa** y cuántos **Productos** tiene.
- [ ] ✔ «[EJ] Alimento»: solo margen 25 %; **Regla que se usa** muestra lo que hereda de
      «Mascotas».
- [ ] Una categoría sin margen: ✔ «Sin margen: no se sugiere precio».
- [ ] Lo mismo está en cada categoría (*Inventario → Configuración → Productos →
      Categorías* → pestaña **Precio de venta**).

**4.2 Producto nuevo: toma el precio solo.** Abrir «[EJ] Correa nylon 1,5 m roja».
- [ ] ✔ **Precio de venta** = **Precio sugerido** = $ 5.230 y **Cómo se calculó** («Costo
      $ 3.200,50 + 35 % … + IVA 21 % → $ 5.230,00 (redondeo $10)»).
- [ ] ✔ En el historial de la ficha: «Precio de venta: $ 1,00 → $ 5.230,00». Un producto
      **todavía en $1** toma el sugerido; uno con precio nunca cambia solo.

**4.3 Cambiar un margen → Precios a actualizar.** En *Márgenes por categoría*, «[EJ]
Mascotas» → margen `40` → guardar. Ir a *Precios a actualizar*.
- [ ] ✔ La correa y los demás de Mascotas con **Precio actual**, **Precio nuevo** y
      **Cambio (%)**: rojo si sube, verde si baja. ✔ El alimento del 1.6 **no** aparece
      (tiene «Precio manual»).
- [ ] ✔ La correa sigue con su precio viejo hasta aplicarlo.
- [ ] Marcar dos → **Aplicar precio nuevo**. ✔ Salen de la lista; en su ficha, el precio nuevo.
- [ ] **Diferencia chica** → `5` → **Guardar**. ✔ Los que cambian hasta 5 % desaparecen (no
      vale la pena cambiarlos). Filtro **Diferencia chica (naranja)**: ✔ ahí están, en
      naranja. Volver a `0` (0 = se ven todos).

**4.4 Etiquetas.** *Precios de venta → Etiquetas a reimprimir*.
- [ ] ✔ Los dos del paso anterior (y los productos nuevos). Marcarlos → **Imprimir
      etiquetas** → ✔ PDF. **Marcar impresas** → ✔ salen de la lista.
- [ ] Volver «[EJ] Mascotas» a `35` → *Precios a actualizar* → todos → **Aplicar precio
      nuevo**. ✔ La lista queda vacía.

**4.5 Precio de un proveedor.** «[EJ] Ferretería» → **Calcular sobre** «Precio de un
proveedor» → **Proveedor de referencia** «[EJ] Ferretera Ejemplo» → guardar.
- [ ] El martillo: ✔ *Cómo se calculó* dice «Precio de [EJ] Ferretera Ejemplo …» en vez de
      «Costo …». Volver a «Costo del producto».

**4.6 Precio manual.** En el alimento del 1.6 destildar **Precio manual** → guardar.
- [ ] ✔ Pasa a *Precios a actualizar* con el precio que le corresponde por margen.

**4.7 Margen especial.** *Precios de venta → Márgenes especiales*.
- [ ] ✔ Vacío (filtro «Con margen especial»).
- [ ] **Agregar producto** → la correa → ✔ muestra el margen de su rubro (35) → `20` →
      **Guardar**. ✔ En la lista: **Precio sugerido** con 20 % y al lado el **Margen del
      rubro** (35).
- [ ] Cambiar `20` por `25` → ✔ el sugerido se recalcula. En la correa: ✔ *Cómo se calculó*
      dice «margen especial del producto».
- [ ] **Calcular sobre** → «Precio de un proveedor» y uno de sus proveedores: ✔ se calcula
      sobre ese precio. Con uno que **no** la tiene en su lista: ✔ avisa y usa el costo.
      Vacío: ✔ vuelve a la base del rubro.
- [ ] Destildar **Margen especial**: ✔ vuelve al margen del rubro.

**4.8 IVA distinto del rubro.** El IVA de la categoría es el **IVA por defecto** de los
nuevos; **manda el del producto** (el que cobra la caja).
- [ ] Correa → **Impuestos cliente** «IVA 10.5%» → guardar. ✔ **Precio sugerido** baja y
      *Cómo se calculó* dice «IVA 10.5 % (del producto)». En *Precios a actualizar*: ✔ la
      columna **IVA** en 10,5 %. Volver a «IVA 21%».

> **En el día a día** (a validar con el negocio):
> - **Quién:** administración o el titular, después de aplicar listas: *Precios a
>   actualizar* → revisar → **Aplicar precio nuevo** → *Etiquetas a reimprimir* → imprimir →
>   alguien **cambia las etiquetas en la góndola** → **Marcar impresas**.
> - **Cuándo:** una vez por semana, o cuando entra una lista con subas.
> - El precio de venta **nunca cambia solo** a mitad del día (salvo un producto todavía en $1).
> - **Huecos a mirar:** si las etiquetas no se cambian, la góndola y la caja no coinciden.
>   Mientras cobren las registradoras, **su lista de precios se actualiza aparte**: ¿quién y
>   cuándo? Ofertas y descuentos (P-049). Márgenes reales por rubro (P-030). IVA de cada rubro
>   (P-034, con el contador).

---

## 5. Pedir al proveedor (15 min)

**5.1 Pedido.** *Compras → Órdenes → Solicitudes de cotización* → **Nuevo** → proveedor
«[EJ] Distribuidora Norte SA» → agregar «[EJ] Alimento gato castrado 7,5 kg», cantidad 10.
- [ ] ✔ El precio sale solo: **25.000** (el de ese proveedor).
- [ ] **Confirmar orden**. ✔ Pasa a orden de compra y aparece **Recibir**. (Esta orden es la
      de la factura de ejemplo de la sección 7.)

**5.2 Debajo del mínimo.** Otra solicitud → «[EJ] Mayorista Sur SRL» → el mismo alimento.
- [ ] ✔ Propone **10** unidades (su mínimo) a **24.500**.
- [ ] Cantidad **5**: ✔ aviso de que la lista pide un mínimo de 10, la línea en amarillo y
      el precio pasa al **costo del producto**. Volver a 10: ✔ 24.500 sin aviso. Descartarla.

**5.3 Catálogo y Lista del proveedor.** Nueva solicitud → proveedor **Ferretera Central**
→ en las líneas:
- [ ] **Catálogo**: ✔ solo lo que tenemos de ese proveedor, vigente.
- [ ] **Lista del proveedor** (al lado): ✔ toda su lista, lo tengamos o no. **Pedir** suma el
      artículo a esta orden.
- [ ] Con un producto en la orden, cambiar el proveedor a otro: ✔ aviso «No están en la lista
      de …» y la línea en amarillo.

**5.4 Mandarlo por WhatsApp.** En la orden del 5.1: **Enviar por WhatsApp**.
- [ ] Sin teléfono: ✔ avisa que no tiene teléfono cargado. Cargarle uno (por ejemplo el
      propio celular).
- [ ] Otra vez: ✔ el mensaje con el pedido escrito (cada producto con el código y la
      descripción **del proveedor**, cantidad y unidad). Cambiar algo → **Abrir WhatsApp**:
      ✔ se abre WhatsApp (Web o la aplicación) con ese chat y el mensaje. Falta tocar Enviar.
- [ ] ✔ En la orden queda la nota de que se abrió WhatsApp y, si era solicitud, pasa a enviada.

> **En el día a día** (a validar con el negocio):
> - **Quién:** quien compra (¿el titular?, ¿el encargado?).
> - **Armar el pedido:** desde *Reabastecimiento* (sección 6), desde *Buscar producto* →
>   **Pedir**, o en la orden con **Catálogo** / **Lista del proveedor**. Confirmar →
>   **Enviar por WhatsApp** (sin la API de WhatsApp Business: sale del WhatsApp de esa PC).
> - **Huecos a mirar:** proveedores que compran por su página con carrito (la orden sale de
>   la factura: sección 7.2); pedidos que toma el viajante; precio de lista que no es el que
>   se paga (P-056).

---

## 6. Recepción y stock (15 min)

**6.1 Recibir.** En la orden del 5.1: **Recibir** → revisar cantidades → **Validar**.
- [ ] ✔ La recepción queda hecha. Botón **Orden de compra** arriba: ✔ lleva a la orden.
- [ ] En el producto: ✔ **A la mano** sube 10. En la orden: ✔ recibido totalmente.

**6.2 Conteo y ajuste.** *Inventario → Operaciones → Ajustes → Inventario físico* → buscar
el producto → cantidad contada `12` → **Aplicar**.
- [ ] ✔ A la mano pasa a 12.
- [ ] Corrección rápida desde la ficha (cantidad a la mano) → ✔ cambia el stock.

**6.3 Dónde mirar.** *Inventario → Reportes → Existencias* e *Historial de movimientos*.
- [ ] ✔ Están la recepción y los ajustes, con fecha y origen. Después de la sección 8,
      también las ventas del puesto.

**6.4 Reposición.** *Inventario → Operaciones → Aprovisionamiento → Reabastecimiento* →
**Nuevo** → el alimento, mínimo `15`, máximo `30`.
- [ ] ✔ A pedir: **20**. Botón **Orden**: ✔ solicitud al **más barato vigente para esa
      cantidad** (Mayorista Sur a 24.500, mínimo 10), no a la Distribuidora a 25.000.
- [ ] Sacar el filtro **A pedir**: ✔ también las reglas que hoy no piden. El **pronosticado**
      suma lo que viene, incluidas las solicitudes en borrador (no pide dos veces).
- [ ] Columna **Disparador** → **Automático** con un mínimo alto. Vender una unidad en el
      puesto (sección 8): ✔ Odoo suma la cantidad a la solicitud en borrador de ese
      proveedor (o la crea), siempre en borrador. Volver a **Manual** (P-042).

> **En el día a día** (a validar con el negocio):
> - **Llega el camión:** abrir la orden → **Recibir** → contar contra el remito →
>   **Validar**. El stock sube recién ahí.
> - **Depósito:** conteos por categoría (al principio, solo ferretería) y ajustes por
>   roturas.
> - El stock **baja con cada pedido impreso en el puesto** (sección 8), aunque cobre la
>   registradora: si en el puesto no se carga todo, el stock deja de servir.
> - **Huecos a mirar:** faltantes y entregas parciales; devoluciones al proveedor; conteo
>   **a ciegas** y control por persona (P-051); mercadería que entra sin orden (que sea la
>   excepción: se pierde el control de lo pedido contra lo recibido).

---

## 7. Facturas de proveedor (25 min)

La factura **la lee el comercio**: un PDF con texto sin IA, una foto con Gemini; la
digitalización paga de Odoo está apagada (ADR 0021). Detalle: `facturas-proveedor.md`.

**7.1 Factura de una orden.** En la orden del 5.1, ya recibida: **Subir factura** →
`data/ejemplos/facturas/factura-ejemplo-distribuidora-norte.pdf`.
- [ ] ✔ Factura en borrador **FA-A 00005-00001234**, fecha 24/10, vencimiento 23/11. El
      proveedor quedó con su CUIT (ficticio) y como Responsable Inscripto.
- [ ] Líneas: ✔ el alimento como dice la factura (10 a 25.500 con 5 % de bonificación), la
      correa (2 a 3.200,50), **Flete 2,50%** (6.216,28 con IVA) y **Perc IIBB Córdoba**.
      **Total 316.035,43**: igual que el papel.
- [ ] Pestaña **Leído de la factura**: ✔ el resumen con el pie; el alimento en amarillo con
      **Diferencia con la orden** (precio y bonificación) y **Diferencia con su lista**
      («¿un descuento?»); la correa: no está en la orden.
- [ ] Borrar la línea del **Flete**: ✔ al momento aparece un **cartel rojo** con la diferencia
      contra el total del proveedor. **Leer factura**: ✔ vuelve el flete y se va el cartel.
- [ ] **Confirmar**. En *Compras → Órdenes → Facturas de proveedor*, filtro de facturas en
      excepción: ✔ está esta (precio distinto y algo que no se pidió). En la factura, **Se
      debe pagar**: Excepción.
- [ ] **Registrar pago** por la mitad → ✔ parcialmente pagada; el resto → ✔ pagada.
- ⚠ La cuenta de las percepciones y del flete la confirma el contador (P-034).

**7.2 Factura que llega sin pedido.** Caso común: compras en la página del proveedor. Con
la factura real de FC si está (`data/privado/comprobantes/fc-factura-A-…pdf`), o con
cualquier factura de un proveedor del lab: *Compras → Órdenes → Facturas de proveedor* →
**Subir**.
- [ ] Si ningún proveedor tiene ese CUIT (FC vino de una lista, sin CUIT): ✔ cartel
      **Elegir proveedor** → elegirlo → se le guarda el CUIT y se lee de nuevo.
- [ ] ✔ Todos los artículos anotados: los que tenemos (tornillos Fix, cadenas) con producto;
      los demás **sin producto**, con descripción y precio de la factura. El total da el del
      papel (unos centavos de diferencia son redondeo).
- [ ] Pestaña **Leído de la factura**: en uno que está en su lista, categoría → **Agregar**;
      en uno que no está, categoría → **Crear producto**; en uno que ya tenemos con otro
      nombre, elegirlo en **Producto** → **Es este**. ✔ La misma línea de la factura toma el
      producto (no se duplica).
- [ ] **Crear orden de compra**: ✔ como faltan productos, abre **Artículos sin producto**.
      Opcional: marcar los dudosos → **Verificar con IA** → los que quedan **¿Es este?** →
      **Es este (el sugerido)**. Marcar el resto → **Agregar al catálogo**: ✔ todos con
      producto (desde su lista o nuevos, sumados a su lista vigente).
- [ ] Volver → **Crear orden de compra**: ✔ orden confirmada, con su recepción, y la factura
      unida. Recibir: ✔ «Se debe pagar» pasa a Sí si todo coincide.
- [ ] Subir la misma factura eligiendo otro proveedor: ✔ cartel amarillo «El CUIT de la
      factura es de …» → **Cambiar a ese proveedor y leer de nuevo**.

**7.3 Precio distinto de la lista.** En cualquier factura, una línea que cobra más que la
lista vigente: ✔ **Diferencia con su lista** dice «¿lista vieja?» (pedir la nueva y
subirla). La factura no cambia costos ni precios de venta: eso lo hacen las listas (P-059).

**7.4 Factura en foto** (necesita Gemini). Sacarle una foto o captura a la factura de
ejemplo → **Subir**. ✔ Se completa igual, leída con IA: revisar cantidades y precios contra
la foto.

**7.5 Compras sin factura** (ADR 0023). Nueva orden a «[EJ] Distribuidora Norte SA»: 2
alimentos → **Confirmar** → **Recibir**.
- [ ] **Sin factura** (al lado de «Subir factura»): ✔ compra en el diario *Compras sin
      factura*, **sin IVA** (2 × 25.000 = 50.000), con un cartel azul.
- [ ] **Confirmar** → **Registrar pago**: ✔ pagada.
- [ ] *Compras → Órdenes → Compras sin factura* → **Subir** → la factura de ejemplo: ✔
      artículos sin IVA, y el IVA y la percepción del papel como líneas comunes (sin
      crédito fiscal). El total da 316.035,43.
- [ ] En el listado de facturas, filtros **Sin factura** / **Con factura**: ✔ las separan.
      Cuando llega la real, la administración la carga y anula a mano la sin factura.

> **En el día a día** (a validar con administración):
> - **Quién:** administración, cuando llega la factura (mail, papel, WhatsApp).
> - **Con orden:** **Subir factura** desde la orden → mirar lo amarillo y el cartel rojo →
>   **Confirmar** → pagar lo que «Se debe pagar: Sí»; las excepciones se hablan con el
>   proveedor (nota de crédito).
> - **Sin orden:** subir la factura → agregar lo que falta → **Crear orden de compra** →
>   recibir.
> - **Huecos a mirar:** si se cargan o no las facturas de proveedor en la primera etapa
>   (P-047); percepciones de provincias sin impuesto en Odoo; quién anula la compra sin
>   factura cuando llega la real.

---

## 8. Venta en el puesto: «Cobrado en registradora» (15 min)

El flujo real de la primera etapa (ADR 0019): el puesto arma el pedido y lo imprime; el
cliente paga en la registradora con ese ticket. Al imprimir, el pedido queda cobrado en Odoo
con el medio «Cobrado en registradora» y **baja el stock**. Nadie cobra en Odoo.

**8.1 Armar e imprimir.** *Punto de venta* → **Mostrador 1** → abrir → PIN **1111**.
- [ ] Si estaba cerrado: ✔ quien atiende lo puede abrir desde la nota de apertura.
- [ ] ✔ Arriba, los botones de categorías del PdV («[EJ] Alimento perro», «[EJ] Alimento
      gato», «[EJ] Accesorios mascotas»): al tocar uno quedan solo esos productos.
- [ ] Agregar la cadena (buscando `cadena`), la cinta **tipeando su código** `7790000002021`
      (o escaneándolo) y, con las listas reales, un tornillo `fix`.
- [ ] Anotar el **A la mano** de la cinta antes (en otra pestaña).
- [ ] ✔ No hay botón «Pago»: está **Imprimir pedido**. Tocarlo.
- [ ] ✔ El ticket: logo, el número del pedido **una sola vez** y «Presentar en caja para
      pagar». **Sin QR**, sin IVA, CUIT, cliente, cajero ni «Odoo». La pantalla queda libre.

**8.2 Qué quedó en Odoo.**
- [ ] ✔ La cinta: **A la mano** bajó 1 en el momento (controla stock: es ferretería).
- [ ] *Punto de venta → Órdenes → Órdenes*: ✔ el pedido del Mostrador 1, cobrado, con el
      pago «Cobrado en registradora».
- [ ] *Punto de venta → Órdenes → Ventas sin factura de Odoo*: ✔ aparece agrupado por día y
      por puesto (el comprobante lo hizo la registradora).

**8.3 Cierre del puesto.**
- [ ] Cerrar el puesto desde el POS: ✔ no tiene efectivo que contar.
- [ ] Cierre nocturno: en modo desarrollador (*Ajustes* → al final, *Activar el modo de
      desarrollador*) → *Ajustes → Técnico → Automatización → Acciones planificadas* →
      «Comercio: cerrar puestos abiertos por la noche» → **Ejecutar manualmente** con un
      puesto abierto. ✔ El puesto queda cerrado.

**8.4 Botones del punto de venta** (P-054). Detalle: `categorias-pos.md`.
- [ ] *Punto de venta → Productos* → vista de lista: ✔ columna **Categoría del PdV** al lado
      del nombre; filtro **Sin categoría del PdV**.
- [ ] Buscar `[EJ]` → marcar «[EJ] Croquetas felinas castrados 3 kg» y «[EJ] Pelota de goma
      con sonido» → **Acciones → Categorizar con IA** (unos 20 segundos). ✔ Propone «[EJ]
      Alimento gato» y «[EJ] Accesorios mascotas», con motivo. **Aplicar** → en el puesto
      (recargar) ✔ aparecen en esos botones.
- [ ] Uno ya categorizado + otro → **Categorizar con IA**: ✔ avisa que el primero se salteó.
      **Categorizar a mano** → elegir botón (o **Reemplazar las que ya tienen**) → **Aplicar**.
- [ ] ✔ El costo y el precio de venta no cambiaron.

**8.5 Fusionar productos repetidos** (solo administradores; app *Limpieza de datos*).
- [ ] Crear a mano un producto repetido de la cinta (otro nombre). En *Inventario →
      Productos* (vista de lista) marcar los dos → **Acciones → Fusionar** → elegir cuál
      queda → fusionar. ✔ Proveedores, stock e historial pasan al que queda; el otro se
      archiva.
- [ ] En *Buscar producto*, **Acciones → Fusionar productos** hace lo mismo desde las filas.
      Detalle: `listas-proveedores.md`.

> **En el día a día** (primera etapa):
> - **Vendedor del puesto:** escanea o busca (o toca un botón), pesa en la balanza,
>   **Imprimir pedido**; el cliente va con el ticket a la registradora.
> - **Caja:** cobra la registradora (Sam4s y Hasar) como hoy; 3C hace las A/B. No se suma
>   trabajo en la caja.
> - **Huecos a mirar:** el cliente que se arrepiente **después de imprimir** (el stock ya
>   bajó: ¿quién lo anula?); que el precio del ticket coincida con el de la registradora;
>   productos que el puesto no carga y la registradora sí (el stock no baja); reservas
>   (P-050); cuenta corriente o fiado. Cuáles botones y qué puesto ve cuáles: Daniel (P-054).

---

## 9. Balanza (5 min; 30 con el equipo real)

**9.1 Simulada.** Sin la balanza enchufada no se puede probar a mano. Para verla funcionar:

```bash
VER=1 .venv/bin/python tests/e2e/pos_balanza_systel.py
```

- [ ] ✔ Peso inestable: espera. Estable: se agrega solo. Balanza muda: un aviso. Dos
      pesadas iguales: se agregan las dos. Error de la balanza: un solo aviso.
- [ ] *Punto de venta → Configuración → Ajustes* → **Balanza Systel Cuora (USB)**: ✔ número
      de balanza, pesaje automático y botón **Conectar balanza Systel**.

**9.2 Real.** Con una Cuora en la mano: seguir `prueba-balanza-real.md` (cable USB A-B,
permiso `dialout`, diagnóstico, número de balanza). En `localhost` no hace falta HTTPS; desde
otra PC sí (en el local, ADR 0013).

> **En el día a día:** el vendedor pone el producto en la balanza y el peso entra solo al
> pedido. Chrome lee la balanza por USB (WebSerial), sin equipos IoT. **Huecos a mirar:**
> modelo exacto de las 8 balanzas (P-040); si se sigue usando la etiqueta de la balanza;
> qué hacer si se desconecta en pleno día (se tipea el peso).

---

## 10. Etapas siguientes (para conocerlas)

Probado y guardado para cuando Odoo cobre (ADR 0017). No es el flujo de la primera etapa.

**10.1 Volver al pedido con QR y la caja de Odoo.** Los puestos dejan de dar el pedido por
cobrado. Sin tocar `config/valores.yaml`, con un archivo de valores extra (ADR 0010):

```bash
echo "puestos_cobran_en_registradora: false" > config/valores.qr.local.yaml   # *.local.yaml no va a git
make plan ENV=lab VALORES=config/valores.qr.local.yaml    # muestra qué cambia
make apply ENV=lab VALORES=config/valores.qr.local.yaml
```

Para volver a la primera etapa: `make apply` (sin `VALORES`). Las pruebas `make e2e-pos`
pasan solas al QR mientras corren y lo dejan como estaba.

- [ ] Pestaña 1: «[EJ] Puesto mascotas (arma pedidos)» → PIN **1111** → productos →
      **Imprimir pedido**. ✔ Ticket con **QR** y número; el stock **no** baja todavía.
- [ ] Pestaña 2: «[EJ] Caja (cobra)» → **Abrir pedido (escanear o tipear número)** → el
      número → cobrar con «[EJ] Efectivo caja» → **Validar**. ✔ Cobrado; el stock baja una
      sola vez.
- [ ] **Dos cajas:** el mismo pedido abierto en «[EJ] Caja 2 (cobra)» y cobrado en la
      primera: ✔ la segunda avisa **Pedido ya cobrado** (P-035).
- [ ] **Devolución:** en la caja, una venta cobrada → reembolso. ✔ Venta negativa enlazada y
      el stock vuelve (`devoluciones.md`).
- [ ] **Cierres:** puesto cerrado con un pedido sin cobrar → ✔ la caja lo sigue pudiendo
      cobrar. Cerrar la **última** caja → ✔ los pedidos no cobrados se cancelan
      (`cierre-de-caja.md`).
- [ ] Ventas ya cobradas: en la caja, *Órdenes* → **Pagado** → elegir una: ✔ reimprimir,
      enviar por mail (llega a <http://localhost:8025>).

**10.2 Caja con y sin factura de Odoo** (ADR 0024). *Punto de venta* → **Caja 1** → PIN **2222**.
- [ ] Una venta → **Pago**: ✔ **Factura** viene marcado. Cobrar → ✔ en *Facturación →
      Clientes → Facturas* una **FA-B** aceptada en ARCA, con CAE de prueba.
- [ ] Otra venta → desmarcar **Factura**: ✔ una **franja de color** al costado de la
      pantalla de pago, sin carteles. Cobrar → ✔ sin factura de Odoo.
- [ ] *Punto de venta → Órdenes → Ventas sin factura de Odoo*: ✔ está, por día y caja.
      Abrirla → **Facturar con CAE** → confirmar: ✔ sale la FA-B, sigue cobrada y sale de la
      lista. Una venta de otro día: ✔ sale con fecha de hoy.
- [ ] *Facturación → Reportes → Impuestos y finanzas → **Libro de IVA*** (período de este mes,
      tipo **Ventas**): ✔ solo lo que facturó Odoo; ⚙ → **Libro de IVA (ZIP)** trae los TXT para ARCA.
- ⚠ Si ARCA responde «Code 10016» (numeración de prueba compartida): probar de nuevo; si
  sigue, `make lab-arca`. Factura A, B y nota de crédito por API: `make e2e-factura`.

**10.3 Ventas mayoristas** (P-015; para conocer la app Ventas). Cómo armarlo a mano:
`listas-de-precios.md`. El lab trae la lista «[EJ] Mayorista» y el cliente «[EJ] Veterinaria
Los Robles (mayorista)» (`config/ejemplos/50-…` a `52-…`).
- [ ] *Ventas → Órdenes → Cotizaciones* → **Nuevo** → ese cliente → «[EJ] Alimento perro
      adulto 15 kg» ×2, el mismo ×10, «[EJ] Cadena galvanizada 4 mm (por metro)» ×5 y «[EJ]
      Consulta veterinaria» ×1. ✔ Alimento a 45.000 con **10 %** (×2) y **15 %** (×10);
      cadena a **1.800** (precio fijo); consulta con 10 %. De 10 a 9: ✔ pasa al 10 %.
- [ ] **Enviar** → ✔ el presupuesto en PDF a <http://localhost:8025>.
- [ ] **Confirmar** → **Entrega** → **Validar** (✔ baja el stock) → **Crear factura** →
      **Confirmar**: ✔ **Factura A** (cliente Responsable Inscripto), con CAE de homologación.

> **En el día a día:** nada de esto corre en la primera etapa. Usar la caja de Odoo implica
> adelantar el punto de venta RECE (P-002, P-029: si ARCA no responde, la caja no cierra la
> venta). Mayorista: cuenta corriente, límite de crédito y entregas (P-015).

---

## 11. Backup y restauración (10 min)

```bash
make backup                                   # → backups/lab-lab-<fecha>.zip + .manifest
make restore-test FILE=backups/<ese archivo>.zip
```

- [ ] ✔ El backup queda en `backups/` con su `.manifest`.
- [ ] ✔ `restore-test` restaura en una base temporal neutralizada, revisa módulos, usuarios
      y adjuntos, termina con «Prueba de restauración OK» y la borra. No toca el lab.

> **En el día a día:** nadie del local lo hace: en el servidor corre solo, con copia fuera
> del local (propuesta: `restic` a Cloudflare R2 + disco USB, P-013). Un backup que nunca se
> restauró no está probado. **Huecos a mirar:** quién revisa que el backup salió; cada
> cuánto se prueba restaurar (registro en `docs/infraestructura/backups.md`).

---

## 12. Pruebas automáticas

Corren contra el lab y dejan todo como estaba. Antes de cambiar un módulo, su prueba.

| Comando | Qué prueba |
|---|---|
| `make e2e-pos` | Puesto con QR, cierres, dos cajas, balanza simulada, «Cobrado en registradora», caja con y sin factura (Chrome, Playwright) |
| `make e2e-catalogo` | Listas de proveedores y Compras con la lista vigente |
| `make e2e-precios` | Precios de venta por margen |
| `make e2e-codigos-fabrica` | Códigos de fábrica |
| `make e2e-factura-proveedor` | Facturas de proveedor: leer, crear la orden, diferencias, pie, compras sin factura |
| `make e2e-ia` | Verificación con IA de listas y categorías del PdV (llama a Gemini de verdad) |
| `make e2e-factura` | Factura electrónica contra ARCA homologación (antes, `make lab-arca`) |

**Verlas en pantalla:** las del punto de venta abren Chrome y van despacio con `VER=1`:

```bash
VER=1 .venv/bin/python tests/e2e/pos_cobro_registradora.py   # primera etapa: puesto que imprime y queda cobrado
VER=1 .venv/bin/python tests/e2e/pos_pedido_qr.py            # puesto → caja con QR
VER=1 .venv/bin/python tests/e2e/pos_cierre.py               # cierres
VER=1 .venv/bin/python tests/e2e/pos_dos_cajas.py            # dos cajas
VER=1 .venv/bin/python tests/e2e/pos_balanza_systel.py       # balanza simulada
VER=1 .venv/bin/python tests/e2e/pos_factura.py              # caja con y sin factura, «Facturar con CAE»
```

⚠ Cierran y reabren las sesiones de los puntos de venta de ejemplo: no correrlas a mitad de
las secciones 8 o 10. Las demás corren por API, sin pantalla.

---

## 13. Qué anotar si algo falla

Por cada cosa rara: **número de paso**, **qué hiciste**, **qué esperabas** (el ✔), **qué
pasó** y una **captura**. También lo que funcione pero sea **incómodo o confuso**: eso también
se mejora. Con eso se reproduce, se arregla y se le suma una prueba para que no vuelva.

Los **huecos del flujo** (algo que en el local pasa y la guía no cubre: «¿y si el proveedor
manda el pedido incompleto?») van a `docs/pendientes.md` como pregunta para el negocio; lo que
preguntó el cliente y se le respondió, a `docs/relevamiento/respuestas-al-cliente.md`.
