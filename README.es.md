# Odoo Implementation as Code

**Una implementación real y completa de Odoo 20 para un comercio con varias actividades, armada
para poder reconstruirse desde cero: configuración como código, módulos propios, tienda online,
servidor propio endurecido, backups, monitoreo y pruebas automáticas.**

[English version](README.md)

> **Sobre este repositorio.** Es una exportación anonimizada de un proyecto privado que está en
> producción. La genera un script que copia solo una lista de archivos permitidos, reemplaza el
> comercio, las personas, los proveedores, los dominios y los identificadores de infraestructura
> por otros ficticios, y después audita el resultado (términos prohibidos, identificadores de
> Cloudflare y Tailscale, hostnames, mails, CUIT, teléfonos y cualquier cosa con forma de clave o
> token, más [gitleaks](https://github.com/gitleaks/gitleaks)). No se incluyen el relevamiento del
> negocio, las charlas, las preguntas abiertas ni la bitácora: algunos enlaces de la documentación
> apuntan a archivos que no están. El historial empieza de cero.

---

## El problema

Un único local reúne varios negocios (ferretería, productos para animales, veterinaria y más) sin
un sistema central: decenas de listas de proveedores en todos los formatos posibles, registradoras
que no tocan el stock y sin tienda online.

El objetivo no era solo «tener Odoo andando», sino una implementación **reproducible, versionada,
probada y recuperable**, que el personal (no técnico) adopte de a poco:

> *Podemos reconstruir esta implementación de Odoo sin depender de recordar cada configuración
> que hicimos a mano.*

## Qué hay

| Área | Qué se construyó |
|---|---|
| **Configuración como código** | `odoo-iac`: herramienta chica y genérica que aplica el estado deseado de Odoo desde YAML por capas (`config/base`, `onpremise`, `ejemplos`) por la API JSON-2, con `plan` (simulación), `apply` y `verify` (vuelve a leer Odoo y comprueba). Idempotente. |
| **18 módulos propios** | Listas de proveedores dentro de Odoo (cualquier formato, columnas detectadas solas, motor de similitud propio, costo desde el precio de lista con descuentos en cadena, IVA y dólar del día, historial, aplicación en segundo plano). Precio de venta por margen de la categoría. Pedido impreso con QR en un puesto y cobrado en otra caja, con dos cajas. Balanza serie leída desde el navegador (WebSerial). Ticket fiscal argentino. Cierre Z de las registradoras (a mano o con foto). Facturas de proveedor leídas y unidas al catálogo. Conteo de stock con lector. Etiquetas ZPL directo a una Zebra. |
| **IA, acotada** | Gemini (clave propia) solo *sugiere*: si una fila del proveedor ya la tenemos, qué le pasa a una fila rota, categorías del PdV, leer una lista desde una foto. Solo se aplica sola lo que confirma con mucha seguridad, y nunca crea productos. Sin internet o si falla, el flujo sigue sin avisos. |
| **Tienda online** | Propia, en Cloudflare: Astro en Workers, D1, un Durable Object como dueño del stock (reservas todo o nada), R2, Resend, API de Orders de Mercado Pago. Un conector dentro del local **sale** a sincronizar con Odoo: el servidor nunca queda expuesto. Minorista y mayorista con el mismo Worker, administración con roles. |
| **Servidor propio** | Debian 13, RAID 1, LUKS que desbloquea el TPM, Caddy con Let's Encrypt DNS-01, acceso remoto por Cloudflare Tunnel + Access y Tailscale, acceso segmentado para las PC del local. |
| **Backups y recuperación** | restic a pendrive y Cloudflare R2, cada noche, con avisos y **pruebas de restauración**. El lab se puede rearmar desde el último backup de producción, neutralizado. |
| **Monitoreo** | Prometheus + Grafana provisionados desde el repo: tableros del servidor, PostgreSQL y el negocio, alertas con umbrales y un relay que deduplica y agrupa los avisos en Discord (mail solo para lo crítico). |
| **Pruebas** | Unitarias de los motores, de punta a punta contra un Odoo de laboratorio descartable para cada flujo (PdV, dos cajas, balanza, listas, facturación, tienda, cuentas, pedidos) y de la tienda. |
| **Decisiones** | 38 ADR con el *porqué* (y lo descartado), y runbooks para operar, instalar y recuperar todo. |

El diagrama de arquitectura y la estructura del repo están en el [README en inglés](README.md#architecture).

## Cómo se encaró

- **Primero lo estándar:** Odoo estándar → configuración → automatización → integración → módulo
  propio. Todo el código propio está inventariado con lo que toca de Odoo y cómo se prueba
  (`docs/codigo-propio.md`).
- **Primero el lab:** cada cambio pasa por un lab descartable y sus pruebas antes de producción, y
  en producción siempre con un backup antes.
- **Verificar, no confiar:** las automatizaciones vuelven a leer Odoo y comprueban el resultado.
- **Adopción gradual:** pantallas mínimas por rol, ocultar en vez de quitar, empezar por un negocio
  (la ferretería) y crecer.
- **Nada por debajo de la mesa:** los flujos fiscales siguen la normativa argentina; factura
  electrónica (CAE) probada en homologación.

## Licencias

- **Módulos (`addons/`)**: LGPL-3, salvo los cinco que dependen de módulos Enterprise
  (`comercio_cierre_z`, `comercio_conteo_catalogo`, `comercio_factura_proveedor`,
  `comercio_libro_iva`, `comercio_pos_ticket_ar`), que son **OPL-1**, la licencia que Odoo pide para
  módulos que dependen de Enterprise.
- **Todo lo demás**: MIT (`LICENSE`).
- No incluye código de Odoo Enterprise.

## Autor

Diseñado y construido por [Josias Tomas Ñañez](https://github.com/JosiasTomasnanez): relevamiento
con el negocio, arquitectura, desarrollo, infraestructura y operación, trabajando con un asistente
de programación con IA (Claude Code).
