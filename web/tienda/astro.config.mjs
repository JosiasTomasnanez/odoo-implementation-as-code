// Tienda online (ADR 0032): Astro en Cloudflare Workers. Todo se arma al pedirlo (datos de D1);
// los archivos fijos (estilos, fuentes, imágenes de la demo) salen directo de los assets.
import { defineConfig } from "astro/config";
import cloudflare from "@astrojs/cloudflare";

export default defineConfig({
  output: "server",
  adapter: cloudflare(),
  trailingSlash: "ignore",
  build: { format: "directory", inlineStylesheets: "never" },
  // Scripts siempre en archivos aparte: la política de seguridad no permite scripts en línea.
  vite: { build: { assetsInlineLimit: 0 } },
});
