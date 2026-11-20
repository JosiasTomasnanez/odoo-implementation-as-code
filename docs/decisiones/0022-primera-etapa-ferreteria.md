# 0022. Primera etapa: ferretería en lugar de alimento para animales

- Estado: aceptado (charla con Daniel, 23/10)
- Fecha: 2026-10-23
- Reemplaza en parte: ADR 0017 (solo el rubro; el resto del alcance sigue igual)

## Contexto

El ADR 0017 (19/10) arrancaba con **alimento para animales**: stock, compras, inventario y
puestos que arman el pedido. El 23/10 Daniel cambió el plan: la primera etapa es
**ferretería**. Pasó las listas reales actuales de sus proveedores de ferretería (36
archivos en `data/privado/listas-proveedores/`, fuera de git).

## Decisión

- El rubro de la primera etapa es **ferretería**. Lo demás del ADR 0017 sigue: sin caja ni
  facturación de ventas en Odoo, las registradoras cobran, el stock baja como dice el
  ADR 0019.
- En el lab, «[EJ] Ferretería» pasa a **controlar stock** (`config/ejemplos/10-categorias.yaml`);
  alimento queda como estaba para no romper las pruebas del POS. En producción el rubro
  con stock se declara al armar la base (P-032).
- Las listas reales de ferretería se usaron para probar y corregir el motor de listas
  (23/10): precio 0 o «sin stock» ya no se carga como costo 0; títulos con « + »; filas de
  títulos repetidas; familias en una fila aparte (y como descripción si no hay columna de
  descripción); columnas por letra; unidades y cantidades escritas con texto; dólar,
  descuentos, flete e IVA incluido por lista («Del precio de la lista al costo»); y la
  sugerencia de columnas ya no toma el precio al público como costo.
- Las planillas internas del comercio (con margen, público y redondeo calculados) no son
  listas de proveedor: se piden las listas originales o se cargan una vez (P-057).

## Consecuencias

- Las preguntas de alimento (balanza para alimento suelto, bolsas, P-053) bajan de
  prioridad; las de ferretería suben: descuentos y dólar de cada proveedor (P-056),
  productos que se venden por metro o por kilo (bulonería, cadenas, cables), etiquetas.
- La balanza (ADR 0012) sigue sirviendo para lo que se vende por kilo en ferretería
  (clavos, bulones sueltos), a confirmar.
- `CLAUDE.md` y `GUIA-EJEMPLO.md` se actualizan con el cambio.
