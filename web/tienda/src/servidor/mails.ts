// Mails de la compra (ADR 0032). El envío lo hace correo.ts (Brevo y, de respaldo, Resend; P-067).
// Sin ningún proveedor configurado no se manda nada: se anota en la bitácora del pedido qué mail se
// habría mandado (demo). Todo el texto se escapa.
import { enviar as enviarSolo, proveedores, type Mensaje } from "./correo.ts";
import { contarMail } from "./resumen-mails.ts";
import { evento } from "./pedidos.ts";
import { pesos } from "./consultas.ts";

const esc = (t: string) => t.replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" })[c]!);
const LOCAL = "Dr. Arturo Capdevila 1235, Córdoba";

type Datos = { id: string; numero: number; token: string; nombre: string; email: string; total: number };
type Linea = { nombre: string; cantidad: number; precio: number; disponible?: number | null };

/** Manda y anota en la cuenta del día por dónde salió (o que no salió). */
async function enviar(env: Env, m: Mensaje) {
  const r = await enviarSolo(env, m);
  await contarMail(env.DB, r.por);
  return r;
}

function plantilla(titulo: string, cuerpo: string, boton?: { texto: string; url: string }) {
  return `<!doctype html><html lang="es"><body style="margin:0;background:#f3efe7;font-family:Arial,sans-serif;color:#1c2733">
  <div style="max-width:560px;margin:0 auto;padding:24px 16px">
    <div style="background:#1c2733;color:#f3efe7;padding:16px 20px;font-size:20px;font-weight:bold;letter-spacing:.5px">COMERCIO EJEMPLO</div>
    <div style="height:5px;background:#6fb233"></div>
    <div style="background:#fff;padding:24px 20px;border:1px solid #ddd5c6;border-top:0">
      <h1 style="margin:0 0 12px;font-size:22px">${esc(titulo)}</h1>${cuerpo}
      ${boton ? `<p style="margin:24px 0 0"><a href="${esc(boton.url)}" style="background:#d42a1c;color:#fff;padding:12px 18px;text-decoration:none;font-weight:bold;border-radius:4px">${esc(boton.texto)}</a></p>` : ""}
    </div>
    <p style="font-size:12px;color:#6c6a63;margin-top:16px">Comercio Ejemplo · ${LOCAL} · 0351 478-7185</p>
  </div></body></html>`;
}

const tabla = (lineas: Linea[]) => `<table style="width:100%;border-collapse:collapse;font-size:14px">${lineas.map((l) =>
  `<tr><td style="padding:6px 0;border-bottom:1px solid #eee">${l.cantidad} × ${esc(l.nombre)}${l.disponible != null && l.disponible < l.cantidad ? ` <b style="color:#d42a1c">(hay ${l.disponible})</b>` : ""}</td><td style="text-align:right;border-bottom:1px solid #eee">${pesos(l.precio * l.cantidad)}</td></tr>`).join("")}</table>`;

async function mandar(env: Env, p: Datos, asunto: string, html: string, texto: string) {
  if (!proveedores(env).length) { await evento(env.DB, p.id, `mail NO enviado (sin proveedor de mails): «${asunto}» a ${p.email}`); return; }
  if (esDePrueba(p.email)) { await evento(env.DB, p.id, `mail NO enviado (dirección de prueba): «${asunto}»`); return; }
  const r = await enviar(env, { para: p.email, asunto, html, texto, idem: `${p.id}-${asunto}` });
  await evento(env.DB, p.id, r.ok ? `mail enviado por ${r.detalle}: «${asunto}»` : `mail con error (${r.detalle}): «${asunto}»`);
}

/** Dominios reservados para pruebas (RFC 2606): nunca se les manda (los rebotes bajan la reputación). */
export const esDePrueba = (email: string) => /@(.+\.)?(example\.(com|net|org)|test|invalid|localhost)$/i.test(email.trim());

const nro = (n: number) => `W-${String(n).padStart(4, "0")}`;

export async function mailRecibido(env: Env, origen: string, p: Datos, lineas: Linea[]) {
  const url = `${origen}/pedido/${p.id}?t=${p.token}`;
  await mandar(env, p, `Recibimos tu pedido ${nro(p.numero)}`,
    plantilla("¡Recibimos tu pedido!", `<p>Hola ${esc(p.nombre)}, ya está pago. Te avisamos cuando esté listo para retirar en ${LOCAL}.</p>${tabla(lineas)}<p style="text-align:right;font-weight:bold">Total ${pesos(p.total)}</p>`, { texto: "Ver mi pedido", url }),
    `Hola ${p.nombre}, recibimos tu pedido ${nro(p.numero)} (total ${pesos(p.total)}). Te avisamos cuando esté listo. ${url}`);
}

