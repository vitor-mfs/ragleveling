"""Modelos de domínio: monstro, spawn, mapa e personagem."""

from __future__ import annotations

from pydantic import BaseModel, Field, field_validator


class Monster(BaseModel):
    """Um monstro do jogo. `base_exp`/`job_exp` são os valores brutos (rate 1x)."""

    id: int
    name: str
    level: int = Field(ge=1)
    hp: int = Field(gt=0)
    base_exp: int = Field(ge=0)
    job_exp: int = Field(ge=0)
    race: str = "desconhecido"
    element: str = "desconhecido"
    size: str = "desconhecido"
    mvp: bool = False


class Spawn(BaseModel):
    """Quantos exemplares de um monstro nascem num mapa e em quanto tempo voltam."""

    monster_id: int
    amount: int = Field(gt=0)
    respawn_seconds: float = Field(default=0.0, ge=0.0)
    """0 = respawn instantâneo (não limita o ritmo de kills)."""


class GameMap(BaseModel):
    """Um mapa e seus spawns."""

    id: str
    name: str
    spawns: list[Spawn] = Field(default_factory=list)
    notes: str = ""


class Character(BaseModel):
    """O personagem e o quanto ele consegue produzir por segundo no campo."""

    base_level: int = Field(ge=1)
    job_level: int = Field(default=1, ge=1)
    job: str = "desconhecido"

    dps: float = Field(gt=0)
    """Dano efetivo por segundo já contando ASPD, cast, misses e downtime de SP."""

    seek_seconds: float = Field(default=2.0, ge=0.0)
    """Tempo médio gasto andando/procurando entre um alvo e o próximo."""

    max_level_gap: int = Field(default=25, ge=0)
    """Quanto acima do personagem um monstro pode estar para a rota considerá-lo."""

    @field_validator("dps")
    @classmethod
    def _dps_finito(cls, v: float) -> float:
        if v != v or v in (float("inf"), float("-inf")):
            raise ValueError("dps precisa ser um número finito")
        return v


class ServerRates(BaseModel):
    """Rates do servidor. LATAM oficial é 1x/1x."""

    base_exp: float = Field(default=1.0, gt=0)
    job_exp: float = Field(default=1.0, gt=0)


class Spot(BaseModel):
    """Um par mapa + monstro já avaliado para um personagem."""

    map_id: str
    map_name: str
    monster_id: int
    monster_name: str
    monster_level: int
    level_diff: int
    exp_rate: float
    kills_per_hour: float
    base_exp_per_hour: float
    job_exp_per_hour: float
    limited_by_respawn: bool


class RouteLeg(BaseModel):
    """Um trecho da rota: uma faixa de níveis feita no mesmo spot."""

    from_level: int
    to_level: int
    spot: Spot
    hours: float | None = None
    """None quando não há tabela de EXP carregada para estimar o tempo."""
