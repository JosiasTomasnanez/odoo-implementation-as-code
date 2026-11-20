# Decisiones técnicas (ADR)

Cada decisión técnica relevante se registra como un documento corto e inmutable:
contexto, decisión, alternativas y consecuencias. Si una decisión cambia, se
escribe un ADR nuevo que la reemplaza (y se marca el anterior como `reemplazado`).

Las decisiones **de negocio** abiertas no van acá sino en pendientes (documento interno, no publicado).

| # | Decisión | Estado |
|---|----------|--------|
| [0001](0001-repositorio-unico.md) | Un único repositorio para todo el proyecto | aceptado |
| [0002](0002-odoo-19-api-json2.md) | Odoo 19 en el laboratorio y API externa JSON-2 | reemplazado en la versión por 0006 (JSON-2 sigue vigente) |
| [0003](0003-configuracion-como-codigo.md) | Configuración como código con `odoo-iac` (YAML + API) | aceptado |
| [0004](0004-docker-compose.md) | Docker Compose para laboratorio y On-Premise | aceptado |
| [0005](0005-formato-de-backup.md) | Backups en el formato zip estándar de Odoo | aceptado |
| [0006](0006-odoo-20.md) | Odoo 20 como versión objetivo | aceptado |
| [0007](0007-produccion-on-premise.md) | Producción en servidor propio; Online solo para pruebas | aceptado (Online reemplazado por 0011) |
| [0009](0009-modulo-pedido-qr-puesto-caja.md) | Módulo propio: pedido del puesto con QR, cobrado en la caja | aceptado |
| [0008](0008-staging-y-despliegue.md) | Staging en el servidor y despliegue por pipeline | propuesto |
| [0010](0010-valores-centralizados.md) | Valores modificables centralizados en `config/valores.yaml` | aceptado |
| [0011](0011-sin-odoo-online.md) | Sin Odoo Online: pruebas en el lab y después en Enterprise local | aceptado |
| [0012](0012-balanza-systel-webserial.md) | Balanza Systel Cuora leída desde el navegador (WebSerial), sin IoT | aceptado (falta equipo real) |
| [0013](0013-https-en-el-local.md) | HTTPS en el local: Caddy, CA interna y Let's Encrypt DNS-01 con dominio | aceptado |
| [0014](0014-catalogo-similitud-y-revision.md) | Catálogo: motor de similitud propio y pantalla de revisión en Odoo | aceptado en parte (IA abierta) |
| [0015](0015-listas-de-proveedores-en-odoo.md) | Listas de proveedores dentro de Odoo, con actualización automática | aceptado |
| [0016](0016-precio-de-venta-por-margen.md) | Precio de venta sugerido por margen de la categoría, revisado antes de aplicarlo | aceptado |
| [0018](0018-verificacion-con-ia-gemini.md) | Verificación con IA (Gemini) de los posibles duplicados, a pedido y solo como sugerencia | aceptado |
| [0019](0019-puesto-cobra-en-registradora.md) | El puesto da el pedido por cobrado al imprimirlo («Cobrado en registradora»), mientras cobran las registradoras | aceptado (temporal) |
| [0020](0020-acceso-remoto-cloudflare-access.md) | Acceso desde fuera del local con Cloudflare Access (túnel), con seguridad en capas | aceptado (27/10) |
| [0017](0017-alcance-primera-etapa.md) | Primera etapa: solo alimento para animales, sin caja ni facturación en Odoo | aceptado (registro de la venta: ADR 0019, temporal; rubro reemplazado por ADR 0022) |
| [0021](0021-leer-facturas-de-proveedor.md) | Leer las facturas de proveedor nosotros (sin la digitalización de Odoo) y agregar sus productos al catálogo | aceptado |
| [0022](0022-primera-etapa-ferreteria.md) | Primera etapa: ferretería en lugar de alimento para animales | aceptado |
| [0023](0023-compras-sin-factura.md) | Compras sin factura en un diario aparte | aceptado |
| [0024](0024-ventas-con-y-sin-factura-de-odoo.md) | Ventas de la caja con y sin factura de Odoo, mientras siguen las registradoras | aceptado en el lab |
| [0025](0025-codigos-de-fabrica.md) | «Códigos de fábrica»: reemplazar rápido el código propio por el del envase | aceptado |
| [0026](0026-servidor-debian-cifrado-tpm.md) | Servidor: Debian 13, discos en espejo y cifrado que se desbloquea solo | aceptado |
| [0027](0027-backups-restic-y-avisos.md) | Backups con restic (pendrive y Cloudflare R2) y avisos por Discord y mail | aceptado |
| [0028](0028-monitoreo-grafana.md) | Monitoreo con Prometheus y Grafana: tableros y alertas con umbrales | aceptado en el lab |
| [0031](0031-tienda-online-separada-del-servidor.md) | Tienda online propia en Cloudflare, separada del servidor del local | aceptado |
| [0032](0032-tienda-tecnologia.md) | Tienda online: Astro en Workers, D1, Durable Objects, R2, Resend, Mercado Pago | aceptado |
| [0033](0033-tienda-sincronizacion-y-stock.md) | Tienda online: conector que sale del local y reservas de stock | aceptado |
| [0034](0034-ia-une-sola-lo-seguro.md) | La IA une sola lo que confirma con seguridad (nunca agrega productos) | aceptado |

Plantilla: [0000-plantilla.md](0000-plantilla.md).
