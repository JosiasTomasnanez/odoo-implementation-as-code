// Cuentas de clientes (fase 6; contraseña desde el 10/11): se entra con mail y contraseña o con
// Google. El mail se verifica una vez con un código de 6 dígitos al crear la cuenta, y «Olvidé mi
// contraseña» manda otro. La sesión es una cookie HttpOnly (30 días); en la base se guarda solo el
// hash del token, del código y de la contraseña.
import { aleatorio, sha256, iguales, bloqueado, fallo, acierto } from "./panel.ts";
import { claveCorrecta } from "./claves.ts";

export const COOKIE_CLI = "cf_cliente";
export const COOKIE_ALTA = "cf_alta"; // ata el código de «crear cuenta» al navegador que lo pidió
const DIAS = 30;
export type Cliente = { id: string; email: string; nombre: string | null; telefono: string | null; mayorista: string | null; lista_id: number | null };

export function cookieCliente(valor: string, segundos: number) {
  // Lax: se mantiene al volver desde el link de un mail. Los POST igual exigen el mismo origen.
  return `${COOKIE_CLI}=${valor}; Path=/; Max-Age=${segundos}; HttpOnly; Secure; SameSite=Lax`;
}

function leer(req: Request): string | null {
  for (const parte of (req.headers.get("cookie") ?? "").split(";")) {
    const [k, v] = parte.trim().split("=");
    if (k === COOKIE_CLI && v && /^[0-9a-f]{64}$/.test(v)) return v;
  }
  return null;
}

export async function clienteActual(db: D1Database, req: Request): Promise<Cliente | null> {
  const t = leer(req);
  if (!t) return null;
  return db.prepare(`SELECT c.id, c.email, c.nombre, c.telefono, c.mayorista, c.lista_id FROM sesiones_cliente s
      JOIN clientes c ON c.id = s.cliente_id WHERE s.token_hash = ? AND s.vence > ?`)
    .bind(await sha256(t), new Date().toISOString()).first<Cliente>();
}

export type Proposito = "alta" | "clave" | "equipo";

/** Código nuevo para ese mail (reemplaza al anterior). En «alta» viaja el hash de la contraseña
 *  elegida: la cuenta se crea recién cuando el código confirma que el mail es suyo. Con `atado`
 *  (un valor al azar en una cookie del navegador que lo pidió) el código solo vale en ese navegador:
 *  otro pedido para el mismo mail no puede colar su contraseña. */
export async function nuevoCodigo(db: D1Database, email: string, proposito: Proposito = "alta", claveHash: string | null = null, atado = ""): Promise<string> {
  const n = crypto.getRandomValues(new Uint32Array(1))[0] % 1_000_000;
  const codigo = String(n).padStart(6, "0");
  await db.prepare(`INSERT INTO codigos_ingreso (email, codigo_hash, vence, intentos, proposito, clave_hash) VALUES (?, ?, ?, 0, ?, ?)
      ON CONFLICT(email) DO UPDATE SET codigo_hash = excluded.codigo_hash, vence = excluded.vence, intentos = 0,
        proposito = excluded.proposito, clave_hash = excluded.clave_hash`)
    .bind(email, await sha256(`${email}:${codigo}${atado ? `:${atado}` : ""}`), new Date(Date.now() + 10 * 60_000).toISOString(), proposito, claveHash).run();
  return codigo;
}

/** Tope que NO se reinicia al pedir otro código, por mail + IP (así un extraño no le bloquea la
 *  cuenta al dueño): 10 fallos → 24 h. Y por mail: como máximo 20 códigos por día (5 intentos cada
 *  uno), contra quien prueba desde muchas IP. */
export const claveFallos = (email: string, ip: string) => `cuenta:${email}:${ip}`;
export const claveCodigos = (email: string) => `codigos:${email}`;
export const codigosAgotados = (db: D1Database, email: string) => bloqueado(db, claveCodigos(email));
export const contarCodigo = (db: D1Database, email: string) => fallo(db, claveCodigos(email), 20, 24 * 60);

/** El código es el último enviado, no venció y no se pasó de 5 intentos (después se borra):
 *  y es para ese trámite: devuelve la contraseña elegida (en «alta»), o null. El intento se descuenta y se
 *  comprueba en una sola operación (sin carreras entre pedidos). */
export async function codigoValido(db: D1Database, email: string, codigo: string, ip: string, proposito: Proposito, atado = ""): Promise<{ clave_hash: string | null } | null> {
  if (await bloqueado(db, claveFallos(email, ip))) return null;
  const r = await db.prepare(`UPDATE codigos_ingreso SET intentos = intentos + 1
      WHERE email = ? AND proposito = ? AND intentos < 5 AND vence > ? RETURNING codigo_hash, clave_hash`).bind(email, proposito, new Date().toISOString())
    .first<{ codigo_hash: string; clave_hash: string | null }>();
  if (!r) return null; // sin código vigente no hay nada que adivinar (y no se cuenta como fallo)
  if (!/^\d{6}$/.test(codigo) || !iguales(await sha256(`${email}:${codigo}${atado ? `:${atado}` : ""}`), r.codigo_hash)) {
    await fallo(db, claveFallos(email, ip), 10, 24 * 60);
    return null;
  }
  await db.prepare("DELETE FROM codigos_ingreso WHERE email = ?").bind(email).run();
  await acierto(db, claveFallos(email, ip));
  return { clave_hash: r.clave_hash };
}

