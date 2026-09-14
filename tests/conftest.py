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
