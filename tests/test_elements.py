import pytest

from ragleveling.elements import ELEMENTO_PT, ELEMENTOS, melhor_elemento, piores_elementos, pt, ranking_por_resistencia

RESIST = {"Neutral": 100, "Water": 0, "Earth": 100, "Fire": 175, "Wind": 100, "Poison": 125}


def test_melhor_elemento_pela_resistencia():
    assert melhor_elemento(RESIST) == ("Fire", 175)


def test_piores_elementos():
    assert piores_elementos(RESIST, limite=1) == [("Water", 0)]


def test_ranking_ordenado_e_desempata_pela_ordem_canonica():
    ranking = ranking_por_resistencia(RESIST)
    valores = [pct for _, pct in ranking]
    assert valores == sorted(valores, reverse=True)
    empatados = [e for e, pct in ranking if pct == 100]
    assert empatados == [e for e in ELEMENTOS if e in empatados]


@pytest.mark.parametrize("resist", [None, {}, {"Plasma": 300}])
def test_sem_resistencia_tudo_vale_100(resist):
    assert ranking_por_resistencia(resist) == [(e, 100) for e in ELEMENTOS]


def test_traducao_com_fallback():
    assert pt("Water", ELEMENTO_PT) == "Água"
    assert pt("Plasma", ELEMENTO_PT) == "Plasma"
