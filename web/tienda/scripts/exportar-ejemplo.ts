// Exporta el catálogo ficticio de la demo (src/data/catalogo.ts) como JSON, para cargarlo en el
// Odoo del lab (infra/scripts/lab-tienda-ejemplo.py). Uso: node scripts/exportar-ejemplo.ts
import { categorias, productos } from "../src/data/catalogo.ts";
process.stdout.write(JSON.stringify({ categorias, productos }));
