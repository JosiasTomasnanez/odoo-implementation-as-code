# 0034. La IA une sola lo que confirma con seguridad (nunca agrega productos)

- Estado: aceptado (implementador, 06/11)
- Fecha: 2026-11-06
- Cambia: ADR 0018 («la IA solo sugiere»), solo en lo que se describe acá.

## Contexto

Con listas reales (FC: 9.663 filas) no es viable que una persona revise a mano cada posible
duplicado o producto nuevo. Hasta ahora la IA solo sugería y una persona aceptaba. El comercio
quiere que la IA tenga autoridad para lo seguro, pero **sin agregar al catálogo propio productos que
no quiere tener**, y sin sumar botones.

## Decisión

- **Une sola** una fila pendiente («posible duplicado» o «producto nuevo») cuando la IA dice **«es
  el mismo»** con confianza **≥ 90 %** a un producto que **ya está en nuestro catálogo**, y el costo
  de la lista **no salta más que el tope** de la ficha («Aplicar solos los cambios de costo de
  hasta», 10 % por defecto) contra el costo actual de ese producto. Un salto mayor suele ser otra
  presentación (unidad contra caja): queda para una persona.
- **Nunca agrega productos.** «Es otro» queda en «No los tenemos» para que una persona decida si lo
  quiere vender; tampoco lo agrega «Aceptar lo que sugirió la IA» (antes sí lo hacía).
- Lo dudoso o con confianza menor queda para una persona (filtro «La IA duda»).
- **Sin botones nuevos:** pasa al tocar «Revisar con IA» y, en las importaciones que ya se aplican
  solas (correo, enlace), la IA revisa sola los posibles duplicados y productos nuevos (hasta 200 por
  vez). Si la IA no está o falla, la importación sigue como siempre.
- Lo leído con IA desde una foto o PDF escaneado sigue sin aplicarse solo.
- **Trazable y reversible:** cada fila queda marcada «Unida por la IA» (filtro con ese nombre, y en la
  lupa) y se deshace como cualquier otra. El mensaje de la importación cuenta cuántas se unieron.

## Consecuencias

- Menos trabajo manual; lo que queda para revisar es lo realmente dudoso y lo que no tenemos.
- Un error de la IA con costo parecido puede unir dos productos distintos: se mitiga con el umbral,
  el control de costo, el filtro «Unidas por la IA» y «Deshacer».
- Consumo de Gemini en cada importación automática (centavos por lista; queda anotado en la
  importación).
- Constantes en `comercio_catalogo_ia/models/importacion.py` (`CONFIANZA_PARA_UNIR`); prueba en
  `make e2e-ia`.
