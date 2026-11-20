"""Leer la foto de un cierre Z con Gemini (comercio_cierre_z): llama a la IA de verdad.

    .venv/bin/python tests/e2e/cierre_z_foto.py [carpeta]

Arma la «foto» de un Z inventado (un ticket dibujado con el navegador, datos ficticios), la sube a un
cierre Z del lab, toca «Leer foto con IA» y compara cada número con el impreso. No confirma el Z:
lo borra al terminar. Requiere GEMINI_API_KEY en el Odoo del lab.
"""

from __future__ import annotations

import base64
import sys
import tempfile
from pathlib import Path

from playwright.sync_api import sync_playwright

from odoo_iac.client import connect
from odoo_iac.settings import load_environment

ESPERADO = {
    "numero": 1521,
    "fecha": "2026-11-12",
    "tique_desde": 4621,
    "tique_hasta": 4750,
    "neto_21": 70000.0,
    "iva_21": 14700.21,
    "neto_105": 12000.0,
    "iva_105": 1260.0,
    "exento": 805.22,
    "total": 98765.43,
}
COBROS = {"efectivo": 40000.0, "debito": 30000.0, "credito": 28765.43}

TICKET = """
<html><body style="margin:0;background:#f4f1ea">
<pre style="font:17px/1.35 'DejaVu Sans Mono',monospace;padding:24px 28px;width:430px;color:#222">
     COMERCIO DE PRUEBA S.A.
     CUIT Nro.: 30-00000000-0
   IVA RESPONSABLE INSCRIPTO
 Ing. Brutos: 30-00000000-0
 Inicio de Actividades: 01/01/2000
--------------------------------------
P.V. Nro.: 0008
Fecha: 12/11/2026        Hora: 21:05
--------------------------------------
     INFORME DIARIO DE CIERRE "Z"
          Nro. Z: 1521
--------------------------------------
Tique desde Nro.  0004621
Tique hasta Nro.  0004750
Cant. comprobantes emitidos:    130
--------------------------------------
TOTAL VENTAS              $98.765,43
NETO GRAVADO 21,00%       $70.000,00
IVA 21,00%                $14.700,21
NETO GRAVADO 10,50%       $12.000,00
IVA 10,50%                 $1.260,00
EXENTO                       $805,22
NO GRAVADO                     $0,00
--------------------------------------
NOTAS DE CREDITO               $0,00
--------------------------------------
MEDIOS DE PAGO
EFECTIVO                  $40.000,00
TARJETA DEBITO            $30.000,00
TARJETA CREDITO           $28.765,43
--------------------------------------
        CF: SM HAB0000000
</pre></body></html>
"""


def main() -> int:
    out = Path(sys.argv[1] if len(sys.argv) > 1 else tempfile.mkdtemp(prefix="e2e_cierre_z_foto_"))
    out.mkdir(parents=True, exist_ok=True)
    foto = out / "cierre-z.png"
    with sync_playwright() as p:
        navegador = p.chromium.launch()
        pagina = navegador.new_page(viewport={"width": 500, "height": 900})
        pagina.set_content(TICKET)
        pagina.screenshot(path=str(foto), full_page=True)
        navegador.close()

    c = connect(load_environment("lab"))
    diario = c.search_read("account.journal", [("code", "=", "RG13")], ["id"])[0]["id"]  # adrede la otra
    z = c.create(
        "comercio.cierre.z",
        {
            "journal_id": diario,
            "foto": base64.b64encode(foto.read_bytes()).decode(),
            "foto_nombre": foto.name,
        },
    )
    errores = []
    try:
        c.call("comercio.cierre.z", "action_leer_foto", [z])
        campos = [*ESPERADO, "journal_id", "cobro_ids", "dudas_ia", "problemas"]
        leido = c.read("comercio.cierre.z", [z], campos)[0]
        for campo, valor in ESPERADO.items():
            bien = (
                leido[campo] == valor if not isinstance(valor, float) else abs(leido[campo] - valor) < 0.005
            )
            print(("✓ " if bien else "✗ ") + f"{campo}: {leido[campo]} (impreso {valor})")
            if not bien:
                errores.append(campo)
        sam4s = c.search_read("account.journal", [("code", "=", "RG08")], ["id"])[0]["id"]
        bien = leido["journal_id"][0] == sam4s
        print(("✓ " if bien else "✗ ") + f"registradora por el punto de venta 0008: {leido['journal_id'][1]}")
        if not bien:
            errores.append("journal_id")
        cobros = {
            r["medio"]: r["importe"]
            for r in c.read("comercio.cierre.z.cobro", leido["cobro_ids"], ["medio", "importe"])
        }
        bien = cobros == COBROS
        print(("✓ " if bien else "✗ ") + f"medios de pago: {cobros}")
        if not bien:
            errores.append("cobros")
        print(("✓ " if not leido["problemas"] else "✗ ") + f"nada para corregir ({leido['problemas']})")
        if leido["problemas"]:
            errores.append("problemas")
        if leido["dudas_ia"]:
            print(f"  dudas de la IA: {leido['dudas_ia']}")
    finally:
        c.call("comercio.cierre.z", "unlink", [z])
    print(f"\nFoto en {foto}")
    if errores:
        print(f"✗ La IA leyó mal: {', '.join(errores)}")
        return 1
    print("✓ Foto del Z leída bien")
    return 0


if __name__ == "__main__":
    sys.exit(main())
