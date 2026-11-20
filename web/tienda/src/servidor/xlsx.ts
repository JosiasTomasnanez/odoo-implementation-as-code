// Planilla .xlsx mínima, sin dependencias (Office Open XML en un ZIP sin comprimir). Alcanza para
// listas: textos, números, fórmulas, estilos fijos, anchos, fila fija, filtro y validación de datos.
// Se escribe a mano para no sumar una librería grande al Worker; se abre en Excel, LibreOffice y
// Google Sheets.

export type Celda =
  | { t: "s"; v: string; e?: number }            // texto
  | { t: "n"; v: number; e?: number }            // número
  | { t: "f"; v: string; e?: number }            // fórmula (sin «=»)
  | { t: "_"; e?: number };                      // vacía con estilo

export type Hoja = {
  nombre: string;
  anchos: number[];
  filas: Celda[][];
  alturas?: Record<number, number>;              // fila (1…) → alto en puntos
  fijarFilas?: number;                           // cuántas filas quedan fijas arriba
  filtro?: string;                               // rango, p. ej. "A7:N120"
  combinar?: string[];                           // rangos combinados
  validaciones?: { rango: string; formula: string; titulo: string; mensaje: string }[];
  horizontal?: boolean;                          // impresión apaisada, ajustada al ancho
};

const esc = (t: string) => t.replace(/[&<>"]/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" })[c]!)
  // fuera los caracteres de control que XML no admite
  .replace(/[\u0000-\u0008\u000b\u000c\u000e-\u001f]/g, "");

export const col = (n: number) => { let s = ""; for (n++; n; n = Math.floor((n - 1) / 26)) s = String.fromCharCode(65 + ((n - 1) % 26)) + s; return s; };

function hojaXml(h: Hoja): string {
  const cols = h.anchos.map((w, i) => `<col min="${i + 1}" max="${i + 1}" width="${w}" customWidth="1"/>`).join("");
  const filas = h.filas.map((fila, r) => {
    const n = r + 1;
    const alto = h.alturas?.[n] ? ` ht="${h.alturas[n]}" customHeight="1"` : "";
    const celdas = fila.map((c, i) => {
      const ref = `${col(i)}${n}`, s = c.e ? ` s="${c.e}"` : "";
      if (c.t === "s") return `<c r="${ref}"${s} t="inlineStr"><is><t xml:space="preserve">${esc(c.v)}</t></is></c>`;
      if (c.t === "n") return Number.isFinite(c.v) ? `<c r="${ref}"${s}><v>${c.v}</v></c>` : `<c r="${ref}"${s}/>`;
      if (c.t === "f") return `<c r="${ref}"${s}><f>${esc(c.v)}</f></c>`;
      return `<c r="${ref}"${s}/>`;
    }).join("");
    return `<row r="${n}"${alto}>${celdas}</row>`;
  }).join("");
  const fijo = h.fijarFilas
    ? `<sheetViews><sheetView workbookViewId="0" showGridLines="0"><pane ySplit="${h.fijarFilas}" topLeftCell="A${h.fijarFilas + 1}" activePane="bottomLeft" state="frozen"/></sheetView></sheetViews>`
    : `<sheetViews><sheetView workbookViewId="0" showGridLines="0"/></sheetViews>`;
  const filtro = h.filtro ? `<autoFilter ref="${h.filtro}"/>` : "";
  const comb = h.combinar?.length ? `<mergeCells count="${h.combinar.length}">${h.combinar.map((r) => `<mergeCell ref="${r}"/>`).join("")}</mergeCells>` : "";
  const val = h.validaciones?.length
    ? `<dataValidations count="${h.validaciones.length}">${h.validaciones.map((v) =>
        `<dataValidation type="custom" allowBlank="1" showErrorMessage="1" showInputMessage="1" errorTitle="${esc(v.titulo)}" error="${esc(v.mensaje)}" promptTitle="${esc(v.titulo)}" prompt="${esc(v.mensaje)}" sqref="${v.rango}"><formula1>${esc(v.formula)}</formula1></dataValidation>`).join("")}</dataValidations>`
    : "";
  const pagina = h.horizontal ? `<pageMargins left="0.4" right="0.4" top="0.5" bottom="0.5" header="0.3" footer="0.3"/><pageSetup orientation="landscape" fitToWidth="1" fitToHeight="0"/>` : "";
  const ajuste = h.horizontal ? `<sheetPr><pageSetUpPr fitToPage="1"/></sheetPr>` : "";
  // Orden de los elementos según el esquema de OOXML (Excel es estricto)
  return `<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<worksheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main" xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships">${ajuste}${fijo}<sheetFormatPr defaultRowHeight="16"/><cols>${cols}</cols><sheetData>${filas}</sheetData>${filtro}${comb}${val}${pagina}</worksheet>`;
}

// El filtro de cada hoja también se declara como nombre oculto (así lo guarda Excel).
const absoluta = (r: string) => r.replace(/^([A-Z]+)(\d+)$/, (_m, c: string, f: string) => `$${c}$${f}`);
function nombres(hojas: Hoja[]): string {
  const n = hojas.map((h, i) => h.filtro
    ? `<definedName name="_xlnm._FilterDatabase" localSheetId="${i}" hidden="1">'${esc(h.nombre.slice(0, 31))}'!${h.filtro.split(":").map(absoluta).join(":")}</definedName>`
    : "").join("");
  return n ? `<definedNames>${n}</definedNames>` : "";
}

