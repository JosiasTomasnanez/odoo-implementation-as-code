# 0007. Producción en servidor propio; Odoo Online solo para pruebas

- Estado: aceptado; el uso de Online para pruebas fue reemplazado por [0011](0011-sin-odoo-online.md)
- Fecha: 2026-10-05

## Contexto

El planteo inicial (CLAUDE.md) era empezar en Odoo Online y evaluar más adelante un
servidor propio. El 05/10/2026 el negocio decidió:

- contratar el plan **Custom** de Odoo Enterprise;
- usar Odoo Online (`casa-ejemplo1.odoo.com`, 20.0+e) **solo para pruebas**;
- que la puesta en marcha en el local sea **directamente en servidor propio**;
- con menos de 10 usuarios (estimado, a confirmar en P-005).

## Decisión

- **Producción:** Odoo 20 Enterprise On-Premise, con el stack del repositorio
  (`infra/docker/`, ADR 0004), en un servidor dentro del local
  (requisitos en `docs/infraestructura/servidor.md`).
- **Online:** entorno de pruebas y de aprendizaje con funciones Enterprise
  mientras se prepara el servidor. No se cargan datos reales masivos.
- **La base de producción se construye desde cero** con `odoo-iac` (config/) y los
  procesos de importación. La base de prueba de Online no se migra, salvo que se
  decida lo contrario (P-023). Así la producción nace reproducible y sin restos de pruebas.
- El lab (Community) sigue siendo el entorno descartable para experimentar.

## Precisión (05/10/2026)

- Se contrata **una sola suscripción Custom desde el primer día**, que habilita el
  servidor propio. No se pagan dos suscripciones: se **usan los dos entornos**, Online
  para pruebas y el servidor local para producción.
- En Online se trabaja en una **base de datos de pruebas aparte**, tratada como
  laboratorio. No se descarta que Online llegue a tener algún uso productivo, pero hoy
  no está previsto.
- **A confirmar con Odoo (P-010):** que una suscripción Custom cubra a la vez la base de
  producción On-Premise y una base de pruebas en Online, y en qué condiciones (vencimiento
  de las bases de prueba, si cuentan como base adicional, usuarios).

## Alternativas consideradas

- Producción en Online y migrar después: más rápido de arrancar, pero obliga a una
  migración con el negocio operando, y Online puede pasar a versiones intermedias
  ("saas") que no se pueden instalar en un servidor propio.
- Migrar la base de prueba de Online al servidor: es posible (descargar el backup
  desde el gestor de bases y restaurarlo en la **misma** versión mayor, 20.0), pero
  arrastra datos de prueba y configuración manual no registrada.

## Consecuencias

- **Plazo:** el servidor (compra, instalación, seguridad, red, backup externo y
  prueba de restauración) pasa a ser un hito que **frena la Fase 4**. Hay que
  comprar el hardware cuanto antes (P-011).
- **Licencia:** Enterprise On-Premise requiere el plan Custom (decidido), por usuario.
  Hay que confirmar con Odoo cómo se traslada la suscripción de Online al servidor sin
  pagar dos veces, y cómo se obtiene el código Enterprise (P-010).
- **Versión:** si la instancia Online se pasa a una "saas~20.x", deja de ser compatible
  con el servidor (20.0). No aceptar actualizaciones de versión en Online sin revisarlo.
- **Internet:** el servidor local permite seguir vendiendo sin Internet, pero la
  factura electrónica (ARCA), los backups externos, el acceso remoto y el futuro
  ecommerce sí dependen de la conexión (P-012, red.md).
- Se vuelven prioritarios: seguridad (`seguridad.md`), red (`red.md`), backups con
  copia externa (P-013), recuperación ante desastres y monitoreo (P-019).
- `odoo-iac` aplica la misma configuración a Online (pruebas) y On-Premise
  (producción): las capas `config/online` y `config/onpremise` absorben las diferencias.
