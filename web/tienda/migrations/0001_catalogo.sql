-- Catálogo copiado de Odoo y control de la sincronización (ADR 0033).
-- Los ids son los de Odoo: el conector reenvía lotes sin duplicar (upsert por id).

CREATE TABLE categorias (
  id_odoo     INTEGER PRIMARY KEY,           -- pos.category
  nombre      TEXT NOT NULL,
  slug        TEXT NOT NULL UNIQUE,
  padre_id    INTEGER,
  orden       INTEGER NOT NULL DEFAULT 0,
  icono       TEXT,
  actualizado TEXT NOT NULL
);

CREATE TABLE productos (
  id_odoo       INTEGER PRIMARY KEY,         -- product.product
  slug          TEXT NOT NULL UNIQUE,
  nombre        TEXT NOT NULL,
  marca         TEXT,
  codigo        TEXT,                        -- código de barras (se busca, no se muestra)
  referencia    TEXT,                        -- referencia interna
  categoria_id  INTEGER REFERENCES categorias(id_odoo),
  unidad        TEXT NOT NULL DEFAULT 'unidad',
  descripcion   TEXT,
  imagen        TEXT,                        -- clave en R2 (sin foto: NULL)
  publicado     INTEGER NOT NULL DEFAULT 1,  -- 0 = se despublicó en Odoo (no se borra: hay pedidos que lo citan)
  consultar     INTEGER NOT NULL DEFAULT 0,  -- «Consultar disponibilidad»: se vende sin tope, se confirma en el día
  dias_encargo  INTEGER,                     -- plazo del proveedor en Odoo, para avisar la fecha
  nuevo_hasta   TEXT,
  actualizado   TEXT NOT NULL
);
CREATE INDEX productos_categoria ON productos(categoria_id, publicado);

-- Precio por lista de Odoo: «Tienda online» (todos) y las mayoristas (clientes aprobados).
CREATE TABLE precios (
  producto_id     INTEGER NOT NULL REFERENCES productos(id_odoo),
  lista_id        INTEGER NOT NULL,          -- product.pricelist
  precio          INTEGER NOT NULL,          -- en centavos, IVA incluido
  precio_anterior INTEGER,                   -- si hay oferta: el precio sin oferta
  oferta_hasta    TEXT,
  PRIMARY KEY (producto_id, lista_id)
);

CREATE TABLE listas_precios (
  id_odoo   INTEGER PRIMARY KEY,
  nombre    TEXT NOT NULL,
  publica   INTEGER NOT NULL DEFAULT 0       -- 1 = «Tienda online»
);

-- Stock libre que informa Odoo (ya descuenta lo reservado en Odoo) y el margen de seguridad.
-- Las reservas de la tienda viven en el Durable Object «Inventario».
CREATE TABLE stock (
  producto_id INTEGER PRIMARY KEY REFERENCES productos(id_odoo),
  libre_odoo  REAL NOT NULL,
  margen      REAL NOT NULL DEFAULT 0,
  actualizado TEXT NOT NULL
);

-- Búsqueda por nombre, marca y códigos, sin acentos (rowid = id_odoo del producto).
CREATE VIRTUAL TABLE productos_busqueda USING fts5(
  nombre, marca, codigo, referencia, categoria,
  tokenize='unicode61 remove_diacritics 2'
);

-- Lotes recibidos del conector: cada número se aplica una sola vez.
CREATE TABLE lotes_sync (
  numero    INTEGER PRIMARY KEY,
  recibido  TEXT NOT NULL,
  cambios   INTEGER NOT NULL
);
