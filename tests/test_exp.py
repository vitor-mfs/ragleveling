import pytest

from ragleveling.exp import PENALIDADE_RENEWAL, exp_por_kill, exp_rate, kills_por_hora
from ragleveling.models import Character, Monster, ServerRates


def test_exp_rate_sem_penalidade_na_faixa_neutra():
    for diff in range(-6, 6):
        assert exp_rate(diff) == 1.0


def test_exp_rate_penaliza_monstro_muito_abaixo():
    assert exp_rate(-10) == pytest.approx(0.60)
    assert exp_rate(-15) == pytest.approx(0.10)


def test_exp_rate_bonifica_monstro_acima():
    assert exp_rate(10) == pytest.approx(1.25)
    assert exp_rate(15) == pytest.approx(1.50)


def test_exp_rate_satura_fora_da_tabela():
    assert exp_rate(-99) == PENALIDADE_RENEWAL[min(PENALIDADE_RENEWAL)]
    assert exp_rate(99) == PENALIDADE_RENEWAL[max(PENALIDADE_RENEWAL)]


def test_exp_por_kill_aplica_penalidade_e_rates():
    monstro = Monster(id=1, name="M", level=30, hp=1000, base_exp=1000, job_exp=500)
    char = Character(base_level=20, dps=100)  # diff +10 -> 1.25
    base, job = exp_por_kill(monstro, char, ServerRates(base_exp=2.0, job_exp=1.0))
    assert base == pytest.approx(1000 * 1.25 * 2.0)
    assert job == pytest.approx(500 * 1.25)


def test_kills_por_hora_limitado_pelo_dano():
    monstro = Monster(id=1, name="M", level=20, hp=1800, base_exp=1, job_exp=1)
    char = Character(base_level=20, dps=100, seek_seconds=0.0)  # 18 s por kill
    ritmo, limitado = kills_por_hora(monstro, char, spawn_amount=100, respawn_seconds=1)
    assert ritmo == pytest.approx(200.0)
    assert limitado is False


def test_kills_por_hora_limitado_pelo_respawn():
    monstro = Monster(id=1, name="M", level=20, hp=10, base_exp=1, job_exp=1)
    char = Character(base_level=20, dps=10_000, seek_seconds=0.0)
    ritmo, limitado = kills_por_hora(monstro, char, spawn_amount=10, respawn_seconds=60)
    assert ritmo == pytest.approx(600.0)  # 10 mobs * 60 respawns/h
    assert limitado is True


def test_crowding_divide_o_ritmo():
    monstro = Monster(id=1, name="M", level=20, hp=100, base_exp=1, job_exp=1)
    char = Character(base_level=20, dps=100, seek_seconds=0.0)
    cheio, _ = kills_por_hora(monstro, char, crowding=1.0)
    dividido, _ = kills_por_hora(monstro, char, crowding=0.5)
    assert dividido == pytest.approx(cheio / 2)


def test_crowding_invalido():
    monstro = Monster(id=1, name="M", level=20, hp=100, base_exp=1, job_exp=1)
    char = Character(base_level=20, dps=100)
    with pytest.raises(ValueError):
        kills_por_hora(monstro, char, crowding=0.0)
