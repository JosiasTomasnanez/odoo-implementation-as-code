# Instalar el servidor del local (paso a paso)

ADR 0026 (servidor), 0013 (HTTPS), 0020 (acceso remoto). Lo que hace cada script está
comentado en `infra/servidor/`.

## 0. Antes

- [ ] Pendrive con `debian-13.7.0-amd64-netinst.iso` (hecho).
- [ ] Servidor por cable al router, con monitor y teclado.
- [ ] Notebook en la misma red, con este repositorio y Tailscale (red `comercio-ejemplo.github`, hecho).
- [ ] Bitwarden: generar **4 claves** → «Servidor: BIOS», «Servidor: recuperación del disco»,
      «Servidor: usuario tecnico», «Servidor: GRUB».
- [ ] GitHub **CasaEjemplo**: verificación en dos pasos activa, invitación a
      `odoo-implementation` aceptada, `odoo/enterprise` visible.
- [ ] Clave de Gemini a mano (opcional).
- [ ] Token de Cloudflare «Servidor: Cloudflare DNS (certificados)» en Bitwarden (hecho).
- [ ] Para el paso 12: token «Servidor: Cloudflare Access (configuración)» y la lista de mails de Daniel.

## 1. BIOS

**Supr** al prender → **F7** (modo avanzado).

- [ ] *Settings → Advanced → Mu Management Setup → Restore after AC Mu Loss* → **Mu On**
- [ ] *Settings → Security → Trusted Computing* → *Security Device Support* **Enabled**,
      *AMD fTPM switch* **AMD CPU fTPM**
- [ ] *Settings → Advanced → Windows OS Configuration* → *BIOS UEFI/CSM Mode* **UEFI**
- [ ] Mismo menú → *Secure Boot* **Enabled**, modo **Standard**
- [ ] **F10**, volver a entrar
- [ ] *Settings → Security → Administrator Password* → «Servidor: BIOS»
- [ ] **F10**

## 2. Instalador de Debian

- [ ] **F11** → el pendrive con «UEFI» → **Install**

| Pantalla | Valor |
|---|---|
| Idioma / país / teclado | Español / Argentina / Latinoamericano |
| Red | automática |
| Nombre de la máquina | `servidor` |
| Dominio | `ejemplo.internal` |
| Contraseña de root | **vacía** (Enter dos veces) |
| Nombre completo / usuario | `Técnico` / `tecnico` |
| Contraseña del usuario | «Servidor: usuario tecnico» |
| Zona horaria | Córdoba |

## 3. Discos

Particionado: **Manual**.

- [ ] Cada disco (la línea del disco) → *Crear una tabla de particiones vacía* → **Sí**
- [ ] En cada disco, 3 particiones:

| N.º | Tamaño | Utilizar como |
|---|---|---|
| 1 | `1 GB` | Partición del sistema EFI |
| 2 | `1 GB` | Volumen físico para RAID |
| 3 | el resto | Volumen físico para RAID |

- [ ] *Configurar el RAID por software* → **Sí** → *Crear un dispositivo MD* → **RAID1** → 2 / 0 →
      **particiones 2** de los dos discos
- [ ] *Crear un dispositivo MD* → **RAID1** → 2 / 0 → **particiones 3** → *Terminar*
- [ ] *Configurar los volúmenes cifrados* → **Sí** → *Crear volúmenes cifrados* → **solo `md1`**
      (~998 GB) → *Se ha terminado…* → *Terminar*
- [ ] ¿Borrar datos? → **Cancelar**
- [ ] Frase de cifrado → «Servidor: recuperación del disco»
- [ ] *Configurar el Gestor de Volúmenes Lógicos (LVM)* → **Sí**:
  - [ ] *Crear grupo de volúmenes* `sistema` → `/dev/mapper/md1_crypt`
  - [ ] *Crear volumen lógico* `sistema` / `swap` / `8 GB`
  - [ ] *Crear volumen lógico* `sistema` / `raiz` / todo
  - [ ] *Terminar*
- [ ] Asignar:

| Línea | Utilizar como | Montaje |
|---|---|---|
| LV `raiz` | ext4 | `/` |
| LV `swap` | área de intercambio | - |
| RAID1 #0 (1 GB) | ext4 | `/boot` |
| Particiones 1 de los dos discos | Partición del sistema EFI | - |

- [ ] *Finalizar el particionado y escribir los cambios* → **Sí**

## 4. Fin del instalador

