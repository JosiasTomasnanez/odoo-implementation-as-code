"""Deja la empresa del LAB lista para pedir CAE a ARCA homologación (P-029, Enterprise).

Solo laboratorio y solo Enterprise (`l10n_ar_edi`). Usa los certificados de prueba que
trae Odoo (`l10n_ar_edi/demo/`, CUIT de prueba de Odoo, autorizados en homologación) y un
CUIT FICTICIO de empresa (el de la empresa demo de Odoo, 30111111118). Nada de esto sirve
para producción: ahí va el certificado propio de Comercio Ejemplo, fuera del repo.

Idempotente: se puede correr varias veces. Lo usa `make lab-arca`, que lo ejecuta con
`odoo shell` dentro del contenedor (necesita leer los archivos del módulo).
"""
from odoo.tools import file_open
from odoo.tools.binary import BinaryBytes

CUIT_FICTICIO = "30111111118"
DIARIO_CODIGO = "FE1"
PUNTO_DE_VENTA = 1  # en homologación cualquier número sirve; en producción, el dado de alta en ARCA
# Si ARCA va adelante con la numeración (CUIT de prueba compartido), se pasa a otro al azar.

# `env` lo define odoo shell.
empresa = env.company
if "l10n_ar_afip_ws_environment" not in empresa:
    raise SystemExit("Falta l10n_ar_edi: el lab no es Enterprise o el módulo no está instalado")

empresa.write({
    "vat": CUIT_FICTICIO,
    "country_id": env.ref("base.ar").id,
    "l10n_ar_afip_start_date": "2020-01-01",
    "l10n_ar_gross_income_type": "exempt",
    "l10n_ar_afip_ws_environment": "testing",  # homologación: nunca producción en el lab
})

clave = env["certificate.key"].search(
    [("name", "=", "ARCA key (demo Odoo)"), ("company_id", "=", empresa.id)], limit=1)
if not clave:
    with file_open("l10n_ar_edi/demo/private_key.pem", "rb") as f:
        clave = env["certificate.key"].create({
            "name": "ARCA key (demo Odoo)", "content": BinaryBytes(f.read()), "company_id": empresa.id})
empresa.l10n_ar_afip_ws_key_id = clave
if not empresa.l10n_ar_afip_ws_crt_id:
    # Uno de los 10 certificados demo, al azar. Si ARCA lo bloquea porque otra base lo
    # está usando, se cambia con el botón de Ajustes o borrando el certificado y
    # volviendo a correr este script.
    empresa.set_demo_random_cert()

diario = env["account.journal"].search(
    [("code", "=", DIARIO_CODIGO), ("company_id", "=", empresa.id)], limit=1)
valores = {
    "name": "Factura electrónica (lab)", "type": "sale", "l10n_latam_use_documents": True,
    "l10n_ar_afip_pos_number": PUNTO_DE_VENTA, "l10n_ar_afip_pos_partner_id": empresa.partner_id.id,
    "l10n_ar_afip_pos_system": "RAW_MAW",  # «Factura electrónica - Web Service» (wsfe)
}
if diario:
    # Solo lo que difiere: Odoo no deja reescribir «Usa documentos» con facturas validadas
    # El punto de venta se respeta: puede haber pasado a otro por desfase con ARCA (abajo)
    distintos = {k: v for k, v in valores.items() if k != "l10n_ar_afip_pos_number"
                 and (diario[k].id if hasattr(diario[k], "id") else diario[k]) != v}
    if distintos:
        diario.write(distintos)
else:
    diario = env["account.journal"].create({**valores, "code": DIARIO_CODIGO, "company_id": empresa.id})

env.cr.commit()


def numeracion_desfasada(diario) -> list[str]:
    """Tipos de comprobante cuyo último número en ARCA no es el último validado en el diario.

    El CUIT y los certificados de prueba son de Odoo y los usan muchas bases a la vez: ARCA
    puede ir adelante y rechazar la próxima factura con el error 10016 (visto el 19/10)."""
    desfasados = []
    for codigo in ("1", "6", "3", "8"):  # factura A, factura B, nota de crédito A y B
        tipo = env["l10n_latam.document.type"].search(
            [("code", "=", codigo), ("country_id", "=", env.ref("base.ar").id)], limit=1)
        en_arca = diario._l10n_ar_get_afip_last_invoice_number(tipo)
        ultima = env["account.move"].search(
            [("journal_id", "=", diario.id), ("state", "=", "posted"),
             ("l10n_latam_document_type_id", "=", tipo.id)], order="sequence_number desc", limit=1)
        if en_arca != (ultima.sequence_number or 0):
            desfasados.append(f"{tipo.doc_code_prefix} (ARCA {en_arca}, lab {ultima.sequence_number or 0})")
    return desfasados


desfasados = numeracion_desfasada(diario)
if desfasados:
    # Un diario nuevo, sin facturas, con otro punto de venta: Odoo le pide a ARCA el último
    # número y sigue desde ahí. El viejo se archiva (sus facturas con CAE quedan de historial).
    import random

    viejo = diario
    # Borradores que dejaron pruebas rechazadas por ARCA: se cancelan (Odoo no archiva un
    # diario con borradores).
    env["account.move"].search([("journal_id", "=", viejo.id), ("state", "=", "draft")]).button_cancel()
    viejo.write({"code": f"FX{viejo.l10n_ar_afip_pos_number % 1000:03d}", "active": False})
    env.flush_all()  # el código queda libre antes de crear el diario nuevo
    punto = random.randint(1000, 99999)
    diario = env["account.journal"].create({**valores, "l10n_ar_afip_pos_number": punto,
                                            "code": DIARIO_CODIGO, "company_id": empresa.id})
    env.cr.commit()
    print(f"==> Numeración desfasada con ARCA ({', '.join(desfasados)}): diario nuevo, "
          f"punto de venta {punto}")

print(f"==> Lab en homologación ARCA: CUIT {empresa.vat}, certificado "
      f"«{empresa.l10n_ar_afip_ws_crt_id.name}», diario {diario.code} "
      f"(punto de venta {diario.l10n_ar_afip_pos_number}, wsfe)")

# Las 2 cajas del local facturan con este diario (ADR 0024): con «Factura» marcado, cada venta sale
# con CAE de homologación; desmarcado, va sin factura de Odoo (la emitiría la registradora). Las
# cajas de ejemplo de las pruebas e2e ([EJ]) no se tocan: sus pruebas no dependen de ARCA.
for xmlid in ("iac.pos_caja_1", "iac.pos_caja_2"):
    caja = env.ref(xmlid, raise_if_not_found=False)
    if caja and caja.journal_id != diario:
        if caja.current_session_id:
            print(f"==> {caja.name}: tiene la caja abierta; cerrala y volvé a correr para que facture con {diario.code}")
            continue
        caja.journal_id = diario
        print(f"==> {caja.name} factura con el diario {diario.code}")
env.cr.commit()
