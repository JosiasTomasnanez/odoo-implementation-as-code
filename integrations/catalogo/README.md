# Catálogo: importar productos y proveedores

> **Para el uso diario está la app «Costos y precios» en Odoo** (sección «Listas de proveedores») (módulo
> `comercio_catalogo`, ADR 0015, guía en `docs/runbooks/listas-proveedores.md`).
> Esta herramienta de línea de comandos usa el mismo motor y sirve para la carga
> inicial masiva o para pruebas.

Carga productos en Odoo desde las listas de los proveedores, con la menor intervención
manual posible. Reglas de códigos y decisiones: docs/areas/codigos.md (documento interno, no publicado).

```text
Excel del proveedor ──convertir.py + mapeo──► planilla modelo (CSV) ──importar.py──► Odoo
```

## Uso

```bash
.venv/bin/pip install -e '.[catalogo]'      # una vez (openpyxl)

# 1. Excel del proveedor (.xlsx, .xls o CSV) → planilla modelo (los Excel reales van en data/privado/)
.venv/bin/python integrations/catalogo/convertir.py \
    integrations/catalogo/proveedores/<proveedor>.yaml data/privado/lista.xlsx -o data/privado/lista.csv

# 2. Simular (no cambia nada): nuevos, vinculados, cambios de costo y filas a revisar
.venv/bin/python integrations/catalogo/importar.py -e lab data/privado/lista.csv --informe data/privado/informe.csv

# 3. Aplicar y verificar
.venv/bin/python integrations/catalogo/importar.py -e lab data/privado/lista.csv --aplicar
```

Ejemplo con datos ficticios: `data/plantillas/productos.csv` (un caso de cada regla).

## Planilla modelo

CSV separado por `;` (se abre con Excel). Una fila por producto **y proveedor**.

| Columna | Obligatoria | Qué va |
|---------|-------------|--------|
| `proveedor` | sí | nombre del proveedor tal como está (o va a quedar) en Odoo |
| `codigo_proveedor` | recomendada | código del producto en la lista de ese proveedor |
| `descripcion_proveedor` | recomendada | descripción tal como la escribe el proveedor |
| `codigo_barras` | no | EAN/UPC del fabricante. Vacío: se asigna uno propio (`20…`) |
| `nombre` | no | nombre en el comercio. Vacío: se usa la descripción del proveedor |
| `categoria` | no | categoría existente en Odoo (nombre completo, p. ej. `Mascotas / Alimento`) |
| `unidad` | no | `u` (por defecto), `kg`, `m` o `l` |
| `costo` | no | precio de compra; acepta `1.234,56` |
| `cantidad_minima` | no | cantidad mínima de compra a ese proveedor |
| `costo_mayor` | no | segundo precio del proveedor, por mayor (p. ej. por bulto) |
| `cantidad_mayor` | no | desde cuántas unidades vale `costo_mayor` (tiene que ser mayor que el mínimo) |
| `plazo_dias` | no | días de entrega |
| `pesable` | no | `si` para vender con balanza |
| `precio_venta` | no | solo si se quiere fijar; si no, sale del margen (P-030) |
| `controla_stock` | no | `si`/`no`; vacío: según la categoría (casilla «Controla stock», declarada en `config/`) |
| `vincular_a` | no | «es el mismo»: referencia o código de barras de un producto existente; une esta fila a ese producto (confirmación de una sola vez) |
| `nuevo` | no | «es nuevo»: `si` crea el producto aunque se parezca a otro |

## Qué hace con cada fila

- Busca el producto por **código de barras del fabricante** y por **código de ese
  proveedor**. Si lo encuentra, le agrega el proveedor o actualiza sus datos (costo,
  mínimo, plazo, código, descripción). Si no, crea el producto.
- Productos nuevos: referencia interna = siguiente número correlativo; si no tienen código
  de fábrica, código propio `20` + ese mismo número.
- El código de un proveedor solo se compara con el mismo proveedor (nunca entre proveedores).
- Cambio de costo: se cierra el precio anterior y se abre uno nuevo desde hoy (historial).
- Lo dudoso queda como **revisar** y no se toca (ver la tabla de docs/areas/codigos.md).
- **Posible duplicado** (ADR 0014): si una fila iba a crear un producto pero su nombre se
  parece a uno existente (o a otro nuevo de la misma carga), no se crea: se muestran los
  3 candidatos más parecidos con la referencia o código para `vincular_a`. Una persona
  confirma «es el mismo» (`vincular_a`) o «es nuevo» (`nuevo=si`) una sola vez. El
  motor (`similitud.py`, portado de `odoo-product-matcher`) compara nombres sin IA:
  palabras, unidades equivalentes, abreviaturas; una cantidad distinta (3 kg vs 15 kg)
  no es duplicado. No compara códigos de proveedor entre proveedores.
- No cambia nombre, categoría ni código de barras de productos existentes (salvo
  completar un código de barras vacío).
- Idempotente: correrlo de nuevo con la misma planilla no cambia nada; al aplicar,
  verifica eso mismo.

## Limitaciones (por ahora)

- La confirmación de posibles duplicados es por columnas de la planilla hasta que esté
  la pantalla en Odoo (`comercio_catalogo_revision`, ADR 0014).
- Nombres muy distintos para el mismo producto (sin palabras en común) no se detectan:
  ahí puede ayudar la IA (M1, a medir con listas reales).
- Todos los productos nuevos quedan disponibles en el POS.
- Los proveedores nuevos se crean como empresa con el nombre de la planilla.
