// Datos que el cliente puede cambiar solo, y el registro de cada cambio (qué decía y qué dice).
// Lo que define la cuenta mayorista (CUIT, razón social, condición de IVA, actividad) NO se cambia
// desde acá: se pide al comercio, porque de eso dependen la aprobación y la factura.
export const CAMPOS = { nombre: "Nombre", contacto: "Contacto", telefono: "Teléfono", direccion: "Dirección", localidad: "Localidad" } as const;
export type Campo = keyof typeof CAMPOS;
export type Cambio = { cliente_id: string; cuando: string; campo: string; antes: string | null; despues: string | null };

/** Qué campos cambian de verdad (vacío y null son lo mismo). */
export function diferencias(antes: Partial<Record<Campo, string | null>>, nuevos: Partial<Record<Campo, string>>) {
  return (Object.keys(nuevos) as Campo[])
    .map((campo) => ({ campo, antes: antes[campo] || null, despues: nuevos[campo] || null }))
    .filter((d) => d.antes !== d.despues);
}

/** Guarda los datos nuevos y anota cada cambio, todo junto. Devuelve cuántos campos cambiaron. */
export async function guardarDatos(db: D1Database, clienteId: string, nuevos: Partial<Record<Campo, string>>): Promise<number> {
  const campos = (Object.keys(nuevos) as Campo[]).filter((c) => Object.hasOwn(CAMPOS, c));
  if (!campos.length) return 0;
  const antes = await db.prepare(`SELECT ${campos.join(", ")} FROM clientes WHERE id = ?`).bind(clienteId).first<Record<Campo, string | null>>();
  if (!antes) return 0;
  const difs = diferencias(antes, nuevos);
  if (!difs.length) return 0;
  const ahora = new Date().toISOString();
  await db.batch([
    db.prepare(`UPDATE clientes SET ${difs.map((d) => `${d.campo} = ?`).join(", ")}, cambios_sin_ver = 1 WHERE id = ?`).bind(...difs.map((d) => d.despues), clienteId),
    ...difs.map((d) => db.prepare("INSERT INTO cambios_cliente (cliente_id, cuando, campo, antes, despues) VALUES (?, ?, ?, ?, ?)").bind(clienteId, ahora, d.campo, d.antes, d.despues)),
  ]);
  return difs.length;
}
