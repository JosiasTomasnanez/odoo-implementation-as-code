# 0031. Tienda online propia en Cloudflare, separada del servidor del local

- Estado: aceptado (implementador, 02/11; P-009). El diseño, el alcance y la sincronización siguen abiertos
- Fecha: 2026-11-02

## Contexto

El negocio quiere una tienda online moderna, rápida en celular y PC, con animaciones cuidadas y
editable por marketing (`docs/areas/ecommerce.md`). Odoo corre en el servidor del local
(ADR 0026), sin nada publicado a Internet salvo el acceso remoto por Cloudflare Tunnel + Access
(ADR 0020). `comercio-ejemplo.example` ya está en Cloudflare con la página «Próximamente» en Workers.

Las opciones eran: el eCommerce de Odoo (nativo, en el servidor), una tienda propia afuera o una
plataforma armada (Tiendanube, Shopify).

## Decisión

- **No se usa el eCommerce de Odoo.** Correría en el servidor del local: la tienda se caería con
  cada corte de luz o de Internet del local y habría que publicar el servidor a Internet.
- **La tienda es propia y se hospeda en Cloudflare**, como la página «Próximamente», separada del
  servidor. Sigue vendiendo aunque el local esté caído.
- **Odoo sigue siendo la fuente** de productos, precios, stock y pedidos. La tienda tiene su copia
  del catálogo y se sincroniza como se pensó en P-009 (27/10): Odoo → tienda solo lo que cambió;
  tienda → Odoo cada pedido por la API JSON-2 (ADR 0002), en cola si el local no responde, por el
  túnel de Cloudflare con una ruta y una credencial solo para eso.

## Consecuencias

- Más desarrollo y mantenimiento que lo nativo: la tienda, la sincronización y el editor para
  marketing son código propio (en `web/`, fuera de `addons/`).
- El stock en la tienda puede atrasarse entre sincronizaciones: hay que definir el margen y si se
  confirma contra Odoo al pagar (P-009).
- Pagos, login, datos de clientes (Ley 25.326) y facturación con CAE de las ventas online se
  resuelven aparte, cada uno con su decisión.
- La tecnología concreta (framework, base de datos de la tienda, editor de contenidos) se elige en
  otro ADR, con el plan de las bases.

## Alternativas descartadas

- **eCommerce de Odoo:** depende de la disponibilidad del servidor del local.
- **Plataforma armada (Tiendanube, Shopify):** mensualidad o comisión, una integración con Odoo
  igual de necesaria y menos control del diseño y las animaciones que pide el negocio.
