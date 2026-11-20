# Mostrar el puesto y la caja (laboratorio)

Para enseñarle el flujo a quien atiende y a quien cobra, con datos ficticios.

> **Ojo: no es el flujo de la primera etapa.** Esto describe el flujo con la caja de Odoo
> (pedido con QR → la caja lo cobra), guardado para la etapa siguiente (ADR 0017). Hoy, en
> el lab, los puestos dan el pedido por cobrado con «Cobrado en registradora» (ADR 0019) y
> las registradoras cobran. Para probar este flujo: `docs/runbooks/prueba-visual.md`,
> sección 10 («Etapas siguientes»).

## Preparar

1. `make lab-up` y, para abrirlo desde otra computadora o celular de la misma red de
   confianza, `make lab-red` (al terminar: `make lab-local`).
2. Entrar con el usuario `admin` del lab en dos pestañas o dos equipos:
   - **Puesto:** Punto de venta → **Mostrador 1** → PIN **1111** («[EJ] Atención mascotas»).
     Si el puesto está cerrado, aparece la nota de apertura: «Abrir caja registradora».
   - **Caja:** Punto de venta → **Caja 1** → PIN **2222** («[EJ] Cajero»).

## Qué mostrar (en este orden)

1. **Puesto:** buscar «Alimento perro» y «Cadena», agregarlos. No hay botón «Pago»: está
   **«Imprimir pedido»**. Al tocarlo sale el ticket con un **QR** y la pantalla queda libre.
2. **Caja:** escanear el QR con el lector 2D (o «Abrir pedido» y tipear el número del
   ticket). Aparece el pedido completo: cobrar con efectivo, débito, crédito o transferencia.
3. **Dos cajas:** abrir el mismo pedido en Caja 1 y Caja 2 y cobrar en una. La otra avisa
   **«Pedido ya cobrado»** y no cobra dos veces.
4. **Recibo por mail:** al terminar de cobrar, «Enviar recibo» con cualquier dirección; el
   mail (ticket + factura en PDF) se ve en <http://localhost:8025>.
5. **Ventas ya cobradas:** en la caja, «Órdenes» → filtro «Activo» → **«Pagado»**. Al elegir
   una: «Recibo/Factura» (descarga la factura en PDF para imprimirla), «Recepción» (reimprime
   el ticket; es la traducción de Odoo de *Receipt*), «Enviar» (por mail) y «Reembolso» (devolución: ver `devoluciones.md`).
6. **Cliente que no paga:** el pedido queda pendiente; se cancela solo al cerrar la última caja.

## Qué preguntarles

- ¿Se entiende el ticket? ¿Le falta o le sobra algo?
- ¿Prefieren escanear o tipear el número?
- ¿Qué nombre le ponen a cada puesto?

Las respuestas van a `docs/pendientes.md` (P-008, P-025) y a la bitácora de la guía.
