# Listas de precios: cómo configurarlas a mano (para enseñar)

Para quien administra Odoo en el negocio. Explica cómo armar una lista de precios
(p. ej. mayorista), asignarla a un cliente y usarla en Ventas y en la caja. Es lo mismo
que el laboratorio carga solo desde `config/ejemplos` (ver «En el repo», al final).

Pantallas verificadas en el lab (Odoo 20, 12/10/2026). Algunas palabras todavía
aparecen en inglés en la traducción de Odoo («Apply», «% on», «Surcharge»): se aclaran
abajo.

---

## 1. Activar las listas de precios (una sola vez)

*Ventas → Configuración → Ajustes* → sección **Precios**:

- Tildar **Listas de precios** → **Guardar**. Aparece el menú *Ventas → Productos →
  Listas de precios* y se crea la lista «Predeterminado» (la de siempre, sin cambios).
- Tildar también **Descuentos** → **Guardar**. Así en el presupuesto y la factura el
  cliente ve el precio normal y el % de descuento, en lugar de un precio ya rebajado.

## 2. Crear la lista

*Ventas → Productos → Listas de precios* → **Nuevo** → nombre (p. ej. «Mayorista») →
pestaña **Reglas** → **Agregar una línea** por cada regla.

Cada regla se arma con tres preguntas:

| Pregunta | Campo | Opciones |
|----------|-------|----------|
| ¿Cómo se calcula? | **Apply** (arriba) | **Descuento**: un % menos · **Surcharge** (recargo): un % más · **Precio fijo**: un monto |
| ¿Sobre qué base? | **% on** | Descuento: sobre el *precio de venta* (o sobre otra lista) · Recargo: sobre **Costo**, **Precio de venta** u otra lista |
| ¿A qué productos? | **Categoría** / **Producto** | Vacíos = todos los productos. Una categoría incluye sus subcategorías |

Opcionales: **Minimum Quantity** (desde cuántas unidades vale), **Validez** (fechas,
para una promoción con fin), **Redondear a** (p. ej. `10` para precios redondos).

Abajo de la ventana, **Example** muestra cómo queda un precio: revisarlo antes de guardar.

### Ejemplo del lab (lista «[EJ] Mayorista»)

1. **Descuento** `10` % on *precio de venta*, sin categoría ni producto → todo 10 % menos.
2. **Descuento** `15` %, Categoría «Alimento», Minimum Quantity `10` → alimentos desde 10
   unidades, 15 % menos.
3. **Precio fijo** `1800`, Producto «Cadena galvanizada» → ese producto, siempre 1.800.

**Si varias reglas sirven**, Odoo usa la más específica: producto antes que categoría y
categoría antes que «todos»; a igual alcance, la de mayor cantidad mínima. Por eso 9
alimentos llevan 10 % y 10 alimentos, 15 %.

## 3. Asignarla al cliente

*Ventas → Órdenes → Clientes* → abrir el cliente → pestaña **Ventas y compras** →
**Lista de precios** → «Mayorista» → guardar.

Desde ahí, todo presupuesto a ese cliente sale con esa lista sin elegir nada.

## 4. Usarla en un presupuesto

*Ventas → Órdenes → Cotizaciones* → **Nuevo** → elegir el cliente → agregar productos.

- La lista del cliente aparece en el campo **Lista de precios** y se aplica sola.
- Si se cambia la lista del presupuesto o la cantidad de una línea, los precios se
  recalculan solos.
- Un cliente sin lista asignada usa «Predeterminado» (precio de venta normal).

## 5. Usarla en la caja (POS)

*Punto de venta → Configuración → Ajustes* → elegir la caja arriba → **Listas de
precios flexibles** → en **Disponible**, las listas que puede usar esa caja (siempre
incluir «Predeterminado») y en **Predeterminado** la del público → **Guardar**.

En la caja aparece un botón para cambiar de lista, y al elegir un cliente con lista
asignada debería pasar a la suya (a verificar en el lab: paso 7.5 de la prueba visual).

## Cuidado

- **Cambiar una regla cambia los precios desde ese momento** en Ventas, la caja y la
  tienda online que usen esa lista. Las ventas ya hechas no cambian.
- Una regla sobre **Costo** cambia sola cuando cambia el costo (p. ej. al importar la
  lista de un proveedor): ver P-030 antes de usarla con el público.
- Para dejar de usar una lista: **archivarla** (no borrarla), así queda el historial.

## En el repo

En el laboratorio esto lo crea `make apply` desde `config/ejemplos/05-ajustes.yaml`
(paso 1) y `50-…` a `52-…` (pasos 2 y 3). Lo que esté en `config/` se vuelve a dejar como
dice el archivo en cada `make apply`: si una lista la va a mantener el negocio desde
Odoo, no debe estar en `config/` (o debe ir con `noupdate`). Qué listas se mantienen en
el repo y cuáles desde Odoo se decide junto con P-015 y P-030.
