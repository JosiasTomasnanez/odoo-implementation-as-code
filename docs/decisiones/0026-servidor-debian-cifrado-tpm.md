# 0026. Servidor: Debian 13, discos en espejo y cifrado que se desbloquea solo

- Estado: aceptado (implementador, 26/10)
- Fecha: 2026-10-26

## Contexto

El servidor del local ya está comprado: Ryzen 5 5600GE, placa MSI A520M-A PRO (TPM 2.0 de AMD,
Secure Boot), 16 GB de RAM (quizás 32), 2 SSD SATA de 1 TB y fuente de 600 W. La UPS se compra
aparte. Detalle en `docs/infraestructura/servidor.md`.

`seguridad.md` pide cifrar el disco por robo del equipo. Con el cifrado clásico, después de un
corte de luz el servidor queda esperando la clave y **nadie puede entrar ni de forma remota**.
El implementador no acepta quedar incomunicado.

## Decisión

- **Sistema:** Debian 13 «trixie», sin escritorio, solo servidor SSH. Estable y con soporte largo.
  Odoo corre en Docker (ADR 0004), así que el sistema solo tiene que ser sólido.
- **Discos:** RAID 1 por software (`mdadm`) entre los dos SSD. Si muere uno, sigue andando.
  Partición EFI en cada disco, copiada sola después de cada actualización, para que también
  arranque desde el segundo disco.
- **Cifrado:** LUKS2 sobre el RAID. `/boot` va sin cifrar, sobre su propio RAID 1.
- **Desbloqueo automático con el TPM** (Clevis, `clevis-initramfs`), atado a **PCR 7** (estado de
  Secure Boot). Después de un corte, el servidor arranca solo. Si alguien arranca con otro
  sistema o apaga Secure Boot, el TPM no entrega la clave. Si se llevan los discos, no se
  pueden leer.
  - **Clave de recuperación:** la frase de LUKS puesta al instalar, guardada en Bitwarden. Se
    usa si falla el TPM o se cambia la placa.
  - Se ata a PCR 7 y no a los PCR del kernel, para que las actualizaciones del kernel no pidan
    la clave.
- **Contraseña en GRUB** (revisión de seguridad del 26/10): atado solo a PCR 7, el TPM entrega la
  clave aunque alguien edite el arranque (`init=/bin/sh`) y entraría con el disco abierto. Con
  `superusers` y las entradas `--unrestricted`, el arranque normal sigue solo y editarlo pide la
  contraseña (Bitwarden «Servidor: GRUB»).
- **Firmware:** contraseña de administrador del BIOS, Secure Boot activado, solo UEFI (sin CSM)
  y **encendido automático al volver la luz**.
- **Más adelante, «llave de red» del local (Tang):** un aparato chico siempre prendido en otro
  lugar del local (Raspberry Pi o mini PC). El desbloqueo pasa a exigir **TPM y Tang**
  (`sss` con `t: 2`), así que el servidor robado entero tampoco arranca fuera del local. Se suma
  sin reinstalar (`clevis luks bind` y después `unbind` del anterior). Gustó al implementador.
- **Acceso:** SSH solo con llave, sin root y sin contraseña. Desde afuera, solo por Tailscale
  (ADR 0020). Firewall con política de rechazo por defecto. Actualizaciones de seguridad
  automáticas.

## Alternativas descartadas

- **Sin cifrado:** el robo de los discos expone la base completa (clientes, costos, ventas).
- **Cifrado con clave a mano en cada arranque:** queda incomunicado después de cada corte.
- **Desbloqueo por SSH en el arranque (`dropbear-initramfs`):** obliga a alguien a conectarse
  después de cada corte, y desde afuera del local necesitaría la VPN dentro del arranque.
- **Cifrar solo los datos:** el sistema y los registros quedarían legibles, y el `.env` con
  claves también.

## Consecuencias

- El robo del servidor **entero** sigue arrancando hasta que esté la llave de red (Tang). Igual,
  sin la contraseña de Odoo ni la llave SSH no se entra. La protección es en capas.
- **Riesgo que queda (revisión de seguridad, 26/10):** `/boot` no está cifrado y PCR 7 no mide el
  kernel ni el initramfs. Alguien con el equipo, tiempo y conocimientos puede modificar el
  initramfs para que guarde la clave cuando el TPM la entrega. Atar también PCR 8/9 (kernel y
  línea de comandos) lo evitaría, pero cada actualización del kernel pediría la frase en el
  arranque: se descarta para no quedar incomunicado. **Lo resuelve la llave de red (Tang)**:
  fuera del local no hay desbloqueo. Por eso se recomienda sumarla.
- Cambiar la placa, resetear el BIOS o borrar las llaves de Secure Boot pide la clave de
  recuperación una vez. Después hay que volver a atar el TPM (`clevis luks regen`).
- Las tareas de la instalación están en `docs/runbooks/instalar-servidor.md`; lo posterior a
  instalar Debian lo hace `infra/servidor/preparar-servidor.sh`.
- **Probado el 26/10 en máquina virtual** (QEMU con Secure Boot de OVMF y TPM simulado, mismo
  esquema de discos): el script en simulación no cambia nada, la segunda corrida saltea lo hecho;
  arranca solo, también después de regenerar el initramfs; sin Secure Boot pide la frase; con
  cualquiera de los dos discos solo arranca; con la contraseña de GRUB arranca solo y editar el
  menú pide usuario. Esa prueba encontró que la EFI del primer disco tiene
  que ir con `nofail` en `/etc/fstab` (si no, sin ese disco entra en modo de emergencia): lo hace
  el script. Falta repetirlo en el equipo real.
