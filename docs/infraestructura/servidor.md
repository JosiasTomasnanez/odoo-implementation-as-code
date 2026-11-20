# Servidor de producción

Estado: **equipo comprado** (26/10/2026, sobre el presupuesto del 13/10). Base: ADR 0007.
Instalación: ADR 0026 y `docs/runbooks/instalar-servidor.md` (probada en máquina virtual;
en el equipo real desde el 27/10). Backups y avisos: ADR 0027.

## Equipo elegido

| Pieza | Modelo | Notas |
|---|---|---|
| Procesador | AMD Ryzen 5 5600GE | 6 núcleos, 35 W: calienta poco; video integrado |
| Placa | MSI A520M-A PRO (AM4, DDR4) | TPM 2.0 de AMD (fTPM), Secure Boot, encendido al volver la luz; red Realtek 1 Gbps; un M.2 libre |
| Memoria | 16 GB DDR4 3200 (un módulo) | Quizás se suma otro igual (32 GB, doble canal) |
| Discos | 2 × SSD WD Green 1 TB SATA | RAID 1; gama económica: vigilar su estado (`smartmontools`) |
| Fuente | Gamemax 600 W 80 Plus Bronze | La pieza más probable de fallar: por eso la UPS |
| Gabinete | Magnum Tech 436B | - |
| UPS | Se compra aparte | 1000 VA o más con USB, que cubra también router y switch |

Sin memoria ECC ni garantía en sitio: lo compensan el RAID 1, la UPS, los backups probados y
la reinstalación reproducible.

Lo que sigue es la recomendación inicial (05/10), que sirvió para elegir.

## Supuestos

- Odoo 20 Enterprise + PostgreSQL 16 en Docker Compose (ADR 0004).
- Menos de 10 usuarios, de los cuales pocos están conectados a la vez. Apps previstas:
  POS (varios puestos), inventario, compras, facturación y contabilidad, y ecommerce
  más adelante.
- Regla de Odoo: 1 *worker* atiende unos 6 usuarios concurrentes; máximo
  `núcleos × 2 + 1` workers; entre 0,5 y 1 GB de RAM por worker.
  Hacen falta unos 4–5 workers + 1 de cron, con margen.

## Lo que hace que un servidor "no falle"

Odoo con menos de 10 usuarios no exige un equipo potente. Las caídas reales casi
nunca vienen de la CPU, sino de: **cortes de luz, discos que mueren, Internet,
actualizaciones mal hechas y errores humanos**. La inversión va primero ahí.

## Hardware recomendado

| Componente | Recomendado | Mínimo aceptable | Por qué |
|---|---|---|---|
| Tipo de equipo | Servidor torre de entrada con garantía de atención en sitio (p. ej. Dell PowerEdge T1x0, HPE ProLiant ML30, Lenovo ThinkSystem ST50) | PC de oficina de línea empresarial, nueva | Componentes pensados para funcionar 24/7, garantía y repuestos |
| CPU | 4–6 núcleos actuales con buen rendimiento por núcleo (Xeon E-2400, Core i5/i7 o Ryzen 5/7 recientes) | 4 núcleos | Cada pedido de Odoo usa un núcleo: importa la velocidad por núcleo |
| RAM | **32 GB, ECC** si el equipo lo soporta | 16 GB | Workers + PostgreSQL + Docker + margen para ecommerce, reportes y pruebas de restauración |
| Discos | **2 × SSD NVMe de 1 TB en RAID 1 (espejo)**, de línea empresarial o con buena durabilidad (TBW alto) | 2 × SSD SATA de 500 GB en RAID 1 | Si muere un disco, el sistema sigue funcionando; se cambia el disco sin perder nada |
| Red | 1 Gbps cableado (idealmente 2 puertos) | 1 Gbps | Nunca por Wi-Fi |
| **UPS** | Interactiva o en línea, **1500 VA**, con USB para apagado automático; que cubra también el router y el switch | 1000 VA | Cortes de luz: el riesgo número uno. Sin UPS se puede corromper la base |
| Backup local | Disco externo o NAS chico para la copia diaria | Disco externo USB | Restauración rápida sin depender de Internet |
| Backup externo | Almacenamiento en la nube, cifrado (P-013) | - | Por si se pierde el local (robo, incendio) |

## Entorno

- **Internet:** conexión principal por fibra y una **secundaria** (otro proveedor o 4G)
  para facturación electrónica, backups externos y acceso remoto. Sin Internet se
  sigue vendiendo en el local, pero no se emiten comprobantes electrónicos.
- **Lugar físico:** cerrado con llave, ventilado, lejos del piso, del agua y del calor;
  no a la vista del público (seguridad.md).
- **Sistema operativo:** Debian 13, mínimo y endurecido (seguridad.md, ADR 0026).
- **Cifrado de disco:** LUKS sobre el RAID, **desbloqueado solo por el TPM** (atado a Secure
  Boot): arranca solo después de un corte. Clave de recuperación en Bitwarden. Más adelante,
  llave de red del local (Tang) para que el equipo robado entero no arranque (ADR 0026).

## Plan ante la caída del servidor

Ningún equipo único es infalible. Lo que garantiza la continuidad es:

1. RAID 1 + UPS → evitan las caídas más comunes.
2. El equipo elegido **no tiene garantía en sitio**: las piezas son de PC común y se
   consiguen en cualquier casa de computación (el disco se cambia sin perder nada por el RAID).
3. Backups probados (ADR 0027) + este repositorio → si el servidor muere, cualquier PC
   razonable puede levantar Odoo y restaurar el último backup (`recuperacion.md`,
   `docs/runbooks/instalar-servidor.md`).
   Definir cuál es esa "PC de reemplazo" y ensayarlo antes de la puesta en marcha.

## Precios de referencia (Argentina, octubre 2026)

Relevados en tiendas y MercadoLibre el 05/10/2026; cambian seguido. Las configuraciones
base traen disco rígido mecánico: sumar 2 SSD y, si vienen con 16 GB, ampliar a 32 GB.

| Equipo | Configuración | Precio aprox. (ARS) |
|---|---|---|
| Lenovo ThinkSystem ST50 V3 | Xeon E-2414, 16 GB, 2 TB HDD | 2.365.000 – 2.550.000 |
| Lenovo ThinkSystem ST50 V3 | Xeon E-2414, 32 GB, 2 × 2 TB | ~3.070.000 |
| Dell PowerEdge T160 | Xeon 6315P, 16 GB, 2 TB HDD | 2.225.000 – 2.450.000 |
| Dell PowerEdge T160 | Xeon 6333P, 16 GB, 2 TB | 3.160.000 – 4.970.000 |
| HPE ProLiant ML30 Gen11 | Xeon E-2414, 16 GB, 1 TB | ~3.645.000 |
| UPS 1500 VA (TRV, Lyonn) | interactiva, USB | 260.000 – 320.000 |
| UPS APC Back-UPS Pro 1500 | interactiva, USB | ~965.000 |

Estimación (sin cotización cerrada): servidor con 32 GB y 2 SSD en espejo + UPS de
1500 VA, entre 3,5 y 4,5 millones de pesos. Documento para el cliente: «Comercio Ejemplo -
Servidor requisitos» (Drive del implementador).

## Pendiente

- Instalarlo en el equipo real y comprar la UPS (P-011).
- RPO/RTO aceptables para el negocio, que ajustan la frecuencia de backup (P-013).
- Ubicación física del servidor y estado de la red actual (red.md).
- Nombre del servidor y certificado: `odoo.comercio-ejemplo.example` con Let's Encrypt (ADR 0013,
  27/10).
