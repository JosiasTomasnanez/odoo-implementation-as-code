-- Productos sin control de stock en Odoo (servicios, consumibles): siempre disponibles.
ALTER TABLE stock ADD COLUMN controla INTEGER NOT NULL DEFAULT 1;