/** Arma el libro. `estilos` es el styles.xml completo (los índices de `e` apuntan a sus cellXfs). */
export function libro(hojas: Hoja[], estilos: string, titulo: string): Uint8Array {
  const archivos: [string, string][] = [
    ["[Content_Types].xml", `<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types"><Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/><Default Extension="xml" ContentType="application/xml"/><Override PartName="/xl/workbook.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet.main+xml"/><Override PartName="/xl/styles.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.styles+xml"/>${hojas.map((_, i) => `<Override PartName="/xl/worksheets/sheet${i + 1}.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.worksheet+xml"/>`).join("")}<Override PartName="/docProps/core.xml" ContentType="application/vnd.openxmlformats-package.core-properties+xml"/></Types>`],
    ["_rels/.rels", `<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships"><Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument" Target="xl/workbook.xml"/><Relationship Id="rId2" Type="http://schemas.openxmlformats.org/package/2006/relationships/metadata/core-properties" Target="docProps/core.xml"/></Relationships>`],
    ["docProps/core.xml", `<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<cp:coreProperties xmlns:cp="http://schemas.openxmlformats.org/package/2006/metadata/core-properties" xmlns:dc="http://purl.org/dc/elements/1.1/" xmlns:dcterms="http://purl.org/dc/terms/" xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"><dc:title>${esc(titulo)}</dc:title><dc:creator>Comercio Ejemplo</dc:creator><dcterms:created xsi:type="dcterms:W3CDTF">${new Date().toISOString().slice(0, 19)}Z</dcterms:created></cp:coreProperties>`],
    ["xl/workbook.xml", `<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<workbook xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main" xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships"><sheets>${hojas.map((h, i) => `<sheet name="${esc(h.nombre.slice(0, 31))}" sheetId="${i + 1}" r:id="rId${i + 1}"/>`).join("")}</sheets>${nombres(hojas)}</workbook>`],
    ["xl/_rels/workbook.xml.rels", `<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">${hojas.map((_, i) => `<Relationship Id="rId${i + 1}" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/worksheet" Target="worksheets/sheet${i + 1}.xml"/>`).join("")}<Relationship Id="rId${hojas.length + 1}" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/styles" Target="styles.xml"/></Relationships>`],
    ["xl/styles.xml", estilos],
    ...hojas.map((h, i): [string, string] => [`xl/worksheets/sheet${i + 1}.xml`, hojaXml(h)]),
  ];
  return zip(archivos.map(([n, t]) => [n, new TextEncoder().encode(t)]));
}

// ---------- ZIP sin comprimir («stored»): suficiente y sin dependencias ----------
const TABLA = (() => {
  const t = new Uint32Array(256);
  for (let n = 0; n < 256; n++) { let c = n; for (let k = 0; k < 8; k++) c = c & 1 ? 0xedb88320 ^ (c >>> 1) : c >>> 1; t[n] = c >>> 0; }
  return t;
})();
const crc32 = (d: Uint8Array) => { let c = 0xffffffff; for (const b of d) c = TABLA[(c ^ b) & 0xff] ^ (c >>> 8); return (c ^ 0xffffffff) >>> 0; };

function zip(archivos: [string, Uint8Array][]): Uint8Array {
  const partes: Uint8Array[] = [], central: Uint8Array[] = [];
  let pos = 0;
  for (const [nombre, datos] of archivos) {
    const n = new TextEncoder().encode(nombre), crc = crc32(datos);
    const loc = new DataView(new ArrayBuffer(30));
    loc.setUint32(0, 0x04034b50, true); loc.setUint16(4, 20, true); loc.setUint16(6, 0x0800, true);
    loc.setUint32(14, crc, true); loc.setUint32(18, datos.length, true); loc.setUint32(22, datos.length, true);
    loc.setUint16(26, n.length, true);
    const cen = new DataView(new ArrayBuffer(46));
    cen.setUint32(0, 0x02014b50, true); cen.setUint16(4, 20, true); cen.setUint16(6, 20, true); cen.setUint16(8, 0x0800, true);
    cen.setUint32(16, crc, true); cen.setUint32(20, datos.length, true); cen.setUint32(24, datos.length, true);
    cen.setUint16(28, n.length, true); cen.setUint32(42, pos, true);
    partes.push(new Uint8Array(loc.buffer), n, datos);
    central.push(new Uint8Array(cen.buffer), n);
    pos += 30 + n.length + datos.length;
  }
  const tamCentral = central.reduce((t, p) => t + p.length, 0);
  const fin = new DataView(new ArrayBuffer(22));
  fin.setUint32(0, 0x06054b50, true); fin.setUint16(8, archivos.length, true); fin.setUint16(10, archivos.length, true);
  fin.setUint32(12, tamCentral, true); fin.setUint32(16, pos, true);
  const todo = [...partes, ...central, new Uint8Array(fin.buffer)];
  const out = new Uint8Array(todo.reduce((t, p) => t + p.length, 0));
  let o = 0; for (const p of todo) { out.set(p, o); o += p.length; }
  return out;
}
