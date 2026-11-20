-- Registro de lo que cada cliente cambia de sus datos (qué campo, qué decía y qué dice ahora), para
-- que la administración lo vea. «cambios_sin_ver»: tiene cambios que el equipo todavía no revisó.
CREATE TABLE cambios_cliente (
  id          INTEGER PRIMARY KEY AUTOINCREMENT,
  cliente_id  TEXT NOT NULL,
  cuando      TEXT NOT NULL,
  campo       TEXT NOT NULL,
  antes       TEXT,
  despues     TEXT
);
CREATE INDEX cambios_cliente_de ON cambios_cliente (cliente_id, cuando);
ALTER TABLE clientes ADD COLUMN cambios_sin_ver INTEGER NOT NULL DEFAULT 0;
