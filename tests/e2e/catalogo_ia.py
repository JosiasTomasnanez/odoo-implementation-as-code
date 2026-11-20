"""Prueba de punta a punta de la verificación con IA (ADR 0018, módulo comercio_catalogo_ia).

Llama de verdad a Gemini (consume unos cientos de tokens; requiere GEMINI_API_KEY en el
.env del repo y el lab levantado con `make lab-up` después de cargarla):

1. Una lista ficticia con dos «posibles duplicados» de productos de ejemplo:
   - «ALIMENTO PERRO ADULTO X 15 KG» = «[EJ] Alimento perro adulto 15 kg» → la IA dice «es el mismo»;
   - «CORREA NYLON 1,5 MTS AZUL» ≠ «[EJ] Correa nylon 1,5 m roja» (otro color) → no dice «es el mismo».
2. Lo que la IA confirma con seguridad (≥ 90 %, costo parecido) se une solo a nuestro producto
   (ADR 0034); lo que es otro no se agrega nunca, ni con «Aceptar lo que sugirió la IA».

Uso: .venv/bin/python tests/e2e/catalogo_ia.py
"""
from __future__ import annotations

import base64
import io
import sys
import time
from pathlib import Path

import openpyxl

from odoo_iac.client import connect
from odoo_iac.settings import load_environment

c = connect(load_environment("lab"))
LINEA = "comercio.lista.importacion.linea"
MARCA = str(int(time.time()))[-6:]


def excel(filas: list[list]) -> str:
    libro = openpyxl.Workbook()
    hoja = libro.active
    hoja.append(["Código", "Descripción", "Precio"])
    for fila in filas:
        hoja.append(fila)
    salida = io.BytesIO()
    libro.save(salida)
    return base64.b64encode(salida.getvalue()).decode()


def producto(nombre: str) -> int:
    encontrado = c.search_read("product.template", [("name", "=", nombre)], ["id"])
    assert encontrado, f"falta el producto de ejemplo «{nombre}»"
    return encontrado[0]["id"]


def producto_categoria() -> int:
    return c.search_read("product.category", [("name", "=", "[EJ] Mascotas")], ["id"])[0]["id"]


def esperado_foto() -> dict:
    """Lo que está impreso en tests/datos/lista_ficticia_foto.png (primera página de la lista)."""
    base = [("P-001", "ALIMENTO PERRO ADULTO X 15 KG", 30250.5),
            ("P-002", "ALIMENTO GATO CASTRADO X 7,5 KG", 24100),
            ("P-003", "ARENA SANITARIA X 4 KG", 3200), ("P-004", "CORREA NYLON 1,5 M ROJA", 3200.5),
            ("P-005", "COMEDERO ACERO CHICO", 1850), ("P-006", "PIPETA ANTIPULGAS PERRO MEDIANO", 6100),
            ("P-007", "HUESO CARNAZA 15 CM", 1450), ("P-008", "COLLAR ANTIPULGAS GATO", 3500),
            ("P-009", "SNACK DENTAL PERRO X 200 G", 18500), ("P-010", "PIEDRAS SANITARIAS X 2 KG", 1900)]
    return {(f"{cod}{i}" if i else cod): ((f"{d} V{i}" if i else d), p + i * 10)
            for i in range(6) for cod, d, p in base}


