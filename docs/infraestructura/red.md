# Red local

Estado: **relevamiento**. La solución debe ser proporcional al comercio.

## A relevar

- Equipamiento actual (router, switches, AP Wi-Fi) y si soportan VLAN.
- Dispositivos: cajas, impresoras, balanzas, lectores, cámaras, IoT.
- Proveedor de Internet, IP fija o no, redundancia.

## Propuesta a evaluar

| Segmento | Contiene | Puede acceder a |
|----------|----------|-----------------|
| Servidores | servidor Odoo | Internet (actualizaciones, backup externo) |
| Operación | cajas, impresoras, balanzas | servidor (443) |
| Empleados | Wi-Fi empleados | Internet; servidor solo si hace falta |
| Invitados | Wi-Fi clientes | solo Internet |
| Administración | acceso de gestión | todo, vía VPN |

Si el hardware no soporta VLAN, empezar con al menos la red de invitados aislada.

## Acceso de los puestos a Odoo (HTTPS)

Diseño en ADR 0013 y puesta en marcha en `docs/runbooks/instalar-servidor.md` (paso 8; dominio propio en `https-servidor.md`):

- **El implementador no tiene acceso al router** (28/10): sin reserva DHCP ni DNS del router.
  La IP fija se configura en el propio servidor (`/etc/network/interfaces`, una IP alta libre,
  `instalar-servidor.md` paso 4) y, si el router bloquea la respuesta de Cloudflare con IP
  privada, va una línea en el `hosts` de cada PC.
- El servidor tiene **IP fija** (configurada en el servidor) y los puestos entran por un nombre
  (`odoo.comercio-ejemplo.example`, ADR 0013), nunca por la IP. **27/10:** el nombre lo resuelve el DNS de
  Cloudflare (registro A a la IP privada); el router o el `hosts` solo si el router bloquea esa respuesta.
- El nombre se resuelve **en la LAN**, sin Internet: entrada en el DNS del router o línea
  en el `hosts` de cada PC. El DNS de la red no depende del servidor.
- Solo 80 (redirige) y 443 del proxy, desde la red de operación. Odoo y PostgreSQL no
  se publican. Nada se abre hacia Internet. **Desde afuera (27/10, ADR 0020):** el personal por
  `remoto.comercio-ejemplo.example` (túnel de Cloudflare, sale del servidor; nada abierto en el router) y
  el técnico por Tailscale (SSH y Odoo con `odoo.comercio-ejemplo.example` → IP de Tailscale en su `hosts`).
  `odoo.comercio-ejemplo.example` desde afuera no abre: apunta a la IP privada.
- A relevar: si el router permite entradas DNS locales.
