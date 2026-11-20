# 0004. Docker Compose para laboratorio y On-Premise

- Estado: aceptado
- Fecha: 2026-09-30

## Contexto

Se necesita un laboratorio destruible y reconstruible, y el despliegue On-Premise
previsto es Docker Compose. Tener dos stacks distintos haría que lo probado en el
lab no sea representativo.

## Decisión

- `infra/docker/compose.yml`: base común (PostgreSQL + Odoo, imágenes oficiales).
- `compose.lab.yml`: puertos en localhost, addons montados, modo desarrollo.
- `compose.onprem.yml`: imagen propia (`Dockerfile`: Odoo oficial + `addons/`),
  reinicio automático, Odoo solo en localhost detrás de un proxy (pendiente P-012),
  configuración y secretos **fuera del repo**.
- Los scripts de `infra/scripts/` funcionan para ambos (`STACK=lab|onprem`).

## Alternativas consideradas

- Instalación nativa (paquetes .deb): más difícil de reconstruir desde cero.
- Kubernetes: desproporcionado para un único servidor en un comercio.

## Consecuencias

- El servidor On-Premise necesita Docker; su endurecimiento se documenta en
  `docs/infraestructura/seguridad.md`.
- Proxy inverso, TLS, monitoreo y backup externo se agregarán como servicios o
  procesos cuando se decidan, no antes.
