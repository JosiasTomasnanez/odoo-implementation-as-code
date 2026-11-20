// Contraseñas: PBKDF2-SHA256 con sal propia (100.000 vueltas, el máximo de Workers). Se guarda
// «pbkdf2$vueltas$sal$hash»; nunca la contraseña.
import { iguales } from "./panel.ts";

const VUELTAS = 100_000;
const enc = new TextEncoder();
const hex = (b: ArrayBuffer | Uint8Array) => [...new Uint8Array(b)].map((x) => x.toString(16).padStart(2, "0")).join("");
const deHex = (h: string) => new Uint8Array(h.match(/../g)!.map((x) => parseInt(x, 16))) as Uint8Array<ArrayBuffer>;

async function derivar(clave: string, sal: Uint8Array<ArrayBuffer>, vueltas: number): Promise<string> {
  const k = await crypto.subtle.importKey("raw", enc.encode(clave.normalize("NFC")), "PBKDF2", false, ["deriveBits"]);
  return hex(await crypto.subtle.deriveBits({ name: "PBKDF2", hash: "SHA-256", salt: sal, iterations: vueltas }, k, 256));
}

export async function hashClave(clave: string): Promise<string> {
  const sal = crypto.getRandomValues(new Uint8Array(16));
  return ["pbkdf2", VUELTAS, hex(sal), await derivar(clave, sal, VUELTAS)].join("$");
}

const FORMA = /^pbkdf2\$(\d{4,6})\$([0-9a-f]{32})\$([0-9a-f]{64})$/;

export async function claveCorrecta(clave: string, guardado: string | null | undefined): Promise<boolean> {
  const m = FORMA.exec(guardado ?? "");
  if (!m) {
    await derivar(clave, new Uint8Array(16), VUELTAS); // tarda lo mismo exista o no la cuenta
    return false;
  }
  return iguales(await derivar(clave, deHex(m[2]), Number(m[1])), m[3]);
}

/** Reglas mínimas y amigables: 8 caracteres o más, nada demasiado obvio, no el mail. */
export function claveAceptable(clave: string, email = ""): string | null {
  if (clave.length < 8) return "La contraseña tiene que tener al menos 8 caracteres.";
  if (clave.length > 200) return "La contraseña es demasiado larga.";
  if (/^(.)\1+$/.test(clave) || /^(0?123456789?|12345678|password|contraseña|qwerty)/i.test(clave)) return "Esa contraseña es muy fácil de adivinar.";
  if (email && clave.toLowerCase() === email.toLowerCase()) return "La contraseña no puede ser tu mail.";
  return null;
}
