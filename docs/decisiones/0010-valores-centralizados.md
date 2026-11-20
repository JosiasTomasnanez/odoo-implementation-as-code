# 0010. Valores modificables centralizados en `config/valores.yaml`

- Estado: aceptado
- Fecha: 2026-10-08

## Contexto

Varias definiciones del local cambian seguido o están en discusión: nombres de puestos y
cajas, nombres de medios de pago, opciones de impresión y, más adelante, márgenes por
rubro (P-030). Estaban repartidas en varios YAML de `config/`, mezcladas con la estructura.
Para una demo o un arreglo rápido había que saber en qué archivo estaba cada dato, o
cambiarlo a mano en Odoo y perder la reproducibilidad.

## Decisión

Un archivo central y comentado, `config/valores.yaml`, al estilo del `values.yaml` de
Helm. Los YAML de `config/` lo referencian con `{valor: ruta.con.puntos}`. Cada entorno
declara sus archivos de valores (`values:` en `environments/<env>.yaml`); se combinan en
orden y el último gana. Para una demo: `make plan|apply ENV=lab VALORES=otro.yaml`,
que suma un archivo extra sin tocar el principal.

Un valor inexistente es un **error** al leer la configuración: nunca se aplica vacío.

## Alternativas consideradas

- **Plantillas de texto (Jinja, como Helm):** más potentes, pero permiten generar YAML
  inválido y esconden la estructura; con reemplazar valores enteros alcanza.
- **Variables de entorno:** no se versionan junto con la configuración y no se pueden
  comentar.
- **Dejar los datos en cada archivo:** más simple, pero obliga a buscar dónde está cada uno.

## Consecuencias

- Lo que cambia seguido se edita en un solo lugar, con `make plan` antes de aplicar.
- `config/valores.yaml` se versiona: no lleva datos sensibles (PIN, claves, CUIT real).
- Solo se reemplaza el valor completo de un campo (no texto dentro de un texto) y solo
  dentro de `values`. Si hace falta más, se revisa este ADR.
- Renombrar una clave de `valores.yaml` exige actualizar los YAML que la usan (el plan
  avisa con un error).
