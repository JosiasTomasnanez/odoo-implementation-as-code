# Tienda online: compra, reserva y pago

Cómo funciona la compra en la tienda (fase 3, ADR 0033) y cómo se conecta Mercado Pago.

## Qué pasa cuando alguien compra

1. En el carrito pone nombre, mail y (opcional) teléfono, y toca **«Pagar con Mercado Pago»**.
2. La tienda arma el pedido **con sus propios precios** (lo que diga el navegador no cuenta) y
   **reserva todo el carrito o nada** por 15 minutos. Si no alcanza el stock de algo, le dice
   cuánto hay. Los productos «Consultar disponibilidad» se venden sin tope.
3. El cliente paga. La tienda da el pago por hecho **solo cuando lo confirma el medio de pago**
   (consulta el pago en Mercado Pago; nunca le cree al aviso) y si el monto es exactamente el del
   pedido. Un monto distinto deja el pedido en «revisar».
4. El conector del local trae el pedido pago y lo crea **confirmado** en Odoo (*Ventas*), con el
   cliente por su mail, `N.º en la tienda` W-000N y su entrega, que reserva el stock en Odoo.
   Nunca dos veces el mismo pedido.
5. Si no paga en 15 minutos, la reserva vence sola (tarea de cada minuto) y el stock vuelve.
   Si el pago llega tarde y ya no hay stock, queda **«pagado con faltante»** (se le ofrece esperar,
   reemplazo o devolución: panel de empleados, fase 4).

El cliente ve el estado en `/pedido/<id>?t=<clave>` (el link que se le muestra y se le va a mandar
por mail).

## Pago de prueba (demo)

Mientras Mercado Pago no esté conectado, `PAGOS_MODO = "simulado"` (en `web/tienda/wrangler.jsonc`)
muestra una pantalla propia con **«Aprobar el pago»** / **«Rechazar el pago»**, que pasa por el
mismo circuito que un pago real. En producción ese modo no existe (la pantalla da «No encontrado»).

## Conectar Mercado Pago (cuando estén las credenciales)

1. En el panel de desarrolladores de Mercado Pago, crear la aplicación (Checkout Pro) con la cuenta
   del negocio. Primero las credenciales **de prueba**.
2. En la aplicación → **Webhooks**: URL `https://<tienda>/api/pago/mercadopago`, evento **Pagos**.
   Copiar la **clave secreta** del webhook.
3. Cargar los secretos (no quedan en git ni en la terminal):
   ```
   cd web/tienda
   npx wrangler secret put MP_ACCESS_TOKEN     # Access Token (de prueba o de producción)
   npx wrangler secret put MP_WEBHOOK_SECRET   # clave secreta del webhook
   ```
4. En `wrangler.jsonc`: `"PAGOS_MODO": "mercadopago"` y `make web-tienda-demo`.
5. Probar con las tarjetas de prueba de Mercado Pago: aprobada, rechazada.

Nada más cambia: el armado, la reserva, el aviso, Odoo y los mails son los mismos.

## Protecciones

- **Turnstile** (anti-bots de Cloudflare) en el formulario; sin clave configurada, no se arma
  ningún pedido. La demo usa las claves de prueba de Cloudflare; en producción, un widget propio
  (`TURNSTILE_SITEKEY` como variable y `TURNSTILE_SECRET` como secreto).
- **Límite de 10 pedidos por minuto por IP** y solo desde la propia tienda (encabezado Origin).
- Datos validados estrictos (un campo de más, como un «precio», hace rechazar el pedido).
- El aviso de Mercado Pago se verifica con su firma (`x-signature`) y después se consulta el pago.
- Cada pago se procesa una sola vez (por su id).

## Probar

`make e2e-tienda-pedidos` (contra demo.comercio-ejemplo.example y el lab): compra aprobada → Odoo; seis
compras a la vez de la última unidad (una sola la reserva); rechazo que libera; precios y
protecciones.
