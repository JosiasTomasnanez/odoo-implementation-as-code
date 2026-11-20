// Panel de pedidos para los empleados (fase 4). Dos llaves:
//  1. El DISPOSITIVO (PC o tablet del local) se habilita una vez con el código de alta
//     (secreto PANEL_CODIGO_ALTA, lo sabe solo el administrador). Queda una cookie larga.
//  2. El EMPLEADO elige su nombre y pone su PIN (el de la caja, de Odoo). Sesión corta.
// Las cookies son HttpOnly, Secure, SameSite=Strict y solo para /panel y /api/panel. En la base
// se guarda el hash de cada token, nunca el token. Los intentos fallidos se frenan.

const enc = new TextEncoder();
export const COOKIE_DISP = "cf_disp";
export const COOKIE_SES = "cf_panel";
const HORAS_SESION = 12;

const hex = (b: ArrayBuffer | Uint8Array) => [...new Uint8Array(b)].map((x) => x.toString(16).padStart(2, "0")).join("");
export const aleatorio = (bytes = 32) => hex(crypto.getRandomValues(new Uint8Array(bytes)));
export async function sha256(t: string) { return hex(await crypto.subtle.digest("SHA-256", enc.encode(t))); }

export async function hashPin(pepper: string, empleadoId: number, pin: string): Promise<string> {
  const k = await crypto.subtle.importKey("raw", enc.encode(pepper), { name: "HMAC", hash: "SHA-256" }, false, ["sign"]);
  return hex(await crypto.subtle.sign("HMAC", k, enc.encode(`${empleadoId}:${pin}`)));
}

export function iguales(a: string, b: string): boolean {
  if (a.length !== b.length) return false;
  let d = 0;
  for (let i = 0; i < a.length; i++) d |= a.charCodeAt(i) ^ b.charCodeAt(i);
  return d === 0;
}

export function leerCookie(req: Request, nombre: string): string | null {
  const c = req.headers.get("cookie") ?? "";
  for (const parte of c.split(";")) {
    const [k, ...v] = parte.trim().split("=");
    if (k === nombre) { const valor = v.join("="); return /^[0-9a-f]{64}$/.test(valor) ? valor : null; }
  }
  return null;
}

export function cookie(nombre: string, valor: string, segundos: number, ruta = "/"): string {
  return `${nombre}=${valor}; Path=${ruta}; Max-Age=${segundos}; HttpOnly; Secure; SameSite=Strict`;
}

export type Dispositivo = { id: string; nombre: string };
export type Sesion = { empleado_id: number; nombre: string; dispositivo: Dispositivo };

export async function dispositivo(db: D1Database, req: Request): Promise<Dispositivo | null> {
  const t = leerCookie(req, COOKIE_DISP);
  if (!t) return null;
  return db.prepare("SELECT id, nombre FROM dispositivos WHERE token_hash = ? AND revocado IS NULL").bind(await sha256(t)).first<Dispositivo>();
}

export async function sesion(db: D1Database, req: Request): Promise<Sesion | null> {
  const d = await dispositivo(db, req);
  const t = leerCookie(req, COOKIE_SES);
  if (!d || !t) return null;
  const s = await db.prepare(`SELECT s.empleado_id, e.nombre FROM sesiones_panel s JOIN empleados e ON e.id_odoo = s.empleado_id
      WHERE s.token_hash = ? AND s.dispositivo_id = ? AND s.vence > ? AND e.activo = 1`)
    .bind(await sha256(t), d.id, new Date().toISOString()).first<{ empleado_id: number; nombre: string }>();
  return s ? { ...s, dispositivo: d } : null;
}

/** true si la clave está bloqueada por muchos fallos. */
export async function bloqueado(db: D1Database, clave: string): Promise<boolean> {
  const r = await db.prepare("SELECT hasta FROM intentos WHERE clave = ?").bind(clave).first<{ hasta: string | null }>();
  return !!r?.hasta && r.hasta > new Date().toISOString();
}

/** Anota un fallo; a los `max` fallos bloquea `minutos`. */
export async function fallo(db: D1Database, clave: string, max = 5, minutos = 10): Promise<void> {
  const hasta = new Date(Date.now() + minutos * 60_000).toISOString();
  const ahora = new Date().toISOString();
  await db.prepare(`INSERT INTO intentos (clave, fallos, hasta, visto) VALUES (?, 1, NULL, ?)
      ON CONFLICT(clave) DO UPDATE SET fallos = CASE WHEN intentos.hasta IS NOT NULL AND intentos.hasta < ? THEN 1 ELSE intentos.fallos + 1 END,
        hasta = CASE WHEN intentos.fallos + 1 >= ? THEN ? ELSE intentos.hasta END, visto = excluded.visto`)
    .bind(clave, ahora, ahora, max, hasta).run();
}

export async function acierto(db: D1Database, clave: string): Promise<void> {
  await db.prepare("DELETE FROM intentos WHERE clave = ?").bind(clave).run();
}

export async function crearSesion(db: D1Database, empleadoId: number, dispositivoId: string): Promise<string> {
  const token = aleatorio();
  const vence = new Date(Date.now() + HORAS_SESION * 3_600_000).toISOString();
  await db.batch([
    db.prepare("DELETE FROM sesiones_panel WHERE vence < ?").bind(new Date().toISOString()),
    db.prepare("INSERT INTO sesiones_panel (token_hash, empleado_id, dispositivo_id, vence) VALUES (?, ?, ?, ?)")
      .bind(await sha256(token), empleadoId, dispositivoId, vence),
  ]);
  return token;
}
export const SEGUNDOS_SESION = HORAS_SESION * 3600;
