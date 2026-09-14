import pytest

from ragleveling.jobs import (
    JOB_ALIASES,
    JOB_PROFILE,
    Perfil,
    canonical_job_key,
    como_aplicar_elemento,
    perfil_de,
    sugerir,
)


@pytest.mark.parametrize(
    ("entrada", "esperado"),
    [
        ("Cavaleiro Rúnico", "Rune_Knight"),
        ("cavaleiro runico", "Rune_Knight"),
        ("Rune_Knight", "Rune_Knight"),
        ("rune knight", "Rune_Knight"),
        ("Arcebispo", "Arch_Bishop"),
        ("caçador", "Hunter"),
    ],
)
def test_canonical_job_key(entrada, esperado):
    assert canonical_job_key(entrada) == esperado


def test_transclasse_cai_na_classe_base():
    assert canonical_job_key("Arcebispo trans") == "Arch_Bishop"


def test_classe_desconhecida():
    assert canonical_job_key("Feiticeiro de Hogwarts") is None
    assert canonical_job_key("") is None


def test_sugestao_para_erro_de_digitacao():
    assert "Arch_Bishop" in sugerir("arcebispu")


def test_todo_alias_aponta_para_classe_com_perfil():
    faltando = {alvo for alvo in JOB_ALIASES.values() if alvo not in JOB_PROFILE}
    assert not faltando


def test_perfis():
    assert perfil_de("Arch_Bishop") is Perfil.MAGIC
    assert perfil_de("Ranger") is Perfil.RANGED
    assert perfil_de("Rune_Knight") is Perfil.MELEE


def test_como_aplicar_elemento_por_perfil():
    assert como_aplicar_elemento("Arch_Bishop", "Fogo") == "magia de Fogo"
    assert como_aplicar_elemento("Ranger", "Fogo") == "flecha de Fogo"
    assert como_aplicar_elemento("Rebellion", "Fogo") == "munição de Fogo"
    assert "carta de Fogo" in como_aplicar_elemento("Rune_Knight", "Fogo")
