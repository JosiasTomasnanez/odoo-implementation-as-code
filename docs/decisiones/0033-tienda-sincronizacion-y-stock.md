# 0033. Tienda online: sincronización con Odoo por un conector que sale del local, y reservas de stock

- Estado: aceptado (implementador, 03/11; plan de la tienda)
- Fecha: 2026-11-03

## Contexto

Odoo es la fuente de productos, precios, stock y pedidos (ADR 0031), pero corre en el servidor
del local, que puede quedarse sin luz o sin Internet y no tiene nada publicado a Internet salvo el
acceso remoto, que bloquea la API (`/json/2`, ADR 0020). La tienda tiene que vender aunque el local
esté caído, sin sobrecargar el servidor y **sin vender dos veces lo mismo**: el mostrador vende del
mismo stock.

## Decisión

### Conector en el local, siempre saliente

- Un servicio chico en el servidor del local, **`conector-tienda`** (contenedor en
  `compose.onprem.yml` y en el del lab), habla con Odoo por JSON-2 en la red interna y con la tienda
  por HTTPS firmado (clave compartida, HMAC con fecha y número de lote). **El local no publica
  ninguna API**; el túnel sigue bloqueando `/json/2`.
- **Odoo → tienda (empuja):** el módulo `comercio_tienda` anota en una cola (outbox) qué productos
  cambiaron (publicación, precio de la lista «Tienda online», stock libre, foto, categoría del
  PdV, texto). El conector lee la cola cada pocos segundos, junta lotes y los manda; la tienda los
  aplica y confirma el lote, recién ahí se borran de la cola. Cada lote se puede reenviar sin
  duplicar (upsert por id de Odoo).
- **Tienda → Odoo (trae):** el conector le pide a la tienda los pedidos pagados y las acciones
  del panel de empleados (preparar, listo, faltante, retirado) y las aplica en Odoo. Si el local
  está caído, todo espera en la tienda.

### Stock y reservas

- `disponible en la tienda = stock libre de Odoo − reservas de la tienda que Odoo todavía no
  refleja − margen de seguridad` (margen por categoría o producto; por defecto en
  `config/valores.yaml`).
- Las reservas pasan por **un solo Durable Object «Inventario»** que las ejecuta de a una:
  al ir a pagar se reserva **todo el carrito o nada**, por unos minutos; el pago confirmado
  (verificado contra la API de Mercado Pago) la pasa a «pagada»; un pago vencido o rechazado la
  libera.
- El conector crea el pedido en Odoo **confirmado** (su entrega reserva el stock). Cuando el stock
  libre que manda Odoo ya incluye ese pedido, la reserva de la tienda deja de restarse aparte.
- Productos **«Consultar disponibilidad»**: se venden y se pagan igual, sin tope de stock, con
  «te confirmamos en el día».
- Lo que igual se escapa (el mostrador vende la última unidad en esos segundos) va al flujo de
  **faltante**: el cliente elige esperar, reemplazo o devolución (reintegro por Mercado Pago).

### Idempotencia

- El pedido lleva un id de la tienda guardado en Odoo con restricción de único; el conector busca
  antes de crear.
- Cada pago de Mercado Pago se procesa una sola vez por su id.
- Las acciones del panel llevan id propio y se aplican una vez; Odoo devuelve el estado final y la
  tienda lo muestra.

## Consecuencias

- El stock de la tienda se atrasa unos segundos respecto del mostrador: lo cubren el margen y el
  flujo de faltante.
- Con el local caído no se crean pedidos en Odoo ni se preparan, pero la tienda vende y cobra.
- Un servicio más en el servidor, con su chequeo en los avisos (ADR 0027) y su prueba
  (`make e2e-tienda`).

## Alternativas descartadas

- **La tienda llama a Odoo por el túnel:** publica la API a Internet y cada visita o pago depende
  del local.
- **Webhooks nativos de Odoo (acción automática «Enviar webhook»):** se disparan en cada escritura,
  frenan al mostrador si la tienda tarda y se pierden si no hay Internet; la cola con lotes no.
- **Consultar a Odoo al pagar:** con el local caído no se podría vender.
