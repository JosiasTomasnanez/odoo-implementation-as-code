"""Prueba de punta a punta de la factura electrónica contra ARCA homologación (P-029).

Requiere el lab Enterprise preparado con `make lab-arca` (CUIT ficticio, certificado de
prueba de Odoo, diario FE1 web service). Cada corrida pide CAE reales de HOMOLOGACIÓN
(sin validez fiscal):

1. Factura B a Consumidor Final: ARCA la aprueba y devuelve CAE con vencimiento.
2. Factura A al cliente mayorista ficticio (Responsable Inscripto).
3. Nota de crédito B que anula la factura del punto 1, con su propio CAE.

Las facturas quedan validadas en el lab (una factura con CAE no se borra; es historial de
prueba). Uso: .venv/bin/python tests/e2e/factura_electronica.py
"""
from __future__ import annotations

import sys

from odoo_iac.client import connect
from odoo_iac.settings import load_environment

c = connect(load_environment("lab"))
# CAE que inventa Odoo cuando está en homologación SIN certificado (l10n_ar_edi/account_move.py):
# si aparece, la factura no llegó a ARCA.
CAE_FALSO = "68448767638166"
CAMPOS = ["name", "state", "l10n_latam_document_type_id", "l10n_ar_afip_auth_code",
          "l10n_ar_afip_auth_code_due", "l10n_ar_afip_result", "amount_total"]


def xmlid(modulo: str, nombre: str) -> int:
    return c.search_read("ir.model.data", [("module", "=", modulo), ("name", "=", nombre)],
                         ["res_id"])[0]["res_id"]


def validar(move_id: int) -> dict:
    c.call("account.move", "action_post", [move_id])
    m = c.read("account.move", [move_id], CAMPOS)[0]
    assert m["state"] == "posted", m
    assert m["l10n_ar_afip_result"] == "A", m  # A = aprobado por ARCA
    cae = m["l10n_ar_afip_auth_code"]
    assert cae and len(cae) == 14 and cae != CAE_FALSO, m
    assert m["l10n_ar_afip_auth_code_due"], m
    return m


def main() -> int:
    empresa = c.search_read("res.company", [], ["l10n_ar_afip_ws_environment", "l10n_ar_afip_ws_crt_id"])[0]
    assert empresa["l10n_ar_afip_ws_environment"] == "testing", "el lab nunca factura en producción"
    assert empresa["l10n_ar_afip_ws_crt_id"], "falta el certificado: correr make lab-arca"
    diario = c.search_read("account.journal", [("code", "=", "FE1")], ["id"])
    assert diario, "falta el diario FE1: correr make lab-arca"
    diario = diario[0]["id"]
    producto = c.search_read("product.product", [("default_code", "!=", False), ("sale_ok", "=", True),
                                                 ("taxes_id", "!=", False)], ["id", "name"], limit=1)[0]

    def factura(cliente: int, tipo: str = "out_invoice", **extra) -> int:
        return c.create("account.move", {
            "move_type": tipo, "partner_id": cliente, "journal_id": diario, **extra,
            "invoice_line_ids": [(0, 0, {"product_id": producto["id"], "quantity": 2, "price_unit": 1210})]})

    cf = xmlid("l10n_ar", "par_cfa")
    b = validar(factura(cf))
    assert "B" in b["l10n_latam_document_type_id"][1], b
    print(f"1. Factura B a Consumidor Final {b['name']}: CAE {b['l10n_ar_afip_auth_code']} "
          f"(vence {b['l10n_ar_afip_auth_code_due']}) ✓")

    mayorista = c.search_read("ir.model.data", [("name", "=", "ej_cliente_mayorista")], ["res_id"])
    assert mayorista, "falta el cliente mayorista de config/ejemplos (make apply ENV=lab)"
    a = validar(factura(mayorista[0]["res_id"]))
    assert "A" in a["l10n_latam_document_type_id"][1], a
    print(f"2. Factura A a Responsable Inscripto {a['name']}: CAE {a['l10n_ar_afip_auth_code']} ✓")

    nc = validar(factura(cf, "out_refund", reversed_entry_id=c.search_read(
        "account.move", [("name", "=", b["name"])], ["id"])[0]["id"]))
    assert "CRÉDITO" in nc["l10n_latam_document_type_id"][1].upper(), nc
    print(f"3. Nota de crédito {nc['name']} sobre {b['name']}: CAE {nc['l10n_ar_afip_auth_code']} ✓")
    print("Todo OK. (homologación ARCA: comprobantes sin validez fiscal)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
