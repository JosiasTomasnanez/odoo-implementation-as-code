# Configuración declarativa

Acá vive el **estado deseado** de Odoo, escrito en YAML y aplicado con `odoo-iac`
(ver `docs/decisiones/0003-configuracion-como-codigo.md`).

## Capas

| Capa | Se aplica en | Contenido |
|------|--------------|-----------|
| `base/` | todos los entornos | visión funcional común: lo que el negocio necesita, independiente de dónde corra Odoo |
| `onpremise/` | servidor propio | ajustes que solo aplican On-Premise (p. ej. módulos propios de `addons/`) |
| `ejemplos/` | solo laboratorio | datos **ficticios** para experimentar; nunca se aplica a producción |

Qué capas usa cada entorno se define en `environments/<entorno>.yaml`.
Una capa posterior puede redefinir un registro con el mismo `id`; sus valores se combinan.

## Formato

Los archivos de cada capa se procesan en orden alfabético; se prefijan con números
para que el orden sea explícito (`00-modulos.yaml`, `10-categorias.yaml`, ...).
Un registro solo puede referenciar a otro definido antes o ya existente en Odoo.

```yaml
# Módulos (apps) a instalar. Nunca se desinstala nada automáticamente.
modules:
  - stock
```

```yaml
model: product.category
match: [name]             # opcional: adoptar un registro existente sin duplicarlo
records:
  - id: cat_mascotas      # id estable → xml_id "iac.cat_mascotas" en Odoo
    values:
      name: Mascotas
      parent_id: {ref: product.product_category_all}   # xml_id de Odoo (módulo.nombre)
  - id: cat_alimentos
    noupdate: true        # solo se crea; después se respetan los cambios hechos en Odoo
    values:
      name: Alimentos
      parent_id: {ref: cat_mascotas}                   # id propio (sin punto)
```

```yaml
# Ajustes generales (pantalla Ajustes de Odoo, modelo res.config.settings).
# Se aplican como el botón «Guardar»: solo se tocan los que difieren.
settings:
  group_product_pricelist: true
```

Valores especiales:

- `{valor: <ruta>}`: un dato de los archivos de valores del entorno (`config/valores.yaml`,
  ADR 0010). Lo que puede cambiar (nombres, opciones, márgenes) va ahí, comentado, y se
  aplica con `make plan` / `make apply`. Para una demo: `make apply ENV=lab VALORES=otro.yaml`.
- `{ref: <id>}`: many2one. Sin punto es un id propio (`iac.<id>`); con punto, un xml_id de Odoo.
- `{refs: [<id>, ...]}`: many2many / one2many; reemplaza la lista completa.
- `{archivo: <ruta>}`: campo binario o imagen con el contenido de un archivo (relativo al
  YAML), p. ej. el logo del ticket: `custom_logo: {archivo: ../imagenes/logo-ticket.png}`.
  Las imágenes van en `config/imagenes/`.

Para descubrir campos y modelos: `odoo-iac inspect -e lab <modelo> [--field texto]`.

## Reglas

- **No declarar decisiones que el negocio no tomó.** Si algo está pendiente, va a
  `docs/pendientes.md`, no a esta carpeta.
- **Nada de datos reales sensibles.** Datos maestros reales (productos, clientes,
  proveedores) no se versionan acá; se cargan con procesos de importación (ver `data/`).
- Esta carpeta describe **configuración**: categorías, listas de precios, métodos de
  pago, puntos de venta, usuarios técnicos, grupos, secuencias, etc.