def main() -> int:
    perro = producto("[EJ] Alimento perro adulto 15 kg")
    correa = producto("[EJ] Correa nylon 1,5 m roja")
    socio = c.create("res.partner", {"name": f"[EJ] Proveedor IA {MARCA}", "is_company": True,
                                     "supplier_rank": 1})
    socios = [socio]
    try:
        wizard = c.create("comercio.importar.lista.wizard", {
            "partner_id": socio, "nombre_archivo": "lista.xlsx",
            "archivo": excel([["IA1", "ALIMENTO PERRO ADULTO X 15 KG", 30000],
                              ["IA2", "CORREA NYLON 1,5 MTS AZUL", 4000]])})
        imp = c.call("comercio.importar.lista.wizard", "action_importar", [wizard])["res_id"]
        filas = {f["codigo_proveedor"]: f for f in c.search_read(
            LINEA, [("importacion_id", "=", imp)], ["codigo_proveedor", "accion", "candidato_ids"])}
        assert filas["IA1"]["accion"] == "posible duplicado", filas
        assert perro in filas["IA1"]["candidato_ids"], filas
        assert filas["IA2"]["accion"] == "posible duplicado", filas
        assert correa in filas["IA2"]["candidato_ids"], filas
        print("1. Dos posibles duplicados para la IA (alimento 15 kg y correa de otro color) ✓")

        c.call("comercio.lista.importacion", "action_verificar_ia", [imp])
        filas = {f["codigo_proveedor"]: f for f in c.search_read(
            LINEA, [("importacion_id", "=", imp)],
            ["codigo_proveedor", "estado", "ia_veredicto", "ia_producto_id", "ia_confianza", "ia_motivo",
             "producto_elegido_id", "unida_por_ia"])}
        ia1, ia2 = filas["IA1"], filas["IA2"]
        print(f"   IA1: {ia1['ia_veredicto']} ({ia1['ia_confianza']:.2f}) - {ia1['ia_motivo']}")
        print(f"   IA2: {ia2['ia_veredicto']} ({ia2['ia_confianza']:.2f}) - {ia2['ia_motivo']}")
        # El mismo producto: el de la prueba u otro con el mismo nombre (p. ej. el de la demo de la tienda)
        assert ia1["ia_veredicto"] == "mismo" and (
            ia1["ia_producto_id"][0] == perro or "Alimento perro adulto 15 kg" in ia1["ia_producto_id"][1]
        ), ia1
        perro = ia1["ia_producto_id"][0]  # desde acá, el que eligió la IA
        assert ia2["ia_veredicto"] in ("distinto", "dudoso"), ia2
        # Seguro y con el mismo costo: se une solo (ADR 0034). La correa (otro producto) no se agrega.
        assert ia1["estado"] == "aplicada" and ia1["unida_por_ia"], ia1
        assert ia2["estado"] == "pendiente" and not ia2["unida_por_ia"], ia2
        mensaje = c.search_read("mail.message", [
            ("model", "=", "comercio.lista.importacion"), ("res_id", "=", imp),
            ("body", "ilike", "Verificación con IA")], ["body"])
        assert mensaje and "tokens" in mensaje[0]["body"], mensaje
        print("2. La IA dice «es el mismo» para el alimento y lo une sola (seguro y mismo costo);")
        print("   la correa azul (otro producto) queda para decidir, sin agregarse")
        print("   y deja el consumo (pedidos y tokens) en la importación ✓")

        c.call(LINEA, "action_deshacer", [ia1["id"]])  # deshecha: vuelve a quedar para decidir
        c.call(LINEA, "action_aceptar_ia", [ia1["id"]])
        vinculada = c.read(LINEA, [ia1["id"]], ["estado", "producto_id", "registrado"])[0]
        assert vinculada["estado"] == "aplicada" and vinculada["producto_id"] and \
            vinculada["producto_id"][0] == perro and vinculada["registrado"], vinculada
        precio = c.search_read("product.supplierinfo",
                               [("partner_id", "=", socio), ("product_tmpl_id", "=", perro)], ["id"])
        assert precio, "no quedó el precio del proveedor en el alimento"
        print("3. Deshecha y aceptada a mano: «Aceptar lo que sugirió la IA» la vincula al alimento ✓")
        productos_antes = c.call("product.template", "search_count", domain=[("active", "in", (True, False))])
        try:
            c.call(LINEA, "action_aceptar_ia", [ia2["id"]])
            raise AssertionError("aceptar «es otro» no debería hacer nada")
        except AssertionError:
            raise
        except Exception:  # noqa: BLE001 - avisa que lo que es otro no se agrega solo
            pass
        todos = [("active", "in", (True, False))]
        productos_despues = c.call("product.template", "search_count", domain=todos)
        assert productos_despues == productos_antes, (productos_antes, productos_despues)
        assert c.read(LINEA, [ia2["id"]], ["estado"])[0]["estado"] == "pendiente"
        print("   «Es otro» no se agrega al catálogo ni aceptando lo de la IA ✓")
        c.call(LINEA, "action_deshacer", [ia1["id"]])
        deshecha = c.read(LINEA, [ia1["id"]], ["estado", "producto_id", "registrado"])[0]
        assert deshecha["estado"] == "pendiente" and not deshecha["registrado"], deshecha
        print("   «Deshacer» la deja otra vez para decidir, fuera de nuestro catálogo ✓")

        # 4. Lo que el programa da por seguro también se puede revisar
        cinta = producto("[EJ] Cinta métrica 5 m")
        wizard = c.create("comercio.importar.lista.wizard", {
            "partner_id": socio, "nombre_archivo": "lista2.xlsx",
            "archivo": excel([["IA1", "ALIMENTO PERRO ADULTO X 15 KG", 30000],
                              ["IA2", "CORREA NYLON 1,5 MTS AZUL", 4000],
                              ["IA3", "FLEXOMETRO 5 METROS", 3000],
                              ["IA4", "COLLAR CUERO PERRO GIGANTE C/TACHAS", 2500]])})
        imp2 = c.call("comercio.importar.lista.wizard", "action_importar", [wizard])["res_id"]
        filas = {f["codigo_proveedor"]: f for f in c.search_read(
            LINEA, [("importacion_id", "=", imp2)], ["codigo_proveedor", "accion"])}
        assert filas["IA3"]["accion"] == "nuevo" and filas["IA4"]["accion"] == "nuevo", filas
        # Alguien se equivoca y une el collar a la correa (un «nuevo» ahora también se puede unir)
        c.write(LINEA, [filas["IA4"]["id"]], {"producto_elegido_id": correa})
        c.call(LINEA, "action_es_el_mismo", [filas["IA4"]["id"]])
        c.call(LINEA, "action_verificar_ia", [filas["IA3"]["id"], filas["IA4"]["id"]])
        ia3, ia4 = c.read(LINEA, [filas["IA3"]["id"], filas["IA4"]["id"]],
                          ["ia_veredicto", "ia_producto_id", "ia_motivo", "estado", "producto_id"])
        print(f"   IA3 (nuevo): {ia3['ia_veredicto']} - {ia3['ia_motivo']}")
        print(f"   IA4 (unido): {ia4['ia_veredicto']} - {ia4['ia_motivo']}")
        assert ia3["ia_veredicto"] in ("mismo", "dudoso"), ia3  # vio la cinta aunque el motor no
        if ia3["ia_veredicto"] == "mismo":
            assert ia3["ia_producto_id"][0] == cinta, ia3
        assert ia3["estado"] == "pendiente", ia3
        assert ia4["estado"] == "aplicada" and ia4["producto_id"][0] == correa, ia4
        assert ia4["ia_veredicto"] in ("distinto", "dudoso"), ia4
        duda = c.search_read(LINEA, [("importacion_id", "=", imp2), ("registrado", "=", True),
                                     ("ia_veredicto", "in", ("distinto", "dudoso"))], ["codigo_proveedor"])
        assert [d["codigo_proveedor"] for d in duda] == ["IA4"], duda
        print("4. «Producto nuevo» que el programa no vinculó: la IA ve la cinta métrica (flexómetro);")
        print("   lo ya unido por error (collar → correa) queda en «La IA duda» ✓")
        if ia3["ia_veredicto"] == "mismo":
            c.call(LINEA, "action_aceptar_ia", [filas["IA3"]["id"]])
            unida = c.read(LINEA, [filas["IA3"]["id"]], ["estado", "producto_id"])[0]
            assert unida["estado"] == "aplicada" and unida["producto_id"][0] == cinta, unida
            print("   «Aceptar sugerencia» une el flexómetro a la cinta (no crea un producto repetido) ✓")
            c.call(LINEA, "action_deshacer", [filas["IA3"]["id"]])
            assert c.search_read("product.template", [("id", "=", cinta)], ["id"]), "se borró la cinta"
        c.call(LINEA, "action_deshacer", [filas["IA4"]["id"]])

        # 5. Lista en foto: la transcribe la IA; se compara con lo impreso y nada se aplica solo
        foto = c.create("res.partner", {"name": f"[EJ] Proveedor foto {MARCA}", "is_company": True,
                                        "supplier_rank": 1})
        socios.append(foto)
        ruta = Path(__file__).parents[1] / "datos" / "lista_ficticia_foto.png"
        wizard = c.create("comercio.importar.lista.wizard", {
            "partner_id": foto, "categoria_id": producto_categoria(), "nombre_archivo": "lista.png",
            "archivo": base64.b64encode(ruta.read_bytes()).decode()})
        imp3 = c.call("comercio.importar.lista.wizard", "action_importar", [wizard])["res_id"]
        datos = c.read("comercio.lista.importacion", [imp3], ["estado", "leida_con_ia", "cant_total"])[0]
        assert datos["estado"] == "simulada" and datos["leida_con_ia"], datos
        leidas = {f["codigo_proveedor"]: (f["descripcion"], f["costo"]) for f in c.search_read(
            LINEA, [("importacion_id", "=", imp3)], ["codigo_proveedor", "descripcion", "costo", "decision"])}
        esperado = esperado_foto()
        errores = {k: (v, esperado.get(k)) for k, v in leidas.items() if esperado.get(k) != v}
        print(f"   Foto: {len(leidas)} filas leídas, {len(errores)} distintas de lo impreso {errores or ''}")
        assert len(leidas) >= 40 and not errores, errores
        automaticas = c.search_read(LINEA, [("importacion_id", "=", imp3), ("decision", "=", "aplicar")],
                                    ["id"])
        assert not automaticas, automaticas
        mensaje = c.search_read("mail.message", [("model", "=", "comercio.lista.importacion"),
                                                 ("res_id", "=", imp3), ("body", "ilike", "leída con IA")],
                                ["body"])
        assert mensaje and "tokens" in mensaje[0]["body"], mensaje
        print("5. Lista en foto: la IA la transcribe igual a lo impreso (código, descripción y precio),")
        print("   queda marcada «leída con IA», nada se aplica solo y se anota el consumo ✓")
        assert not c.read(LINEA, [filas["IA4"]["id"]], ["producto_id"])[0]["producto_id"]
    finally:
        precios = c.search_read("product.supplierinfo", [("partner_id", "in", socios)], ["id"])
        if precios:
            c.call("product.supplierinfo", "unlink", [p["id"] for p in precios])
        listas = c.search_read("comercio.lista.proveedor", [("partner_id", "in", socios)], ["id"])
        importaciones = c.search_read("comercio.lista.importacion",
                                      [("lista_id", "in", [x["id"] for x in listas])], ["id"])
        if importaciones:
            c.call("comercio.lista.importacion", "unlink", [x["id"] for x in importaciones])
        if listas:
            c.call("comercio.lista.proveedor", "unlink", [x["id"] for x in listas])
        c.write("res.partner", socios, {"active": False})
    print("Todo OK.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
