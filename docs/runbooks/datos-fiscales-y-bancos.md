# Cargar los datos fiscales y los bancos (producción)

Qué hay que cargar para que Odoo facture de verdad y lleve los bancos, quién lo hace y dónde.
Para verlo funcionar antes, en el lab: `demo-facturacion.md`.

**Nada de esto va al repo**: CUIT real, certificado, clave privada y números de cuenta se cargan
a mano en la base `produccion` y se guardan en Bitwarden. Al repo va solo la estructura (diarios
y medios de pago, en `config/`).

## 1. Qué pedirle a la administración

| Dato | Para qué |
|------|----------|
| Razón social, CUIT, domicilio fiscal | Encabezado de la factura |
| Condición frente al IVA (Responsable Inscripto) | Letra A o B |
| Ingresos Brutos: número y tipo (local o Convenio Multilateral) | Encabezado de la factura |
| Inicio de actividades y actividad principal (constancia de inscripción de ARCA) | Encabezado de la factura y reporte de IVA Simple |
| Quién tiene la **clave fiscal nivel 3** del CUIT | Trámites en ARCA (abajo) |
| Bancos: banco, tipo de cuenta, número y CBU de cada cuenta | Diarios de banco |
| Una **factura A de 3C** y un **ticket de la registradora** | Modelo para los comprobantes de Odoo |

## 2. En Odoo: los datos de la empresa (antes que ARCA)

Va primero: sin CUIT y ciudad, Odoo no deja generar la solicitud del certificado (paso 3).

*Ajustes → Ajustes generales* → sección **Empresas** → **Actualizar información** (o *Ajustes →
Usuarios y empresas → Empresas* → Comercio Ejemplo). En la ficha de la empresa:

- **Dirección**: calle y número, **ciudad** (obligatoria para el certificado), provincia, código
  postal y país **Argentina**. Es el domicilio fiscal que sale en la factura.
- **Tipo de identificación**: CUIT, y el número (sin guiones).
- **Responsabilidad de ARCA**: IVA Responsable Inscripto.
- **Ingresos brutos**: el tipo (Local o Convenio Multilateral) y el número.
- **Inicio de las actividades**: la fecha de la constancia de inscripción.
- **Nombre**: ojo, en la factura sale el nombre de la empresa. Si la **razón social** no es
  «Comercio Ejemplo», no cambiarlo acá (la configuración lo vuelve a poner): cambiar `empresa.nombre`
  en `config/valores.yaml` y aplicar, o decidir cómo mostrar razón social y nombre de fantasía.

Guardar. Después, *Ajustes → **Contabilidad*** → sección **Localización para Argentina**:

- **Actividad ARCA → Actividad principal**: la de la constancia (la usa el reporte de IVA Simple).

Con esto el encabezado de la factura A4 sale completo. El del ticket de la caja todavía no: hay que
agregarlo al módulo `comercio_pos_ticket_ar` (pendiente, P-029).

## 3. En ARCA y en Odoo: punto de venta y certificado (una sola vez)

Lo hace quien tenga la **clave fiscal nivel 3**, con el implementador al lado. La clave fiscal se
usa solo para entrar a la página de ARCA; en Odoo no se tipea ninguna clave.

1. **Punto de venta nuevo (ARCA).** Servicio *Administración de puntos de venta y domicilios* →
   alta de un punto de venta con sistema **«RECE para aplicativo y web services»**. Anotar el
   número. (No usar el 8 ni el 13: son de las registradoras. El 12 es el de 3C: no compartirlo
   mientras 3C siga facturando, porque los dos programas se pisarían la numeración.)
2. **Solicitud del certificado (Odoo).** *Ajustes → Contabilidad* → **Localización para
   Argentina** → **Web Services de ARCA**: elegir **Producción** y tocar **Generar solicitud**.
   Odoo crea solo la **clave privada** (queda guardada en Odoo; no hay que copiarla) y descarga un
   archivo de solicitud (CSR).
