# 0001. Un único repositorio para todo el proyecto

- Estado: aceptado
- Fecha: 2026-09-30

## Contexto

La implementación abarca conocimiento del negocio, configuración de Odoo,
infraestructura, backups y eventualmente módulos e integraciones. Si cada parte
vive en un lugar distinto, se pierde la trazabilidad entre "por qué" y "qué".

## Decisión

Todo vive en este repositorio, separado por carpetas con responsabilidades claras
(`docs/`, `config/`, `environments/`, `src/`, `infra/`, `addons/`, `integrations/`,
`data/`). La documentación y el código de una decisión se cambian en el mismo commit.

Excepción: herramientas con vida propia y reutilizables fuera de este cliente, como
`odoo-product-matcher`, siguen en su repositorio y se integran desde `integrations/`.

## Alternativas consideradas

- Repos separados (docs / infra / módulos): más overhead y dependencias cruzadas
  para un equipo chico.
- Wiki externa para la documentación: se desincroniza del código.

## Consecuencias

- Un commit responde "qué cambió y por qué".
- La herramienta `odoo-iac` es genérica (no conoce al cliente): podría extraerse a
  su propio paquete si se reutiliza en otras implementaciones.
