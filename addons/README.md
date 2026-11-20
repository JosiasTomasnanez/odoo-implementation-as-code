# Módulos Odoo propios

Solo se usan **On-Premise** (Odoo Online no permite instalar módulos con código Python propio).
Se incluyen en la imagen de `infra/docker/Dockerfile` y se montan en el laboratorio.

Crear un módulo solo cuando la configuración y las integraciones no alcancen
(escalera de `docs/README.md`), documentando el porqué en el área correspondiente.

**Inventario:** cada módulo está descrito en [`docs/codigo-propio.md`](../docs/codigo-propio.md)
(qué piezas de Odoo usa o modifica y cómo se prueba). Un módulo nuevo o un cambio que
toque algo interno de Odoo se anota ahí en el mismo cambio.

Convenciones:

- Nombre `comercio_<función>` (p. ej. `comercio_pos_simple`), un módulo por necesidad.
- Versión `20.0.x.y.z`, licencia LGPL-3; OPL-1 si depende de un módulo Enterprise (licencia OEEL-1), como pide Odoo.
- Dependencias Python adicionales en `addons/requirements.txt`.
- Tests del módulo dentro del módulo (`tests/`), ejecutables en el laboratorio.
- Para instalarlo: agregarlo a `config/onpremise/00-modulos.yaml`.

Para generar el esqueleto: `docker run --rm -u $(id -u) -v "$PWD/addons:/out" odoo:20.0 odoo scaffold comercio_x /out`.
