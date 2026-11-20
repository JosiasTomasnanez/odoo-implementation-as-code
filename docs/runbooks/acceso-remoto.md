# Entrar a Odoo desde fuera del local

ADR 0020. Instalación: `instalar-servidor.md`, paso 12.

| Quién | Por dónde |
|---|---|
| PC de ferretería (hasta cablear el local) | Tailscale con etiqueta, solo Odoo (abajo) |
| Personal (depósitos, Daniel en su casa) | `https://remoto.comercio-ejemplo.example` (Cloudflare Access + túnel) |
| PCs del local | `https://odoo.comercio-ejemplo.example` (red del local, sin cambios) |
| Técnico | Tailscale: SSH y Odoo (abajo) |

## Qué ve la persona

1. Abre `https://remoto.comercio-ejemplo.example` → pantalla de Cloudflare: escribe **su** mail.
2. Le llega un código (de `noreply@notify.cloudflare.com`; mirar en spam) → lo escribe.
3. Aparece el login de Odoo: su usuario y contraseña de siempre.

El código vale 10 minutos. La entrada dura **7 días** en ese navegador; después vuelve a pedir el código. Se cambia con
`--sesion` (p. ej. `--sesion 24h` o `--sesion 730h`, un mes) al correr el script de nuevo; para
cortar antes a alguien: *Zero Trust → Access → Applications → la aplicación → Revoke existing tokens*. Solo desde
Argentina. Si el mail no está autorizado, la pantalla dice lo mismo pero el código no llega.
Cada persona entra con su mail: no hay mail compartido.

## Sumar o sacar a alguien

La lista la decide Daniel.

```bash
ssh tecnico@servidor-ejemplo
sudo nano /etc/odoo-comercio/acceso-remoto-mails.txt     # un mail por línea
cd /opt/odoo-implementation
sudo bash infra/servidor/configurar-acceso-remoto.sh     # token: Bitwarden «Servidor: Cloudflare Access (configuración)»
```

Sin el servidor a mano: Cloudflare → *Zero Trust → Access controls → Policies* → «Personal autorizado
(remoto.comercio-ejemplo.example)» → editar los mails. Anotarlo después en el archivo (si no, la próxima
corrida del script lo vuelve atrás).

**Sacar a alguien ya** (se fue, perdió el celular): además de sacarlo de la lista, Zero Trust →
*Users* (buscar la persona) → **Revoke session**; y en Odoo, archivar el usuario o
cambiarle la contraseña.

## Si no abre

| Qué pasa | Qué hacer |
|---|---|
| No llega el código | Spam; pedir otro. ¿El mail está en la lista? |
| «Access denied» | Mail no autorizado o fuera de Argentina (VPN del celular, roaming) |
| Error 1033 / «tunnel error» de Cloudflare | El túnel está caído: `cd /opt/odoo-implementation && STACK=onprem bash -c 'source infra/scripts/lib.sh && compose ps cloudflared && compose logs --tail 50 cloudflared'`; reiniciar con `compose restart cloudflared` |
| No abre nada y en el local tampoco hay Internet | Se cortó Internet del local: desde afuera no se entra; adentro Odoo sigue andando |
| Error 502 | Odoo o el proxy caídos: `compose ps` (y el aviso de Discord) |

El aviso «Contenedores con problemas: cloudflared» llega a Discord como los demás.

**Servidor nuevo** (restaurado): `/etc/odoo-comercio` no va en los backups. Correr de nuevo
`configurar-acceso-remoto.sh`: vuelve a bajar el token del mismo túnel. Los mails, copiarlos de
la política en Cloudflare (arriba) al archivo.

## Técnico: Tailscale

SSH: `ssh tecnico@servidor-ejemplo`. Odoo, con el mismo certificado: en la notebook (con
Tailscale prendido), una línea en `/etc/hosts`:

```
100.x.y.z  odoo.comercio-ejemplo.example      # IP de Tailscale del servidor: tailscale ip -4 servidor-ejemplo
```

Sacarla al volver al local (o dejarla: por Tailscale también anda). Necesita
`PROXY_BIND_IP=0.0.0.0` en `onprem.env` (con la IP del local, el 443 no responde por Tailscale).

## PC de ferretería por Tailscale (temporal, 02/11)

Hasta que cableen el local, la PC de ferretería entra por Tailscale y no por
`remoto.comercio-ejemplo.example` (decidido el 02/11: sin código por mail cada 7 días). Entra con una
**etiqueta** (`tag:ferreteria`), no con la cuenta de CasaEjemplo, y solo llega al Odoo del
servidor (puerto 443), no al SSH ni a Grafana.

