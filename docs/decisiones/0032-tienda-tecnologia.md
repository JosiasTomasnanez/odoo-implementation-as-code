# 0032. Tienda online: tecnología (Astro en Workers, D1, Durable Objects, R2)

- Estado: aceptado (implementador, 03/11; plan de la tienda)
- Fecha: 2026-11-03

## Contexto

La tienda vive en Cloudflare, separada del servidor del local (ADR 0031). La demo visual
(`web/tienda/`, Astro 5 estático, 02/11) confirmó la identidad (B1) y las pantallas. Ahora la tienda
necesita datos reales, carrito con reservas, pagos, cuentas, un panel de empleados y un editor
para marketing (`docs/areas/ecommerce.md`).

## Decisión

| Pieza | Elección | Por qué |
|---|---|---|
| Sitio y APIs | **Astro 7** con salida en servidor en **Cloudflare Workers** (`@astrojs/cloudflare`) | Sigue la demo (mismos componentes); páginas que se arman al pedirlas, con caché; poco JavaScript en el celular |
| Datos | **D1** (SQLite de Cloudflare) | Catálogo copiado de Odoo, pedidos, cuentas, contenido del editor; búsqueda con FTS5 (sin acentos) |
| Reservas de stock | **Un Durable Object «Inventario»** | Ejecuta las reservas de a una, con su propio SQLite y consistencia fuerte: dos clientes no reservan la misma última unidad (ADR 0033) |
| Fotos y facturas | **R2** | Las fotos de Odoo que sube el conector y los PDF de las facturas; se sirven redimensionadas |
| Tareas programadas | **Cron Triggers** | Vencer reservas, recordatorios de retiro |
| Mails | **Resend** (el implementador ya tiene cuenta), con el dominio `comercio-ejemplo.example` verificado | La tienda manda los de la compra por su API (pedido, listo con la factura, recordatorio, faltante; clave en `wrangler secret`). Odoo lo usa como servidor SMTP para las campañas de *Email Marketing* y los avisos del servidor (ADR 0027). Remitentes separados (p. ej. `pedidos@` y `ofertas@`) para cuidar la reputación |
| Pagos | **Mercado Pago Checkout Pro** + aviso de pago (webhook) verificado contra su API | La tienda nunca ve tarjetas |
| Ingreso | Google (OAuth) y código por mail, sesiones propias en D1; empleados con sesión del local + PIN | Sin contraseñas que guardar |
| Panel interno | `/admin` detrás de **Cloudflare Access** además del login y el rol | Doble barrera, como el acceso remoto (ADR 0020) |
| Editor de marketing | **Puck** (MIT) con bloques propios | El diseño no se rompe; marketing arma carrusel, promos, secciones y banners con fechas |
| Anti-bots | **Turnstile** | Checkout, ingreso y formularios |

- Entornos: `demo` (https://demo.comercio-ejemplo.example, conectado al lab, Mercado Pago de prueba) y
  `produccion` (comercio-ejemplo.example, al salir). Cada uno con su D1, su R2 y sus secretos
  (`wrangler secret`, nunca en git).
- Node 22 en la máquina de desarrollo (Astro 7 lo pide; Node 20 se queda para lo demás).

## Consecuencias

- Todo es código propio en `web/tienda/` (fuera de `addons/`): se mantiene con pruebas propias
  (`npm test` y `make e2e-tienda`).
- Atado a Cloudflare (como el DNS, el túnel, R2 de los backups y la página actual). Los datos
  importantes no se pierden: la fuente es Odoo y D1 se exporta en los backups.
- Una cuenta externa más (Resend) con su clave: en Bitwarden y como secreto, nunca en git.

## Alternativas descartadas

- **Seguir con Astro 5 estático:** no alcanza para carrito, cuentas ni pagos.
- **Next.js (OpenNext/vinext):** más pesado y más JavaScript en el celular; nada que la tienda necesite.
- **Reservas solo con D1:** posible con UPDATE condicional, pero un carrito de varias líneas
  todo-o-nada es más claro y seguro en un Durable Object.
- **Cloudflare Email Sending:** sin claves, pero solo transaccional; las campañas igual necesitarían otro
  proveedor, y Resend ya está.
