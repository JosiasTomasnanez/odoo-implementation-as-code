// Lista de precios mayorista en Excel (sitio mayorista, solo cuenta aprobada): los mismos datos y
// precios que la lista en pantalla (su lista de Odoo, mínimo y bulto), una fila por producto para
// poder filtrar y ordenar, y una columna «Cantidad» con su validación y el subtotal.
import { env } from "cloudflare:workers";
import { clienteActual } from "../../servidor/clientes";
import { conLista, contarPublicados, preciosDeLista, primeraValida, todos } from "../../servidor/consultas";
import { local } from "../../data/catalogo";
import { condiciones, listaDeOdoo, resumen } from "../../servidor/listas";
import { libro, type Celda } from "../../servidor/xlsx";

export const prerender = false;

// Índices de cellXfs (ver ESTILOS)
const E = { titulo: 1, sub: 2, cab: 3, txt: 4, cod: 5, ent: 6, pub: 7, suyo: 8, pct: 9, cant: 10, subt: 11, totEt: 12, tot: 13, nota: 14, hay: 15, no: 16 };
const ESTILOS = `<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<styleSheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main">
<numFmts count="1"><numFmt numFmtId="164" formatCode="&quot;$ &quot;#,##0.00"/></numFmts>
<fonts count="9">
<font><sz val="10"/><name val="Calibri"/></font>
<font><b/><sz val="16"/><color rgb="FF1C2733"/><name val="Calibri"/></font>
<font><sz val="10"/><color rgb="FF5F6B76"/><name val="Calibri"/></font>
<font><b/><sz val="10"/><color rgb="FFFFFFFF"/><name val="Calibri"/></font>
<font><sz val="9"/><color rgb="FF5F6B76"/><name val="Consolas"/></font>
<font><b/><sz val="11"/><color rgb="FF1C2733"/><name val="Calibri"/></font>
<font><strike/><sz val="10"/><color rgb="FF5F6B76"/><name val="Calibri"/></font>
<font><i/><sz val="9"/><color rgb="FF5F6B76"/><name val="Calibri"/></font>
<font><b/><sz val="10"/><color rgb="FF3F7A14"/><name val="Calibri"/></font>
</fonts>
<fills count="6">
<fill><patternFill patternType="none"/></fill>
<fill><patternFill patternType="gray125"/></fill>
<fill><patternFill patternType="solid"><fgColor rgb="FF1C2733"/></patternFill></fill>
<fill><patternFill patternType="solid"><fgColor rgb="FFFFF8E1"/></patternFill></fill>
<fill><patternFill patternType="solid"><fgColor rgb="FFF2F5F8"/></patternFill></fill>
<fill><patternFill patternType="solid"><fgColor rgb="FFE8F5E1"/></patternFill></fill>
</fills>
<borders count="2">
<border><left/><right/><top/><bottom/><diagonal/></border>
<border><left style="thin"><color rgb="FFDDE3E9"/></left><right style="thin"><color rgb="FFDDE3E9"/></right><top style="thin"><color rgb="FFDDE3E9"/></top><bottom style="thin"><color rgb="FFDDE3E9"/></bottom><diagonal/></border>
</borders>
<cellStyleXfs count="1"><xf numFmtId="0" fontId="0" fillId="0" borderId="0"/></cellStyleXfs>
<cellXfs count="17">
<xf numFmtId="0" fontId="0" fillId="0" borderId="0" xfId="0"/>
<xf numFmtId="0" fontId="1" fillId="0" borderId="0" xfId="0" applyFont="1" applyAlignment="1"><alignment vertical="center"/></xf>
<xf numFmtId="0" fontId="2" fillId="0" borderId="0" xfId="0" applyFont="1"/>
<xf numFmtId="0" fontId="3" fillId="2" borderId="1" xfId="0" applyFont="1" applyFill="1" applyBorder="1" applyAlignment="1"><alignment horizontal="center" vertical="center" wrapText="1"/></xf>
<xf numFmtId="0" fontId="0" fillId="0" borderId="1" xfId="0" applyBorder="1" applyAlignment="1"><alignment vertical="center" wrapText="1"/></xf>
<xf numFmtId="49" fontId="4" fillId="0" borderId="1" xfId="0" applyNumberFormat="1" applyFont="1" applyBorder="1" applyAlignment="1"><alignment vertical="center"/></xf>
<xf numFmtId="1" fontId="0" fillId="0" borderId="1" xfId="0" applyNumberFormat="1" applyBorder="1" applyAlignment="1"><alignment horizontal="center" vertical="center"/></xf>
<xf numFmtId="164" fontId="6" fillId="0" borderId="1" xfId="0" applyNumberFormat="1" applyFont="1" applyBorder="1" applyAlignment="1"><alignment vertical="center"/></xf>
<xf numFmtId="164" fontId="5" fillId="0" borderId="1" xfId="0" applyNumberFormat="1" applyFont="1" applyBorder="1" applyAlignment="1"><alignment vertical="center"/></xf>
<xf numFmtId="9" fontId="0" fillId="0" borderId="1" xfId="0" applyNumberFormat="1" applyBorder="1" applyAlignment="1"><alignment horizontal="center" vertical="center"/></xf>
<xf numFmtId="1" fontId="5" fillId="3" borderId="1" xfId="0" applyNumberFormat="1" applyFont="1" applyFill="1" applyBorder="1" applyAlignment="1" applyProtection="1"><alignment horizontal="center" vertical="center"/><protection locked="0"/></xf>
<xf numFmtId="164" fontId="0" fillId="4" borderId="1" xfId="0" applyNumberFormat="1" applyFill="1" applyBorder="1" applyAlignment="1"><alignment vertical="center"/></xf>
<xf numFmtId="0" fontId="5" fillId="0" borderId="0" xfId="0" applyFont="1" applyAlignment="1"><alignment horizontal="right" vertical="center"/></xf>
<xf numFmtId="164" fontId="5" fillId="5" borderId="1" xfId="0" applyNumberFormat="1" applyFont="1" applyFill="1" applyBorder="1" applyAlignment="1"><alignment vertical="center"/></xf>
<xf numFmtId="0" fontId="7" fillId="0" borderId="0" xfId="0" applyFont="1" applyAlignment="1"><alignment vertical="center"/></xf>
<xf numFmtId="0" fontId="8" fillId="0" borderId="1" xfId="0" applyFont="1" applyBorder="1" applyAlignment="1"><alignment horizontal="center" vertical="center"/></xf>
<xf numFmtId="0" fontId="2" fillId="0" borderId="1" xfId="0" applyFont="1" applyBorder="1" applyAlignment="1"><alignment horizontal="center" vertical="center"/></xf>
</cellXfs>
<cellStyles count="1"><cellStyle name="Normal" xfId="0" builtinId="0"/></cellStyles>
</styleSheet>`;

