# 0003. Configuración como código con `odoo-iac`

- Estado: aceptado
- Fecha: 2026-09-30

## Contexto

La configuración de Odoo (módulos, categorías, listas de precios, métodos de pago,
puntos de venta, etc.) suele hacerse a mano y quedar solo en la memoria del
implementador. Se busca reproducibilidad, idempotencia, dry run y validación
(ver `CLAUDE.md`), compatible con Odoo Online.

## Decisión

Una herramienta propia y pequeña, `odoo-iac` (`src/odoo_iac/`), que:

1. Lee el estado deseado de YAML por capas (`config/`), según el entorno.
2. Identifica cada registro con un **xml_id estable** (`iac.<id>` en `ir.model.data`),
   así aplicar N veces no duplica. Puede **adoptar** registros existentes por campos `match`.
3. `plan`: calcula diferencias sin escribir (dry run).
4. `apply`: aplica en orden y **vuelve a planificar** para verificar que no queden diferencias.
5. `verify`: detecta desvíos (cambios manuales en Odoo) con código de salida ≠ 0.
6. Nunca desinstala módulos ni borra registros automáticamente.

`noupdate: true` permite crear un registro una vez y luego respetar los cambios
hechos desde Odoo (útil para valores que el negocio administra en el día a día).

### Qué va en `config/` y qué no

- **Sí**: configuración estructural (módulos, categorías, UoM, listas de precios,
  diarios, métodos de pago, POS, grupos, secuencias, automatizaciones).
- **No**: datos maestros masivos o vivos (catálogo completo, clientes, stock, precios
  del día). Eso se carga con procesos de importación e integraciones (`integrations/`,
  `data/`), que deben ser igualmente idempotentes y con dry run.

## Alternativas consideradas

- Módulo Odoo con datos XML: es lo "nativo", pero no se puede instalar en Online.
  Podrá usarse On-Premise para lo que solo exista allí.
- Importaciones CSV manuales: no tienen dry run, ni verificación, ni detección de desvíos.
- Herramientas genéricas (Ansible/Terraform con providers de Odoo): dependencias
  pesadas y poco mantenidas para el valor que agregan hoy (ver `CLAUDE.md`).

## Consecuencias

- Los ids del YAML son un contrato: renombrarlos crea registros nuevos.
- Se requiere permiso para crear `ir.model.data` (usuario técnico administrador de
  configuración); verificado en el lab, **a confirmar en Odoo Online** (P-010).
- Campos que Odoo transforma al guardar (p. ej. HTML) pueden mostrar diferencias
  permanentes; se resolverán caso por caso si aparecen.
