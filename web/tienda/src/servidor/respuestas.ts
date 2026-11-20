// Respuestas de la API: sin detalles internos hacia afuera (los errores van al log del Worker).
export const json = (datos: unknown, estado = 200) =>
  Response.json(datos, { status: estado, headers: { "Cache-Control": "no-store" } });
export const error = (estado: number, mensaje: string) => json({ error: mensaje }, estado);

/** Lee el cuerpo con tope de tamaño (corta antes de cargar todo en memoria si viene más). */
export async function cuerpoConTope(req: Request, maxBytes: number): Promise<ArrayBuffer | null> {
  const largo = Number(req.headers.get("content-length") || "0");
  if (largo > maxBytes) return null;
  if (!req.body) return new ArrayBuffer(0);
  const lector = req.body.getReader();
  const partes: Uint8Array[] = [];
  let total = 0;
  for (;;) {
    const { done, value } = await lector.read();
    if (done) break;
    total += value.byteLength;
    if (total > maxBytes) { await lector.cancel(); return null; }
    partes.push(value);
  }
  const out = new Uint8Array(total);
  let o = 0;
  for (const p of partes) { out.set(p, o); o += p.byteLength; }
  return out.buffer;
}
