# 0029. Del precio de la lista al costo: descuentos en cadena, IVA por producto y dólar del día

- Estado: aceptado (pedido del cliente, 30/10; reemplaza lo decidido el 26/10 sobre el dólar)
- Fecha: 2026-10-30

## Contexto

Al revisar las listas cargadas en el lab apareció un problema: en varias, la columna
«descuento» no venía del proveedor. Era una cuenta de Daniel (su descuento, el IVA y demás hasta
un precio final). El motor ya pasaba el precio al costo con un único factor por lista
(descuentos en cadena, recargo, cotización fija e IVA incluido, 23/10), pero:

- los proveedores hacen descuentos extra que no figuran en la lista: «sobre cierto porcentaje,
  después otro» (Daniel, 30/10), a veces solo para una familia o un producto;
- una lista con IVA incluido mezcla alícuotas (10,5 %, 21 %, 27 %) y un solo valor por lista no
  alcanza;
- Daniel quiere los productos en dólares al **dólar del Banco Nación**, no al que pone el
  proveedor (lo decidido el 26/10 deja de valer);
- cambiar un descuento o el dólar obligaba a subir la lista de nuevo.

El usuario no estaba seguro de todas sus respuestas; pidió que quede simple y funcional.

## Decisión

En `comercio_catalogo` (motor en `catalogo/costo.py`, compartido con `integrations/catalogo`):

- **Una sola cuenta, en este orden y todo opcional:** precio de la lista → × dólar (si la lista
  está en dólares) → descuentos de toda la lista → descuentos de la **familia** (primera regla
  cuyo texto aparece en la descripción o el código) → descuentos del **producto** (por código
  del proveedor) → descuento de la **columna** del archivo → + recargo → sin IVA (si la lista lo
  trae). Todos los descuentos son en cadena, uno después del otro.
- **Promociones en texto** (FC, «Descuentos y Promociones Vigentes»; 98 de 100 se entienden):
  columna «promociones». «N% DTO. X UNIDAD» baja el costo; «N% DTO. X Q unidades/rollos/kg» es
  el precio por mayor desde Q (el primer escalón; el texto entero queda como aviso). Si una
  promoción se termina, la fila avisa que el costo sube por eso y no se aplica sola (pedido del
  cliente: que no parezca un aumento). Lo que no es un porcentaje («va sin cargo») solo se muestra.
- **IVA del producto:** si la lista trae la alícuota de cada producto (columna «IVA»; FC:
  9.444 al 21 % y 175 al 10,5 %), los productos **nuevos** se crean con ese IVA de venta y de
  compra (si no, el del rubro). En los que ya tenemos **manda el IVA del producto** (pedido del
  cliente): si la lista dice otro, la fila avisa y no se cambia nada.
- **IVA incluido:** se saca con el IVA de compra del producto que ya tenemos; si no, con el de
  la columna «IVA»; si no, con el «IVA si no se sabe» de la lista (21).
- **La columna «descuento» nunca se sugiere sola**, para no volver a tomar una cuenta del
  comercio; se elige a mano y solo si es del proveedor. La de IVA sí se sugiere.
- **Dólar:** «Moneda de la lista» Pesos o Dólares. En dólares se usa la **cotización oficial que
  publica ARCA** (divisa vendedor del Banco Nación), nativa de Odoo con `l10n_ar_edi`
  (`currency_rate_live`, proveedor «[AR] ARCA»; `config/onpremise/55-dolar-del-dia.yaml`). Queda
  una «Cotización fija» opcional por lista. Una tarea diaria (7 h) trae la cotización si no la
  hay y **recalcula las listas en dólares** cuyo dólar se movió más de 0,5 %; los cambios dentro
  del tope se aplican solos y el resto espera revisión, como una lista nueva.
- **Se guarda la cuenta de cada fila** (precio de la lista, descuento e IVA de la fila, «cálculo
  del costo» paso a paso) y la lista muestra **un ejemplo** con filas reales.
- **«Recalcular costos»** (botón en la lista): vuelve a leer el último archivo con los valores
  de ahora. Si no se aplicó nada, se simula de nuevo; si no, entra como una importación nueva
  del mismo archivo (simular → revisar → aplicar, con historial y deshacer). El costo sigue
  guardado en el precio del proveedor (`product.supplierinfo.price`) como hasta ahora, así
  Compras, «Buscar producto», las facturas de proveedor y los márgenes no cambian.

## Consecuencias

- El costo de un producto en dólares cambia casi todos los días. «Diferencia chica» de
  `comercio_precios` evita que el precio de venta cambie por centavos.
- **ARCA necesita el certificado** de factura electrónica de la empresa. Mientras la
  facturación no esté en Odoo (ADR 0017), en producción el dólar del día no llega solo: se
  carga a mano en **Costos y precios → Dólar** (pantalla propia, 30/10, pedido del cliente, con
  «Recalcular listas en dólares») o se usa la «Cotización fija». Con el certificado, la misma
  pantalla se llena sola cada mañana. En el lab responde
  ARCA homologación (cotización de prueba, no la real).
- Divisa (ARCA) y billete (pizarra del BNA) difieren poco (en general 1 a 3 %). Si el negocio
  quiere el billete, hace falta leer la página del BNA (sin API oficial, se rompe si la
  cambian): otro ADR.
- Los valores de cada proveedor los confirma el negocio (P-056), revisando lista por lista.

## Alternativas descartadas

- **Descuento del producto en el campo nativo `discount` del precio del proveedor:** se
  perdía al cerrar el precio y abrir uno nuevo (historial) y no servía para los productos
  que todavía no tenemos.
- **Guardar el precio en dólares (`currency_id` = USD) en el precio del proveedor y convertir
  al comprar:** nativo, pero el costo, los márgenes, «Buscar producto» y las facturas comparan
  en pesos; habría que tocar todo eso.
- **Leer el dólar billete de la página del BNA:** frágil; se elige el oficial de ARCA.
