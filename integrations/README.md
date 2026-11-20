# Integraciones externas

Cada integración vive en su propia carpeta y se comunica con Odoo **solo por la API
externa** (puede reutilizar `odoo_iac.client`), así funciona en Online y On-Premise.

Estructura sugerida por integración:

```text
integrations/<nombre>/
  README.md     qué hace, hardware/protocolos, credenciales necesarias (no los valores),
                dependencias, limitaciones y procedimiento de recuperación
  ...           código
```

Requisitos para toda integración que escriba en Odoo:

- Idempotente (correrla dos veces no duplica).
- Modo `--dry-run` que muestre qué cambiaría.
- Verificación posterior del resultado.
- Sin credenciales en el código: variables de entorno / `.env`.

Candidatas (a confirmar): importación de catálogo y listas de proveedores
(integrando `odoo-product-matcher`, repo independiente, sin duplicar su lógica),
balanzas, medios de pago.
