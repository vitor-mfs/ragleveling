import pytest

from ragleveling.models import Character
from ragleveling.router import avaliar_spots, montar_rota


def test_avaliar_spots_ignora_mvp(catalogo, char):
    spots = avaliar_spots(catalogo, char)
    assert all(s.monster_id != 3 for s in spots)


def test_avaliar_spots_respeita_max_level_gap(catalogo):
    char = Character(base_level=20, dps=200, max_level_gap=5)
    spots = avaliar_spots(catalogo, char)
    assert {s.monster_id for s in spots} == {1}


def test_avaliar_spots_ordena_por_criterio(catalogo, char):
    por_base = avaliar_spots(catalogo, char, criterio="base")
    assert por_base == sorted(por_base, key=lambda s: s.base_exp_per_hour, reverse=True)
    por_job = avaliar_spots(catalogo, char, criterio="job")
    assert por_job == sorted(por_job, key=lambda s: s.job_exp_per_hour, reverse=True)


def test_criterio_invalido(catalogo, char):
    with pytest.raises(ValueError):
        avaliar_spots(catalogo, char, criterio="exp")


def test_rota_agrupa_niveis_no_mesmo_spot(catalogo, char):
    pernas = montar_rota(catalogo, char, até_o_nivel=30)
    assert pernas[0].from_level == 20
    assert pernas[-1].to_level == 30
    for anterior, seguinte in zip(pernas, pernas[1:], strict=False):
        assert anterior.to_level == seguinte.from_level
        assert (anterior.spot.map_id, anterior.spot.monster_id) != (seguinte.spot.map_id, seguinte.spot.monster_id)


def test_rota_estima_horas_com_exp_table(catalogo, char):
    pernas = montar_rota(catalogo, char, até_o_nivel=25)
    assert all(p.hours is not None and p.hours > 0 for p in pernas)


def test_rota_sem_exp_table_nao_estima_horas(catalogo, char):
    catalogo.exp_table = {}
    pernas = montar_rota(catalogo, char, até_o_nivel=25)
    assert all(p.hours is None for p in pernas)


def test_rota_exige_alvo_acima_do_nivel_atual(catalogo, char):
    with pytest.raises(ValueError):
        montar_rota(catalogo, char, até_o_nivel=20)


def test_histerese_evita_troca_por_ganho_marginal(catalogo, char):
    sem = montar_rota(catalogo, char, até_o_nivel=45, histerese=0.0)
    com = montar_rota(catalogo, char, até_o_nivel=45, histerese=0.30)
    assert len(com) <= len(sem)
