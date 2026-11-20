import pytest
from fake_odoo import make_client

from odoo_iac.engine import ADOPT, CREATE, INSTALL, OK, UPDATE, Engine, PlanError
from odoo_iac.state import Archivo, DesiredState, Record


def record(id, model="product.category", match=None, noupdate=False, **values):
    return Record(id=id, model=model, values=values, match=match or [], noupdate=noupdate,
                  source=f"test#{id}")


def kinds(result):
    return [c.kind for c in result.changes]


def test_plan_no_escribe():
    client, fake = make_client()
    state = DesiredState(records=[record("cat_a", name="A")])
    result = Engine(client).run(state, apply=False)
    assert kinds(result) == [CREATE]
    assert fake.writes == []


def test_apply_es_idempotente():
    client, fake = make_client()
    state = DesiredState(records=[
        record("cat_a", name="A"),
        record("cat_b", name="B", parent_id={"ref": "cat_a"}),
    ])
    assert kinds(Engine(client).run(state, apply=True)) == [CREATE, CREATE]
    writes = len(fake.writes)

    again = Engine(client).run(state, apply=True)
    assert kinds(again) == [OK, OK]
    assert len(fake.writes) == writes
    assert len(fake.db["product.category"]) == 2
    child = next(r for r in fake.db["product.category"].values() if r["name"] == "B")
    assert fake.db["product.category"][child["parent_id"]]["name"] == "A"


def test_plan_resuelve_referencias_a_registros_nuevos():
    client, _ = make_client()
    state = DesiredState(records=[
        record("cat_a", name="A"),
        record("cat_b", name="B", parent_id={"ref": "cat_a"}),
    ])
    assert kinds(Engine(client).run(state)) == [CREATE, CREATE]


def test_detecta_y_corrige_desvios():
    client, fake = make_client()
    state = DesiredState(records=[record("cat_a", name="A")])
    Engine(client).run(state, apply=True)
    row = next(iter(fake.db["product.category"].values()))
    row["name"] = "Cambiado a mano"

    plan = Engine(client).run(state)
    assert kinds(plan) == [UPDATE]
    assert plan.changes[0].diff == {"name": ("Cambiado a mano", "A")}
    Engine(client).run(state, apply=True)
    assert row["name"] == "A"


def test_adopta_registro_existente_por_match():
    client, fake = make_client()
    existing = fake.insert("product.category", name="All")
    state = DesiredState(records=[record("cat_all", match=["name"], name="All")])
    assert kinds(Engine(client).run(state, apply=True)) == [ADOPT]
    assert len(fake.db["product.category"]) == 1
    assert kinds(Engine(client).run(state)) == [OK]
    assert Engine(client).lookup_xmlid("cat_all")[2] == existing


def test_match_ambiguo_falla():
    client, fake = make_client()
    fake.insert("product.category", name="X")
    fake.insert("product.category", name="X")
    state = DesiredState(records=[record("cat_x", match=["name"], name="X")])
    with pytest.raises(PlanError, match="ambigüedad"):
        Engine(client).run(state)


def test_noupdate_respeta_cambios_manuales():
    client, fake = make_client()
    state = DesiredState(records=[
        record("p1", model="product.template", noupdate=True, name="P", list_price=10.0),
    ])
    Engine(client).run(state, apply=True)
    next(iter(fake.db["product.template"].values()))["list_price"] = 12.5
    assert kinds(Engine(client).run(state)) == [OK]


def test_many2many_y_floats():
    client, fake = make_client()
    state = DesiredState(records=[
        record("tag_a", model="product.tag", name="a"),
        record("tag_b", model="product.tag", name="b"),
        record("p1", model="product.template", name="P", list_price=10,
               product_tag_ids={"refs": ["tag_b", "tag_a"]}),
    ])
    Engine(client).run(state, apply=True)
    assert kinds(Engine(client).run(state)) == [OK, OK, OK]


def test_imagen_desde_archivo_es_idempotente():
    client, fake = make_client()
    state = DesiredState(records=[
        record("p1", model="product.template", name="P", image_1920=Archivo("iVBORw==", "logo.png")),
    ])
    plan = Engine(client).run(state)
    assert plan.changes[0].diff["image_1920"] == (None, {"archivo": "logo.png"})
    Engine(client).run(state, apply=True)
    assert kinds(Engine(client).run(state)) == [OK]
    otro = DesiredState(records=[
        record("p1", model="product.template", name="P", image_1920=Archivo("R0lGOD==", "otro.gif")),
    ])
    cambio = Engine(client).run(otro).changes[0]
    assert cambio.kind == UPDATE
    assert cambio.diff["image_1920"] == ("(otro archivo)", {"archivo": "otro.gif"})