- [ ] Réplica: **Argentina** → `deb.debian.org`, proxy vacío
- [ ] Encuesta: **No**
- [ ] Programas: **solo** «Servidor SSH» y «Utilidades estándar del sistema»
- [ ] Reinicia (sacar el pendrive) → frase del disco (solo esta vez) → entrar como `tecnico`
- [ ] IP fija en el servidor (el router no se puede tocar): `ip -br a` (placa, p. ej. `enp3s0`) e
      `ip route` (`default via` = puerta de enlace) → elegir una IP alta libre (`ping -c 3 192.168.1.250`
      no responde) → `sudo nano /etc/network/interfaces`: `iface enp3s0 inet dhcp` pasa a

```
iface enp3s0 inet static
    address 192.168.1.250/24
    gateway 192.168.1.1
```

- [ ] `printf 'nameserver 1.1.1.1\nnameserver 8.8.8.8\n' | sudo tee /etc/resolv.conf` → `sudo reboot`
      → `ip -br a` muestra la IP fija y `ping -c 2 deb.debian.org` responde. Anotarla en
      `docs/infraestructura/red.md` y usarla en vez de `192.168.1.10` en todo el runbook

Desde acá, todo desde la notebook.

## 5. preparar-servidor.sh

```bash
# Si no hay llave: ssh-keygen -t ed25519
ssh-copy-id tecnico@192.168.1.10
cd /mnt/datos1/odoo-implementation
scp infra/servidor/preparar-servidor.sh infra/servidor/instalar-odoo.sh tecnico@192.168.1.10:
ssh tecnico@192.168.1.10
sudo bash preparar-servidor.sh --simular
sudo bash preparar-servidor.sh
```

- [ ] Contraseña de GRUB (dos veces) → «Servidor: GRUB» (usuario `admin`)
- [ ] Frase del disco (una vez, para atar el TPM)
- [ ] Tailscale → **sí** → abrir el link → *Sign in with GitHub* como **CasaEjemplo**
- [ ] Panel de Tailscale → *Machines → servidor-ejemplo → ⋯ → Disable key expiry*
- [ ] Si algo sale con ⚠: corregirlo y volver a correr el script

## 6. Pruebas del servidor

- [ ] `sudo reboot` → arranca solo, entra por SSH
- [ ] Menú de GRUB, `e` → pide usuario y contraseña → **Esc**
- [ ] BIOS: Secure Boot **Disabled** → pide la frase. Volver a **Enabled** → arranca solo
- [ ] Desenchufar y enchufar → se prende y arranca solo
- [ ] Desconectar un disco → arranca. Reconectar:
      `cat /proc/mdstat`, `sudo mdadm /dev/md0 --add /dev/sdX2`, `sudo mdadm /dev/md1 --add /dev/sdX3`
- [ ] Desde fuera del local (datos del celular como hotspot): `ssh tecnico@servidor-ejemplo`
- [ ] Odoo por Tailscale (después del paso 7): en la notebook, `/etc/hosts` con
      `<tailscale ip -4 servidor-ejemplo>  odoo.comercio-ejemplo.example` → abre con candado

Si algún día pide la frase: escribirla y después `sudo clevis luks regen -d /dev/md1 -s 1`.

## 7. instalar-odoo.sh

```bash
ssh tecnico@192.168.1.10
sudo bash instalar-odoo.sh
```

- [ ] Muestra una llave → GitHub como **CasaEjemplo** → *Settings → SSH and GPG keys →
      New SSH key* (`servidor-ejemplo`) → Enter
- [ ] Clave de Gemini (o Enter)
- [ ] Dominio → Enter (`comercio-ejemplo.example`) → token de Cloudflare
- [ ] ✓ `odoo.comercio-ejemplo.example → 192.168.1.10` y ✓ «Certificado válido»
- [ ] Muestra el plan de configuración (`make apply`) → **s**
- [ ] Contraseña maestra y la del `admin` de Odoo: aparecen al generarse → **guardar en
      Bitwarden** → Enter (no se vuelven a mostrar)

## 8. Probar desde las PCs

Con dominio no se instala nada en las PCs: el certificado es de Let's Encrypt.

- [ ] En una PC del local: Chrome/Edge → `https://odoo.comercio-ejemplo.example` → candado, sin advertencia
- [ ] Si no lo encuentra (algunos routers bloquean respuestas con IP privada): en el DNS del
      router `odoo.comercio-ejemplo.example → 192.168.1.10`, o en cada PC, en
      `C:\Windows\System32\drivers\etc\hosts`: `192.168.1.10  odoo.comercio-ejemplo.example`
