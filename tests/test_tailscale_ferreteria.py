"""Política de Tailscale para la PC de ferretería (infra/servidor/tailscale_ferreteria.py)."""

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parents[1] / "infra" / "servidor"))
import tailscale_ferreteria as tf  # noqa: E402

IP = "100.64.0.1"


def test_politica_nueva_con_grants_limita_la_etiqueta_al_443_del_servidor():
    actual = {"grants": [{"src": ["*"], "dst": ["*"], "ip": ["*"]}],
              "ssh": [{"action": "check", "src": ["autogroup:member"], "dst": ["autogroup:self"],
                       "users": ["autogroup:nonroot", "root"]}]}
    nueva = tf.politica_con_ferreteria(actual, IP)
    assert nueva["tagOwners"] == {"tag:ferreteria": ["autogroup:admin"]}
    assert nueva["grants"] == [{"src": ["autogroup:member"], "dst": ["*"], "ip": ["*"]},
                               {"src": ["tag:ferreteria"], "dst": [IP], "ip": ["tcp:443"]}]
    assert nueva["ssh"] == actual["ssh"]  # el SSH no se toca
    assert actual["grants"][0]["src"] == ["*"]  # no modifica la que recibe
    assert tf.politica_con_ferreteria(nueva, IP) == nueva  # idempotente


def test_politica_vieja_con_acls():
    actual = {"acls": [{"action": "accept", "src": ["*"], "dst": ["*:*"]}]}
    nueva = tf.politica_con_ferreteria(actual, IP)
    assert nueva["acls"] == [{"action": "accept", "src": ["autogroup:member"], "dst": ["*:*"]},
                             {"action": "accept", "src": ["tag:ferreteria"], "dst": [f"{IP}:443"]}]
    assert "grants" not in nueva
    assert tf.politica_con_ferreteria(nueva, IP) == nueva


def test_si_cambia_la_ip_del_servidor_se_reemplaza_la_regla():
    vieja = tf.politica_con_ferreteria({"grants": []}, "100.1.1.1")
    nueva = tf.politica_con_ferreteria(vieja, IP)
    assert [r for r in nueva["grants"] if r["src"] == ["tag:ferreteria"]] == [
        {"src": ["tag:ferreteria"], "dst": [IP], "ip": ["tcp:443"]}]


def test_ip_del_servidor_por_su_nombre_de_magicdns_no_por_el_hostname():
    dispositivos = [{"name": "equipo-tecnico.tail1.ts.net", "hostname": "servidor-ejemplo",
                     "addresses": ["100.64.0.2"]},  # hostname elegido por el equipo: no cuenta
                    {"name": "servidor-ejemplo.tail1.ts.net", "hostname": "x", "nodeId": "n1",
                     "addresses": ["fd7a:115c::1", IP]}]
    assert tf.ip_del_servidor(dispositivos) == IP
    with pytest.raises(tf.ErrorTailscale):
        tf.ip_del_servidor(dispositivos[:1])
    repetido = dispositivos + [{"name": "servidor-ejemplo-1.tail1.ts.net", "addresses": ["100.9.9.9"]},
                               {"name": "servidor-ejemplo.otro.ts.net", "addresses": ["100.8.8.8"]}]
    with pytest.raises(tf.ErrorTailscale, match="Hay 2"):
        tf.ip_del_servidor(repetido)


def test_el_asterisco_mezclado_tambien_se_corrige():
    actual = {"grants": [{"src": ["*", "group:admins"], "dst": ["*"], "ip": ["*"]}]}
    nueva = tf.politica_con_ferreteria(actual, IP)
    assert nueva["grants"][0]["src"] == ["autogroup:member", "group:admins"]


@pytest.mark.parametrize("origen", ["autogroup:tagged", "tag:ferreteria"])
def test_una_regla_ajena_que_incluye_equipos_con_etiqueta_frena(origen):
    actual = {"grants": [{"src": ["group:x", origen], "dst": ["*"], "ip": ["*"]}]}
    with pytest.raises(tf.ErrorTailscale, match="revisarla a mano"):
        tf.politica_con_ferreteria(actual, IP)


def test_la_clave_es_de_un_solo_uso_y_con_la_etiqueta():
    pedido = tf.pedido_de_clave()["capabilities"]["devices"]["create"]
    assert pedido == {"reusable": False, "ephemeral": False, "preauthorized": True,
                      "tags": ["tag:ferreteria"]}
