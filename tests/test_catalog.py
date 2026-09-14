import pytest

from ragleveling.catalog import carregar


def _escrever(tmp_path, nome, conteudo):
    arquivo = tmp_path / nome
    arquivo.write_text(conteudo, encoding="utf-8")
    return arquivo


def test_carrega_arquivo_unico(tmp_path):
    arquivo = _escrever(
        tmp_path,
        "c.yaml",
        """
monsters:
  - {id: 1, name: M, level: 10, hp: 100, base_exp: 50, job_exp: 25}
maps:
  - id: campo
    name: Campo
    spawns:
      - {monster_id: 1, amount: 10, respawn_seconds: 15}
exp_table:
  10: 1000
""",
    )
    catalogo = carregar(arquivo)
    assert catalogo.monster(1).name == "M"
    assert catalogo.maps[0].spawns[0].amount == 10
    assert catalogo.exp_para_subir(10) == 1000


def test_carrega_diretorio_juntando_arquivos(tmp_path):
    _escrever(tmp_path, "a.yaml", "monsters:\n  - {id: 1, name: M, level: 10, hp: 100, base_exp: 50, job_exp: 25}\n")
    _escrever(tmp_path, "b.yaml", "maps:\n  - {id: campo, name: Campo, spawns: [{monster_id: 1, amount: 5}]}\n")
    catalogo = carregar(tmp_path)
    assert catalogo.monster(1) is not None
    assert catalogo.maps[0].id == "campo"


def test_spawn_orfao_e_erro(tmp_path):
    conteudo = "maps:\n  - {id: campo, name: Campo, spawns: [{monster_id: 99, amount: 5}]}\n"
    arquivo = _escrever(tmp_path, "c.yaml", conteudo)
    with pytest.raises(ValueError, match="99"):
        carregar(arquivo)


def test_diretorio_vazio(tmp_path):
    with pytest.raises(FileNotFoundError):
        carregar(tmp_path)


def test_exemplo_do_repositorio_carrega():
    from pathlib import Path

    catalogo = carregar(Path(__file__).resolve().parents[1] / "data")
    assert catalogo.monsters and catalogo.maps
