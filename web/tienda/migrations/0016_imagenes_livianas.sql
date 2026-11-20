-- Fotos livianas (WebP de 400 y 800 px, srcset): «variantes» = 1 cuando ya se subieron las dos.
-- Una foto sin ellas se vuelve a pedir al conector, que sube la original y las variantes.
ALTER TABLE imagenes ADD COLUMN variantes INTEGER NOT NULL DEFAULT 0;
