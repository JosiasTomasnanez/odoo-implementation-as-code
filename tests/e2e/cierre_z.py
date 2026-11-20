"""Prueba de punta a punta del cierre Z de las registradoras (comercio_cierre_z, P-070, ADR 0038).

    .venv/bin/python tests/e2e/cierre_z.py

Flujo verificado en el lab (por la API JSON-2, como lo haría la pantalla):
1. Cargar un Z a mano con dos alícuotas y dos medios de pago: el diario de cada medio sale solo.
2. Confirmar: comprobante «Tique» del diario de la registradora, con el IVA impreso en el Z (no el
   recalculado), la foto adjunta y cobrado (efectivo y tarjetas).
3. Libro IVA Digital: el renglón del comprobante va del primer al último tique del día, y el de
   alícuotas con el IVA del Z.
4. Controles: un Z con el IVA mal leído no se confirma; el número repetido no se acepta; si se salta
   un número avisa que falta el anterior.
5. «Volver a borrador» anula comprobante y cobros, y se vuelve a confirmar.
6. Puestos que cobran en la registradora cerrados antes del módulo: quedan sin efecto contable (el
   comprobante de cierre revertido con nota de crédito, los cobros anulados), en cero en ventas e IVA;
   las cajas que cobran plata no se tocan. Al cerrar un puesto pasa solo: lo prueba
   tests/e2e/pos_cobro_registradora.py (make e2e-pos).
No usar en producción: crea comprobantes de prueba.
"""

from __future__ import annotations

import base64
import sys

from odoo_iac.client import connect
from odoo_iac.settings import load_environment

# Una «foto» mínima (PNG de 1×1): solo para ver que se adjunta al comprobante.
FOTO = base64.b64encode(
    bytes.fromhex(
        "89504e470d0a1a0a0000000d4948445200000001000000010806000000"
        "1f15c4890000000d49444154789c6360000002000154a24f5d0000000049454e44ae426082"
    )
).decode()

ERRORES: list[str] = []


def ok(condicion: bool, mensaje: str) -> None:
    print(("✓ " if condicion else "✗ ") + mensaje)
    if not condicion:
        ERRORES.append(mensaje)


def diario(c, codigo: str) -> int:
    filas = c.search_read("account.journal", [("code", "=", codigo)], ["id"])
    if not filas:
        raise SystemExit(f"Falta el diario {codigo}: correr make apply (config/onpremise/64-cierre-z.yaml)")
    return filas[0]["id"]


def falla(c, model: str, method: str, ids: list[int], **kwargs) -> str | None:
    """Llama y devuelve el mensaje de error, o None si no falló."""
    try:
        c.call(model, method, ids, **kwargs)
    except Exception as error:  # noqa: BLE001 (el error de Odoo llega como excepción del cliente)
        return str(error)
    return None


