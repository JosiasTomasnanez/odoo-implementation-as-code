# 0020. Acceso desde fuera del local con Cloudflare Access (túnel), con seguridad en capas

- Estado: aceptado (27/10), con los cambios de «Actualización 27/10»
- Fecha: 2026-10-22 (actualizado 2026-10-27)

## Contexto

Las cajas y los puestos están en el local, en la misma red que el servidor (ADR 0013). Fuera
del local hay **4 o 5 depósitos** (P-032) y es probable que el negocio quiera entrar a Odoo
**desde cualquier lado** (Daniel desde su casa, la administración desde su computadora).

El ADR 0013 dejó «nada publicado a Internet; el acceso remoto, por VPN». Con una VPN
(Tailscale) cada equipo necesita la app, activada por un técnico, y solo entran equipos
propios (así quedó anotado en P-032 el 22/10). Es lo más seguro, pero depende del técnico
para cada equipo nuevo y no sirve para entrar desde cualquier equipo.

## Decisión (propuesta del 22/10; lo que cambió, abajo)

Odoo se alcanza desde afuera por **Cloudflare Access** con un **túnel** (`cloudflared`):

- Un contenedor `cloudflared` en `compose.onprem.yml` abre una conexión **de salida** hacia
  Cloudflare. No se abre ningún puerto del router ni hace falta IP fija.
- En Cloudflare, la aplicación `odoo.<dominio>` (dominio de P-022, con el DNS en Cloudflare)
  solo deja pasar a los **mails autorizados**, que entran **con Google** (con verificación
  en dos pasos). Recién después aparece el login de Odoo.
- En el local, las cajas y los puestos siguen yendo directo al servidor por la red local
  (mismo nombre: adentro apunta al servidor, afuera al túnel).
- El acceso técnico al servidor (consola, SSH) sigue por **VPN (Tailscale)**, solo en el
  equipo del técnico y el servidor; no pasa por Cloudflare.

### Capas de seguridad (lo que compensa abrir la puerta)

En Cloudflare:
1. Solo mails autorizados, entrando con Google; verificación en dos pasos obligatoria en
   esas cuentas.
2. Solo desde Argentina.
3. Sesión de un día a una semana, no indefinida.
4. `/web/database/*` bloqueado desde afuera.
5. Cuenta de Cloudflare a nombre del negocio (Gmail del negocio, titular Daniel) con dos
   pasos; el técnico entra como miembro con su propia cuenta.

En Odoo:
6. Verificación en dos pasos para usuarios con permisos fuertes (titular, administración,
   técnico).
7. Administrador de bases apagado (`list_db = False`) y clave maestra fuerte en Bitwarden.
8. Permisos mínimos por rol (`docs/areas/roles-y-tareas.md`).

En el servidor:
9. Ningún puerto abierto hacia adentro.
10. Backups probados, actualizaciones y registros (Cloudflare suma quién entró, cuándo y
    desde dónde).

## Alternativas consideradas

- **Tailscale en equipos propios** (lo anotado en P-032 el 22/10): más seguro (cifrado de
  punta a punta, solo equipos del negocio), pero cada equipo lo activa un técnico y no sirve
  para entrar desde cualquier equipo. Queda para el acceso técnico.
- **Publicar Odoo directo a Internet** (puerto abierto, solo el login de Odoo): lo más
  simple, pero deja el servidor expuesto a cualquiera. Descartada.
- **Cloudflare Access + WARP** (app en cada equipo para exigir equipos propios): vuelve a
  necesitar instalar algo en cada equipo; solo si después se quiere restringir por equipo.

## Consecuencias

- Para el personal: navegador + su Google, desde cualquier lado; nada que instalar. Sumar o
  sacar a alguien es editar la lista de mails en Cloudflare, sin técnico.
- **Cloudflare ve el tráfico** (corta el cifrado en sus servidores y lo vuelve a cifrar
  hacia el túnel). Viaja cifrado por Internet; el riesgo es confiar en Cloudflare. Para un
  comercio se considera aceptable; los riesgos reales (claves, sesiones, permisos) se cubren
  con las capas de arriba.
- Controla **personas, no equipos**: quien tenga un mail autorizado entra desde cualquier
  equipo. Por eso la verificación en dos pasos y la sesión limitada.
- Depende de comprar el dominio (P-022) y de una cuenta de Cloudflare más (a nombre del
  negocio). Si se corta Internet en el local, desde afuera no se entra; adentro sigue todo.
- Reemplaza, en lo que hace al acceso desde afuera, el «nada publicado a Internet» del
  ADR 0013. Con el DNS en Cloudflare, Caddy puede sacar el certificado de Let's Encrypt por
  DNS-01 como ya preveía ese ADR.
