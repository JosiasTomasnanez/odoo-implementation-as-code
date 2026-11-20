-- Fotos ya subidas a R2 (la clave es el checksum del adjunto en Odoo).
CREATE TABLE imagenes (
  clave   TEXT PRIMARY KEY,
  tipo    TEXT NOT NULL,
  bytes   INTEGER NOT NULL,
  subida  TEXT NOT NULL
);
