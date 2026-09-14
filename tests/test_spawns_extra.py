import json

import pytest

from ragleveling.config import Settings
from ragleveling.rathena import VERSAO_INDICE, SyncError, carregar_indice, carregar_spawns_extra


def _escrever(tmp_path, conteudo):
    arquivo = tmp_path / "spawns_extra.yaml"
    arquivo.write_text(conteudo, encoding="utf-8")
    return arquivo


def test_arquivo_ausente_nao_e_erro(tmp_path):
    assert carregar_spawns_extra(tmp_path / "nao_existe.yaml") == {}


def test_vazio(tmp_path):
    assert carregar_spawns_extra(_escrever(tmp_path, "mapas: {}\n")) == {}


def test_le_spawns_e_marca_origem(tmp_path):
    arquivo = _escrever(
        tmp_path,
        """
mapas:
  clock_01:
    fonte: https://www.divine-pride.net/database/map/clock_01
    spawns:
      - { monster_id: 20940, amount: 30, respawn_s: 5 }
      - { monster_id: 20942, amount: 25 }
""",
    )
    extra = carregar_spawns_extra(arquivo)
    assert extra["20940"] == [{"map": "clock_01", "amount": 30, "respawn_ms": 5000, "extra": True}]
    assert extra["20942"][0]["respawn_ms"] == 0


def test_spawn_invalido(tmp_path):
    arquivo = _escrever(tmp_path, "mapas:\n  clock_01:\n    spawns:\n      - { amount: 30 }\n")
    with pytest.raises(SyncError, match="spawn inválido"):
        carregar_spawns_extra(arquivo)


def test_mapas_com_formato_errado(tmp_path):
    with pytest.raises(SyncError, match="mapeamento"):
        carregar_spawns_extra(_escrever(tmp_path, "mapas:\n  - clock_01\n"))


def test_indice_funde_o_complemento(tmp_path, monkeypatch):
    indice = {
        "version": VERSAO_INDICE,
        "monsters": [],
        "skills": {},
        "spawns": {"20940": [{"map": "ja_existia", "amount": 10, "respawn_ms": 0}]},
        "attr_fix": {},
    }
    (tmp_path / "index.json").write_text(json.dumps(indice), encoding="utf-8")
    extra = _escrever(
        tmp_path,
        "mapas:\n  clock_01:\n    spawns:\n      - { monster_id: 20940, amount: 30 }\n",
    )
    monkeypatch.setenv("RAGLEVELING_SPAWNS_EXTRA", str(extra))

    carregado = carregar_indice(Settings(cache_dir=tmp_path))
    mapas = [s["map"] for s in carregado["spawns"]["20940"]]
    assert mapas == ["ja_existia", "clock_01"]
    assert carregado["spawns"]["20940"][1]["extra"] is True