export async function mailListo(env: Env, origen: string, p: Datos) {
  const url = `${origen}/pedido/${p.id}?t=${p.token}`;
  await mandar(env, p, `Tu pedido ${nro(p.numero)} está listo para retirar`,
    plantilla("Tu pedido está listo para retirar", `<p>Hola ${esc(p.nombre)}, ya lo tenemos preparado. Pasá a retirarlo por ${LOCAL} con el número <b>${nro(p.numero)}</b> y tu nombre.</p>`, { texto: "Ver mi pedido", url }),
    `Hola ${p.nombre}, tu pedido ${nro(p.numero)} está listo para retirar en ${LOCAL}. ${url}`);
}

export async function mailFaltante(env: Env, origen: string, p: Datos, lineas: Linea[]) {
  const url = `${origen}/pedido/${p.id}?t=${p.token}`;
  await mandar(env, p, `Tu pedido ${nro(p.numero)}: falta algo`,
    plantilla("Nos falta algo de tu pedido", `<p>Hola ${esc(p.nombre)}, al prepararlo vimos que no tenemos todo:</p>${tabla(lineas)}<p>Elegí qué preferís: esperar a que llegue, otro producto o la devolución de lo que falta.</p>`, { texto: "Elegir qué hacemos", url }),
    `Hola ${p.nombre}, falta algo de tu pedido ${nro(p.numero)}. Elegí qué hacemos: ${url}`);
}

export async function mailRecordatorio(env: Env, origen: string, p: Datos) {
  const url = `${origen}/pedido/${p.id}?t=${p.token}`;
  await mandar(env, p, `Te esperamos: tu pedido ${nro(p.numero)} sigue listo`,
    plantilla("Tu pedido te está esperando", `<p>Hola ${esc(p.nombre)}, tu pedido sigue listo para retirar en ${LOCAL}.</p>`, { texto: "Ver mi pedido", url }),
    `Hola ${p.nombre}, tu pedido ${nro(p.numero)} sigue listo para retirar. ${url}`);
}

/** Código para confirmar el mail (crear la cuenta), cambiar la contraseña o el ingreso del equipo. */
export async function mailCodigo(env: Env, email: string, codigo: string, para: "alta" | "clave" | "equipo" = "alta"): Promise<boolean> {
  if (!proveedores(env).length || esDePrueba(email)) { console.log("mail de código NO enviado (sin proveedor o dirección de prueba)"); return false; }
  const titulo = { alta: "Confirmá tu mail", clave: "Cambiá tu contraseña", equipo: "Tu código de ingreso" }[para];
  const que = { alta: "para confirmar tu mail y crear tu cuenta", clave: "para elegir una contraseña nueva", equipo: "para entrar a la administración de la tienda" }[para];
  const html = plantilla(titulo, `<p>Tu código ${que} es:</p><p style="font-size:32px;font-weight:bold;letter-spacing:6px;margin:8px 0">${codigo}</p><p>Vence en 10 minutos. Si no lo pediste, ignorá este mail: nadie puede entrar sin él.</p>`);
  const r = await enviar(env, { para: email, asunto: `${titulo}: ${codigo}`, html, texto: `Tu código ${que} en Comercio Ejemplo es ${codigo}. Vence en 10 minutos.` });
  if (!r.ok) console.log(`mail de código con error: ${r.detalle}`);
  return r.ok;
}

/** Aviso suelto (no atado a un pedido): alta de mayorista aprobada, sumado al equipo. */
export async function mailAviso(env: Env, email: string, titulo: string, html: string, texto: string, boton?: { texto: string; url: string }): Promise<boolean> {
  if (!proveedores(env).length || esDePrueba(email)) { console.log(`aviso NO enviado (sin proveedor o dirección de prueba): «${titulo}»`); return false; }
  const r = await enviar(env, { para: email, asunto: titulo, html: plantilla(titulo, html, boton), texto });
  if (!r.ok) console.log(`aviso con error: ${r.detalle}`);
  return r.ok;
}
export { esc as escHtml };