/** Mail y contraseña: el id del cliente si es correcta. 8 fallos por mail + IP → 15 minutos, y
 *  30 por mail desde cualquier IP → 1 hora (contra quien prueba desde muchas IP). */
export async function conClave(db: D1Database, email: string, clave: string, ip: string): Promise<string | null> {
  const k = `clave:${email}:${ip}`, km = `clave:${email}`;
  if (await bloqueado(db, k) || await bloqueado(db, km)) return null;
  const c = await db.prepare("SELECT id, clave_hash FROM clientes WHERE email = ?").bind(email).first<{ id: string; clave_hash: string | null }>();
  if (!(await claveCorrecta(clave, c?.clave_hash))) { await fallo(db, k, 8, 15); await fallo(db, km, 30, 60); return null; }
  await acierto(db, k);
  await acierto(db, km);
  return c!.id;
}

/** Cuenta de Google (mail verificado por Google): por su id de Google, si no por el mail (se
 *  vincula), si no se crea. */
export async function deGoogle(db: D1Database, sub: string, email: string, nombre: string | null): Promise<void> {
  const ya = await db.prepare("SELECT id FROM clientes WHERE google_sub = ?").bind(sub).first<{ id: string }>();
  if (ya) return;
  await db.prepare("INSERT INTO clientes (id, email, nombre, creado, google_sub) VALUES (?, ?, ?, ?, ?) ON CONFLICT(email) DO UPDATE SET google_sub = excluded.google_sub, nombre = COALESCE(clientes.nombre, excluded.nombre)")
    .bind(aleatorio(16), email, nombre, new Date().toISOString(), sub).run();
}

/** Busca o crea el cliente (el mail ya está verificado) y le abre una sesión. Con `claveHash`, esa
 *  pasa a ser su contraseña. Devuelve el token. */
export async function entrar(db: D1Database, email: string, claveHash: string | null = null): Promise<string> {
  const ahora = new Date().toISOString();
  await db.prepare("INSERT INTO clientes (id, email, creado, clave_hash) VALUES (?, ?, ?, ?) ON CONFLICT(email) DO UPDATE SET clave_hash = COALESCE(excluded.clave_hash, clientes.clave_hash)")
    .bind(aleatorio(16), email, ahora, claveHash).run();
  const c = await db.prepare("SELECT id FROM clientes WHERE email = ?").bind(email).first<{ id: string }>();
  const token = aleatorio();
  await db.batch([
    db.prepare("DELETE FROM sesiones_cliente WHERE vence < ?").bind(ahora),
    // Contraseña nueva: se cierran las sesiones abiertas de esa cuenta en otros lados y se levanta
    // el bloqueo por intentos (el código del mail prueba que es suya)
    db.prepare("DELETE FROM sesiones_cliente WHERE cliente_id = ? AND ? IS NOT NULL").bind(c!.id, claveHash),
    db.prepare("DELETE FROM intentos WHERE (clave = ? OR substr(clave, 1, ?) = ?) AND ? IS NOT NULL")
      .bind(`clave:${email}`, `clave:${email}:`.length, `clave:${email}:`, claveHash),
    db.prepare("INSERT INTO sesiones_cliente (token_hash, cliente_id, vence) VALUES (?, ?, ?)")
      .bind(await sha256(token), c!.id, new Date(Date.now() + DIAS * 86_400_000).toISOString()),
    // Los pedidos que hizo antes con ese mail pasan a ser suyos (el mail está verificado)
    db.prepare("UPDATE pedidos SET cliente_id = ? WHERE email = ? AND cliente_id IS NULL").bind(c!.id, email),
  ]);
  return token;
}
export const SEGUNDOS_CLIENTE = DIAS * 86400;

export async function salir(db: D1Database, req: Request) {
  const t = leer(req);
  if (t) await db.prepare("DELETE FROM sesiones_cliente WHERE token_hash = ?").bind(await sha256(t)).run();
}

/** CUIT con su dígito verificador (módulo 11). */
export function cuitValido(c: string): boolean {
  const d = c.replace(/\D/g, "");
  if (!/^(20|23|24|25|26|27|30|33|34)\d{9}$/.test(d)) return false;
  const pesos = [5, 4, 3, 2, 7, 6, 5, 4, 3, 2];
  const s = pesos.reduce((t, p, i) => t + p * Number(d[i]), 0);
  let v = 11 - (s % 11);
  if (v === 11) v = 0;
  if (v === 10) return false;
  return v === Number(d[10]);
}

