import pytest

from ragleveling.catalog import Catalog
from ragleveling.models import Character, GameMap, Monster, Spawn


@pytest.fixture
def catalogo() -> Catalog:
    monstros = {
        1: Monster(id=1, name="Fraco", level=20, hp=500, base_exp=100, job_exp=80),
        2: Monster(id=2, name="Forte", level=40, hp=4000, base_exp=1600, job_exp=900),
        3: Monster(id=3, name="Chefe", level=50, hp=100000, base_exp=90000, job_exp=50000, mvp=True),
    }
    mapas = [
        GameMap(id="campo", name="Campo", spawns=[Spawn(monster_id=1, amount=30, respawn_seconds=20)]),
        GameMap(id="dungeon", name="Dungeon", spawns=[Spawn(monster_id=2, amount=30, respawn_seconds=20)]),
        GameMap(id="covil", name="Covil", spawns=[Spawn(monster_id=3, amount=1, respawn_seconds=3600)]),
    ]
    return Catalog(monsters=monstros, maps=mapas, exp_table={lvl: 10_000 for lvl in range(1, 100)})


@pytest.fixture
def char() -> Character:
    return Character(base_level=20, job_level=10, dps=200, seek_seconds=2.0)


@pytest.fixture
def indice() -> dict:
    """Índice mínimo no mesmo formato que `ragleveling sync` grava."""
    return {
        "version": 1,
        "generated_at": 0,
        "monsters": [
            {
                "id": 10, "aegis_name": "FACIL", "name": "Facil", "level": 60, "hp": 1000,
                "base_exp": 500, "job_exp": 400, "attack": 100, "magic_attack": 50,
                "defense": 10, "magic_defense": 5, "attack_range": 1, "race": "Plant",
                "element": "Water", "element_level": 2, "size": "Medium",
                "classe": "Normal", "mvp": False, "boss": False,
            },
            {
                "id": 11, "aegis_name": "DIFICIL", "name": "Dificil", "level": 70, "hp": 50000,
                "base_exp": 9000, "job_exp": 7000, "attack": 2000, "magic_attack": 900,
                "defense": 120, "magic_defense": 90, "attack_range": 3, "race": "Demon",
                "element": "Fire", "element_level": 3, "size": "Large",
                "classe": "Normal", "mvp": False, "boss": False,
            },
            {
                "id": 12, "aegis_name": "CHEFE", "name": "Chefe", "level": 65, "hp": 300000,
                "base_exp": 90000, "job_exp": 50000, "attack": 5000, "magic_attack": 2000,
                "defense": 200, "magic_defense": 150, "attack_range": 3, "race": "Demon",
                "element": "Dark", "element_level": 4, "size": "Large",
                "classe": "Boss", "mvp": True, "boss": True,
            },
            {
                "id": 13, "aegis_name": "LONGE", "name": "Longe", "level": 130, "hp": 2000,
                "base_exp": 800, "job_exp": 600, "attack": 300, "magic_attack": 100,
                "defense": 20, "magic_defense": 10, "attack_range": 1, "race": "Brute",
                "element": "Wind", "element_level": 1, "size": "Small",
                "classe": "Normal", "mvp": False, "boss": False,
            },
            {
                "id": 14, "aegis_name": "SEMMAPA", "name": "Sem Mapa", "level": 62, "hp": 1200,
                "base_exp": 600, "job_exp": 500, "attack": 150, "magic_attack": 60,
                "defense": 15, "magic_defense": 8, "attack_range": 1, "race": "Fish",
                "element": "Neutral", "element_level": 1, "size": "Medium",
                "classe": "Normal", "mvp": False, "boss": False,
            },
        ],
        "skills": {
            "11": [
                {"name": "NPC_SUMMONSLAVE", "state": "attack"},
                {"name": "NPC_STUNATTACK", "state": "attack"},
                {"name": "AL_HEAL", "state": "idle"},
            ],
            "10": [{"name": "NPC_EMOTION", "state": "idle"}],
        },
        "spawns": {
            "10": [{"map": "campo01", "amount": 40, "respawn_ms": 5000}],
            "11": [
                {"map": "dungeon02", "amount": 30, "respawn_ms": 10000},
                {"map": "treasure01", "amount": 99, "respawn_ms": 0},
                {"map": "1@cata", "amount": 50, "respawn_ms": 0},
            ],
            "12": [{"map": "boss_map", "amount": 1, "respawn_ms": 3600000}],
            "13": [{"map": "campo09", "amount": 20, "respawn_ms": 5000}],
            "14": [{"map": "raro01", "amount": 2, "respawn_ms": 5000}],
        },
        "attr_fix": {
            "1": {
                "Neutral": {"Water": 100, "Fire": 100, "Wind": 100, "Earth": 100, "Dark": 100},
                "Water": {"Water": 25, "Fire": 150, "Wind": 100, "Earth": 100, "Dark": 100},
                "Wind": {"Water": 150, "Fire": 100, "Wind": 25, "Earth": 50, "Dark": 100},
                "Fire": {"Water": 50, "Fire": 25, "Wind": 100, "Earth": 150, "Dark": 100},
                "Earth": {"Water": 100, "Fire": 100, "Wind": 50, "Earth": 25, "Dark": 100},
            },
            "2": {
                "Neutral": {"Water": 100, "Fire": 100, "Wind": 100, "Earth": 100, "Dark": 100},
                "Water": {"Water": 0, "Fire": 175, "Wind": 100, "Earth": 100, "Dark": 100},
                "Wind": {"Water": 175, "Fire": 100, "Wind": 0, "Earth": 25, "Dark": 100},
                "Fire": {"Water": 25, "Fire": 0, "Wind": 100, "Earth": 175, "Dark": 100},
                "Earth": {"Water": 100, "Fire": 100, "Wind": 25, "Earth": 0, "Dark": 100},
            },
            "3": {
                "Neutral": {"Water": 100, "Fire": 100, "Wind": 100, "Earth": 100, "Dark": 100},
                "Water": {"Water": -25, "Fire": 200, "Wind": 100, "Earth": 100, "Dark": 100},
                "Wind": {"Water": 200, "Fire": 100, "Wind": -25, "Earth": 0, "Dark": 100},
                "Fire": {"Water": 0, "Fire": -25, "Wind": 100, "Earth": 200, "Dark": 100},
                "Earth": {"Water": 100, "Fire": 100, "Wind": 0, "Earth": -25, "Dark": 100},
            },
        },
    }
