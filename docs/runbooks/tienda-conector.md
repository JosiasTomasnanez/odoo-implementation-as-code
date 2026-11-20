# Conector de la tienda online

Lleva a la tienda (comercio-ejemplo.example o la de prueba demo.comercio-ejemplo.example) lo que se publica en Odoo:
productos, precios de las listas, stock libre, fotos y rubros. Corre en el servidor del local y
siempre **sale** hacia la tienda: el local no publica ninguna API (ADR 0033).

## En Odoo (lo hace el negocio)

- **Publicar un producto:** en su ficha, casilla **«Publicar en la tienda»**. De a muchos: lista de
  productos → marcar → *Acciones* → **Publicar en la tienda** (o **Quitar de la tienda**). Filtro
  «En la tienda online» en la búsqueda.
- **Consultar disponibilidad:** casilla al lado (aparece si está publicado). Se vende y se paga
  igual; el cliente ve que se le confirma en el día.
- **Precio y ofertas:** lista de precios **«Tienda online»**. Sin reglas = el precio de venta del
  local. Una oferta = una regla con precio y **fechas de inicio y fin**; cuando termina, vuelve sola
  al precio normal (la revisa una tarea cada hora).
- **Mayoristas:** una lista con «Sincronizar con la tienda» marcado viaja también (la ven solo los
  mayoristas aprobados, fase 6).
- **A reponer** (*Compras → Órdenes → Tienda: a reponer*, también en *Inventario → Productos*): cuando
  un producto publicado llega al mínimo (stock libre ≤ margen), la tienda lo pasa **sola** a
  «Consultar disponibilidad» (se sigue vendiendo, sin tope, y se confirma en el día) y aparece en
  esta lista, sin mandar avisos. Marcando uno o varios: **Pedir al proveedor** (lo suma a la
  solicitud en borrador del proveedor más barato, con su compra mínima; queda «Pedido»), **Dejar
  siempre a consultar**, **No reponer por ahora** o **Quitar de la tienda**. Cuando el stock vuelve
  sale solo de la lista y se vende normal. Una tarea cada hora repasa la lista por si el conector
  estuvo parado.
- **Margen de stock:** unidades que no se ofrecen online. Por defecto `tienda.margen_stock` en
  `config/valores.yaml`; cada categoría puede tener el suyo (ficha de la categoría → «Tienda online»).

## Instalar (una vez por entorno)

1. Módulo: `comercio_tienda` está en `config/onpremise/00-modulos.yaml` → `make apply ENV=...`.
2. Usuario técnico y su clave (usuario **portal** con solo el grupo «Tienda online: conector»: no ve
   clientes, costos ni nada más; la clave vence en un año):
   - Lab: `STACK=lab infra/scripts/crear-conector-tienda.sh` → `infra/docker/conector-tienda.lab.env`.
   - Servidor: `STACK=onprem sudo -E infra/scripts/crear-conector-tienda.sh` → `/etc/odoo-comercio/conector-tienda.env`.
3. En ese archivo: `TIENDA_URL` (https), `CONECTOR_SECRETO` (lo genera el script si falta) y,
   en el servidor, `HC_PING_URL` (healthchecks.io; la dirección está en Bitwarden).
4. El mismo `CONECTOR_SECRETO` en la tienda: `cd web/tienda && npx wrangler secret put CONECTOR_SECRETO`
   (se pega el valor; no queda en la terminal ni en git).
5. `TIENDA=1` en `onprem.env` (servidor) o en el `.env` del repo (lab) y
   `STACK=... bash -c 'source infra/scripts/lib.sh; compose up -d conector-tienda'`.
6. Primera carga: `compose run --rm -T conector-tienda --todo --una-vez`.

## Día a día

- Revisa la cola cada 5 s (`INTERVALO`). Un precio o una venta del mostrador llegan en segundos.
- Si la tienda o Internet no responden, reintenta solo (cada vez más espaciado, hasta 5 min) y no
  pierde nada: lo no confirmado se vuelve a mandar. A los 3 errores seguidos avisa a healthchecks;
  si se cae el servidor o el conector, healthchecks avisa porque deja de recibir el ping.
- Logs: `compose logs --tail 50 conector-tienda`.

## Problemas

| Qué pasa | Qué hacer |
|---|---|
| `HTTP 401` de la tienda | El `CONECTOR_SECRETO` no coincide con el de la tienda, o el reloj del servidor está corrido más de 5 min (el chequeo de hora de los avisos lo detecta). |
| `HTTP 422` de la tienda | Un dato no pasa la validación (p. ej. un nombre de más de 300 letras). El log de la tienda (`npx wrangler tail`) dice cuál. Se corrige en Odoo. |
| `HTTP 403` de Odoo | Venció la clave (1 año) o se tocó el usuario: volver a correr `crear-conector-tienda.sh`. |
| La tienda muestra algo viejo | `compose run --rm -T conector-tienda --todo --una-vez` lo vuelve a mandar todo. |

## Seguridad

- Cada envío va firmado (HMAC-SHA256 sobre fecha, método, ruta y contenido; se rechaza lo de más
  de 5 minutos) y la tienda valida cada campo (tipos, largos, sin campos de más) antes de guardar.
  Todo en D1 con consultas preparadas. Las fotos se aceptan solo si sus bytes son JPEG, PNG o WebP.
- La clave de Odoo y el secreto viven solo en el archivo de entorno (600) y como secreto de la
  tienda. Rotar: volver a correr el script (clave de Odoo) o generar otro secreto y cargarlo en los
  dos lados.
