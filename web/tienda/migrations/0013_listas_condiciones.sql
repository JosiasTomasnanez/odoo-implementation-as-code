-- Listas de clientes más completas (ADR 0037): además del descuento general sobre la lista base,
-- descuentos propios por rubro o por producto, que se pueden cambiar después. Cada cambio sube la
-- versión y deja la lista «pendiente» (1) hasta que Odoo la pone al día; 2 = Odoo no pudo.
ALTER TABLE listas_nuevas ADD COLUMN reglas TEXT NOT NULL DEFAULT '[]';   -- [{tipo: rubro|producto, id, descuento}]
ALTER TABLE listas_nuevas ADD COLUMN version INTEGER NOT NULL DEFAULT 1;
ALTER TABLE listas_nuevas ADD COLUMN pendiente INTEGER NOT NULL DEFAULT 0;
CREATE INDEX listas_nuevas_odoo ON listas_nuevas(odoo_id);
