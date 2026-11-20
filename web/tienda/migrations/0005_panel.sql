-- Panel de pedidos para los empleados (fase 4).
-- Empleados: vienen de Odoo (hr.employee con «Usa el panel»). El PIN nunca se guarda: solo un
-- HMAC con una clave secreta de la tienda (PIN_PEPPER), así una copia de la base no lo revela.
CREATE TABLE empleados (
  id_odoo   INTEGER PRIMARY KEY,
  nombre    TEXT NOT NULL,
  pin_hash  TEXT,
  activo    INTEGER NOT NULL DEFAULT 1
);

-- PCs o tablets del local habilitadas una vez (con el código de alta). Se pueden revocar.
CREATE TABLE dispositivos (
  id         TEXT PRIMARY KEY,
  nombre     TEXT NOT NULL,
  token_hash TEXT NOT NULL UNIQUE,
  creado     TEXT NOT NULL,
  revocado   TEXT
);

-- Sesión de un empleado en un dispositivo (corta).
CREATE TABLE sesiones_panel (
  token_hash     TEXT PRIMARY KEY,
  empleado_id    INTEGER NOT NULL,
  dispositivo_id TEXT NOT NULL,
  vence          TEXT NOT NULL
);

-- Intentos fallidos (PIN o código de alta) para frenar a quien prueba números.
CREATE TABLE intentos (
  clave   TEXT PRIMARY KEY,
  fallos  INTEGER NOT NULL,
  hasta   TEXT
);

-- Acciones del panel que el conector aplica en Odoo (preparar, listo, faltante, retirado).
CREATE TABLE acciones (
  id          TEXT PRIMARY KEY,
  pedido_id   TEXT NOT NULL,
  tipo        TEXT NOT NULL,
  datos       TEXT,
  empleado_id INTEGER NOT NULL,
  creada      TEXT NOT NULL,
  aplicada    TEXT,
  resultado   TEXT
);
CREATE INDEX acciones_pendientes ON acciones(aplicada, creada);

ALTER TABLE pedidos ADD COLUMN listo TEXT;
ALTER TABLE pedidos ADD COLUMN retirado TEXT;
ALTER TABLE pedidos ADD COLUMN recordado TEXT;
ALTER TABLE pedido_lineas ADD COLUMN disponible INTEGER;  -- lo que había al preparar (faltante)