const COLUMNAS: [string, number][] = [
  ["Categoría", 16], ["Producto", 46], ["Código de barras", 17], ["Código interno", 13], ["Unidad", 10],
  ["Bulto (unidades)", 10], ["Compra mínima", 10], ["Precio público", 14], ["Tu precio", 14],
  ["Descuento", 10], ["Disponibilidad", 13], ["Cantidad", 11], ["Subtotal", 15],
];

export async function GET({ request }: { request: Request }) {
  const c = await clienteActual(env.DB, request);
  if (!(c?.mayorista === "aprobado" && c.lista_id)) return new Response("No autorizado", { status: 403 });
  const extra = await env.DB.prepare("SELECT razon_social, cuit FROM clientes WHERE id = ?").bind(c.id).first<{ razon_social: string | null; cuit: string | null }>();
  // Toda la lista (hasta 20.000 productos). Si alguna vez hubiera más, se avisa arriba: nunca se
  // corta en silencio.
  const TOPE = 20_000;
  const [publicos, enTotal] = await Promise.all([todos(env.DB, TOPE), contarPublicados(env.DB)]);
  const incompleta = enTotal > publicos.length ? ` · LISTA INCOMPLETA: ${publicos.length} de ${enTotal} productos (pedí el resto al local)` : "";
  const precios = await preciosDeLista(env.DB, c.lista_id, publicos.map((p) => p.id));
  const propia = await listaDeOdoo(env.DB, c.lista_id);
  const cond = propia ? resumen(await condiciones(env.DB, propia)) : "";
  const tusCond = cond ? ` · Tus condiciones: ${cond}, sobre la lista mayorista` : "";
  const ahora = new Date();
  const fecha = ahora.toLocaleString("es-AR", { timeZone: "America/Argentina/Cordoba", day: "2-digit", month: "2-digit", year: "numeric", hour: "2-digit", minute: "2-digit" });
  const cuit = extra?.cuit ? ` · CUIT ${extra.cuit.replace(/^(\d{2})(\d{8})(\d)$/, "$1-$2-$3")}` : "";
  const s = (v: string, e?: number): Celda => ({ t: "s", v, e });
  const n = (v: number, e?: number): Celda => ({ t: "n", v, e });
  const vacias = (k: number): Celda[] => Array.from({ length: k }, () => ({ t: "_" }));

  const primera = 7; // fila del primer producto
  const filas: Celda[][] = [
    [s("Comercio Ejemplo · Lista de precios mayorista", E.titulo), ...vacias(12)],
    [s(`Cliente: ${extra?.razon_social ?? c.email}${cuit}${tusCond}`, E.sub), ...vacias(12)],
    [s(`Generada el ${fecha} · Precios en pesos, con IVA incluido · Pueden cambiar sin aviso: vale el precio al confirmar el pedido.${incompleta}`, E.sub), ...vacias(12)],
    [s(`Cómo pedir: cargá la «Cantidad» (desde la compra mínima y en bultos cerrados) y mandala, o pedí en el sitio mayorista. ${local.direccion}, ${local.ciudad} · Tel. ${local.telefono}`, E.nota), ...vacias(12)],
    [],
    COLUMNAS.map(([t]) => s(t, E.cab)),
  ];
  // Mismo orden que la lista en pantalla: categoría y nombre
  publicos.forEach((pub, i) => {
    const p = conLista(pub, precios);
    const r = primera + i;
    const bulto = p.bulto && p.bulto > 1 ? p.bulto : 1;
    const disp = p.consultar ? "Consultar" : p.disponible ? "Hay" : "Sin stock";
    filas.push([
      s(p.categoria ?? "Otros", E.txt), s(p.nombre, E.txt), s(p.codigo ?? "", E.cod), s(p.referencia ?? "", E.cod),
      s(p.unidad, E.txt), n(bulto, E.ent), n(primeraValida(p), E.ent),
      n((pub.precio_anterior ?? pub.precio) / 100, E.pub), n(p.precio / 100, E.suyo),
      { t: "f", v: `IF(H${r}>0,1-I${r}/H${r},0)`, e: E.pct },
      s(disp, disp === "Hay" ? E.hay : E.no),
      { t: "_", e: E.cant },
      { t: "f", v: `IF(L${r}="","",L${r}*I${r})`, e: E.subt },
    ]);
  });
  const ultima = primera + publicos.length - 1;
  filas.push([...vacias(10), s("Total del pedido", E.totEt), { t: "f", v: `SUM(L${primera}:L${ultima})`, e: E.ent }, { t: "f", v: `SUM(M${primera}:M${ultima})`, e: E.tot }]);

  const xlsx = libro([{
    nombre: "Lista mayorista",
    anchos: COLUMNAS.map(([, w]) => w),
    filas,
    alturas: { 1: 28, 6: 30 },
    fijarFilas: 6,
    filtro: `A6:M${ultima}`,
    combinar: ["A1:M1", "A2:M2", "A3:M3", "A4:M4"],
    validaciones: [{
      rango: `L${primera}:L${ultima}`,
      formula: `OR(L${primera}="",AND(ISNUMBER(L${primera}),L${primera}>=G${primera},MOD(L${primera},F${primera})=0))`,
      titulo: "Cantidad",
      mensaje: "Desde la compra mínima y en bultos cerrados (múltiplo del bulto).",
    }],
    horizontal: true,
  }], ESTILOS, "Lista de precios mayorista · Comercio Ejemplo");

  const dia = ahora.toISOString().slice(0, 10);
  return new Response(xlsx as unknown as BodyInit, {
    headers: {
      "Content-Type": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
      "Content-Disposition": `attachment; filename="lista-mayorista-casa-ejemplo-${dia}.xlsx"`,
      "Cache-Control": "no-store",
    },
  });
}