3. **Certificado (ARCA).** Servicio *Administración de Certificados Digitales* → agregar un alias
   (p. ej. `odoo-ejemplo`) → subir la solicitud → descargar el certificado (`.crt`).
4. **Cargar el certificado (Odoo).** En el mismo lugar del paso 2, campo **Certificado** → subir el
   `.crt` → Guardar.
5. **Autorizar el certificado a facturar (ARCA).** *Administrador de Relaciones de Clave Fiscal* →
   nueva relación → servicio **Facturación Electrónica** (wsfe) → representante: el alias del
   paso 3.
6. **Probar (Odoo).** *Web Services de ARCA* → **Conexiones de prueba**: tiene que dar OK.

El certificado vence (suele ser a los 2 años): anotar la fecha en Bitwarden. Para renovarlo, en el
mismo lugar, **Generar solicitud de renovación** y repetir los pasos 3 a 6.

**Hasta ese día, no tocar esa pantalla en producción**: queda en **Prueba** y sin certificado.

## 4. En Odoo: el diario de facturación electrónica

*Contabilidad → Configuración → Diarios* → **Nuevo**:

- Tipo **Ventas**, nombre «Factura electrónica», **Usa Documentos?** marcado.
- **Sistema de PdV de ARCA**: Factura Electrónica - Web Service.
- **Número del PdV de ARCA**: el del paso 3.1.

Después, en *Punto de venta → Configuración → Punto de venta* → **Caja 1** y **Caja 2** →
Facturación → ese diario. Las dos cajas comparten el punto de venta (probado: no se pisan).

En el lab esto lo hace `make lab-arca` con datos de prueba (`infra/scripts/lab-arca-homologacion.py`).

## 5. En Odoo: los bancos

*Contabilidad → Configuración → Diarios* → **Nuevo**, uno por cuenta bancaria:

- Tipo **Banco**, nombre (p. ej. «Banco Nación CC»), número de cuenta (CBU) y banco.
- Hoy débito, crédito y transferencia del punto de venta van a un diario provisorio «Banco»
  (`config/base/20-medios-de-pago.yaml`, P-016). Cuando se sepa a qué cuenta se acredita cada
  uno, se cambia ahí y se aplica con `make apply`.

## 6. Conciliación (lo que hace hoy la administración con Flexus, P-045)

Hoy: suben las **liquidaciones de las tarjetas**, las cruzan con lo cobrado y cruzan el
**resumen del banco** para ver que se acreditó. En Odoo Enterprise esto **viene incluido** y no
hace falta un módulo nuevo para empezar:

| Qué | Cómo en Odoo |
|-----|--------------|
| **Resumen del banco** | Se baja del homebanking (CSV u OFX) y se importa en el diario del banco (*Contabilidad* → en el tablero, el recuadro del diario del banco → **Importar archivo**, a veces dentro de ⋮). Odoo propone con qué movimiento va cada línea y se confirma; lo que se repite (comisiones, impuesto al débito y crédito) se automatiza con **modelos de conciliación**. |
| **Cobros con tarjeta** | Cada cobro con débito o crédito del punto de venta queda como «pendiente de acreditar». Cuando la tarjeta deposita, la línea del banco se concilia contra esos cobros. |
| **Liquidación de la tarjeta** (bruto − arancel − IVA del arancel − retenciones = neto) | Odoo no lee las liquidaciones argentinas (Prisma, Fiserv). Al principio: un asiento por liquidación con un modelo de conciliación que reparte la diferencia (arancel, IVA, retenciones). Si son muchas por mes, se hace un importador chico del archivo de la liquidación. |

Para decidir si hace falta el importador: pedir **una liquidación de tarjeta y un resumen del
banco de un mes** (con datos tapados si quieren) y cuántas liquidaciones llegan por mes. Con eso
se prueba en el lab. Las **cuentas** donde van el arancel, el IVA y cada retención las define el
contador (P-034).