def main() -> int:
    c = connect(load_environment("lab"))
    sam4s = diario(c, "RG08")
    efectivo, tarjetas = diario(c, "EFRG"), diario(c, "TARJ")
    ultimos = c.search_read(
        "comercio.cierre.z", [("journal_id", "=", sam4s)], ["numero"], order="numero desc", limit=1
    )
    n = (ultimos[0]["numero"] if ultimos else 1000) + 1
    desde = n * 1000 + 1
    hasta = desde + 119

    # 1. Cargar a mano
    z = c.create(
        "comercio.cierre.z",
        {
            "journal_id": sam4s,
            "fecha": "2026-11-11",
            "numero": n,
            "tique_desde": desde,
            "tique_hasta": hasta,
            "neto_21": 100000.0,
            "iva_21": 21000.37,
            "neto_105": 20000.0,
            "iva_105": 2100.0,
            "total": 143100.37,
            "foto": FOTO,
            "foto_nombre": f"z-{n}.png",
            "cobro_ids": [
                [0, 0, {"medio": "efectivo", "importe": 60000.0}],
                [0, 0, {"medio": "credito", "importe": 83100.37}],
            ],
        },
    )
    leido = c.read("comercio.cierre.z", [z], ["problemas", "cobro_ids", "name"])[0]
    ok(not leido["problemas"], f"{leido['name']}: sin nada para corregir ({leido['problemas']})")
    cobros = c.read("comercio.cierre.z.cobro", leido["cobro_ids"], ["medio", "journal_id"])
    ok(
        {r["medio"]: r["journal_id"][0] for r in cobros} == {"efectivo": efectivo, "credito": tarjetas},
        "cada medio de pago va a su diario (efectivo → Efectivo registradoras, "
        "crédito → Tarjetas a liquidar)",
    )

    # 2. Confirmar
    c.call("comercio.cierre.z", "action_confirmar", [z])
    z_leido = c.read("comercio.cierre.z", [z], ["state", "move_id"])[0]
    ok(z_leido["state"] == "confirmado" and z_leido["move_id"], "el Z queda confirmado con su comprobante")
    move_id = z_leido["move_id"][0]
    mov = c.read(
        "account.move",
        [move_id],
        [
            "state",
            "journal_id",
            "l10n_latam_document_type_id",
            "amount_untaxed",
            "amount_tax",
            "amount_total",
            "payment_state",
            "name",
            "comercio_tique_hasta",
            "invoice_date",
        ],
    )[0]
    ok(
        mov["state"] == "posted" and mov["journal_id"][0] == sam4s,
        f"comprobante {mov['name']} confirmado en el diario de la Sam4s",
    )
    tipo = c.read("l10n_latam.document.type", [mov["l10n_latam_document_type_id"][0]], ["code"])[0]["code"]
    ok(tipo == "83", "tipo de comprobante: Tique (83)")
    ok(
        abs(mov["amount_untaxed"] - 120000.0) < 0.001
        and abs(mov["amount_tax"] - 23100.37) < 0.001
        and abs(mov["amount_total"] - 143100.37) < 0.001,
        f"importes del Z tal cual: neto {mov['amount_untaxed']}, IVA {mov['amount_tax']} "
        "(el impreso, no 23.100,00)",
    )
    ok(mov["payment_state"] in ("paid", "in_payment"), f"cobrado ({mov['payment_state']})")
    ok(mov["invoice_date"] == "2026-11-11", "con la fecha del Z")
    adjuntos = c.search_read(
        "ir.attachment", [("res_model", "=", "account.move"), ("res_id", "=", move_id)], ["name"]
    )
    ok(any(a["name"] == f"z-{n}.png" for a in adjuntos), "la foto del Z queda adjunta al comprobante")

    # 3. Libro IVA Digital
    libro = c.call("comercio.cierre.z", "comercio_renglones_libro_iva", [z])
    renglon = libro["comprobante"][0]
    ok(renglon[8:11] == "083" and renglon[11:16] == "00008", "Libro IVA: tipo 083 y punto de venta 00008")
    ok(
        renglon[16:36] == f"{desde:0>20d}" and renglon[36:56] == f"{hasta:0>20d}",
        f"Libro IVA: del tique {desde} al {hasta} (Odoo solo no pone el «hasta»)",
    )
    alicuotas = libro["alicuotas"]
    ok(
        any(r.endswith("000000002100037") for r in alicuotas)
        and any(r.endswith("000000000210000") for r in alicuotas),
        "Libro IVA: alícuotas con el IVA impreso en el Z (21.000,37 y 2.100,00)",
    )

    # 4. Controles
    error = falla(
        c,
        "comercio.cierre.z",
        "create",
        None,
        vals_list=[{"journal_id": sam4s, "fecha": "2026-11-11", "numero": n}],
    )
    ok(error is not None and "ya está cargado" in error, "un número de Z repetido no se acepta")
    salteado = c.create(
        "comercio.cierre.z",
        {
            "journal_id": sam4s,
            "fecha": "2026-11-13",
            "numero": n + 2,
            "tique_desde": hasta + 300,
            "tique_hasta": hasta + 400,
            "neto_21": 100000.0,
            "iva_21": 12000.0,
            "total": 112000.0,
        },
    )
    avisos = c.read("comercio.cierre.z", [salteado], ["avisos", "problemas"])[0]
    ok(f"Falta cargar el Z {n + 1}" in (avisos["avisos"] or ""), "avisa que falta el Z del medio")
    ok(
        "no corresponde" in (avisos["problemas"] or ""),
        "detecta el IVA mal leído (12.000 en lugar de 21.000)",
    )
    error = falla(c, "comercio.cierre.z", "action_confirmar", [salteado])
    ok(error is not None and "No se puede confirmar" in error, "un Z que no cierra no se confirma")
    c.call("comercio.cierre.z", "unlink", [salteado])

    # 5. Volver a borrador y confirmar de nuevo
    c.call("comercio.cierre.z", "action_volver_a_borrador", [z])
    anulado = c.read("account.move", [move_id], ["state"])[0]["state"]
    pagos = c.search_read("account.payment", [("memo", "like", f"Z {n}")], ["state"])
    ok(
        anulado == "cancel" and pagos and all(p["state"] == "canceled" for p in pagos),
        "volver a borrador anula el comprobante y sus cobros",
    )
    c.call("comercio.cierre.z", "action_confirmar", [z])
    nuevo = c.read("comercio.cierre.z", [z], ["state", "move_id"])[0]
    ok(
        nuevo["state"] == "confirmado" and nuevo["move_id"][0] != move_id,
        "se vuelve a confirmar con otro comprobante",
    )

    # 6. Puestos sin efecto contable
    probar_puestos(c)

    print()
    if ERRORES:
        print(f"✗ {len(ERRORES)} controles fallaron")
        return 1
    print("✓ Cierre Z: todo bien")
    return 0


