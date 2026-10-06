import json

import pytest
from typer.testing import CliRunner

from ragleveling.cli import app
from ragleveling.config import Settings, set_settings
from ragleveling.dp_itens import VERSAO_INDICE_ITENS

runner = CliRunner()


def _item(item_id, nome, descricao, locais, tipo="Armor"):
    return {
        "id": item_id, "name": nome, "aegis_name": "", "type": tipo, "subtype": "", "locations": locais,
        "location_raw": [], "required_level": 0, "weight": 0, "description": descricao, "all_jobs": True,
        "job_ids": [], "scripts": [], "icon_url": "",
    }  # fmt: skip


@pytest.fixture
def com_indice(tmp_path):
    settings = Settings(cache_dir=tmp_path)
    itens = [
        _item(1, "Carta Caramelo", "Dano físico contra a raça Inseto +20%.", ["carta"], "Card"),
        _item(2, "Elmo Verde", "Dano físico contra a raça Inseto +10%.", ["topo"]),
        _item(3, "Escudo", "Resistência as raças Dragão e Inseto +15%.", ["escudo"]),
    ]
    settings.items_index_path.write_text(
        json.dumps({"version": VERSAO_INDICE_ITENS, "items": itens}, ensure_ascii=False), encoding="utf-8"
    )
    set_settings(settings)
    yield settings
    set_settings(Settings.from_env())


def test_buscar_lista_do_maior_bonus_para_o_menor(com_indice):
    resultado = runner.invoke(app, ["buscar", "aumentar dano em insetos"])
    assert resultado.exit_code == 0
    assert resultado.output.index("Carta Caramelo") < resultado.output.index("Elmo Verde")
    assert "Escudo" not in resultado.output  # resistência não é dano causado


def test_buscar_reduzir_dano_acha_a_resistencia(com_indice):
    resultado = runner.invoke(app, ["buscar", "reduzir dano de dragões"])
    assert resultado.exit_code == 0 and "Escudo" in resultado.output


def test_buscar_filtra_por_local_e_aceita_carta(com_indice):
    topo = runner.invoke(app, ["buscar", "aumentar dano em insetos", "--local", "topo"])
    assert "Elmo Verde" in topo.output and "Carta Caramelo" not in topo.output
    cartas = runner.invoke(app, ["buscar", "aumentar dano em insetos", "--local", "carta"])
    assert "Carta Caramelo" in cartas.output and "Elmo Verde" not in cartas.output


def test_buscar_mostra_a_descricao_completa(com_indice):
    resultado = runner.invoke(app, ["buscar", "aumentar dano em insetos", "--completo"])
    assert resultado.exit_code == 0 and "Dano físico contra a raça Inseto +20%." in resultado.output


def test_buscar_frase_que_nao_entende_sai_com_erro(com_indice):
    resultado = runner.invoke(app, ["buscar", "aumentar EXP em insetos"])
    assert resultado.exit_code == 1 and "dano e resistência" in resultado.output


def test_buscar_sem_resultado_e_sem_indice(com_indice, tmp_path):
    vazio = runner.invoke(app, ["buscar", "aumentar dano da habilidade Xyz"])
    assert vazio.exit_code == 1 and "Nenhum item" in vazio.output
    com_indice.items_index_path.unlink()
    sem = runner.invoke(app, ["buscar", "aumentar dano em insetos"])
    assert sem.exit_code == 1 and "índice de itens não encontrado" in sem.output


def test_itens_local_carta_lista_so_cartas(com_indice):
    resultado = runner.invoke(app, ["itens", "--local", "carta"])
    assert resultado.exit_code == 0 and "Carta Caramelo" in resultado.output and "Elmo Verde" not in resultado.output
