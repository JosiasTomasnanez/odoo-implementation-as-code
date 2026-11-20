-- Cuentas con contraseña (10/11): se entra con mail y contraseña; el mail se verifica una vez con
-- un código al crear la cuenta, y «Olvidé mi contraseña» manda otro. Con Google no hace falta el
-- código (Google ya verificó el mail). Solo se guarda el hash (PBKDF2).
ALTER TABLE clientes ADD COLUMN clave_hash TEXT;
ALTER TABLE clientes ADD COLUMN google_sub TEXT;
CREATE UNIQUE INDEX clientes_google ON clientes(google_sub) WHERE google_sub IS NOT NULL;
-- Para qué es el código: «alta» (crear cuenta, con la contraseña elegida ya en hash) o «clave»
-- (olvidé mi contraseña). Los del equipo usan la clave «equipo:<mail>».
ALTER TABLE codigos_ingreso ADD COLUMN proposito TEXT NOT NULL DEFAULT 'ingreso';
ALTER TABLE codigos_ingreso ADD COLUMN clave_hash TEXT;
