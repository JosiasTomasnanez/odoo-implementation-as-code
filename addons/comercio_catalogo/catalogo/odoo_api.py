"""Lectura del estado de Odoo y aplicación del plan, con cualquier «cliente».

El cliente tiene `context`, `search_read(model, domain, fields, **kw)`,
`create(model, vals)` y `write(model, ids, vals)`. Lo cumplen el cliente JSON-2 de
`odoo_iac` (herramienta de línea de comandos) y el adaptador del ORM del módulo
(`models/`), así los dos usan exactamente la misma lógica.
"""
from __future__ import annotations

import datetime

from .plan import ACTUALIZAR, BAJA, NUEVO, UNIDADES, VINCULAR, Foto, _clave

SIN_ARCHIVADOS = {"active_test": False}


def _ayer(hoy: str) -> str:
    return (datetime.date.fromisoformat(hoy) - datetime.timedelta(days=1)).isoformat()


def categorias_con_stock(c) -> list[str]:
    """Categorías marcadas «Controla stock» (rubros con stock desde el principio, P-032)."""
    filas = c.search_read("product.category", [("comercio_controla_stock", "=", True)], ["complete_name"])
    return [f["complete_name"] for f in filas]


def _id(valor):
    """Many2one leído: [id, nombre] (JSON-2) o id."""
    return valor[0] if isinstance(valor, (list, tuple)) else (valor or None)


def unidades(c) -> dict:
    """{id: {"nombre", "familia"}} de todas las unidades. La familia es la clave de UNIDADES
    («u», «kg», «m», «l») cuya unidad comparte la raíz (Odoo 20: «Contiene» N de otra unidad);
    solo se convierte entre unidades de la misma familia."""
    filas = c.search_read("uom.uom", [], ["name", "relative_uom_id"], context={**c.context, **SIN_ARCHIVADOS})
    padre = {u["id"]: _id(u["relative_uom_id"]) for u in filas}

    def raiz(i):
        vistos = set()
        while padre.get(i) and i not in vistos:
            vistos.add(i)
            i = padre[i]
        return i

    familias = {}
    for clave, nombre in UNIDADES.items():
        ref = c.search_read("ir.model.data", [("module", "=", "uom"), ("name", "=", nombre)], ["res_id"])
        if ref:
            familias[raiz(ref[0]["res_id"])] = clave
    return {u["id"]: {"nombre": u["name"], "familia": familias.get(raiz(u["id"]))} for u in filas}


def sacar_foto(c, hoy: str) -> Foto:
    ctx = {**c.context, **SIN_ARCHIVADOS}
    todas = unidades(c)
    productos = c.search_read("product.template", [], ["barcode", "default_code", "name", "active", "uom_id"],
                              context=ctx)
    unidad_de = {p["id"]: _id(p["uom_id"]) for p in productos}
    for p in productos:
        p["familia"] = (todas.get(unidad_de[p["id"]]) or {}).get("familia")
    socios = {p["id"]: p["name"] for p in c.search_read("res.partner", [], ["name"], context=ctx)}
    # Solo los precios vigentes: los cerrados (D7) son historial
    prov = c.search_read(
        # Sin las filas «precio por mayor»: las crea Odoo a partir del precio principal
        "product.supplierinfo", ["|", ("date_end", "=", False), ("date_end", ">=", hoy),
                                 ("comercio_escala_de_id", "=", False)],
        ["partner_id", "product_tmpl_id", "product_code", "product_name", "price", "min_qty", "delay",
         "date_start", "comercio_precio_mayor", "comercio_cantidad_mayor", "comercio_bulto",
         "comercio_presentaciones", "comercio_lista_id", "uom_id"],
    )
    # Los cerrados, del más reciente al más viejo: queda el último de cada proveedor y código
    cerrados = {}
    for s in c.search_read("product.supplierinfo",
                           [("date_end", "<", hoy), ("comercio_escala_de_id", "=", False)],
                           ["partner_id", "product_tmpl_id", "product_code", "product_name", "price"],
                           order="date_end desc, id desc"):
        if s["product_tmpl_id"] and s["partner_id"]:
            clave = (s["partner_id"][0], s["product_code"] or "", s["product_name"] or "")
            cerrados.setdefault(clave, {"id": s["id"], "partner": socios.get(s["partner_id"][0], ""),
                                        "partner_id": s["partner_id"][0], "tmpl": s["product_tmpl_id"][0],
                                        "product_code": s["product_code"] or False,
                                        "product_name": s["product_name"] or False, "price": s["price"]})
    return Foto(
        cerrados=list(cerrados.values()),
        productos=productos,
        proveedores_producto=[
            {"id": s["id"], "partner": socios.get(s["partner_id"][0], ""), "partner_id": s["partner_id"][0],
             "tmpl": s["product_tmpl_id"][0],
             "product_code": s["product_code"] or False, "product_name": s["product_name"] or False,
             "price": s["price"], "min_qty": s["min_qty"], "delay": s["delay"],
             "comercio_precio_mayor": s["comercio_precio_mayor"],
             "comercio_cantidad_mayor": s["comercio_cantidad_mayor"],
             "comercio_bulto": s.get("comercio_bulto") or 0.0,
             "comercio_presentaciones": s.get("comercio_presentaciones") or False,
             "date_start": str(s["date_start"]) if s["date_start"] else None,
             "lista_id": s["comercio_lista_id"][0] if s.get("comercio_lista_id") else None,
             "uom_id": _id(s.get("uom_id")),
             # La caja del proveedor («Caja 1000 = 2,5 kg»): su precio es el de esa unidad
             "unidad_propia": bool(_id(s.get("uom_id"))
                                   and _id(s.get("uom_id")) != unidad_de.get(s["product_tmpl_id"][0]))}
            for s in prov if s["product_tmpl_id"]
        ],
        proveedores=set(socios.values()),
        socios=socios,
        categorias={cat["complete_name"] for cat in c.search_read("product.category", [], ["complete_name"])},
        hoy=hoy,
        unidades=todas,
    )


