# Cierre de caja y puestos

Procedimiento para el personal. Versión para compartir: documento «Comercio Ejemplo —
Reglas de cierre de caja y puestos» (Claude Docs). Detalle técnico: ADR 0009 y
`addons/comercio_pos_pedido_qr`.

> **Ojo: no es el flujo de la primera etapa.** Esto describe el flujo con la caja de Odoo
> (pedido con QR → la caja lo cobra), guardado para la etapa siguiente (ADR 0017). Hoy, en
> el lab, los puestos dan el pedido por cobrado con «Cobrado en registradora» (ADR 0019) y
> las registradoras cobran. Para probar este flujo: `docs/runbooks/prueba-visual.md`,
> sección 10 («Etapas siguientes»).

## La regla principal

**La caja no cierra mientras haya alguien con ticket esperando para pagar.** El orden en
que cierran puestos y caja da igual.

## Cierre del día

1. Cada puesto cierra su sesión al terminar. Quien atiende el puesto puede hacerlo aunque
   su rol no le permita cobrar (los puestos no manejan plata).
2. La caja cobra a los últimos clientes con ticket.
3. La caja cierra con el conteo de efectivo. Siempre lo hace una persona.

## Tickets que nadie pagó

| Situación | Qué pasa |
|---|---|
| El puesto cierra y la caja sigue abierta | No se anulan: la caja los puede seguir cobrando. |
| La caja cierra | Se anulan los que nadie cobró. |
| El puesto cierra con la caja ya cerrada | Se anulan en ese momento. |

Un ticket sin pagar no descuenta stock ni suma plata. Cada anulación queda registrada en el
pedido y en la sesión.

## Cierre automático

Todas las noches a las 23:30 (Argentina) se cierran solos los puestos que quedaron
abiertos (acción planificada «Comercio: cerrar puestos abiertos por la noche»). La caja
nunca se cierra sola. Si un puesto no se puede cerrar, queda anotado en su sesión.

## Qué evitar

- Cerrar la caja con clientes esperando con su ticket.
- Dejar la caja abierta de un día para otro (mezcla el conteo de dos días).
- Si el lector no lee el ticket: en la caja, «Abrir pedido» y tipear el número impreso.

## Verificación

`make e2e-pos` (cuidado: cierra y reabre las sesiones de los POS de ejemplo del lab).
