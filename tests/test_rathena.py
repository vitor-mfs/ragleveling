import pytest

from ragleveling.rathena import (
    _fundir_spawns,
    _scripts_de_spawn,
    parse_attr_fix,
    parse_mob_db,
    parse_mob_skills,
    parse_spawns,
)

MOB_DB = """
Header:
  Type: MOB_DB
Body:
  - Id: 1002
    AegisName: PORING
    Name: Poring
    Level: 1
    Hp: 50
    BaseExp: 27
    JobExp: 20
    Attack: 7
    Defense: 2
    MagicDefense: 5
    Race: Plant
    Element: Water
    ElementLevel: 1
    Size: Medium
  - Id: 1086
    AegisName: GOLDEN_BUG
    Name: Golden Thief Bug
    Level: 65
    Hp: 120000
    BaseExp: 60000
    Class: Boss
    Race: Insect
    Element: Dark
    ElementLevel: 3
    Modes:
      Mvp: true
  - Id: 1120
    AegisName: GHOSTRING
    Name: Ghostring
    Level: 18
    Hp: 8000
    Class: Normal
    Race: Demon
    Element: Ghost
    ElementLevel: 4
    Modes:
      Detector: true
"""


def test_parse_mob_db_campos_basicos():
    monstros = {m["id"]: m for m in parse_mob_db(MOB_DB)}
    poring = monstros[1002]
    assert poring["name"] == "Poring"
    assert (poring["level"], poring["hp"], poring["base_exp"]) == (1, 50, 27)
    assert poring["element"] == "Water" and poring["element_level"] == 1
    assert poring["boss"] is False


def test_parse_mob_db_marca_chefe_e_mvp():
    monstros = {m["id"]: m for m in parse_mob_db(MOB_DB)}
    assert monstros[1086]["boss"] is True
    assert monstros[1086]["mvp"] is True
    # Detector não é chefe.
    assert monstros[1120]["boss"] is False


def test_parse_mob_db_preenche_ausentes_com_zero():
    monstros = {m["id"]: m for m in parse_mob_db(MOB_DB)}
    assert monstros[1120]["base_exp"] == 0
    assert monstros[1120]["defense"] == 0


SPAWNS = """\
//===== comentário =====
ein_dun01,0,0\tmonster\tPitman\t1616,70,5000
ein_dun01,0,0\tmonster\tOld Stove\t1617,1,5000
ein_dun01,0,0\tmonster\tUngoliant\t1618,1,3600000,3000000
prt_fild08,50,50,30,30\tmonster\tPoring\t1002,40,5000
moc_pryd04,0,0\tboss_monster\tOsiris\t1038,1,3600000,600000
"""


def test_parse_spawns_le_mapa_quantidade_e_respawn():
    spawns = parse_spawns(SPAWNS)
    assert spawns[1616] == [{"map": "ein_dun01", "amount": 70, "respawn_ms": 5000}]
    assert spawns[1002][0]["map"] == "prt_fild08"
    assert spawns[1618][0]["respawn_ms"] == 3600000


def test_parse_spawns_ignora_boss_monster():
    assert 1038 not in parse_spawns(SPAWNS)


def test_fundir_spawns_soma_o_mesmo_mapa():
    destino = {}
    _fundir_spawns(destino, {1: [{"map": "campo", "amount": 10, "respawn_ms": 9000}]})
    _fundir_spawns(destino, {1: [{"map": "campo", "amount": 5, "respawn_ms": 3000}]})
    assert destino["1"] == [{"map": "campo", "amount": 15, "respawn_ms": 3000}]


def test_fundir_spawns_mantem_mapas_diferentes():
    destino = {}
    _fundir_spawns(destino, {1: [{"map": "a", "amount": 10, "respawn_ms": 0}]})
    _fundir_spawns(destino, {1: [{"map": "b", "amount": 7, "respawn_ms": 0}]})
    assert {s["map"] for s in destino["1"]} == {"a", "b"}


SKILLS = """\
//comentário
1001,Scorpion@NPC_FIREATTACK,attack,186,1,2000,0,5000,yes,target,always,0,,,,,,,
1001,Scorpion@NPC_FIREATTACK,idle,186,1,2000,0,5000,yes,target,always,0,,,,,,,
1002,Poring@NPC_EMOTION,loot,197,1,2000,0,5000,yes,self,always,0,2,,,,,,
"""


def test_parse_mob_skills_agrupa_e_remove_duplicadas():
    skills = parse_mob_skills(SKILLS)
    assert [s["name"] for s in skills[1001]] == ["NPC_FIREATTACK"]
    assert skills[1002][0]["state"] == "loot"


ATTR_FIX = """
Body:
  - Level: 1
    Water:
      Fire: 150
      Water: 25
  - Level: 2
    Water:
      Fire: 175
      Water: 0
"""


def test_parse_attr_fix():
    tabela = parse_attr_fix(ATTR_FIX)
    assert tabela[1]["Water"]["Fire"] == 150
    assert tabela[2]["Water"]["Water"] == 0


def test_scripts_de_spawn_ignora_comentados():
    conf = """
// comentário
npc: npc/re/mobs/fields/prontera.txt
//npc: npc/re/mobs/academy.txt
npc: npc/re/mobs/dungeons/ein_dun.txt
"""
    assert _scripts_de_spawn(conf) == [
        "npc/re/mobs/fields/prontera.txt",
        "npc/re/mobs/dungeons/ein_dun.txt",
    ]


def test_carregar_indice_sem_sync(tmp_path):
    from ragleveling.config import Settings
    from ragleveling.rathena import SyncError, carregar_indice

    with pytest.raises(SyncError, match="sync"):
        carregar_indice(Settings(cache_dir=tmp_path))


SPAWNS_SEM_COORDENADAS = """\
oz_dun02\tmonster\tLava Toad\t21300,25
amicitia1\tmonster\tAmitera\t20924,55
iz_d05_i\tmonster\tDeep Sea Sedora\t20806,45,5000,0,"iz_d05_i_boss::OnMyMobDead"
ein_dun01,0,0\tmonster\tPitman\t1616,70,5000
"""


def test_parse_spawns_aceita_linha_sem_coordenadas():
    """As dungeons dos episódios recentes omitem x,y — o monstro nasce no mapa todo."""
    spawns = parse_spawns(SPAWNS_SEM_COORDENADAS)
    assert spawns[21300] == [{"map": "oz_dun02", "amount": 25, "respawn_ms": 0}]
    assert spawns[20924] == [{"map": "amicitia1", "amount": 55, "respawn_ms": 0}]


def test_parse_spawns_le_respawn_antes_do_evento():
    spawns = parse_spawns(SPAWNS_SEM_COORDENADAS)
    assert spawns[20806] == [{"map": "iz_d05_i", "amount": 45, "respawn_ms": 5000}]


def test_parse_spawns_nao_regride_no_formato_com_coordenadas():
    assert parse_spawns(SPAWNS_SEM_COORDENADAS)[1616][0]["map"] == "ein_dun01"
