-- Mayoristas (ADR 0035): cantidad mínima de cada producto en cada lista (la de la regla de Odoo) y
-- bulto del producto (su embalaje más chico en Odoo). El sitio mayorista no deja comprar menos que
-- el mínimo ni cantidades que no sean bultos enteros. La tienda minorista no los usa.
ALTER TABLE precios ADD COLUMN minimo INTEGER NOT NULL DEFAULT 1;
ALTER TABLE productos ADD COLUMN bulto INTEGER;
