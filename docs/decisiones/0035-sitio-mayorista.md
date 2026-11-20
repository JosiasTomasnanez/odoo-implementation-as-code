# 0035. Sitio mayorista aparte: mismo Worker, otro dominio

- Estado: aceptado (implementador, 09/11; pedido de Daniel)
- Fecha: 2026-11-09
- Cambia: ADR 0031/0032/0033 solo en lo que se describe acá (antes lo mayorista vivía dentro de la
  tienda, en «Mi cuenta → Lista de precios»).

## Contexto

Daniel quiere que lo mayorista sea **otra página**, que no se vea desde la tienda minorista, **más
seria y muy práctica**, y que el mayorista **nunca compre suelto**. Además, la lista mayorista tiene
que poder **descargarse en Excel**, completa y sin inconsistencias, útil para cualquier comprador.

## Decisión

- **Mismo Worker, otro dominio**: `mayoristas.comercio-ejemplo.example` (prueba:
  `mayoristas-demo.comercio-ejemplo.example`, un solo nivel para que lo cubra el certificado). Un middleware
  elige el sitio por el dominio (`src/servidor/sitio.ts`): en el sitio mayorista las direcciones se
  sirven desde `src/pages/mayoristas/` (la tienda no se ve desde ahí) y en la tienda `/mayoristas` no
  existe. Comparten catálogo, stock, reservas, pagos y pedidos: no hay dos copias que sincronizar ni
  riesgo de vender dos veces lo mismo.
- **Cuentas separadas**: la sesión es una cookie de cada dominio. La tienda ya no muestra nada
  mayorista (ni lista, ni «Soy mayorista», ni anuncio). Cada pedido guarda de qué sitio salió
  (`pedidos.sitio`) y «Mis pedidos» muestra solo los de ese sitio.
- **Precios**: los de la lista de Odoo del cliente. Se crea la lista **«Mayorista»**
  (`config/onpremise/62-tienda-mayorista.yaml`, con «Sincronizar con la tienda»), la de todos por
  defecto; un cliente con condiciones especiales puede tener otra. La tienda calcula el total con esa
  lista y Odoo recibe el precio pagado. Si una oferta pública queda más barata que su precio, paga la
  oferta (el mayorista nunca paga más que el público; a confirmar con Daniel).
- **Nunca suelto**: cada producto se vende **desde su cantidad mínima** (la menor «Cantidad mínima»
  de las reglas de su lista que le aplican; el precio es el de esa cantidad) y **en bultos enteros**
  (el embalaje más chico del producto: en Odoo 20 los «Embalajes», `uom_ids`; ya no existe
  `product.packaging`). Lo exige la tienda al armar el pedido (no solo la pantalla): la lista sube las
  cantidades a la válida más cercana, el carrito suma de a un bulto, y el servidor rechaza lo demás.
  Para que nada se venda suelto, la regla general de la lista lleva su mínimo (p. ej. «desde 2»).
- **Excel**: `/lista.xlsx`, solo con cuenta aprobada, armado en la tienda sin dependencias
  (`src/servidor/xlsx.ts`). Una fila por producto (se puede filtrar y ordenar), encabezado con cliente
  y CUIT, fecha, aclaraciones (con IVA, puede cambiar), columnas: rubro, producto, código de barras,
  código interno, unidad, bulto, compra mínima, precio público, su precio, descuento, disponibilidad,
  cantidad (con validación: mínimo y bulto) y subtotal con fórmula, total al pie.

## Consecuencias

- Un solo despliegue y una sola base; las páginas compartidas (pedido, pago, 404) usan el layout del
  sitio que se está viendo.
- El pedido mayorista entra a Odoo con el contacto que crea la tienda por mail; **vincularlo con el
  contacto real del mayorista** y aprobar cuentas desde una pantalla queda para la fase 7.
- **Precios por escala** («desde 10, otro precio») todavía no: la tienda guarda un precio por lista y
  producto (el de la cantidad mínima).
- Al salir a producción: agregar `mayoristas.comercio-ejemplo.example` a las rutas del Worker de producción.