def test_campo_inexistente_falla():
    client, _ = make_client()
    state = DesiredState(records=[record("cat_a", nombre="A")])
    with pytest.raises(PlanError, match="no existe"):
        Engine(client).run(state)


def test_referencia_desconocida_falla():
    client, _ = make_client()
    state = DesiredState(records=[record("cat_b", name="B", parent_id={"ref": "nada"})])
    with pytest.raises(PlanError, match="desconocida"):
        Engine(client).run(state)


def test_modulos():
    client, fake = make_client()
    fake.insert("ir.module.module", name="stock", state="uninstalled")
    fake.insert("ir.module.module", name="product", state="installed")
    state = DesiredState(modules=["product", "stock"])
    assert kinds(Engine(client).run(state)) == [OK, INSTALL]
    Engine(client).run(state, apply=True)
    assert kinds(Engine(client).run(state)) == [OK, OK]

    with pytest.raises(PlanError, match="no disponibles"):
        Engine(client).run(DesiredState(modules=["inexistente"]), apply=True)


def test_modulo_propio_nuevo_refresca_la_lista():
    client, fake = make_client()
    fake.available = ["comercio_x"]
    state = DesiredState(modules=["comercio_x"])
    # plan: no escribe, avisa que se refresca al aplicar
    assert kinds(Engine(client).run(state)) == [INSTALL]
    assert not fake.db["ir.module.module"]
    Engine(client).run(state, apply=True)
    assert kinds(Engine(client).run(state)) == [OK]


def test_xmlid_huerfano_se_reapunta():
    client, fake = make_client()
    state = DesiredState(records=[record("cat_a", name="A")])
    Engine(client).run(state, apply=True)
    fake.db["product.category"].clear()  # alguien borró el registro en Odoo
    assert kinds(Engine(client).run(state, apply=True)) == [CREATE]
    assert len(fake.db["ir.model.data"]) == 1
    assert kinds(Engine(client).run(state)) == [OK]


def test_campo_de_un_modulo_pendiente_no_frena_el_plan():
    client, fake = make_client()
    fake.insert("ir.module.module", name="stock", state="uninstalled")
    state = DesiredState(
        modules=["stock"],
        records=[record("cat", name="A", campo_de_stock=True)],
    )
    result = Engine(client).run(state)
    assert kinds(result) == [INSTALL, CREATE]
    assert "campo_de_stock" in result.changes[1].note
    # Sin módulos pendientes, un campo inexistente sigue siendo un error
    with pytest.raises(PlanError, match="no existe"):
        Engine(client).run(DesiredState(records=[record("cat", name="A", campo_de_stock=True)]))


def test_referencia_a_un_modulo_pendiente_no_frena_el_plan():
    """Base nueva: el plan de un apply todavía no tiene instalado el módulo de la referencia."""
    client, fake = make_client()
    fake.insert("ir.module.module", name="stock", state="uninstalled")
    state = DesiredState(modules=["stock"],
                         records=[record("cat", name="A", parent_id={"ref": "stock.categoria_x"})])
    result = Engine(client).run(state)
    assert kinds(result) == [INSTALL, CREATE]
    assert result.changes[1].diff["parent_id"] == (None, {"ref": "stock.categoria_x"})
    # Sin módulos pendientes, una referencia desconocida sigue siendo un error
    with pytest.raises(PlanError, match="desconocida"):
        Engine(client).run(DesiredState(records=[
            record("cat", name="A", parent_id={"ref": "stock.categoria_x"})]))


def test_ajustes():
    client, fake = make_client()
    state = DesiredState(settings={"group_product_pricelist": True})
    plan = Engine(client).run(state)
    assert kinds(plan) == [UPDATE]
    assert plan.changes[0].diff == {"group_product_pricelist": (False, True)}
    assert [w for w in fake.writes if w[1] != "create"] == []

    Engine(client).run(state, apply=True)
    assert fake.settings["group_product_pricelist"] is True
    writes = len(fake.writes)
    assert kinds(Engine(client).run(state, apply=True)) == [OK]
    assert len(fake.writes) == writes


def test_ajuste_inexistente_falla():
    client, _ = make_client()
    with pytest.raises(PlanError, match="ajustes inexistentes"):
        Engine(client).run(DesiredState(settings={"no_existe": True}))