TANDA = 200  # productos nuevos creados juntos (mucho más rápido que de a uno)


def _impuestos_iva(c) -> dict:
    """{("sale" | "purchase", alícuota): id} de los IVA de la localización («IVA 21%», «IVA 10.5%»…)."""
    salida = {}
    for t in c.search_read("account.tax", [("amount_type", "=", "percent"), ("name", "=like", "IVA %"),
                                           ("type_tax_use", "in", ["sale", "purchase"])],
                           ["type_tax_use", "amount"], order="sequence, id"):
        salida.setdefault((t["type_tax_use"], round(t["amount"], 4)), t["id"])
    return salida


def aplicar(c, acciones, hoy: str, lista_id: int | None = None) -> dict:
    """Aplica las acciones. Devuelve {clave de producto nuevo del plan: id creado}.

    `lista_id`: la lista del módulo que se está aplicando; queda anotada en cada precio que
    carga o actualiza (para calcular las bajas de esa lista sola).

    Si el cliente tiene `create_many(model, lista)`, los productos nuevos se crean en tandas.
    """
    def ref(nombre: str) -> int:
        filas = c.search_read("ir.model.data", [("module", "=", "uom"), ("name", "=", nombre)], ["res_id"])
        return filas[0]["res_id"]

    # Proveedor por nombre solo cuando la fila no trae su id (herramienta de línea de comandos);
    # se prefieren los contactos activos.
    socios: dict[str, int] = {}
    for p in c.search_read("res.partner", [], ["name", "active"], context={**c.context, **SIN_ARCHIVADOS}):
        if p["active"] or _clave(p["name"]) not in socios:
            socios[_clave(p["name"])] = p["id"]
    impuestos_iva = _impuestos_iva(c)
    categorias = {_clave(cat["complete_name"]): cat["id"]
                  for cat in c.search_read("product.category", [], ["complete_name"])}
    unidades: dict[str, int] = {}
    nuevos: dict[str, int] = {}

    def socio(nombre: str) -> int:
        clave = _clave(nombre)
        if clave not in socios:
            socios[clave] = c.create("res.partner", {"name": nombre, "is_company": True, "supplier_rank": 1})
        return socios[clave]

    def valores_proveedor(v: dict, nuevo: bool = False) -> dict:
        campos = ("product_code", "product_name", "price", "min_qty", "delay", "date_start",
                  "comercio_precio_mayor", "comercio_cantidad_mayor", "comercio_bulto",
                  "comercio_presentaciones", "uom_id")
        out = {k: v[k] for k in campos if k in v}
        if lista_id:
            out["comercio_lista_id"] = lista_id
        if nuevo:
            out.setdefault("date_start", hoy)  # el historial muestra desde cuándo rige cada precio
        if v.get("partner_id"):
            out["partner_id"] = v["partner_id"]
        elif "partner" in v:
            out["partner_id"] = socio(v["partner"])
        return out

    pendientes: list = []  # (clave del plan, valores) de productos nuevos por crear
    acciones_nuevas = {a.tmpl: a for a in acciones if a.tipo == NUEVO}
    campos_prov = ["product_code", "product_name", "price", "min_qty", "delay", "comercio_precio_mayor",
                   "comercio_cantidad_mayor", "comercio_bulto", "comercio_presentaciones", "uom_id"]

    def crear_pendientes():
        if not pendientes:
            return
        if hasattr(c, "create_many"):
            ids = c.create_many("product.template", [vals for _k, vals in pendientes])
        else:
            ids = [c.create("product.template", vals) for _k, vals in pendientes]
        for (clave, _vals), id_ in zip(pendientes, ids, strict=True):
            nuevos[clave] = id_
            acciones_nuevas[clave].deshacer = {"producto": id_}
        pendientes.clear()

    for a in acciones:
        if a.tipo == NUEVO:
            p = a.producto
            unidades.setdefault(p["uom"], ref(p["uom"]))
            vals = {"name": p["name"], "default_code": p["default_code"], "barcode": p["barcode"],
                    "uom_id": unidades[p["uom"]], "type": "consu", "is_storable": p["is_storable"],
                    "available_in_pos": True, "purchase_ok": True,
                    "to_weight": p["to_weight"], "standard_price": p["standard_price"],
                    "seller_ids": [[0, 0, valores_proveedor(a.proveedor, nuevo=True)]]}
            if p["categoria"]:
                vals["categ_id"] = categorias[_clave(p["categoria"])]
            if p["list_price"] is not None:
                vals["list_price"] = p["list_price"]
            if p.get("codigo_lista"):  # el código de la lista que no se pudo usar: para verificarlo
                vals["comercio_codigo_lista"] = p["codigo_lista"]
            venta, compra = (impuestos_iva.get((uso, p.get("iva"))) for uso in ("sale", "purchase"))
            if p.get("iva") and venta and compra:  # la alícuota de la lista; si no, la del rubro
                vals["taxes_id"] = [[6, 0, [venta]]]
                vals["supplier_taxes_id"] = [[6, 0, [compra]]]
            pendientes.append((a.tmpl, vals))
            if len(pendientes) >= TANDA:
                crear_pendientes()
        elif a.tipo in (VINCULAR, ACTUALIZAR):
            if isinstance(a.tmpl, str):
                crear_pendientes()
            tmpl = nuevos.get(a.tmpl, a.tmpl)
            if isinstance(tmpl, str):
                raise ValueError(f"fila {a.fila}: el producto nuevo al que se vincula no se creó todavía")
            if a.tipo == VINCULAR:
                vals = {"product_tmpl_id": tmpl, **valores_proveedor(a.proveedor, nuevo=True)}
                a.deshacer["borrar_prov"] = c.create("product.supplierinfo", vals)
            elif a.historial:  # D7: se cierra el precio anterior y se abre uno nuevo desde hoy
                c.write("product.supplierinfo", [a.proveedor_id], {"date_end": _ayer(hoy)})
                a.deshacer["reabrir_prov"] = a.proveedor_id
                a.deshacer["borrar_prov"] = c.create(
                    "product.supplierinfo", {"product_tmpl_id": tmpl, **valores_proveedor(a.proveedor)})
            elif a.proveedor:
                antes = c.search_read("product.supplierinfo", [("id", "=", a.proveedor_id)], campos_prov)[0]
                antes = {k: _id(v) if k == "uom_id" else v for k, v in antes.items() if k in campos_prov}
                a.deshacer["restaurar_prov"] = [a.proveedor_id, antes]
                c.write("product.supplierinfo", [a.proveedor_id], valores_proveedor(a.proveedor))
            if a.completar_barcode and a.codigo_propio_anterior:
                # El de fábrica reemplaza al propio (20/11); el propio queda como código alternativo
                # (presentación de la unidad del producto), así la caja sigue leyendo la etiqueta pegada
                c.write("product.template", [tmpl], {"barcode": a.completar_barcode})
                variante = c.search_read("product.product", [("product_tmpl_id", "=", tmpl)],
                                         ["id", "uom_id"])[0]
                alternativo = c.create("product.uom", {"product_id": variante["id"],
                                                       "uom_id": _id(variante["uom_id"]),
                                                       "barcode": a.codigo_propio_anterior})
                a.deshacer["restaurar_barcode"] = [tmpl, a.codigo_propio_anterior, alternativo]
            elif a.completar_barcode:
                c.write("product.template", [tmpl], {"barcode": a.completar_barcode})
                a.deshacer["quitar_barcode"] = tmpl
        elif a.tipo == BAJA:
            # Se cierra hasta ayer (desde hoy ya no rige). Si el precio empezó hoy (p. ej. dos
            # listas el mismo día), Odoo no acepta un fin anterior al inicio: el inicio también
            # pasa a ayer, y deshacer lo devuelve.
            ayer = _ayer(hoy)
            inicio = c.search_read("product.supplierinfo", [("id", "=", a.proveedor_id)], ["date_start"])
            inicio = str(inicio[0]["date_start"]) if inicio and inicio[0]["date_start"] else None
            vals = {"date_end": ayer}
            if inicio and inicio > ayer:
                vals["date_start"] = ayer
                a.deshacer["restaurar_inicio"] = [a.proveedor_id, inicio]
            c.write("product.supplierinfo", [a.proveedor_id], vals)
            a.deshacer["reabrir_prov"] = a.proveedor_id
    crear_pendientes()
    return nuevos