- [ ] Si cambió la IP del servidor: `sudo bash /opt/odoo-implementation/infra/servidor/registrar-dns.sh odoo.comercio-ejemplo.example`

Sin dominio (CA propia de Caddy): `https-servidor.md`, «Sin dominio».

## 9. Odoo

- [ ] **Código de suscripción** (solo acá, nunca en el repo). En una base recién creada el cartel
      «expira en 1 mes» no trae el link «Registrar» hasta que Odoo habla con sus servidores (una
      vez por día; «My Subscription» del menú del usuario solo abre odoo.com). Se registra desde el
      servidor, igual que ese link (el código no se ve al pegarlo):

```bash
read -rsp "Código de suscripción: " COD; echo
sudo docker exec -i -e COD="$COD" odoo-prod-odoo-1 odoo shell -c /etc/odoo/odoo.conf -d produccion --no-http --log-level=warn <<'PY'
import os
icp = env["ir.config_parameter"].sudo()
icp.set_str("database.enterprise_code", os.environ["COD"].strip())
env.cr.commit()
env["publisher_warranty.contract"].update_notification(cron_mode=False)
env.cr.commit()
for k in ("expiration_date", "expiration_reason", "already_linked_email", "already_linked_subscription_url"):
    print(k, "=", icp.get_str("database." + k))
PY
unset COD
```

- [ ] Imprime `expiration_date` = fin del plan y `expiration_reason = renewal`; los `already_linked_…`
      vacíos (si traen algo, el código está atado a otra base: liberarlo con Odoo, no forzarlo).
      En *Ajustes → Acerca de*, el vencimiento es el del plan (28/10/2026: 30/10/2027)
- [ ] POS: *Conectar balanza Systel* ofrece el puerto COM

## 10. Backups y avisos

Antes (una vez):

- [ ] Discord: canal de avisos → ⚙ *Editar canal → Integraciones → Webhooks → Nuevo webhook*
      → *Copiar URL* → Bitwarden «Servidor: webhook Discord»
- [ ] Resend: dominio `comercio-ejemplo.example` verificado y clave «Servidor: Resend (avisos)» en Bitwarden
- [ ] Cloudflare → *R2* (pide tarjeta; la capa gratis alcanza al principio) → *Create bucket*
      `comercio-ejemplo-backups` → *Manage API tokens → Create* «Object Read & Write», **solo ese
      bucket** → Access Key ID, Secret Access Key y el Account ID → Bitwarden «Servidor: R2 backups»
- [ ] Pendrive enchufado al servidor (se borra)

```bash
ssh tecnico@servidor-ejemplo
cd /opt/odoo-implementation && git pull
sudo bash infra/servidor/configurar-respaldo-y-avisos.sh --simular
sudo bash infra/servidor/configurar-respaldo-y-avisos.sh
```

- [ ] Webhook de Discord, clave de Resend y a qué mail → llega «Prueba de avisos» a Discord y al mail
- [ ] Pendrive → escribir **BORRAR**
- [ ] Clave de las copias: aparece → **Bitwarden** «Servidor: backups (restic)» → Enter
- [ ] Datos de R2
- [ ] Primer backup → **S** → llega «Backup OK» a Discord
- [ ] `sudo systemctl start odoo-prueba-restauracion` → llega «Copias verificadas: … restauración»
- [ ] Sacar el pendrive → en ≤ 15 min «El pendrive de backups no está». Volver a enchufarlo
      → «Se arregló»

Uso diario, restaurar y servidor nuevo: `backup-restauracion.md`.

## 11. Monitoreo (Grafana)

ADR 0028. Va después del paso 10, porque usa `avisos.env`.

Antes (una vez):

- [ ] Bitwarden: el script genera la clave «Servidor: Grafana admin».
- [ ] Tailscale, panel → *DNS*: **MagicDNS** y **HTTPS Certificates** activados. Si no,
      `tailscale serve` muestra el link para activarlos.

```bash
ssh tecnico@servidor-ejemplo
cd /opt/odoo-implementation && git pull
sudo bash infra/servidor/configurar-monitoreo.sh --simular
sudo bash infra/servidor/configurar-monitoreo.sh
```

- [ ] Clave de Grafana: aparece → **Bitwarden** «Servidor: Grafana admin» → Enter
- [ ] La base se reinicia unos segundos la primera vez (`pg_stat_statements`): hacerlo fuera
      del horario del local
