# Probar los periféricos de un puesto (PC Windows)

Con el pendrive: copiar la carpeta con `PROBAR-PERIFERICOS.bat` y `probar-perifericos.ps1`
(`infra/windows/`) y hacer **doble clic en el .bat** en la PC del puesto. No pide administrador
ni claves: se puede dejar en el pendrive.

## Qué hace (paso a paso, pregunta antes de cambiar algo)

1. **Lista lo enchufado**: USB con marca, modelo y VID:PID, y avisa si la balanza no tiene driver.
2. **Balanza Systel**: la busca en los puertos COM (115200 y 9600 baudios, número 70, 1 y 2 a
   99) y muestra el peso en vivo 15 segundos. Solo lee. Antes, cerrar Chrome y Qendra (si la
   tienen abierta, el puerto está ocupado).
3. **Lector**: pide escanear 3 códigos y muestra qué leyó. Probar un envase curvo, uno chico y un QR.
4. **Impresora de tickets**: elegirla de la lista; queda **predeterminada** (y Windows ya no la
   cambia solo) e imprime una página de prueba.
5. **Acceso directo «Odoo Puesto»** en el escritorio: Chrome (o Edge) con `--kiosk-printing`,
   que imprime el ticket directo, sin el cuadro de impresión. Opcional: que se abra al prender.
6. **Informe** `perifericos-<PC>-<fecha>.txt` al lado del .bat (queda en el pendrive): traerlo
   para anotar los equipos en `docs/relevamiento/hardware.md`.

## Después, en Odoo

Cerrar todas las ventanas del navegador y abrir **Odoo Puesto**:

- Abrir el puesto. Si el script encontró la balanza con otro número que no es 1, cargarlo en el
  puesto (P-040) y autorizar el puerto la primera vez.
- Pesar algo, escanear un producto e **Imprimir pedido**: tiene que salir sin preguntar.

## Si algo falla

- **Balanza «sin driver»**: conectar la PC a internet unos minutos (Windows Update) o instalar
  el driver VCP de FTDI (<https://ftdichip.com/drivers/vcp-drivers/>).
- **Sigue apareciendo el cuadro de impresión**: había una ventana del navegador abierta de
  antes. Cerrar todas (también el ícono junto al reloj) y abrir «Odoo Puesto».
- **El ticket sale chico o cortado**: en las preferencias de la impresora, papel de 80 mm.
- **La impresora de la balanza** no sirve para Odoo (la balanza no imprime lo que manda la PC).
- Zebra de etiquetas: va aparte, con el IoT de Windows (`etiquetas-zebra.md`).
