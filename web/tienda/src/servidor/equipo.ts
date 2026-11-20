// Equipo de la tienda (fase 7): entra a /admin con mail y contraseña; la primera vez en cada equipo
// (PC o celular) además con un código por mail, y ese equipo queda de confianza 60 días. Sesión de
// 12 horas. Cookies HttpOnly, Secure, SameSite=Strict; en la base solo hashes.
import { aleatorio, sha256, leerCookie, bloqueado, fallo, acierto } from "./panel.ts";
import { claveCorrecta } from "./claves.ts";

export const ROLES = {
  admin: "Administración (todo, también el equipo)",
  mayoristas: "Mayoristas y listas de clientes",
  marketing: "Marketing (próximamente)",
} as const;
export type Rol = keyof typeof ROLES;
export const esRol = (r: string): r is Rol => Object.prototype.hasOwnProperty.call(ROLES, r);

export const COOKIE_EQ = "cf_equipo";
export const COOKIE_CONF = "cf_equipo_conf";
const HORAS = 12, DIAS_CONF = 60;
export const SEGUNDOS_EQ = HORAS * 3600, SEGUNDOS_CONF = DIAS_CONF * 86400;
export const cookieEq = (nombre: string, valor: string, segundos: number) =>
  `${nombre}=${valor}; Path=/; Max-Age=${segundos}; HttpOnly; Secure; SameSite=Strict`;

export type Miembro = { id: string; email: string; nombre: string; roles: Rol[] };
const deFila = (r: { id: string; email: string; nombre: string; roles: string }): Miembro =>
  ({ id: r.id, email: r.email, nombre: r.nombre, roles: r.roles.split(",").filter(esRol) });
export const puede = (m: Miembro | null, rol: Rol) => !!m && (m.roles.includes("admin") || m.roles.includes(rol));

export async function miembroActual(db: D1Database, req: Request): Promise<Miembro | null> {
  const t = leerCookie(req, COOKIE_EQ);
  if (!t) return null;
  const r = await db.prepare(`SELECT e.id, e.email, e.nombre, e.roles FROM sesiones_equipo s JOIN equipo e ON e.id = s.miembro_id
      WHERE s.token_hash = ? AND s.vence > ? AND e.activo = 1`).bind(await sha256(t), new Date().toISOString())
    .first<{ id: string; email: string; nombre: string; roles: string }>();
  return r ? deFila(r) : null;
}

/** Mail y contraseña del equipo: el id si es correcta. 8 fallos por mail + IP → 15 minutos; 30 por
 *  mail desde cualquier IP → 1 hora, salvo en un navegador de confianza de esa persona (así nadie
 *  puede dejar afuera al dueño de la cuenta probando contraseñas desde otro lado). */
export async function claveEquipo(db: D1Database, req: Request, email: string, clave: string, ip: string): Promise<string | null> {
  const k = `equipo:${email}:${ip}`, km = `equipo:${email}`;
  const m = await db.prepare("SELECT id, clave_hash FROM equipo WHERE email = ? AND activo = 1").bind(email).first<{ id: string; clave_hash: string | null }>();
  const confiable = !!m && await deConfianza(db, req, m.id);
  if (await bloqueado(db, k) || (!confiable && await bloqueado(db, km))) return null;
  if (!(await claveCorrecta(clave, m?.clave_hash))) { await fallo(db, k, 8, 15); await fallo(db, km, 30, 60); return null; }
  await acierto(db, k);
  await acierto(db, km);
  return m!.id;
}

/** ¿Este equipo (navegador) ya confirmó con el código del mail para esa persona? */
export async function deConfianza(db: D1Database, req: Request, miembroId: string): Promise<boolean> {
  const t = leerCookie(req, COOKIE_CONF);
  if (!t) return false;
  return !!(await db.prepare("SELECT 1 FROM confianza_equipo WHERE token_hash = ? AND miembro_id = ? AND vence > ?")
    .bind(await sha256(t), miembroId, new Date().toISOString()).first());
}

export async function confiar(db: D1Database, miembroId: string): Promise<string> {
  const t = aleatorio();
  await db.prepare("INSERT INTO confianza_equipo (token_hash, miembro_id, vence) VALUES (?, ?, ?)")
    .bind(await sha256(t), miembroId, new Date(Date.now() + SEGUNDOS_CONF * 1000).toISOString()).run();
  return t;
}

export async function abrirSesion(db: D1Database, miembroId: string): Promise<string> {
  const t = aleatorio(), ahora = new Date().toISOString();
  await db.batch([
    db.prepare("DELETE FROM sesiones_equipo WHERE vence < ?").bind(ahora),
    db.prepare("DELETE FROM confianza_equipo WHERE vence < ?").bind(ahora),
    db.prepare("INSERT INTO sesiones_equipo (token_hash, miembro_id, vence) VALUES (?, ?, ?)")
      .bind(await sha256(t), miembroId, new Date(Date.now() + SEGUNDOS_EQ * 1000).toISOString()),
  ]);
  return t;
}

export async function cerrarSesion(db: D1Database, req: Request) {
  const t = leerCookie(req, COOKIE_EQ);
  if (t) await db.prepare("DELETE FROM sesiones_equipo WHERE token_hash = ?").bind(await sha256(t)).run();
}

/** Al dar de baja o cambiar los roles: se cierran sus sesiones (vuelve a entrar con lo nuevo). */
export const cortarSesiones = (db: D1Database, miembroId: string) =>
  db.prepare("DELETE FROM sesiones_equipo WHERE miembro_id = ?").bind(miembroId);

export const registrar = (db: D1Database, quien: Miembro, que: string) =>
  db.prepare("INSERT INTO registro_admin (cuando, quien, que) VALUES (?, ?, ?)").bind(new Date().toISOString(), `${quien.nombre} <${quien.email}>`, que.slice(0, 500));
