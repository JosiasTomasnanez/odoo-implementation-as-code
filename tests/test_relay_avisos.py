"""Relay de alertas de Grafana (infra/docker/monitoreo/relay/relay_discord.py): sin repetir
avisos encendidos en cada reenvío del grupo y sin mail para las alertas de negocio."""
import importlib
import sys
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ / "infra" / "servidor"))
sys.path.insert(0, str(RAIZ / "infra" / "docker" / "monitoreo" / "relay"))
relay = importlib.import_module("relay_discord")


def alerta(huella, tipo="negocio", estado="firing"):
    return {"status": estado, "fingerprint": huella,
            "labels": {"alertname": "Lista de proveedor sin importar", "tipo": tipo, "nivel": "aviso",
                       "lista": huella},
            "annotations": {"summary": f"La lista {huella} no se importa"}}


def setup_function():
    relay._avisadas.clear()


def test_reenvio_del_grupo_no_repite_las_ya_avisadas():
    primero = list(relay.avisos_de({"alerts": [alerta("a"), alerta("b")]}))
    assert len(primero) == 2
    # Grafana reenvía el grupo con una lista más: solo sale la nueva
    segundo = list(relay.avisos_de({"alerts": [alerta("a"), alerta("b"), alerta("c")]}))
    assert [a[1] for a in segundo] == ["La lista c no se importa"]


def test_al_dia_siguiente_se_repite():
    relay.nueva("a", ahora=0)
    assert relay.nueva("a", ahora=relay.REPETIR_CADA - 1) is False
    assert relay.nueva("a", ahora=relay.REPETIR_CADA) is True


def test_negocio_solo_discord_y_servidor_tambien_mail():
    avisos = list(relay.avisos_de({"alerts": [alerta("x"), alerta("disco", tipo="servidor")]}))
    assert [a[-1] for a in avisos] == [False, True]


def test_se_arreglo_siempre_sale_y_permite_volver_a_avisar():
    list(relay.avisos_de({"alerts": [alerta("a")]}))
    arreglo = list(relay.avisos_de({"alerts": [alerta("a", estado="resolved")]}))
    assert arreglo[0][0] == "ok"
    assert len(list(relay.avisos_de({"alerts": [alerta("a")]}))) == 1


def test_muchas_iguales_van_en_un_solo_aviso():
    pares = list(relay._avisos_y_alertas({"alerts": [alerta(str(i), estado="resolved") for i in range(49)]}))
    avisos = relay.juntar([a for a, _ in pares], [al for _, al in pares])
    assert len(avisos) == 1
    assert avisos[0][0] == "ok" and avisos[0][1].startswith("Se arreglaron 49:")


def test_pocas_van_por_separado():
    pares = list(relay._avisos_y_alertas({"alerts": [alerta("a"), alerta("b")]}))
    assert len(relay.juntar([a for a, _ in pares], [al for _, al in pares])) == 2
