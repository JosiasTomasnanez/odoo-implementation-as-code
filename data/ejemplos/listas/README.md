# Lista de proveedor de ejemplo (FICTICIA)

«[EJ] Ferretera Ejemplo», parecida a la de FC, para mostrar todo lo que puede pasar con una
lista de proveedor y cómo se llega del precio de la lista al costo. La generan
`infra/scripts/generar-lista-ejemplo.py` (para cambiar un caso, editar el script) y
`make lab-completo` la carga en el lab (`infra/scripts/lab-lista-ejemplo.py`). Prueba a mano:
`docs/runbooks/prueba-visual.md`, sección 2.

- `ferretera-ejemplo-1.xlsx`: tres hojas, una «parte» de la lista cada una.
  - **Lista general** (pesos, sin IVA): títulos y notas arriba; familias en una fila aparte
    («ABRAZADERAS») con la medida debajo; descripción partida en «Detalle» + «Descripción del
    producto»; un código de barras de fábrica; «Desc. %» del proveedor en dos filas (ofertas);
    filas sin precio («SIN STOCK», «Consultar», 0); un código repetido (EJ-4002); «Promociones
    vigentes» en texto como FC (martillo 5 % por unidad; destornillador 10 % desde 6 y 15 %
    desde 12); y la columna
    **«PRECIO FINAL (cálculo interno)»**, una cuenta del comercio que **no** es el costo.
  - **Bulones**: precio por unidad suelta y precio por unidad comprando la caja cerrada, con las
    unidades de la caja (dos precios).
  - **Importados USD**: en dólares, con IVA incluido y alícuota por fila (21 y 10,5).
- `ferretera-ejemplo-2.xlsx`: la lista siguiente. Martillo +3 % y se terminó su promoción
  (avisa y espera revisión), tornillos +4 % (se aplican solos), candado de 40 mm +25 % (espera), el candado de 50 mm vuelve a tener precio, la
  cinta métrica ya no está (baja), una llave francesa nueva, bulones +8 %; y en la hoja general
  el título del precio cambió a «P. Lista $» (aviso de **formato cambiado**).