def saldo_ventas_e_iva(c, sesion: int) -> float:
    """Ventas e IVA del cierre de la sesión más todo lo que lo revierte: en un puesto, cero."""
    cierres = c.search_read(
        "account.move",
        [
            "|",
            ("pos_session_sales_id", "=", sesion),
            ("pos_session_refunds_id", "=", sesion),
            ("state", "=", "posted"),
        ],
        ["id"],
    )
    ids = {m["id"] for m in cierres}
    ids |= {
        m["id"]
        for m in c.search_read(
            "account.move", [("reversed_entry_id", "in", list(ids)), ("state", "=", "posted")], ["id"]
        )
    }
    lineas = c.search_read(
        "account.move.line",
        [
            ("move_id", "in", list(ids)),
            "|",
            ("account_id.account_type", "in", ["income", "income_other"]),
            ("tax_line_id", "!=", False),
        ],
        ["balance"],
    )
    return round(sum(li["balance"] for li in lineas), 2)


def probar_puestos(c) -> None:
    """Sesiones de puestos cerradas antes del módulo: quedan sin efecto contable (salvo las que tienen pedidos
    facturados después del cierre, que se revisan a mano). El cierre en vivo lo prueba
    pos_cobro_registradora."""
    antes = {
        s["id"] for s in c.search_read("pos.session", [("comercio_contable_anulado", "=", True)], ["id"])
    }
    cantidad = c.call("pos.session", "comercio_anular_puestos_anteriores", None)
    nuevas = c.search_read(
        "pos.session",
        [("comercio_contable_anulado", "=", True), ("id", "not in", list(antes))],
        ["id", "name"],
    )
    print(f"  (sesiones de puestos cerradas antes que quedaron sin efecto contable ahora: {cantidad})")
    for sesion in nuevas:
        ok(saldo_ventas_e_iva(c, sesion["id"]) == 0.0, f"{sesion['name']}: ventas e IVA en cero")
        pagos = c.search_read("account.payment", [("pos_session_id", "=", sesion["id"])], ["state"])
        ok(
            all(p["state"] == "canceled" for p in pagos),
            f"{sesion['name']}: cobros de «Cobrado en registradora» anulados",
        )
    ok(
        c.call("pos.session", "comercio_anular_puestos_anteriores", None) == 0,
        "volver a correrlo no hace nada (idempotente)",
    )
    # Una caja que cobra plata de verdad no se toca: su venta sigue en la contabilidad
    cierre = c.search_read(
        "account.move",
        [("pos_session_sales_id", "!=", False), ("state", "=", "posted"), ("reversal_move_ids", "=", False)],
        ["pos_session_sales_id"],
        limit=20,
    )
    cajas = [m["pos_session_sales_id"] for m in cierre]
    cajas = [
        s
        for s in cajas
        if not c.read("pos.session", [s[0]], ["comercio_contable_anulado"])[0]["comercio_contable_anulado"]
    ]
    if cajas:
        ok(
            saldo_ventas_e_iva(c, cajas[0][0]) != 0.0,
            f"{cajas[0][1]} (cobra plata): su venta sigue en la contabilidad",
        )


if __name__ == "__main__":
    sys.exit(main())
