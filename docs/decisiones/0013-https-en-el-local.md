# 0013. HTTPS en el local: Caddy como proxy, CA interna ya y Let's Encrypt (DNS-01) con dominio propio

- Estado: aceptado (08/10/2026: CA interna ahora; dominio con Let's Encrypt antes de la puesta en marcha). **27/10: dominio `comercio-ejemplo.example` (Cloudflare); el servidor se instala directo en modo dominio** (ver al final)
- Fecha: 2026-10-08

## Contexto

Producción corre en un servidor dentro del local (ADR 0007). Las 9 PCs de los puestos y
las 2 cajas (Windows, Chrome/Edge) entran por la LAN, y **el POS tiene que seguir
andando sin Internet**, que se corta a veces. Hace falta HTTPS **válido, sin
advertencias**:

- La balanza Systel se lee con **WebSerial** (ADR 0012), que el navegador solo habilita
  en un *contexto seguro* (HTTPS válido o `localhost`). Lo mismo cámara, PWA del POS.
- Odoo manda usuario y contraseña en claro si no hay HTTPS: su documentación dice que un
  despliegue seguro **debe** usar HTTPS, con un proxy que termine TLS, `proxy_mode` y
  `/websocket` dirigido al puerto gevent (8072) cuando hay *workers*
  ([Odoo 20, deploy: HTTPS y LiveChat](https://www.odoo.com/documentation/20.0/administration/on_premise/deploy.html#https)).
- Hoy no hay dominio propio (P-022). El servidor no debería exponerse a Internet.

Dos hechos que valen para cualquier opción:

1. **Resolver el nombre sin Internet.** Los puestos tienen que encontrar el nombre del
   servidor aunque no haya Internet: entrada en el DNS del router (si lo permite) o una
   línea en el archivo `hosts` de cada PC. No conviene que el DNS de toda la red dependa
   del servidor (si cae, se cae Internet para todos).
2. **IP fija del servidor** (reserva DHCP en el router).

## Decisión

- **Proxy: Caddy** (imagen oficial `caddy:2.11.7` compilada con el plugin DNS), en
  `compose.onprem.yml`, con su configuración versionada en `infra/docker/caddy/Caddyfile`.
  Publica 80 (redirige a 443) y 443; Odoo sigue solo en `127.0.0.1`.
- **Certificado en dos etapas, elegidas con una variable (`CADDY_TLS_MODO`):**
  - **Ahora: `interna`.** Caddy hace de autoridad certificante propia (`tls internal`):
    raíz de 10 años, intermedia de 7 días y certificado del sitio de 12 horas, que Caddy
    renueva solo y **sin Internet**
    ([Caddy, tls internal](https://caddyserver.com/docs/caddyfile/directives/tls)). La
    raíz se instala **una vez** en cada PC (`certutil -addstore root`). Nombre:
    `odoo.ejemplo.internal` (`.internal` está reservado por ICANN para redes privadas
    desde 2024 y nunca va a existir en Internet; no usar `.local`, que es mDNS).
  - **Cuando haya dominio: `dominio`.** Certificado de **Let's Encrypt validado por
    DNS-01** para `odoo.<dominio>`: Caddy crea un registro TXT por la API del DNS, sin
    abrir puertos ni exponer el servidor
    ([Caddy, Automatic HTTPS](https://caddyserver.com/docs/automatic-https)). El nombre
    apunta a la IP LAN con DNS local o `hosts`. Ninguna PC necesita instalar nada.
- Se recomienda pasar a `dominio` cuando el negocio compre el dominio; mientras tanto (y
  como respaldo si falla el DNS externo) `interna` funciona sola.

## Alternativas consideradas

### a) Dominio real + Let's Encrypt DNS-01 + DNS local

- **A favor:** confianza en cualquier dispositivo (también celulares de prueba o
  tablets) sin instalar nada; la misma URL sirve con la VPN y si algún día se publica el
  portal (autofacturación por QR, P-037) o el ecommerce.
- **En contra:** depende del dominio (no lo hay) y de un DNS con API soportado por un
  plugin de Caddy (`github.com/caddy-dns`: Cloudflare, Route 53, deSEC, Porkbun,
  DigitalOcean, OVH, RFC 2136, entre otros; **no hay plugin para el DNS de NIC.ar**:
  con un `.com.ar` hay que delegar la zona a uno de esos DNS). El servidor guarda un
  token que puede editar la zona: limitarlo a esa zona y a registros DNS. Caddy estándar
  no trae los plugins: hay que compilarlo (lo hace `caddy/Dockerfile`).
- **Renovación e Internet:** hoy los certificados duran 90 días; Let's Encrypt los baja a
  64 días (10/02/2027) y 45 días (16/02/2028)
  ([Let's Encrypt, «Decreasing Certificate Lifetimes to 45 Days»](https://letsencrypt.org/2025/12/02/from-90-to-45/)).
  Caddy renueva solo, con semanas de margen (recomendado: a 2/3 de la vida útil): un
  corte de Internet de horas o días no afecta; uno de más de ~2 semanas (con 45 días)
  sí. El nombre queda publicado en los registros públicos de Certificate Transparency
  (solo el nombre, no la IP ni el acceso).
- **Costo:** el dominio (anual, verificar tarifa vigente del registrador); el DNS con API
  puede ser gratuito (p. ej. Cloudflare plan Free); Let's Encrypt es gratis.

### b) CA interna propia con la raíz en las ~11 PCs

- **A favor:** no depende de dominio ni de Internet para nada; costo cero; renovación
  automática y local con Caddy. Se puede usar hoy.
- **En contra:** hay que instalar la raíz en cada PC (11, una vez cada 10 años) y en todo
  dispositivo nuevo (Chrome y Edge usan el almacén de Windows; Firefox puede necesitar
  configuración aparte, y los puestos no lo usan). La **clave privada de la raíz** queda en el servidor: quien la robe puede
  suplantar cualquier sitio ante esas PCs, así que el directorio de datos de Caddy se
  protege y se respalda como un secreto. Si se pierde, hay que reinstalar una raíz nueva
  en todas las PCs. Python/odoo-iac no usa el almacén de Windows ni de Linux por sí
  solo: indicarle la raíz (`SSL_CERT_FILE`).
- **Variantes descartadas dentro de b):** `mkcert` (pensado para desarrollo, certificados
  de 2 años renovados a mano), `step-ca` (otro servicio más que mantener, sin ventaja a
  esta escala) u `openssl` a mano (renovación manual y fácil de olvidar). Caddy ya trae
  la CA y la renueva sola.
- **Distribución por GPO:** requiere dominio de Active Directory, que el local no tiene;
  y Microsoft documenta problemas con raíces distribuidas por GPO
  ([Microsoft Learn](https://learn.microsoft.com/troubleshoot/windows-server/certificates-and-public-key-infrastructure-pki/valid-root-ca-certificates-untrusted)).
  Con 11 PCs alcanza `certutil` a mano.

### c) Otras

- **HTTP y marcar el origen como seguro en Chrome/Edge** (política
  `OverrideSecurityRestrictionsOnInsecureOrigin`): habilita WebSerial, pero las
  contraseñas viajan en claro por la LAN, contra la recomendación de Odoo. Descartada.
- **Certificado autofirmado aceptando la advertencia:** el navegador no lo considera
  contexto seguro; WebSerial no anda. Descartada.
- **Túnel/servicio externo (Cloudflare Tunnel, Tailscale Funnel):** depende de Internet
  para que el POS funcione. Descartada para la LAN.

### Proxy: Caddy frente a nginx y Traefik

- **Caddy:** HTTPS automático (CA interna o ACME), renovación sola, websockets y
  cabeceras `X-Forwarded-*` sin configurar: el `Caddyfile` entero tiene ~40 líneas.
- **nginx:** es el ejemplo de la documentación de Odoo, pero no gestiona certificados:
  habría que sumar certbot (o acme.sh) con su plugin DNS, un cron de renovación y la
  recarga de nginx, o una CA a mano. Más piezas que mantener.
- **Traefik:** también automatiza ACME, pero está pensado para descubrir contenedores por
  etiquetas; para un único sitio agrega complejidad sin beneficio y no trae una CA
  interna equivalente.

## Consecuencias

- Probado en el lab (08/10/2026) con modo `interna`: certificado válido para
  `odoo.ejemplo.internal` verificado con la raíz; HTTP → HTTPS (308); Odoo responde por
  el proxy; cookie `session_id` con `Secure; SameSite=Lax`; HSTS; y con *workers*,
  `/websocket` llega al puerto gevent (101), mientras que directo a 8069 Odoo responde
  «Couldn't bind the websocket. Is the connection opened on the evented port (8072)?».
  El modo `dominio` solo se validó en sintaxis: falta el dominio para probarlo.
- Falta probar en una PC Windows real: instalar la raíz, entrar desde Chrome/Edge sin
  advertencias y conectar la balanza (WebSerial).
- El directorio de datos de Caddy (`CADDY_DATA_DIR`) entra en los backups (en modo
  `interna` contiene la clave de la CA).
- HSTS de un año: si el certificado deja de ser válido, los navegadores no dejan
  saltear el error. Es lo buscado, pero obliga a mantener el proxy sano.
- Pendiente del negocio: comprar el dominio y elegir dónde se aloja su DNS (P-022);
  definir nombre final; ver si el router permite entradas DNS locales.
- Acceso remoto administrativo (también P-012): se recomienda VPN (WireGuard o similar)
  hacia el servidor, sin publicar Odoo ni SSH a Internet. Se decide aparte.

## Actualización 27/10: dominio `comercio-ejemplo.example`

- Dominio comprado en Cloudflare (a nombre de Daniel, P-022). El servidor se instala **directo
  en modo `dominio`**: `https://odoo.comercio-ejemplo.example` con certificado de Let's Encrypt
  (DNS-01, token de Cloudflare con «Zone → DNS → Edit» solo sobre la zona, en
  `/etc/odoo-comercio/proxy.env`). La CA interna queda como alternativa sin dominio.
- **Nombre en la LAN:** registro A en el DNS público de Cloudflare `odoo.comercio-ejemplo.example` →
  IP privada del servidor, nube gris (`infra/servidor/registrar-dns.sh`, lo corre
  `instalar-odoo.sh`). Se elige sobre el DNS del router o el `hosts` de cada PC porque no hay
  que tocar nada en el local; se acepta que la IP privada sea visible (no da acceso a nada).
  Si un router bloquea respuestas con IP privada (protección contra *DNS rebinding*), se usa
  el DNS del router o el `hosts`.
- **Consecuencias:** las PCs no instalan ninguna raíz (desaparece el `certutil` en cada una) y
  la CA de Caddy deja de ser crítica para los backups. Caddy necesita Internet unos minutos
  para renovar (cada ~60 días); el chequeo del servidor avisa si el certificado vence en
  menos de 14 días (ADR 0027).

