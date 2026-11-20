# Cuentas de Odoo por rol

Tres cuentas además del administrador (P-005, 18/11). Se declaran en `config/cuentas/` y los
nombres de usuario están en `config/valores.yaml` → `cuentas`. Probado en el lab.

| Cuenta (usuario) | Quién | Puede | No puede |
|---|---|---|---|
| **Gerencia y administración** (`gerencia`) | Daniel y Carla | Productos, precios y listas («Costos y precios»), compras, inventario (aplicar conteos y ajustes), facturas, pagos y reportes contables, sesiones y reportes del PdV, empleados y sus PIN, imprimir en la Zebra | Ajustes generales, usuarios, módulos, impuestos, plan de cuentas, configuración de los puestos |
| **Puestos y cajas** (`puestos`) | Las PCs de los puestos y las cajas | Abrir el puesto o la caja; cada vendedor entra con su PIN | Productos, precios, stock, compras, contabilidad |
| **Conteo de stock** (`conteo`) | Quien cuenta (y recibe mercadería) | App Código de barras: contar y confirmar, recibir pedidos | Precios, productos, códigos de productos, compras |
| Administrador (`admin`) | Solo el implementador, con 2FA | Todo, incluida la configuración | No se comparte |

Lo que no pueden tocar desde las pantallas lo cambia el implementador en `config/`. Hay cosas que
Gerencia podría cambiar igual (almacenes, tipos de operación, nombre de un diario). Si las cambia,
`make verify` lo marca y `make apply` lo vuelve atrás.

Al contar, si aparece un código que no es nuestro, la cuenta de **Conteo** no lo agrega ni se
lo pone a un producto: lo anota con «No lo tenemos». Lo resuelve **Gerencia**, desde la misma
pantalla.

## Crear las cuentas en producción (después de comprarlas)

1. En `environments/onpremise.yaml`, descomentar `- config/cuentas`.
2. `make plan ENV=onpremise`: tienen que aparecer solo **3 crear** de `res.users`.
3. `make apply ENV=onpremise`.
4. Contraseñas: entrar como administrador → **Ajustes → Usuarios** → la cuenta →
   **Acción → Cambiar contraseña**. Guardarlas en Bitwarden; nunca en el repo ni en el chat.
5. **Puestos y cajas:** en cada PC, entrar con `puestos` y dejar que el navegador guarde la
   contraseña. En la PC de ferretería, primero borrar la contraseña del administrador que tiene
   guardada (*Contraseñas* → odoo.comercio-ejemplo.example → eliminar).

## PIN de los vendedores y cajeros

Los PIN se cargan en Odoo, **nunca en el repo**. Desde la cuenta **Gerencia**:

1. **Empleados → Nuevo** → nombre.
2. Pestaña de ajustes de RR. HH. → **PIN** (4 dígitos, distinto para cada persona).
3. Guardar.

Mientras la lista de empleados de un puesto esté vacía, cualquier empleado con PIN puede entrar
a ese puesto. Para limitar quién entra en cada uno o quién cobra en las cajas, se configura por
puesto en `config/onpremise/40-puestos.yaml` (como en el lab: `config/ejemplos/40-puestos-reales-lab.yaml`).
