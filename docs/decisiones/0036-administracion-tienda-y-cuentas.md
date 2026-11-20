# 0036. Administración en la tienda, cuentas con contraseña y Google

- Estado: aceptado (implementador, 10/11)
- Fecha: 2026-11-10
- Cambia: ADR 0033/0035 en lo que se describe acá (antes: ingreso solo con código por mail y
  mayoristas aprobados a mano en la base).

## Contexto

- El código por mail **para cada ingreso** no gusta: el cliente quiere su contraseña, verificar el
  mail una sola vez y poder recuperarla («Olvidé mi contraseña»). Con Google, sin código.
- El sitio mayorista **sigue exigiendo aprobación** y ahora **más datos de la empresa**.
- Aprobar mayoristas, manejar listas para clientes recurrentes y el equipo con sus roles tiene que
  ser **fácil para Daniel, dentro de la página**, no en Odoo (aunque por dentro todo quede en Odoo).

## Decisión

- **Cuentas de clientes:** mail + contraseña (PBKDF2-SHA256, 100.000 vueltas, sal propia). Al
  crear la cuenta se confirma el mail con un código de 6 dígitos (una vez); el código queda **atado
  al navegador** que la pidió (cookie al azar), así otro pedido para el mismo mail no puede colar su
  contraseña. «Olvidé mi contraseña»: código + contraseña nueva; cierra las otras sesiones. Topes:
  8 fallos por mail e IP (15 min) y 30 por mail (1 h). Las cuentas viejas (solo código) eligen
  contraseña con «Olvidé mi contraseña».
- **Google** (OpenID Connect con PKCE, canje del código en el servidor): no pide código porque
  Google ya verificó el mail; vincula por id de Google o por mail. Se activa con los secretos
  `GOOGLE_CLIENT_ID` y `GOOGLE_CLIENT_SECRET` (sin ellos el botón no aparece).
- **Alta mayorista:** razón social, CUIT (dígito verificador), condición frente al IVA, actividad,
  dirección, localidad, teléfono y persona de contacto. Queda **pendiente** hasta que se aprueba.
- **Administración en `/admin`** (dominio de la tienda; en el mayorista no existe), para el
  **equipo** (tabla propia, no los clientes): mail + contraseña y, la primera vez en cada navegador,
  un código por mail (queda de confianza 60 días); sesión de 12 h; cookies `SameSite=Strict`.
  Roles: **admin** (todo, también el equipo), **mayoristas** (aprobar y listas), **marketing**
  (reservado). Nadie se saca su propio admin ni se da de baja. Todo queda en un registro.
  El primer admin se carga con `make tienda-admin EMAIL=… NOMBRE=…`.
- **Aprobar = Odoo por dentro:** al aprobar se elige la lista; el conector
  (`tienda_sincronizar_clientes`) vincula el contacto que tenga ese CUIT o crea uno con los datos
  del alta, le pone la lista de precios y la etiqueta «Mayorista (tienda online)». A un contacto que ya existía solo se lo vincula si su mail es el mail verificado de la cuenta (nunca al de la empresa ni a uno con usuario); si no, no se lo toca y la administración muestra qué hacer. Desde ahí los
  pedidos mayoristas entran a Odoo **con su contacto y su lista**.
- **Listas para clientes:** «otra lista − X %» desde `/admin/listas`; Odoo la crea con una regla
  general sobre la base (misma compra mínima) y «Sincronizar con la tienda», y vuelve con sus
  precios. Lo más fino (precio por producto, escalas) se sigue haciendo en Odoo.
- **Pagar en una pantalla aparte** (`/compra`, los dos sitios), con pasos y color sobrio.

## Consecuencias

- El panel de pedidos del local sigue con dispositivo + PIN de Odoo (pensado para la tablet del
  mostrador); unificarlo con el equipo de `/admin` queda para después si hace falta.
- Google necesita un cliente OAuth en Google Cloud (pendiente, con la cuenta del negocio).
- Las pruebas e2e dejan datos ficticios en la demo y el lab (contacto y lista de prueba) hasta que
  exista el entorno `prueba` aislado.
