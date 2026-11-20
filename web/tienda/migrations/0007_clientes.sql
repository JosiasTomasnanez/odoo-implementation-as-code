-- Cuentas de clientes (fase 6). Ingreso con un código por mail (sin contraseñas); Google después.
CREATE TABLE clientes (
  id             TEXT PRIMARY KEY,
  email          TEXT NOT NULL UNIQUE,      -- verificado (entró con el código que le llegó)
  nombre         TEXT,
  telefono       TEXT,
  creado         TEXT NOT NULL,
  mayorista      TEXT,                      -- NULL | pendiente | aprobado | rechazado
  cuit           TEXT,
  razon_social   TEXT,
  odoo_partner_id INTEGER,
  lista_id       INTEGER                    -- lista de precios mayorista (al aprobar)
);

-- Códigos de ingreso: solo el hash; vencen a los 10 minutos; 5 intentos.
CREATE TABLE codigos_ingreso (
  email        TEXT PRIMARY KEY,
  codigo_hash  TEXT NOT NULL,
  vence        TEXT NOT NULL,
  intentos     INTEGER NOT NULL DEFAULT 0
);

CREATE TABLE sesiones_cliente (
  token_hash  TEXT PRIMARY KEY,
  cliente_id  TEXT NOT NULL,
  vence       TEXT NOT NULL
);

ALTER TABLE pedidos ADD COLUMN cliente_id TEXT;
CREATE INDEX pedidos_email ON pedidos(email);
