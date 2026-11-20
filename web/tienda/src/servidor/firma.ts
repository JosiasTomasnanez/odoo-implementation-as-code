// Firma de lo que manda el conector del local (ADR 0033): HMAC-SHA256 con una clave compartida
// (secreto CONECTOR_SECRETO), sobre fecha, método, ruta y el hash del cuerpo. Se rechaza lo viejo
// (más de 5 minutos) para que no se pueda reenviar una petición capturada.

const enc = new TextEncoder();
export const VENTANA_SEGUNDOS = 300;

export async function sha256Hex(datos: ArrayBuffer | Uint8Array<ArrayBuffer> | string): Promise<string> {
  const bytes = typeof datos === "string" ? enc.encode(datos) : datos;
  const h = await crypto.subtle.digest("SHA-256", bytes);
  return [...new Uint8Array(h)].map((b) => b.toString(16).padStart(2, "0")).join("");
}

function hexABytes(hex: string): Uint8Array<ArrayBuffer> | null {
  if (!/^[0-9a-f]{64}$/.test(hex)) return null;
  const out = new Uint8Array(32);
  for (let i = 0; i < 32; i++) out[i] = parseInt(hex.slice(i * 2, i * 2 + 2), 16);
  return out;
}

export function mensajeAFirmar(fecha: string, metodo: string, ruta: string, hashCuerpo: string): string {
  return `${fecha}.${metodo.toUpperCase()}.${ruta}.${hashCuerpo}`;
}

/** true si la firma es válida y reciente. La comparación es de tiempo constante (subtle.verify). */
export async function firmaValida(
  secreto: string, fecha: string | null, firma: string | null, metodo: string, ruta: string,
  cuerpo: ArrayBuffer, ahora = Date.now(),
): Promise<boolean> {
  if (!secreto || secreto.length < 32 || !fecha || !firma) return false;
  if (!/^\d{10}$/.test(fecha)) return false;
  if (Math.abs(ahora / 1000 - Number(fecha)) > VENTANA_SEGUNDOS) return false;
  const bytes = hexABytes(firma);
  if (!bytes) return false;
  const clave = await crypto.subtle.importKey("raw", enc.encode(secreto), { name: "HMAC", hash: "SHA-256" }, false, ["verify"]);
  const msg = mensajeAFirmar(fecha, metodo, ruta, await sha256Hex(cuerpo));
  return crypto.subtle.verify("HMAC", clave, bytes, enc.encode(msg));
}
