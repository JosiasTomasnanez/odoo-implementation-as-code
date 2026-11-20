-- De qué sitio salió cada pedido (ADR 0035): la tienda o el sitio mayorista. Cada sitio muestra en
-- «Mis pedidos» solo los suyos (las cuentas se usan por separado).
ALTER TABLE pedidos ADD COLUMN sitio TEXT NOT NULL DEFAULT 'tienda';
