"""Genera data/ejemplos/facturas/factura-ejemplo-distribuidora-norte.pdf: factura A ficticia del
proveedor de ejemplo «[EJ] Distribuidora Norte SA» para la prueba visual (paso 7.1 de
docs/runbooks/prueba-visual.md). Coincide con la orden del paso 5.1 (10 alimentos de gato a
$ 25.000) pero cobra otro precio con bonificación, suma un artículo que no se pidió, flete y una
percepción de IIBB Córdoba. CUIT inventado (30-99999999-5).

    .venv/bin/python infra/scripts/factura-ejemplo.py
"""
from pathlib import Path

DESTINO = Path(__file__).parents[2] / "data" / "ejemplos" / "facturas" / "factura-ejemplo-distribuidora-norte.pdf"


def pdf_con_texto(renglones: list[tuple[int, int, str]]) -> bytes:
    """Un PDF de una página con textos en posiciones fijas (x, y en puntos), Helvetica 9 (como el de
    tests/e2e/factura_proveedor.py)."""

    def escapar(texto: str) -> str:
        return texto.replace("\\", "\\\\").replace("(", "\\(").replace(")", "\\)")

    contenido = "BT /F1 9 Tf " + " ".join(f"1 0 0 1 {x} {y} Tm ({escapar(t)}) Tj" for x, y, t in renglones) + " ET"
    flujo = contenido.encode("latin-1")
    objetos = [
        b"<< /Type /Catalog /Pages 2 0 R >>",
        b"<< /Type /Pages /Kids [3 0 R] /Count 1 >>",
        b"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 595 842] /Contents 4 0 R "
        b"/Resources << /Font << /F1 5 0 R >> >> >>",
        b"<< /Length " + str(len(flujo)).encode() + b" >>\nstream\n" + flujo + b"\nendstream",
        b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica /Encoding /WinAnsiEncoding >>",
    ]
    salida = bytearray(b"%PDF-1.4\n")
    posiciones = []
    for i, objeto in enumerate(objetos, start=1):
        posiciones.append(len(salida))
        salida += f"{i} 0 obj\n".encode() + objeto + b"\nendobj\n"
    xref = len(salida)
    salida += f"xref\n0 {len(objetos) + 1}\n0000000000 65535 f \n".encode()
    salida += b"".join(f"{p:010d} 00000 n \n".encode() for p in posiciones)
    salida += f"trailer\n<< /Size {len(objetos) + 1} /Root 1 0 R >>\nstartxref\n{xref}\n%%EOF\n".encode()
    return bytes(salida)


def main() -> None:
    r = [(40, 800, "FACTURA   ORIGINAL"), (40, 785, "A"), (300, 785, "Nº A 0005-00001234"), (40, 770, "Código: 1"),
         (300, 770, "Fecha: 24/10/2026"), (300, 755, "Vto.: 23/11/2026"),
         (40, 755, "[EJ] Distribuidora Norte SA - CUIT: 30-99999999-5 (datos ficticios)"),
         (40, 740, "Cliente: COMERCIO EJEMPLO")]
    columnas = [40, 100, 330, 380, 430, 490, 545]
    for y, fila in ((700, ["CANTIDAD", "ARTÍCULO", "T.IVA", "PRECIO", "% BONIF.", "P.BONIF.", "IMPORTE"]),
                    (685, ["10,00", "A-100 - ALIM GATO CASTRADO X 7.5KG", "21,00", "25500,00", "5", "24225,00",
                           "242250,00"]),
                    (670, ["2,00", "A-101 - CORREA NYLON 1.5M ROJA", "21,00", "3200,50", "", "3200,50", "6401,00"])):
        r += [(x, y, t) for x, t in zip(columnas, fila, strict=True) if t]
    for y, fila in ((630, ["Subtotal", "Flete 2,50%", "Neto Gravado", "IVA", "Percepciones", "TOTAL"]),
                    (615, ["248651,00", "6216,28", "254867,28", "53522,13", "7646,02", "316035,43"])):
        r += [(x, y, t) for x, t in zip([40, 140, 220, 340, 415, 520], fila, strict=True)]
    r.append((40, 590, "Perc.IIBB: CORDOBA 7.646,02"))
    DESTINO.parent.mkdir(parents=True, exist_ok=True)
    DESTINO.write_bytes(pdf_con_texto(r))
    print(f"==> {DESTINO}")


if __name__ == "__main__":
    main()
