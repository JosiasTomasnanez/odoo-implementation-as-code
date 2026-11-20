# 0008. Staging en el servidor y despliegue por pipeline

- Estado: propuesto (se implementa cuando exista el servidor, P-011)
- Fecha: 2026-10-05

## Contexto

La producción va a estar en un servidor propio (ADR 0007). Cualquier cambio
(actualizar módulos, configuración, versión de Odoo) debería probarse antes, con
datos parecidos a los reales, sin arriesgar la base que usa el local.

## Decisión propuesta

Dos copias del mismo stack en el servidor, separadas por proyecto de Compose
(`odoo-staging` y `odoo-prod`): cada una con su base, su filestore, su red y su
`environments/<entorno>.yaml`.

```text
push a main  ──► staging     build de imagen → actualizar módulos → odoo-iac apply + verify
tag vX.Y.Z   ──► producción  backup obligatorio → aprobación manual → imagen del tag
                             → actualizar módulos → odoo-iac apply + verify
                             → si falla: imagen del tag anterior + restaurar el backup
```

- **Datos de staging:** copia de producción restaurada con `restore.sh --neutralize`
  cada tanto (sin correos ni tareas programadas reales). Staging se puede apagar
  cuando no se usa.
- **Pipeline:** runner self-hosted de GitHub Actions en el servidor, con un usuario
  dedicado. Solo con el repositorio **privado**: en uno público un PR ajeno podría
  ejecutar código en el servidor. Alternativa más simple: script en el servidor que
  consulta el repo y despliega.
- Despliegues a producción fuera del horario de atención.

## Alternativas consideradas

- Probar solo en el lab o en Online: no tiene los datos ni la versión exacta de producción.
- Desplegar a mano: depende de recordar los pasos, que es lo que el proyecto quiere evitar.

## Consecuencias / a verificar antes de implementar (P-024)

- **ARCA:** staging no puede emitir comprobantes reales. Verificar si la neutralización
  pasa la facturación electrónica a homologación; si no, el despliegue a staging lo fuerza.
  Staging usa el certificado de homologación de ARCA, nunca el de producción.
- **Licencia:** confirmar con Odoo que la suscripción Enterprise admite una base de
  staging además de la de producción.
- **Recursos:** el servidor tiene que alcanzar para dos Odoo y dos PostgreSQL
  (`docs/infraestructura/servidor.md`).
- Volver atrás tras actualizar módulos exige restaurar la base: el backup previo no es opcional.
- Staging usa su propia API key para `odoo-iac`, distinta de la de producción.
