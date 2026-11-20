# Panel de pedidos de la tienda (para el personal)

Los pedidos online se preparan desde **`/panel`** de la tienda (en la PC o tablet del local). Por
detrás todo lo hace Odoo: cada botón deja una acción que el conector aplica en el pedido de venta.

## Una vez por equipo: habilitarlo

1. Abrir `https://<tienda>/panel` → pide **Habilitar esta PC**.
2. Poner un nombre («PC de ferretería») y el **código de alta** (lo tiene el administrador;
   en la demo está en `~/panel-tienda-demo.txt`, fuera de git). Queda habilitada por un año.
3. Cambiar el código: `cd web/tienda && npx wrangler secret put PANEL_CODIGO_ALTA`. Sacar un equipo:
   por ahora `npx wrangler d1 execute comercio-ejemplo-tienda-demo --remote --command "UPDATE dispositivos SET revocado = datetime('now') WHERE nombre = '…'"` (pantalla de administración: fase 7).

## Quién entra

En Odoo, ficha del empleado → **«Usa el panel de pedidos de la tienda»** y su **PIN** (el mismo de
la caja). En el panel: tocar el nombre y poner el PIN. La sesión dura 12 horas. 5 PIN mal de una
persona la bloquean 10 minutos; 15 mal en el equipo, 15 minutos.

## Día a día

| Columna | Botón | Qué pasa |
|---|---|---|
| Para preparar | **Empezar a preparar** | Odoo: «Preparando» |
| Preparando | **Listo para retirar** | Odoo valida la entrega con lo preparado; al cliente le llega «Tu pedido está listo» |
| Preparando | **Falta algo** → cuánto hay de cada uno → **Avisar al cliente** | Odoo: «Falta algo» con el detalle; al cliente le llega el mail para elegir esperar, otro producto o la devolución |
| Listos para retirar | **Ya lo retiró** | Odoo: «Retirado» |

Con «Falta algo», al cliente le llega un mail con el link a su pedido, donde ve qué falta («hay 1 de 2»)
y elige **esperar**, **otro producto** (se lo llama) o **la devolución de lo que falta**. La elección
aparece en la tarjeta del panel y queda anotada en el pedido de venta de Odoo. La devolución con
Mercado Pago se hace a mano mientras no esté conectado.

Un pedido listo hace más de 7 días (`DIAS_AVISO_LOCAL`) se marca para llamar al cliente; a los 3
días (`DIAS_RECORDATORIO`) le llega un recordatorio por mail.

## Cancelar un pedido (arrepentimiento)

En **Administración → Arrepentimientos** (rol «admin»), en el pedido de arrepentimiento:
**Confirmo → Cancelar el pedido**. La tienda lo pasa a «Cancelado» y libera la reserva; en Odoo:

- **No lo retiró:** se cancela el pedido de venta; si ya estaba separado («listo»), la mercadería
  vuelve al depósito en el acto.
- **Ya lo retiró:** queda la **devolución preparada** (Inventario → Recepciones) y la tarea «Recibir
  la devolución de la tienda»: cuando el cliente trae la mercadería, validarla y cancelar el pedido.
- **Siempre:** la tarea «Devolver el dinero del pedido de la tienda», con el monto y el pago. El
  reembolso se hace a mano en Mercado Pago hasta tener la API.

Si se resolvió de otra forma (cambio de producto, el cliente desistió), «Marcar resuelto».

## Reporte de uso de Cloudflare

Cada día a las 9:05 llega a Discord una tarjeta con el uso de **toda la cuenta** contra el plan
gratis: pedidos, CPU por pedido (y pedidos cortados por CPU), D1, Durable Objects, KV y R2. Dice
«dentro del plan gratis», «cerca del cupo, mirar» (50 % de algo o CPU p99 sobre 10 ms) o **«pasar al
plan pago»** (80 % de algo o algún pedido cortado): ahí, Workers Paid (USD 5 por mes) desde el panel
de Cloudflare. Lo manda un solo Worker, el que tenga `REPORTE_USO = "1"` en `wrangler.jsonc` (hoy la
demo; al lanzar, la tienda de producción). Necesita un token de Cloudflare con permiso **Account
Analytics: Read** de la cuenta: `npx wrangler secret put CF_ANALYTICS_TOKEN`.

## Mails

Los manda la tienda por el primer proveedor configurado que lo acepte (`src/servidor/correo.ts`, P-067): **Brevo** (`BREVO_API_KEY`: cuenta gratis, dominio autenticado en Brevo y `npx wrangler secret put BREVO_API_KEY`) y, si rechaza o no está, **Resend**; `MAIL_ORDEN` (p. ej. `resend,brevo`) cambia el orden. Con el plan pago de Cloudflare se suma su servicio de mails: binding `send_email` llamado `CORREO` en `wrangler.jsonc` y pasa a ir primero. La bitácora del pedido dice por cuál salió. **Resumen diario por Discord:** la tienda cuenta los mails por día y proveedor (tabla `mails_dia`) y a las 9:00 manda el resumen de ayer al canal del secreto `DISCORD_WEBHOOK_URL` (`npx wrangler secret put DISCORD_WEBHOOK_URL`); los días sin mails no avisa. Cuenta solo los de la tienda, no los de Odoo ni los avisos del servidor. Resend: la tienda lo usa con **Resend** (`RESEND_API_KEY` como secreto, remitente `MAIL_DESDE`, por defecto
`pedidos@comercio-ejemplo.example`; el dominio ya está verificado en Resend). La clave «tienda» (solo envío)
es la misma para la demo y producción; **al salir a producción, renovarla** (crear otra en Resend,
`npx wrangler secret put RESEND_API_KEY` y borrar la vieja). Sin la clave no se manda nada: queda
anotado en la bitácora del pedido. Para probar, solo mails reales propios (los rebotes bajan la
reputación del dominio, que comparten los avisos del servidor).

## Probar

`make e2e-tienda-panel` (5 casos). Ojo: el último caso bloquea el PIN 10 minutos; esperar antes de
volver a correrla.
