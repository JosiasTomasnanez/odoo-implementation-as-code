# Documentación

## Metodología

Para cada necesidad del negocio (ver `CLAUDE.md`, "Forma de trabajar"):

```text
1. Relevar         docs/relevamiento/    ¿cómo funciona hoy? ¿qué duele?
2. Diseñar         docs/areas/<área>.md   ¿qué debe lograr Odoo? ¿qué trae estándar?
3. Decidir         docs/pendientes.md    preguntas abiertas → respuesta del cliente
                   docs/decisiones/      decisiones técnicas con su porqué (ADR)
4. Implementar     config/               configuración declarativa (preferido)
                   integrations/         si hace falta algo externo
                   addons/               si hace falta un módulo (solo On-Premise)
5. Probar          laboratorio           make plan / apply / verify
6. Aplicar         onpremise             mismo YAML, el servidor del local (Online no se usa, ADR 0011)
```

Escalera de soluciones, en orden de preferencia:
**estándar → configuración → automatización de Odoo → integración externa →
módulo propio → desarrollo complejo.** Subir un escalón debe justificarse en el
documento del área.

## Estados de un área

Cada documento de `areas/` declara su estado:

| Estado | Significado |
|--------|-------------|
| `relevamiento` | todavía se está entendiendo el proceso real |
| `diseño` | hay entendimiento; se evalúan opciones de Odoo |
| `decidido` | la solución está acordada con el cliente |
| `implementado` | existe en `config/` (u otro mecanismo) y se verificó en el lab |
| `productivo` | aplicado y verificado en el entorno real |

## Índice

- Pendientes (decisiones abiertas) (documento interno, no publicado)
- [Código propio](codigo-propio.md): módulos y código a mantener al cambiar de versión de Odoo
- Relevamiento: negocio, usuarios y roles,
  hardware, datos existentes,
  procesos (documento interno, no publicado)
- Áreas: inventario, códigos,
  compras y proveedores, punto de venta,
  balanzas y lectores,
  facturación y contabilidad,
  flujos de dinero, mayorista,
  ecommerce, usuarios y permisos,
  precios y promociones, roles y tareas,
  matching entre proveedores (documento interno, no publicado)
- [Decisiones técnicas (ADR)](decisiones/)
- Infraestructura On-Premise: [arquitectura](infraestructura/README.md),
  [seguridad](infraestructura/seguridad.md), [red](infraestructura/red.md),
  [backups](infraestructura/backups.md), [recuperación](infraestructura/recuperacion.md),
  [observabilidad](infraestructura/observabilidad.md), [servidor](infraestructura/servidor.md),
  [Enterprise vs Community](infraestructura/enterprise-vs-community.md)
- Runbooks: [laboratorio](runbooks/laboratorio.md),
  [instalar el servidor](runbooks/instalar-servidor.md),
  [backup y restauración](runbooks/backup-restauracion.md),
  [mostrar puesto y caja](runbooks/demo-puesto-caja.md),
  [cierre de caja](runbooks/cierre-de-caja.md), [devoluciones](runbooks/devoluciones.md),
  [prueba de la balanza real](runbooks/prueba-balanza-real.md), [HTTPS del servidor: paso a dominio propio y problemas de HTTPS](runbooks/https-servidor.md),
  [listas de proveedores](runbooks/listas-proveedores.md),
  [facturas de proveedor](runbooks/facturas-proveedor.md),
  [códigos de fábrica](runbooks/codigos-fabrica.md),
  [ventas con y sin factura de Odoo](runbooks/ventas-con-y-sin-factura.md),
  [categorías del POS](runbooks/categorias-pos.md),
  [listas de precios](runbooks/listas-de-precios.md),
  [prueba visual paso a paso](runbooks/prueba-visual.md)