- La autofacturación por QR del ticket (P-037) necesitaría el portal abierto para los
  clientes: con Access delante no entran, salvo una excepción solo para esas rutas.
  Se decide en P-037.
- Antes de aceptarlo: confirmar con Daniel quiénes entrarían desde afuera y desde dónde,
  y verificar el plan gratuito de Cloudflare Zero Trust (límite de usuarios).

## Actualización 27/10 (aceptado)

Lo que quedó implementado (`compose.acceso-remoto.yml`, `caddy/remoto.caddy`,
`infra/servidor/configurar-acceso-remoto.sh`; uso en `docs/runbooks/acceso-remoto.md`):

- **Nombre aparte: `remoto.comercio-ejemplo.example`.** No se usa el mismo nombre adentro y afuera:
  el registro público de `odoo.comercio-ejemplo.example` apunta a la IP privada del servidor (ADR 0013,
  27/10), así que no puede apuntar también al túnel. La LAN sigue con `odoo.comercio-ejemplo.example`
  sin cambios; desde afuera ese nombre no abre.
- **Túnel administrado desde Cloudflare** (`servidor-ejemplo`), contenedor `cloudflared` con
  versión fija y token en `/etc/odoo-comercio/tunel.env`. Va al proxy por HTTPS con el
  certificado de Let's Encrypt de `remoto.comercio-ejemplo.example` (sin `noTLSVerify`), y cloudflared
  también exige el permiso de Access de la aplicación (no alcanza con llegar al túnel).
- **Inicio con código por mail** (One-time PIN de Cloudflare) en vez de Google: no hay que
  configurar nada en Google y sirve con cualquier mail. Se puede sumar Google más adelante
  (Zero Trust → Integrations → Identity providers) y elegirlo en la aplicación.
- **Política:** los mails autorizados **y** desde Argentina; sesión de 7 días en cada navegador (27/10: con 24 h la PC de ferretería pedía el código todos los días; `--sesion` la cambia). La lista vive en
  `/etc/odoo-comercio/acceso-remoto-mails.txt` (fuera del repo: son datos del personal) y la
  decide **Daniel**. Access controla **personas**: no hay usuario compartido. La primera en usarlo
  es la PC de ferretería (mientras no llega el cableado del local): entra con un mail
  autorizado de quien la usa; después, los depósitos y Daniel desde su casa.
- **En el proxy, el nombre remoto** solo atiende a cloudflared (IP fija en una red propia) y
  devuelve 404 en `/web/database`, `/xmlrpc`, `/jsonrpc`, `/json/2` y `/doc` (gestor de bases y
  API: desde afuera solo se usa el navegador). `odoo-iac` usa JSON-2 desde el mismo servidor
  contra `odoo.comercio-ejemplo.example`, que no cambia. Odoo registra la IP real de quien entra
  (`Cf-Connecting-IP`, creída solo si viene de cloudflared).
- **Técnico por Tailscale**, para SSH y para Odoo: en su notebook, `hosts` con
  `<IP de Tailscale del servidor> odoo.comercio-ejemplo.example` (mismo certificado; Docker publica el
  443 en todas las interfaces, también `tailscale0`).
- Ya resuelto de la lista de arriba: el plan Free de Zero Trust alcanza (hasta 50 usuarios;
  los registros de quién entró se guardan 24 h).

Resuelto (27/10): si un administrador inicia sesión por `remoto.comercio-ejemplo.example`, Odoo cambia
`web.base.url` a ese nombre, y los PDF (que Odoo arma pidiéndose a sí mismo) pasarían por
Cloudflare y Access los cortaría (verificado en Odoo 20: `res_users.py` y
`ir_actions_report._get_report_url`). Por eso `report.url` = `http://localhost:8069` en
`config/base/07-direccion-reportes.yaml` (los PDF van por adentro del contenedor; probado en el
lab) y `instalar-odoo.sh` fija `web.base.url` = `https://odoo.comercio-ejemplo.example` con
`web.base.url.freeze`.

## Actualización 02/11: la PC de ferretería por Tailscale

Con el servidor instalado, la PC de ferretería (mientras no cablean el local) entra por
**Tailscale** en vez de `remoto.comercio-ejemplo.example`: sin código por mail cada 7 días y sin
depender de Cloudflare. Se suma con una clave de un solo uso y la etiqueta `tag:ferreteria`
(no con la cuenta de CasaEjemplo), y la política de Tailscale solo le deja llegar al 443 del
servidor. El acceso por Cloudflare sigue para el resto del personal. Pasos:
`docs/runbooks/acceso-remoto.md`.

