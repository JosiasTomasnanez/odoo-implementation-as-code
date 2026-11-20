# Stock por compra: a qué precio se compró lo que hay

Muestra de cada producto **de qué compras viene lo que queda** y a qué precio se compró.
Odoo supone que se vende primero lo que entró primero. Es una estimación: no sabe qué unidad
física es cuál.

1. *Inventario → Informes → Análisis de movimientos*.
2. *Favoritos* (en el buscador) → **Stock por compra**.
3. La primera vez: en el borde derecho de la lista, el ícono de columnas → tildar
   **Cantidad restante** y **Valor**.
4. Abrir un producto. Cada fila es una compra recibida:
   - **Cantidad**: lo que entró en esa compra.
   - **Cantidad restante**: lo que todavía queda de esa compra.
   - **Valor**: lo que costó esa compra entera. Precio por unidad = Valor ÷ Cantidad.

No mirar «Valor restante»: lo calcula al costo de hoy, no al de la compra.

**Ejemplo:** entraron 5 martillos a $ 100 y después 10 a $ 90; se vendieron 8. Aparece solo la
segunda compra: Cantidad 10, Cantidad restante 7, Valor $ 900 (→ $ 90 cada uno).

**Para que sea cierto:** las compras se reciben en Odoo y el stock está contado. Lo que entra por un
ajuste de inventario aparece al costo que tenía el producto ese día.

Detalle: P-073 en `docs/pendientes.md`; configuración en `config/onpremise/66-stock-por-compra.yaml`.
