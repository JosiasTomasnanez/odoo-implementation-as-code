import pytest

from odoo_iac.settings import ROOT, load_environment
from odoo_iac.state import StateError, load_state


def write(path, text):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text)


def test_capas_se_combinan(tmp_path):
    write(tmp_path / "base/00-mod.yaml", "modules: [stock]\n")
    write(tmp_path / "base/10-cat.yaml", """
model: product.category
records:
  - id: cat_a
    values: {name: A}
""")
    write(tmp_path / "online/10-cat.yaml", """
model: product.category
records:
  - id: cat_a
    values: {name: A online}
  - id: cat_b
    values: {name: B}
""")
    state = load_state([tmp_path / "base", tmp_path / "online"])
    assert state.modules == ["stock"]
    assert [(r.id, r.values["name"]) for r in state.records] == [("cat_a", "A online"), ("cat_b", "B")]


@pytest.mark.parametrize("text, message", [
    ("model: x\nrecords:\n  - values: {}\n", "necesita 'id'"),
    ("model: x\nrecords:\n  - id: Mal-Id\n", "inválido"),
    ("model: x\nrecords:\n  - id: a\n    name: A\n", "faltó 'values'"),
    ("records: []\n", "falta 'model'"),
    ("modules: [a]\nmodel: x\n", "solo contiene"),
    ("settings: [a]\n", "solo contiene"),
])
def test_errores_de_formato(tmp_path, text, message):
    write(tmp_path / "c/a.yaml", text)
    with pytest.raises(StateError, match=message):
        load_state([tmp_path / "c"])


def test_mismo_id_en_otro_modelo_falla(tmp_path):
    write(tmp_path / "c/a.yaml", "model: x\nrecords:\n  - id: a\n")
    write(tmp_path / "c/b.yaml", "model: y\nrecords:\n  - id: a\n")
    with pytest.raises(StateError, match="ya definido"):
        load_state([tmp_path / "c"])


def test_configuracion_del_repo_es_valida():
    """Todas las capas de todos los entornos del repo deben poder leerse."""
    for path in (ROOT / "environments").glob("*.yaml"):
        env = load_environment(path.stem)
        load_state(env.layers, env.values)


def test_valores_centralizados(tmp_path):
    write(tmp_path / "valores.yaml", """
puestos:
  caja_1: Caja 1
  cajas_cobran: true
""")
    write(tmp_path / "valores.demo.yaml", "puestos:\n  caja_1: Caja demo\n")
    write(tmp_path / "c/a.yaml", """
model: pos.config
records:
  - id: caja
    values:
      name: {valor: puestos.caja_1}
      activo: {valor: puestos.cajas_cobran}
      payment_method_ids: {refs: [pm_a]}
""")
    state = load_state([tmp_path / "c"], [tmp_path / "valores.yaml"])
    assert state.records[0].values == {
        "name": "Caja 1", "activo": True, "payment_method_ids": {"refs": ["pm_a"]}}
    # Un archivo posterior pisa solo lo que define (como un values.yaml de demo)
    state = load_state([tmp_path / "c"], [tmp_path / "valores.yaml", tmp_path / "valores.demo.yaml"])
    assert state.records[0].values["name"] == "Caja demo"
    assert state.records[0].values["activo"] is True


def test_archivo_se_lee_en_base64(tmp_path):
    (tmp_path / "imagenes").mkdir()
    (tmp_path / "imagenes/logo.png").write_bytes(b"\x89PNG-logo")
    write(tmp_path / "c/a.yaml", """
model: pos.config
records:
  - id: puesto
    values:
      custom_logo: {archivo: ../imagenes/logo.png}
""")
    valor = load_state([tmp_path / "c"]).records[0].values["custom_logo"]
    assert valor == "iVBORy1sb2dv"  # base64 de b"\x89PNG-logo"
    assert valor.ruta == "../imagenes/logo.png"
    write(tmp_path / "c/a.yaml", "model: x\nrecords:\n  - id: a\n    values: {logo: {archivo: nada.png}}\n")
    with pytest.raises(StateError, match="no existe"):
        load_state([tmp_path / "c"])


def test_valor_inexistente_falla(tmp_path):
    write(tmp_path / "valores.yaml", "puestos: {}\n")
    write(tmp_path / "c/a.yaml", "model: x\nrecords:\n  - id: a\n    values: {name: {valor: puestos.nada}}\n")
    with pytest.raises(StateError, match="no está definido"):
        load_state([tmp_path / "c"], [tmp_path / "valores.yaml"])


def test_ajustes_se_combinan(tmp_path):
    write(tmp_path / "base/00-ajustes.yaml", "settings: {a: true, b: 1}\n")
    write(tmp_path / "lab/00-ajustes.yaml", "settings: {b: 2}\n")
    state = load_state([tmp_path / "base", tmp_path / "lab"])
    assert state.settings == {"a": True, "b": 2}
