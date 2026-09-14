import pytest

from ragleveling.elements import ELEMENTO_PT, TabelaElemental, pt


@pytest.fixture
def tabela(indice) -> TabelaElemental:
    return TabelaElemental(indice["attr_fix"])


def test_melhor_elemento_contra_agua(tabela):
    elemento, pct = tabela.melhor_elemento("Water", 2)
    assert (elemento, pct) == ("Wind", 175)


def test_melhor_elemento_escala_com_o_nivel(tabela):
    assert tabela.melhor_elemento("Water", 1)[1] == 150
    assert tabela.melhor_elemento("Water", 3)[1] == 200


def test_modificador_direto(tabela):
    assert tabela.modificador("Fire", "Earth", 2) == 175
    assert tabela.modificador("Water", "Water", 2) == 0


def test_modificador_desconhecido_vale_100(tabela):
    assert tabela.modificador("Holy", "Water", 1) == 100


def test_piores_elementos(tabela):
    piores = tabela.piores("Fire", 3, limite=1)
    assert piores[0] == ("Fire", -25)


def test_nivel_fora_da_tabela_usa_o_mais_proximo(tabela):
    assert tabela.melhor_elemento("Water", 9) == tabela.melhor_elemento("Water", 3)


def test_ranking_ordenado(tabela):
    valores = [pct for _, pct in tabela.ranking("Water", 2)]
    assert valores == sorted(valores, reverse=True)


def test_tabela_vazia():
    with pytest.raises(ValueError, match="sync"):
        TabelaElemental({}).melhor_elemento("Water", 1)


def test_traducao_com_fallback():
    assert pt("Water", ELEMENTO_PT) == "Água"
    assert pt("Plasma", ELEMENTO_PT) == "Plasma"
