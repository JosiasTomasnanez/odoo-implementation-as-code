-- Faltante: el cliente elige esperar, reemplazo o devolución de lo que falta.
ALTER TABLE pedidos ADD COLUMN eleccion TEXT;
ALTER TABLE pedidos ADD COLUMN eleccion_fecha TEXT;