def costo_por_unidad(precios: list[dict]) -> float | None:
    """Costo de un producto a partir de sus precios vigentes ({price_discounted, min_qty}).

    Cuenta el **precio por unidad** (cantidad mínima hasta 1) más barato entre sus
    proveedores: un precio por bulto dejaría el costo más bajo de lo que cuesta comprar
    una unidad. Si ningún proveedor vende por unidad, se toma el de menor cantidad mínima
    (el más barato entre esos). Sin precios vigentes: None (el costo no se toca).
    """
    if not precios:
        return None
    por_unidad = [p for p in precios if (p["min_qty"] or 0) <= 1]
    if not por_unidad:
        menor = min(p["min_qty"] for p in precios)
        por_unidad = [p for p in precios if p["min_qty"] == menor]
    return round(min(p["price_discounted"] for p in por_unidad), 2)


def actualizar_costos(c, plantillas, hoy: str) -> dict:
    """Costo del producto = el precio por unidad vigente más barato entre sus proveedores (P-044).

    Solo lo cambian las listas de proveedores (aplicar o deshacer una importación, carga
    inicial) y una tarea diaria (precios que empiezan o vencen). Los productos con «Costo
    manual» (alguien escribió el costo a mano) no se tocan. Es el costo que usa Odoo cuando una compra
    no tiene precio de lista (fuera de la lista o por debajo del mínimo), la base del
    margen (P-030) y el que valoriza el stock. Las listas están en pesos. Un producto sin
    precio vigente conserva su costo. Devuelve {plantilla: (costo anterior, costo nuevo)}
    de los que cambiaron.
    """
    ids = sorted({t for t in plantillas if isinstance(t, int)})
    if not ids:
        return {}
    vigentes = c.search_read(
        "product.supplierinfo",
        [("product_tmpl_id", "in", ids), "|", ("date_end", "=", False), ("date_end", ">=", hoy),
         "|", ("date_start", "=", False), ("date_start", "<=", hoy)],
        ["product_tmpl_id", "price_discounted", "min_qty", "partner_id"],
    )
    precios: dict[int, list[dict]] = {}
    for s in vigentes:
        precios.setdefault(s["product_tmpl_id"][0], []).append(s)
    cambios = {}
    actuales = c.search_read("product.template", [("id", "in", list(precios)),
                                                  ("comercio_costo_manual", "=", False)],
                             ["standard_price", "comercio_costo_de_id"],
                             context={**c.context, **SIN_ARCHIVADOS})
    socios = {}
    elegidos = {p["comercio_costo_de_id"][0] for p in actuales if p.get("comercio_costo_de_id")}
    if elegidos:  # «Costo de»: los precios de ese proveedor (o de sus contactos)
        socios = {s["id"]: s["commercial_partner_id"][0] for s in c.search_read(
            "res.partner", [("id", "in", list({s["partner_id"][0] for s in vigentes if s["partner_id"]}))],
            ["commercial_partner_id"])}
    for p in actuales:
        suyos = precios[p["id"]]
        if p.get("comercio_costo_de_id"):
            elegido = p["comercio_costo_de_id"][0]
            del_elegido = [s for s in suyos if s["partner_id"] and socios.get(s["partner_id"][0]) == elegido]
            suyos = del_elegido or suyos  # sin precio vigente de ese proveedor: el más barato
        nuevo = costo_por_unidad(suyos)
        if nuevo is not None and abs((p["standard_price"] or 0) - nuevo) > 0.005:
            # Con la marca explícita: así el módulo no lo toma como un cambio a mano
            c.write("product.template", [p["id"]],
                    {"standard_price": nuevo, "comercio_costo_manual": False})
            cambios[p["id"]] = (p["standard_price"], nuevo)
    return cambios
