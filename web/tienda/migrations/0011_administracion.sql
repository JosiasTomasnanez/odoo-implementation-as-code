-- Administración de la tienda (fase 7, 10/11): el equipo entra a /admin con mail y contraseña (y
-- un código por mail la primera vez en cada equipo). Roles: admin (todo, también el equipo),
-- mayoristas (aprobar cuentas y listas de clientes) y marketing (más adelante).
CREATE TABLE equipo (
  id          TEXT PRIMARY KEY,
  email       TEXT NOT NULL UNIQUE,
  nombre      TEXT NOT NULL,
  roles       TEXT NOT NULL DEFAULT '',     -- separados por coma
  clave_hash  TEXT,
  activo      INTEGER NOT NULL DEFAULT 1,
  creado      TEXT NOT NULL,
  creado_por  TEXT
);
CREATE TABLE sesiones_equipo (
  token_hash  TEXT PRIMARY KEY,
  miembro_id  TEXT NOT NULL,
  vence       TEXT NOT NULL
);
-- Equipos (PC, celular) donde ya confirmó con el código del mail: ahí alcanza la contraseña.
CREATE TABLE confianza_equipo (
  token_hash  TEXT PRIMARY KEY,
  miembro_id  TEXT NOT NULL,
  vence       TEXT NOT NULL
);
-- Quién hizo qué (aprobaciones, listas, cambios del equipo).
CREATE TABLE registro_admin (
  id      INTEGER PRIMARY KEY AUTOINCREMENT,
  cuando  TEXT NOT NULL,
  quien   TEXT NOT NULL,
  que     TEXT NOT NULL
);

-- Mayoristas: quién y cuándo aprobó; «odoo_pendiente» = hay que llevar el contacto a Odoo.
ALTER TABLE clientes ADD COLUMN aprobado TEXT;
ALTER TABLE clientes ADD COLUMN aprobado_por TEXT;
ALTER TABLE clientes ADD COLUMN pedido_alta TEXT;
ALTER TABLE clientes ADD COLUMN nota TEXT;
ALTER TABLE clientes ADD COLUMN odoo_pendiente INTEGER NOT NULL DEFAULT 0;  -- 1 = mandar, 2 = falló
ALTER TABLE clientes ADD COLUMN odoo_error TEXT;
-- Más datos de la empresa al pedir el alta (para aprobar y para el contacto de Odoo)
ALTER TABLE clientes ADD COLUMN condicion_iva TEXT;   -- ri | monotributo | exento | final
ALTER TABLE clientes ADD COLUMN actividad TEXT;       -- ferretería, obra, comercio…
ALTER TABLE clientes ADD COLUMN direccion TEXT;
ALTER TABLE clientes ADD COLUMN localidad TEXT;
ALTER TABLE clientes ADD COLUMN contacto TEXT;        -- persona que hace los pedidos

-- Listas de precios nuevas para clientes, pedidas desde la administración: Odoo las crea
-- (basadas en otra lista, con un descuento) y vuelven con la sincronización.
CREATE TABLE listas_nuevas (
  id          TEXT PRIMARY KEY,
  nombre      TEXT NOT NULL,
  base_id     INTEGER NOT NULL,
  descuento   REAL NOT NULL,
  creada      TEXT NOT NULL,
  creada_por  TEXT NOT NULL,
  odoo_id     INTEGER,
  resultado   TEXT
);
