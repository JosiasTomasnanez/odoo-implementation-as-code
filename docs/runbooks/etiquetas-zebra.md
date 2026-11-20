# Etiquetas directo a la Zebra (IoT de Windows)

Para imprimir las etiquetas de productos en la Zebra ZD420 **sin descargar archivos**: se
elige «Imprimir etiquetas» y la etiqueta sale. Decisión: ADR 0030. Pendiente: P-062 (medida
del rollo, en qué PC va). Probado en el local el 18/11 (notebook de administración): IoT vinculada e impresión directa desde Odoo.

## Qué hace falta

- Una **PC con Windows** (10 u 11) prendida cuando se imprime, con la Zebra por USB.
- Que Windows la vea como impresora con **«ZPL» en el nombre**. No hace falta el driver de Zebra:
  el IoT de Windows le manda el ZPL en crudo (RAW) y la reconoce como impresora de etiquetas por el
  nombre. Probado el 18/11 en la notebook de administración (PowerShell como administrador):

  ```powershell
  Add-PrinterDriver -Name 'Generic / Text Only'
  Add-Printer -Name 'Zebra ZD420 ZPL' -DriverName 'Generic / Text Only' -PortName 'USB001'
  ```

  (`USB001` es el puerto que crea Windows al enchufar la Zebra: `Get-PrinterPort`.)
- Odoo con los módulos `iot` y `comercio_etiquetas` (ya están en `config/onpremise/00-modulos.yaml`).

## 1. Los rollos (una vez por tipo de rollo)

Al imprimir se elige el **Rollo** y la etiqueta se acomoda a su medida. Cada usuario vuelve a ver
el último que usó. Las medidas cargadas son **provisorias** (18/11): Chico 40 × 25 y Grande 57 × 32.

Medir **una** etiqueta de cada tipo de rollo: el ancho de costado a costado y el alto de corte a
corte, sin el espacio entre etiquetas, en mm. Cargarlas en `config/valores.yaml`:

```yaml
etiquetas:
  rollos:
    chico:
      nombre: Chico
      ancho_mm: 40
      alto_mm: 25
```

y aplicar (`make plan|apply ENV=onpremise`).

**Un rollo que no está en la lista:** al imprimir, en el campo **Rollo** escribir el nombre →
**Crear y editar…** → ancho y alto en mm → Guardar. Lo puede hacer la cuenta Gerencia (no Puestos
ni Conteo). Si ese rollo se va a usar siempre, pasarlo también a `config/valores.yaml` y
`config/onpremise/56-medida-etiquetas.yaml`, así queda en la configuración. El primero de la lista es el predeterminado.
Después de cambiar de rollo en la Zebra, calibrarla: con la impresora prendida, mantener
apretado FEED hasta que la luz parpadee dos veces y soltar.

## 2. Instalar la impresora y la IoT en la PC de Windows (script)

`infra/windows/INSTALAR-IOT-ZEBRA.bat` (doble clic, como administrador) o, por SSH,
`powershell -ExecutionPolicy Bypass -File instalar-iot-zebra.ps1 [-Token '…']`. Idempotente:

1. Crea la impresora «Zebra ZD420 ZPL» (driver genérico, en crudo) en el puerto USB de la Zebra.
2. Instala la IoT de Odoo (servicio `odoo-iot`) con la **versión fijada en el script**
   (`odoo_iot_setup_20.0.20261118.exe`): verifica SHA256 y firma de Odoo S.A. antes de instalar.
   El instalador se toma de `infra/windows/descargas/` (copia guardada, fuera de git) o se baja
   de `nightly.odoo.com/20.0/nightly/iot/` (ahí los fechados duran unos dos meses).
   Usar el de **20.0** (`odoo_iot_setup_20.0…`), no el «Download Virtual IoT Box» del menú de
   Odoo, que apunta al de 19.0.
3. Vincular: en Odoo (administrador) **IoT → Conectar** → copiar el token y pegarlo en
   `http://localhost:8069` de esa PC (o pasarlo al script con `-Token`).
4. Verifica que la IoT responda y vea la Zebra.

## 3. Vincular la etiqueta a la Zebra

En Odoo 20 no se hace desde la ficha del dispositivo: **IoT → Configuración → Gestionar
impresoras → Nuevo** → Nombre `Zebra etiquetas`, Tipo **IoT**, Dispositivo IoT **Zebra ZD420
ZPL**, Reportes vinculados **Etiqueta del producto (ZPL)** → Guardar. Desde ahí, las etiquetas
salen directo.

**Si se eligió mal la impresora** y Odoo no vuelve a preguntar: IoT → Configuración →
Restablecer impresoras vinculadas (lo guarda el navegador de cada PC).

## 4. Imprimir

Productos → marcar los productos → **Imprimir etiquetas** → Formato **Etiquetas ZPL**,
plantilla **Comercio Ejemplo (nombre en 2 líneas)** → **Rollo** (el que está puesto en la Zebra) →
cantidad → **Confirmar**. Odoo recuerda el formato y el rollo elegidos por cada usuario.

## Si algo falla

- **El papel avanza pero sale en blanco:** la ZD420 centra el rollo en el cabezal (10 cm); si la
  etiqueta no dice su ancho (`^PW`), imprime a la izquierda, fuera del papel. Revisar que el
  **Rollo** elegido tenga la medida real (el rollo de ferretería mide unos 38 × 20 mm, a confirmar).
- **Luz roja (rombo) y naranja (‖):** papel corrido o tapa abierta. Acomodar el papel entre las
  guías, cerrar la tapa hasta el clic y apretar ‖.

- **No aparece la Zebra en IoT:** ver que Windows la tenga instalada con el driver ZDesigner y
  reiniciar el servicio de la IoT (o la PC).
- **Sale en blanco o cortada:** revisar que el **Rollo** elegido sea el que está puesto, calibrar
  (FEED dos parpadeos) y revisar la medida del paso 1.
- **El lector no lee el código:** probar con un lector 2D (P-006); el MLLC401S solo lee pegado.
- **Reinstalar la PC:** repetir el paso 2; la vinculación del paso 3 queda en Odoo.