1. Desde la notebook del técnico, con un token de la API (panel de Tailscale → *Settings →
   Keys → Generate access token*, que vence solo; guardarlo en `~/tailscale.env` con permisos
   600 como `TAILSCALE_API_TOKEN=…`, y borrarlo después):

   ```bash
   set -a; source ~/tailscale.env; set +a
   python3 infra/servidor/tailscale_ferreteria.py --simular                      # qué cambiaría
   python3 infra/servidor/tailscale_ferreteria.py --clave ~/clave-ferreteria.txt  # lo hace
   ```

   Deja en la política la etiqueta `tag:ferreteria`, cambia la regla «todos con todos» a
   `autogroup:member` (así los equipos con etiqueta no quedan incluidos) y agrega
   `tag:ferreteria` → solo `tcp:443` del servidor. La anterior queda en
   `~/tailscale-politica-anterior.json`. Crea una clave de **un solo uso** con la etiqueta
   (vale 7 días) en `~/clave-ferreteria.txt`. Los equipos con etiqueta no vencen.
2. Sin el script, lo mismo a mano en *Access controls*:

   ```json
   "tagOwners": {"tag:ferreteria": ["autogroup:admin"]},
   "grants": [
     {"src": ["autogroup:member"], "dst": ["*"], "ip": ["*"]},
     {"src": ["tag:ferreteria"], "dst": ["100.x.y.z"], "ip": ["tcp:443"]}
   ]
   ```

   (`100.x.y.z` = `tailscale ip -4 servidor-ejemplo`) y la clave en *Settings → Keys →
   Generate auth key* (un solo uso, **Tags: tag:ferreteria**).
**Forma rápida (04/11):** `infra/windows/` tiene `INSTALAR-TAILSCALE.bat` + `instalar-tailscale-ferreteria.ps1`.
En el ps1 se completan la clave (`~/clave-ferreteria.txt`) y la IP del servidor; se copian a un
pendrive y en la PC se hace **doble clic en el .bat** (pide administrador): instala Tailscale en modo
desatendido, se une con `tag:ferreteria`, agrega la línea al `hosts`, comprueba 443 sí y 22 no, y abre
Odoo. Después, **borrar la carpeta del pendrive** (tiene la clave, de un solo uso). A mano:

3. En la PC: instalar Tailscale. En PowerShell **como administrador**:
   `tailscale up --auth-key=tskey-…` (la clave de `~/clave-ferreteria.txt`; es de un solo uso:
   después, borrar el archivo).
4. Bloc de notas **como administrador** → abrir `C:\Windows\System32\drivers\etc\hosts` →
   agregar al final `100.x.y.z  odoo.comercio-ejemplo.example` → guardar.
5. Abrir `https://odoo.comercio-ejemplo.example` (con candado) → entrar → dejar que el navegador
   **guarde la contraseña** (mientras haya una sola cuenta, P-005).
6. Comprobar que no llega a más: en PowerShell, `Test-NetConnection 100.x.y.z -Port 22` →
   `TcpTestSucceeded : False`.

Cuando haya usuarios propios: en el navegador, borrar la contraseña guardada (*Contraseñas* →
odoo.comercio-ejemplo.example → eliminar) y entrar con el usuario de esa PC, con solo lo que se hace
ahí. Al cablear el local: borrar la línea del `hosts` y quitar la PC del panel de Tailscale.

## Token de la API (una vez, Bitwarden)

Cloudflare → *My Profile → API Tokens → Create Token → Custom*, nombre «Servidor: Cloudflare
Access (configuración)»:

- Account → **Cloudflare Tunnel** → Edit
- Account → **Access: Apps and Policies** → Edit
- Account → **Access: Organizations, Identity Providers, and Groups** → Edit (crea el inicio con
  código por mail la primera vez y lee el nombre del equipo)
- Zone → **DNS** → Edit, solo `comercio-ejemplo.example`

No se guarda en el servidor: el script lo pide cada vez.

## Probar desde la notebook contra el lab

```bash
echo 'mi-mail@ejemplo.com' > ~/mails-prueba.txt
bash infra/servidor/configurar-acceso-remoto.sh --nombre prueba-remoto.comercio-ejemplo.example \
  --tunel prueba-ejemplo --origen http://odoo:8069 --mails ~/mails-prueba.txt --tunel-env ~/tunel-prueba.env
docker run --rm --network odoo-lab_default --env-file ~/tunel-prueba.env cloudflare/cloudflared:2026.9.3 tunnel run
```

El celular con datos móviles → `https://prueba-remoto.comercio-ejemplo.example`. Ojo: el lab no tiene
proxy ni `list_db = False` (detrás de Access igual), y si se entra como `admin` Odoo guarda
ese nombre en `web.base.url` del lab. Al terminar: Ctrl+C y el mismo comando
de configuración con `--borrar`; borrar `~/tunel-prueba.env`.
