# 0011. Sin Odoo Online: pruebas en el lab y después en Enterprise local

- Estado: aceptado
- Fecha: 2026-10-08
- Reemplaza en parte a: [0007](0007-produccion-on-premise.md) (el uso de Online para pruebas)

## Contexto

El ADR 0007 dejaba Odoo Online (`casa-ejemplo1.odoo.com`) como entorno de pruebas
mientras se preparaba el servidor propio. Desde entonces se hizo el primer módulo
propio, `comercio_pos_pedido_qr` (ADR 0009), que es central para el flujo puesto → caja.
Odoo Online no permite instalar módulos propios con código Python, así que en Online
no se puede probar el flujo real del local: las pruebas ahí quedan limitadas.

## Decisión

- **No se usa Odoo Online**, ni para producción ni para pruebas.
- **Ahora:** las pruebas se hacen en el **lab Community** (`odoo:20.0`), con
  `config/base` + `onpremise` + `ejemplos`.
- **Cuando se pague el plan Enterprise** y esté disponible la versión local, se pasa a
  trabajar sobre **Odoo 20 Enterprise On-Premise**.
- La producción sigue siendo en el servidor propio (ADR 0007, sin cambios).

## Alternativas consideradas

- Seguir probando en Online lo que no depende del módulo: se descarta porque obliga a
  mantener dos entornos y no prueba el flujo que el local va a usar.
- Odoo.sh (permite módulos propios): no se evaluó; la producción ya es On-Premise.

## Consecuencias

- Lo que solo existe en Enterprise (por ejemplo, partes de la facturación electrónica
  AR, IoT, Studio) **no se puede probar en el lab Community**: queda para cuando esté
  la versión Enterprise local. Al probar algo en el lab, anotar si depende de Enterprise.
- La base `casa-ejemplo1.odoo.com` es la que Odoo creó al abrir la cuenta. Al pagar
  la suscripción Custom puede cambiar. Si queda activa, se usa **a lo sumo para pruebas
  puntuales**, nunca como entorno productivo ni como respaldo en la nube. No tiene datos
  que haya que conservar.
- **Ante una falla del servidor** no se recurre a Online: se pone otra computadora,
  se reconstruye el stack (infraestructura reproducible) y se restaura el último backup.
  La reconstrucción recupera la configuración; **los datos del negocio** (ventas, stock,
  facturas) solo vuelven desde el backup, que por eso tiene que guardarse fuera del
  servidor (P-013).
- P-023 se resuelve: la producción se arma desde cero (no hay base Online que migrar).
- Falta confirmar con Odoo (P-010) cómo se obtiene el código o la imagen Enterprise
  con la suscripción Custom anual.
- Se quitan la capa `config/online`, `environments/online.yaml` y su API key en
  `.env.example`. `odoo-iac` sigue siendo genérico (funcionaría contra Online), pero este
  proyecto no tiene ese entorno.
