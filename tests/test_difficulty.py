from ragleveling.difficulty import Pesos, calcular, classificar_skills
from ragleveling.jobs import Perfil


def test_classificar_skills_por_categoria():
    categorias, peso = classificar_skills(
        [
            {"name": "NPC_SUMMONSLAVE", "state": "attack"},
            {"name": "NPC_STUNATTACK", "state": "attack"},
            {"name": "AL_HEAL", "state": "idle"},
        ]
    )
    assert categorias == {"invocação": 1, "status": 1, "cura/reviver": 1}
    assert peso == 3.0 + 2.0 + 2.5


def test_skill_desconhecida_pesa_pouco():
    categorias, peso = classificar_skills([{"name": "NPC_XYZ", "state": "attack"}])
    assert categorias == {}
    assert peso == 0.5


def test_calcular_ordena_facil_e_dificil(indice):
    monstros = [m for m in indice["monsters"] if m["id"] in (10, 11)]
    scores = calcular(monstros, indice["skills"], Perfil.MELEE)
    assert scores[10].score == 0.0
    assert scores[11].score == 100.0
    assert scores[10].rotulo == "fácil"
    assert scores[11].rotulo == "difícil"


def test_perfil_magico_usa_mdef(indice):
    monstros = [m for m in indice["monsters"] if m["id"] in (10, 11)]
    so_defesa = Pesos(hp=0, defesa=1, ataque=0, skills_perigosas=0, quantidade_skills=0)
    fisico = calcular(monstros, {}, Perfil.MELEE, so_defesa)
    magico = calcular(monstros, {}, Perfil.MAGIC, so_defesa)
    # Ambos separam os dois monstros, mas por colunas diferentes do banco.
    assert fisico[11].score == magico[11].score == 100.0
    assert fisico[10].score == magico[10].score == 0.0


def test_lista_vazia(indice):
    assert calcular([], indice["skills"], Perfil.MELEE) == {}


def test_valores_iguais_nao_diferenciam(indice):
    monstro = dict(indice["monsters"][0])
    scores = calcular([monstro, dict(monstro, id=99)], {}, Perfil.MELEE)
    assert scores[99].score == 0.0


def test_perigos_ignora_categorias_inofensivas():
    from ragleveling.difficulty import Dificuldade

    d = Dificuldade(score=1, rotulo="fácil", categorias={"dano forte": 2, "invocação": 1})
    assert d.perigos == "invocação"
