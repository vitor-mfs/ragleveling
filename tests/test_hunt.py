import pytest

from ragleveling.hunt import cacar
from ragleveling.jobs import Perfil


def test_retorna_alvos_da_faixa(indice):
    alvos = cacar(indice, 60, "Rune_Knight")
    assert [a.id for a in alvos] == [10, 11]


def test_ignora_chefe_e_mvp(indice):
    assert all(a.id != 12 for a in cacar(indice, 60, "Rune_Knight"))


def test_ignora_monstro_fora_da_faixa(indice):
    # Id 13 é nível 130: fora de -5..+15 para um base 60.
    assert all(a.id != 13 for a in cacar(indice, 60, "Rune_Knight"))
    assert any(a.id == 13 for a in cacar(indice, 120, "Rune_Knight"))


def test_ignora_spawn_raro_demais(indice):
    # Id 14 só nasce em um mapa com 2 exemplares.
    assert all(a.id != 14 for a in cacar(indice, 60, "Rune_Knight"))
    assert any(a.id == 14 for a in cacar(indice, 60, "Rune_Knight", min_spawn=1))


def test_ignora_mapa_de_instancia_e_de_woe(indice):
    alvo = next(a for a in cacar(indice, 60, "Rune_Knight") if a.id == 11)
    assert [s.map_id for s in alvo.spawns] == ["dungeon02"]


def test_instancias_e_mapas_bloqueados_sob_demanda(indice):
    alvo = next(
        a
        for a in cacar(indice, 60, "Rune_Knight", incluir_instancias=True, todos_mapas=True)
        if a.id == 11
    )
    assert {s.map_id for s in alvo.spawns} == {"dungeon02", "treasure01", "1@cata"}


def test_ordena_do_mais_facil_ao_mais_dificil(indice):
    alvos = cacar(indice, 60, "Rune_Knight")
    assert alvos[0].dificuldade.score < alvos[-1].dificuldade.score


def test_ordenar_por_exp(indice):
    alvos = cacar(indice, 60, "Rune_Knight", ordenar_por="exp")
    assert alvos[0].id == 11  # muito mais EXP, apesar de mais difícil


def test_ordenar_invalido(indice):
    with pytest.raises(ValueError, match="ordenar_por"):
        cacar(indice, 60, "Rune_Knight", ordenar_por="drop")


def test_elemento_sugerido_vem_da_tabela(indice):
    alvo = next(a for a in cacar(indice, 60, "Rune_Knight") if a.id == 10)
    assert alvo.elemento_sugerido == ("Vento", 175)  # Água 2
    assert alvo.como_aplicar.startswith("carta de Vento")


def test_como_aplicar_muda_com_a_classe(indice):
    alvo = next(a for a in cacar(indice, 60, "Arch_Bishop") if a.id == 10)
    assert alvo.como_aplicar == "magia de Vento"


def test_perfil_explicito_sobrescreve_a_classe(indice):
    magico = cacar(indice, 60, "Rune_Knight", perfil=Perfil.MAGIC)
    assert magico  # não quebra e continua devolvendo a faixa
    fisico = cacar(indice, 60, "Rune_Knight")
    assert {a.id for a in magico} == {a.id for a in fisico}


def test_exp_efetiva_aplica_penalidade(indice):
    alvo = next(a for a in cacar(indice, 55, "Rune_Knight") if a.id == 11)
    assert alvo.level_diff == 15
    assert alvo.exp_rate == 1.5
    assert alvo.exp_efetiva == pytest.approx(9000 * 1.5)


def test_mapa_principal_e_o_de_maior_quantidade(indice):
    alvo = next(a for a in cacar(indice, 60, "Rune_Knight") if a.id == 10)
    assert alvo.mapa_principal.map_id == "campo01"
    assert alvo.mapa_principal.respawn_s == 5.0


def test_limite(indice):
    assert len(cacar(indice, 60, "Rune_Knight", limite=1)) == 1


def test_nivel_invalido(indice):
    with pytest.raises(ValueError, match="base level"):
        cacar(indice, 0, "Rune_Knight")


def test_faixa_invertida(indice):
    with pytest.raises(ValueError, match="faixa"):
        cacar(indice, 60, "Rune_Knight", faixa=(10, -10))


def test_sem_classe_ainda_sugere_elemento(indice):
    alvo = cacar(indice, 60, None)[0]
    assert "dano de" in alvo.como_aplicar


def test_alvo_carrega_link_do_divine_pride(indice):
    alvo = next(a for a in cacar(indice, 60, "Rune_Knight") if a.id == 10)
    assert alvo.url == "https://www.divine-pride.net/database/monster/10"


def test_spawn_do_complemento_fica_marcado(indice):
    indice["spawns"]["10"].append({"map": "clock_01", "amount": 30, "respawn_ms": 0, "extra": True})
    alvo = next(a for a in cacar(indice, 60, "Rune_Knight") if a.id == 10)
    marcados = [s for s in alvo.spawns if s.extra]
    assert [s.map_id for s in marcados] == ["clock_01"]
    assert all(not s.extra for s in alvo.spawns if s.map_id == "campo01")
