-- Cuántos mails mandó la tienda cada día (hora de Argentina) y por qué proveedor, para el resumen
-- diario por Discord y para ver cuánto falta para el cupo (P-067). «fallidos»: no salió por ninguno.
CREATE TABLE mails_dia (
  dia TEXT NOT NULL,
  proveedor TEXT NOT NULL,
  cantidad INTEGER NOT NULL DEFAULT 0,
  PRIMARY KEY (dia, proveedor)
);
