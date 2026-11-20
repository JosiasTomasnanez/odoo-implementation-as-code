# Licenses of the Odoo modules

Each module declares its license in `__manifest__.py`:

- **LGPL-3** (https://www.gnu.org/licenses/lgpl-3.0.html): modules that depend only on Odoo
  Community modules.
- **OPL-1** (Odoo Proprietary License v1.0, https://www.odoo.com/documentation/master/legal/licenses.html):
  modules that depend on Odoo Enterprise modules (`comercio_cierre_z`, `comercio_conteo_catalogo`,
  `comercio_factura_proveedor`, `comercio_libro_iva`, `comercio_pos_ticket_ar`). Using them requires
  a valid Odoo Enterprise subscription.

No Odoo Enterprise code is included in this repository.
