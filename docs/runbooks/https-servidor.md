# Runbook: HTTPS del servidor del local

Base: ADR 0013. El proxy Caddy (`infra/docker/caddy/`) pone HTTPS delante de Odoo.
Modo actual: **`dominio`**: `https://odoo.comercio-ejemplo.example`, certificado de Let's Encrypt
validado por DNS en Cloudflare (27/10). Nada queda publicado en Internet. Con el acceso
desde afuera (ADR 0020) el proxy suma `remoto.comercio-ejemplo.example` (`caddy/remoto.caddy`, mismo
token y certificado por DNS), al que solo llega el túnel: `acceso-remoto.md`.

La instalación está en `instalar-servidor.md`, pasos 7 y 8: `instalar-odoo.sh` pregunta el
dominio, guarda el token y registra el nombre. Acá: cómo funciona y qué hacer si algo falla.

## Cómo funciona

- **Certificado:** Caddy lo pide a Let's Encrypt probando que maneja el dominio. Para eso
  escribe un registro TXT en Cloudflare con el token de `/etc/odoo-comercio/proxy.env`
  (`CLOUDFLARE_API_TOKEN`, permiso «Zone → DNS → Edit» solo sobre `comercio-ejemplo.example`;
  Bitwarden «Servidor: Cloudflare DNS (certificados)»). Se renueva solo: Caddy necesita
  Internet unos minutos cada pocas semanas, y un corte de días no afecta.
- **Nombre:** en Cloudflare, `odoo.comercio-ejemplo.example` → IP privada del servidor, registro A
  con nube gris (solo DNS). Lo crea o actualiza `infra/servidor/registrar-dns.sh`. En el
  servidor mismo, `/etc/hosts` lo apunta a 127.0.0.1.
- **Las PCs no instalan nada.** Si alguna no encuentra el nombre (routers que bloquean
  respuestas con IP privada): DNS del router o archivo `hosts` (`instalar-servidor.md`, paso 8).
- **Si el token se filtra:** se revoca en Cloudflare (*My Profile → API Tokens*), se crea
  otro y se cambia en `proxy.env`.

## Verificar desde el servidor

```bash
H=odoo.comercio-ejemplo.example
curl -sI --resolve $H:80:127.0.0.1 http://$H/ | head -1               # 308
curl -s --resolve $H:443:127.0.0.1 https://$H/web/health               # {"status": "pass"}
echo | openssl s_client -connect 127.0.0.1:443 -servername $H 2>/dev/null \
  | openssl x509 -noout -issuer -enddate                               # Let's Encrypt
```

El chequeo de cada 15 minutos (`revisar-servidor.sh`) avisa si el certificado vence en menos
de 14 días, o sea, si Caddy no lo pudo renovar.

## Si algo falla

- **No obtiene el certificado:** `compose logs proxy`. Suele ser el token (revocado, sin
  permiso sobre la zona). Corregir `proxy.env` y `compose up -d --force-recreate proxy`.
- **Una PC no encuentra `odoo.comercio-ejemplo.example`:** `nslookup odoo.comercio-ejemplo.example` en la PC.
  Si no da la IP del servidor, es el router: paso 8 del runbook de instalación.
- **Cambió la IP del servidor:** `sudo bash infra/servidor/registrar-dns.sh odoo.comercio-ejemplo.example`.
- **El POS no recibe avisos / se desconecta:** revisar que `/websocket` llegue a 8072
  (`workers` > 0 y `gevent_port` en `odoo.conf`).
- Entrar siempre por el nombre, no por la IP (el certificado es del nombre).

## Sin dominio (CA propia de Caddy)

Si alguna vez hiciera falta (por ejemplo, perder el dominio): en `instalar-odoo.sh`, a la
pregunta del dominio, responder `-`. Queda `odoo.ejemplo.internal` con la CA propia de
Caddy y hay que:

1. En el servidor: `openssl x509 -in /etc/odoo-comercio/caddy-raiz.crt -noout -subject -fingerprint -sha1`
   → dice `Comercio Ejemplo - AAAA ECC Root`. Copiarlo a un pendrive como `ejemplo-raiz.crt`
   (nunca `root.key`).
2. Nombre → servidor en el DNS del router o en el `hosts` de cada PC.
3. En cada PC, consola como administrador:
   `certutil -addstore -f root "%USERPROFILE%\Desktop\ejemplo-raiz.crt"`; en Linux,
   `sudo cp ejemplo-raiz.crt /usr/local/share/ca-certificates/ && sudo update-ca-certificates`.
4. `url:` de `environments/onpremise.yaml` a `https://odoo.ejemplo.internal`.

`CADDY_DATA_DIR` guarda la clave de esa CA y va en los backups (ADR 0027): si se pierde,
hay que reinstalar la raíz en todas las PCs.
