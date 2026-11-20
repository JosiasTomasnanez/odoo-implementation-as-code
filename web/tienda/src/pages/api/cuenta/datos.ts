// Mis datos: el cliente cambia los datos de contacto de su cuenta. En la tienda, nombre y teléfono;
// en el sitio mayorista, contacto, teléfono, dirección y localidad (el CUIT, la razón social y la
// condición de IVA no se cambian desde acá). Cada cambio queda registrado (servidor/cambios.ts).
import { env } from "cloudflare:workers";
import { z } from "zod";
import { guardarDatos } from "../../../servidor/cambios";
import { clienteActual } from "../../../servidor/clientes";
import { limitar, mismoOrigen } from "../../../servidor/protecciones";
import { error } from "../../../servidor/respuestas";
import { sitioDe } from "../../../servidor/sitio";

export const prerender = false;
const limpio = (t: unknown) => String(t ?? "").replace(/\s+/g, " ").trim();
const texto = (min: number, max: number) => z.string().min(min).max(max).regex(/^[^<>\p{Cc}]+$/u);
const telefono = z.string().min(6).max(30).regex(/^\+?[\d\s().-]+$/);
const Tienda = z.object({ nombre: texto(2, 120), telefono: z.union([z.literal(""), telefono]) });
const Mayorista = z.object({ contacto: texto(2, 80), telefono, direccion: texto(2, 120), localidad: texto(2, 80) });

export async function POST({ request, url }: { request: Request; url: URL }) {
  if (!mismoOrigen(request, url)) return error(403, "Origen no permitido");
  const lim = await limitar(env.LIMITE_INGRESO, `datos:${request.headers.get("cf-connecting-ip") ?? "?"}`);
  if (lim) return lim;
  const mayorista = sitioDe(url) === "mayorista";
  const pagina = `${url.origin}${mayorista ? "/cuenta" : "/cuenta/datos"}`;
  const cliente = await clienteActual(env.DB, request);
  if (!cliente) return Response.redirect(`${url.origin}${mayorista ? "/ingresar" : "/cuenta"}`, 303);
  if (mayorista && !cliente.mayorista) return Response.redirect(`${url.origin}/`, 303);
  const f = await request.formData();
  const crudo = Object.fromEntries(["nombre", "contacto", "telefono", "direccion", "localidad"].map((k) => [k, limpio(f.get(k))]));
  const d = (mayorista ? Mayorista : Tienda).safeParse(crudo);
  if (!d.success) return Response.redirect(`${pagina}?e=1`, 303);
  await guardarDatos(env.DB, cliente.id, d.data);
  return Response.redirect(`${pagina}?ok=1`, 303);
}
