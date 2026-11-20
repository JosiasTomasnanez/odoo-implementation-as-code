-- Botón de arrepentimiento (Res. SCI 424/2020): pedidos de dejar sin efecto una compra, con su
-- código de gestión. Los ve y los resuelve la administración.
CREATE TABLE arrepentimientos (
  codigo    TEXT PRIMARY KEY,
  creado    TEXT NOT NULL,
  nombre    TEXT NOT NULL,
  email     TEXT NOT NULL,
  telefono  TEXT,
  pedido    TEXT NOT NULL,
  motivo    TEXT,
  resuelto  TEXT,
  resuelto_por TEXT,
  nota      TEXT
);
-- Para poder limpiar los contadores de intentos que ya no sirven
ALTER TABLE intentos ADD COLUMN visto TEXT;
-- Índices para cuando haya volumen
CREATE INDEX pedidos_cliente ON pedidos(cliente_id, sitio);
CREATE INDEX clientes_mayorista ON clientes(mayorista);
CREATE INDEX sesiones_cliente_de ON sesiones_cliente(cliente_id);
CREATE INDEX sesiones_equipo_de ON sesiones_equipo(miembro_id);
