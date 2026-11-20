-- Pedidos de la tienda (ADR 0033). El total y los precios los calcula la tienda al armar el
-- pedido (nunca se toman del navegador). Estados:
--   pendiente_pago → pagado → en_odoo → (fase 4: preparando → listo → retirado)
--   pendiente_pago → vencido | rechazado   (se libera la reserva)
CREATE TABLE pedidos (
  id            TEXT PRIMARY KEY,               -- aleatorio (no se puede adivinar)
  numero        INTEGER NOT NULL UNIQUE,        -- correlativo para hablar con el cliente: W-0001
  token         TEXT NOT NULL,                  -- para ver el estado sin cuenta (link del mail)
  estado        TEXT NOT NULL,
  nombre        TEXT NOT NULL,
  email         TEXT NOT NULL,
  telefono      TEXT,
  total         INTEGER NOT NULL,               -- centavos, IVA incluido
  lista_id      INTEGER NOT NULL,
  creado        TEXT NOT NULL,
  vence         TEXT NOT NULL,                  -- hasta cuándo dura la reserva sin pagar
  pagado        TEXT,
  pago_id       TEXT,                           -- id del pago en el medio de pago
  pago_medio    TEXT,                           -- simulado | mercadopago
  odoo_id       INTEGER,
  odoo_nombre   TEXT,
  actualizado   TEXT NOT NULL
);
CREATE INDEX pedidos_estado ON pedidos(estado, vence);

CREATE TABLE pedido_lineas (
  pedido_id     TEXT NOT NULL REFERENCES pedidos(id),
  producto_id   INTEGER NOT NULL,
  nombre        TEXT NOT NULL,
  cantidad      INTEGER NOT NULL,
  precio        INTEGER NOT NULL,               -- centavos por unidad
  consultar     INTEGER NOT NULL DEFAULT 0,
  PRIMARY KEY (pedido_id, producto_id)
);

-- Avisos de pago recibidos (cada pago se procesa una sola vez).
CREATE TABLE pagos (
  pago_id       TEXT PRIMARY KEY,
  pedido_id     TEXT NOT NULL,
  medio         TEXT NOT NULL,
  estado        TEXT NOT NULL,
  monto         INTEGER NOT NULL,
  recibido      TEXT NOT NULL
);

-- Bitácora del pedido (qué pasó y cuándo), para el panel y para revisar problemas.
CREATE TABLE pedido_eventos (
  id            INTEGER PRIMARY KEY AUTOINCREMENT,
  pedido_id     TEXT NOT NULL,
  cuando        TEXT NOT NULL,
  que           TEXT NOT NULL
);
CREATE INDEX pedido_eventos_pedido ON pedido_eventos(pedido_id);

CREATE TABLE contadores (nombre TEXT PRIMARY KEY, valor INTEGER NOT NULL);
INSERT INTO contadores (nombre, valor) VALUES ('pedido', 0);
