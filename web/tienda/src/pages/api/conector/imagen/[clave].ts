// El conector sube la foto de un producto (la clave es el checksum del adjunto en Odoo) y después sus
// versiones livianas: «<clave>-400» y «<clave>-800» (WebP). Con la de 800 la foto queda completa.
import { env } from "cloudflare:workers";
import { firmaValida } from "../../../../servidor/firma";
import { tipoImagen } from "../../../../servidor/catalogo";
import { cuerpoConTope, error, json } from "../../../../servidor/respuestas";

export const prerender = false;
const MAX = 4 * 1024 * 1024;

export async function PUT({ request, url, params }: { request: Request; url: URL; params: { clave?: string } }) {
  const clave = params.clave ?? "";
  const m = /^([0-9a-f]{40,64})(?:-(400|800))?$/.exec(clave);
  if (!m) return error(400, "Clave inválida");
  const [, base, ancho] = m;
  const cuerpo = await cuerpoConTope(request, MAX);
  if (!cuerpo) return error(413, "Imagen demasiado grande");
  const ok = await firmaValida(env.CONECTOR_SECRETO, request.headers.get("x-tienda-fecha"),
    request.headers.get("x-tienda-firma"), "PUT", url.pathname, cuerpo);
  if (!ok) return error(401, "Firma inválida");
  const tipo = tipoImagen(new Uint8Array(cuerpo));
  if (!tipo) return error(415, "No es una imagen JPEG, PNG o WebP");
  await env.IMAGENES.put(`productos/${clave}`, cuerpo, { httpMetadata: { contentType: tipo, cacheControl: "public, max-age=31536000, immutable" } });
  if (ancho) {
    if (ancho === "800") await env.DB.prepare("UPDATE imagenes SET variantes = 1 WHERE clave = ?").bind(base).run();
  } else {
    await env.DB.prepare(`INSERT INTO imagenes (clave, tipo, bytes, subida) VALUES (?, ?, ?, ?)
      ON CONFLICT(clave) DO NOTHING`).bind(clave, tipo, cuerpo.byteLength, new Date().toISOString()).run();
  }
  return json({ ok: true });
}