- [ ] Al final: `✓ Monitoreo verificado` y la dirección `https://servidor-ejemplo.<tailnet>.ts.net:8443`
- [ ] Desde la notebook (con Tailscale): abrir esa dirección → `admin` + la clave → *Dashboards →
      Comercio Ejemplo*: se ven «Servidor», «PostgreSQL» y «Negocio (Odoo)»
- [ ] Desde una PC del local **sin** Tailscale: `http://192.168.1.10:3000` **no** abre
- [ ] *Alertas → Puntos de contacto → avisos → Probar* → llega «⚠️ …» a Discord con el pie
      «… · Grafana» (y el mail, si hay SMTP)

Uso, umbrales y qué hacer con cada alerta: `monitoreo.md`.

## 12. Acceso desde afuera (Cloudflare Access)

ADR 0020. El personal entra por `remoto.comercio-ejemplo.example`; nada se abre en el router.

Antes (una vez):

- [ ] Cloudflare → *Zero Trust* → nombre del equipo (p. ej. `comercio-ejemplo`) → plan **Free**
- [ ] Token «Servidor: Cloudflare Access (configuración)» en Bitwarden, con los permisos de
      `acceso-remoto.md` («Token de la API»)
- [ ] Mails autorizados (los decide Daniel), uno por línea:
      `sudo nano /etc/odoo-comercio/acceso-remoto-mails.txt` (o el script los pide)

```bash
ssh tecnico@servidor-ejemplo
cd /opt/odoo-implementation && git pull
sudo bash infra/servidor/configurar-acceso-remoto.sh --simular
sudo bash infra/servidor/configurar-acceso-remoto.sh
```

- [ ] Token → al final: ✓ certificado, ✓ cloudflared conectado, ✓ Access pide el código
- [ ] Celular **con datos móviles** (sin Wi-Fi): `https://remoto.comercio-ejemplo.example` → mail →
      llega el código → login de Odoo → entrar
- [ ] Mismo celular: `https://remoto.comercio-ejemplo.example/web/database/manager` → **404**
- [ ] Mismo celular: `https://odoo.comercio-ejemplo.example` → **no** abre
- [ ] Un mail que no está en la lista → el código no llega

Uso diario, sumar o sacar personas y problemas: `acceso-remoto.md`.

## 13. Lo que sigue

- [ ] UPS por USB, apagado ordenado (`nut`), cuando llegue con el rack
- [ ] Tang (llave de red del local)

---

## Actualizar Odoo o los módulos propios

Primero el lab, después el servidor.

**En la PC:**

```bash
# misma fecha en infra/docker/lab.env (ODOO_IMAGE) y onprem.env.example (ODOO_BASE_IMAGE)
infra/scripts/fijar-enterprise.sh /mnt/datos1/odoo-enterprise-git odoo:20.0-AAAAMMDD
make lab-completo
make e2e-catalogo e2e-precios e2e-codigos-fabrica e2e-factura-proveedor e2e-pos e2e-factura e2e-ia
git commit … && git push
```

**En el servidor:**

```bash
cd /opt/odoo-implementation
sudo systemctl start odoo-backup        # copia antes de tocar nada (llega «Backup OK»)
git pull
sudo nano /etc/odoo-comercio/onprem.env          # ODOO_BASE_IMAGE, si cambió la fecha
sudo bash infra/servidor/instalar-odoo.sh
STACK=onprem bash -c 'source infra/scripts/lib.sh && compose stop odoo &&
  odoo_cli -c /etc/odoo/odoo.conf -d produccion -u all --stop-after-init &&
  compose up -d --wait odoo'
```

- [ ] **Siempre `instalar-odoo.sh` antes del `-u`:** los módulos propios van dentro de la imagen y
      ese script la rearma; sin él, `-u` actualiza con el código viejo (19/11). Al final pide
      confirmación para `make apply`: sin terminal no aplica nada (bien, si no se quería aplicar).
- [ ] Si Odoo queda detenido después del `-u` (pasó el 18 y el 19/11: el `compose up` de la misma
      línea no arrancó), levantarlo aparte: `STACK=onprem bash -c 'source infra/scripts/lib.sh && compose up -d --wait odoo'`.
- [ ] Comprobar que Odoo corre con los módulos nuevos: `sudo docker exec odoo-prod-odoo-1 ls /opt/comercio-addons`
  (04/11: antes estaban en `/mnt/extra-addons`, un volumen que Docker reusaba con los archivos viejos).
- [ ] Probar una venta y una compra. Si falla: restaurar el backup (`backup-restauracion.md`, «Restaurar producción», `--desde pendrive`).
