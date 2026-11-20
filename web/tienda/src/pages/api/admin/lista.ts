// Listas de precios para clientes (rol «mayoristas», ADR 0037): crear una («tal lista − X %»),
// cambiarle el nombre o el descuento general, sumarle o quitarle descuentos por rubro o por
// producto, y pasar clientes a una lista. Cada cambio queda para que el conector lo lleve a Odoo.
import { env } from "cloudflare:workers";
import { aleatorio } from "../../../servidor/panel";
import { miembroActual, puede, registrar } from "../../../servidor/equipo";
import { TOPE_REGLAS, descuentoValido, leerDescuento, listaPorId, pct, type Regla } from "../../../servidor/listas";
import { mismoOrigen } from "../../../servidor/protecciones";
import { error } from "../../../servidor/respuestas";

export const prerender = false;

export async function POST({ request, url }: { request: Request; url: URL }) {
  if (!mismoOrigen(request, url)) return error(403, "Origen no permitido");
  const yo = await miembroActual(env.DB, request);
  if (!yo) return Response.redirect(`${url.origin}/admin/ingresar`, 303);
  if (!puede(yo, "mayoristas")) return error(403, "Sin permiso");
  const f = await request.formData();
  const accion = String(f.get("accion") ?? "crear");
  const ir = (ruta: string) => Response.redirect(`${url.origin}${ruta}`, 303);
  const nombre = String(f.get("nombre") ?? "").replace(/\s+/g, " ").trim().slice(0, 60);
  const descuento = leerDescuento(f.get("descuento"));

  if (accion === "crear") {
    const base = Number(f.get("base"));
    const b = await env.DB.prepare("SELECT nombre FROM listas_precios WHERE id_odoo = ?").bind(base).first<{ nombre: string }>();
    if (nombre.length < 3 || !b || !descuentoValido(descuento)) return ir("/admin/listas?e=1");
    await env.DB.batch([
      env.DB.prepare("INSERT INTO listas_nuevas (id, nombre, base_id, descuento, creada, creada_por) VALUES (?, ?, ?, ?, ?, ?)")
        .bind(aleatorio(16), nombre, base, descuento, new Date().toISOString(), yo.nombre),
      registrar(env.DB, yo, `pidió la lista «${nombre}» = ${b.nombre} − ${pct(descuento)}`),
    ]);
    return ir("/admin/listas?ok=1");
  }

  // Pasar clientes aprobados a una lista (cualquiera mayorista, también las hechas en Odoo)
  if (accion === "clientes") {
    const lista = Number(f.get("lista"));
    const l = await env.DB.prepare("SELECT nombre FROM listas_precios WHERE id_odoo = ? AND publica = 0").bind(lista).first<{ nombre: string }>();
    const ids = [...new Set(f.getAll("cliente").map(String))].filter((x) => /^[0-9a-f]{32}$/.test(x)).slice(0, 50);
    if (!l) return error(422, "Lista inválida");
    if (!ids.length) return ir(`/admin/listas/${lista}`);
    await env.DB.batch([
      ...ids.map((id) => env.DB.prepare("UPDATE clientes SET lista_id = ?, odoo_pendiente = 1 WHERE id = ? AND mayorista = 'aprobado'").bind(lista, id)),
      registrar(env.DB, yo, `pasó ${ids.length} ${ids.length === 1 ? "cliente" : "clientes"} a la lista «${l.nombre}»`),
    ]);
    return ir(`/admin/listas/${lista}?ok=clientes`);
  }

  // Lo demás cambia una lista hecha acá (ya creada en Odoo)
  const l = await listaPorId(env.DB, String(f.get("id") ?? ""));
  if (!l?.odoo_id) return error(404, "No encontrada");
  const volver = (q: string) => ir(`/admin/listas/${l.odoo_id}?${q}`);
  let reglas: Regla[] = l.reglas, nuevoNombre = l.nombre, general = l.descuento, hizo = "";
  if (accion === "general") {
    if (nombre.length < 3 || !descuentoValido(descuento)) return volver("e=datos");
    nuevoNombre = nombre; general = descuento;
    hizo = `cambió la lista «${l.nombre}»: ${nombre}, ${pct(descuento)} general`;
  } else if (accion === "regla" || accion === "quitar") {
    const tipo = f.get("tipo") === "rubro" ? "rubro" : "producto", ref = Number(f.get("ref"));
    const que = Number.isInteger(ref) && ref > 0
      ? await env.DB.prepare(`SELECT nombre FROM ${tipo === "rubro" ? "categorias" : "productos"} WHERE id_odoo = ?`).bind(ref).first<{ nombre: string }>() : null;
    reglas = l.reglas.filter((r) => !(r.tipo === tipo && r.id === ref));
    if (accion === "regla") {
      if (!que || !descuentoValido(descuento)) return volver("e=datos");
      if (reglas.length >= TOPE_REGLAS) return volver("e=tope");
      reglas.push({ tipo, id: ref, descuento });
      hizo = `lista «${l.nombre}»: ${pct(descuento)} en ${que.nombre}`;
    } else {
      if (reglas.length === l.reglas.length) return volver("");
      hizo = `lista «${l.nombre}»: quitó el descuento propio de ${que?.nombre ?? `${tipo} ${ref}`}`;
    }
  } else return error(400, "Acción inválida");
  await env.DB.batch([
    // «version» evita que la confirmación de un envío anterior tape un cambio hecho mientras tanto
    env.DB.prepare("UPDATE listas_nuevas SET nombre = ?, descuento = ?, reglas = ?, version = version + 1, pendiente = 1, resultado = NULL WHERE id = ?")
      .bind(nuevoNombre, general, JSON.stringify(reglas), l.id),
    registrar(env.DB, yo, hizo),
  ]);
  return volver("ok=cambio");
}
