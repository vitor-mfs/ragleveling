"""Fórmula de EXP do Renewal: penalidade por diferença de nível e EXP por kill.

A tabela de penalidade abaixo é o padrão do Renewal (equivalente ao
`db/re/level_penalty.yml` do rAthena) e vale como ponto de partida.
Servidores oficiais podem ajustá-la — sobrescreva com `carregar_penalidade()`
se você tiver os valores confirmados do LATAM.
"""

from __future__ import annotations

from .models import Character, Monster, ServerRates

#: diferença (nível do monstro - nível do personagem) -> multiplicador de EXP.
#: Fora da faixa, vale o valor da ponta mais próxima.
PENALIDADE_RENEWAL: dict[int, float] = {
    -15: 0.10,
    -14: 0.20,
    -13: 0.30,
    -12: 0.40,
    -11: 0.50,
    -10: 0.60,
    -9: 0.70,
    -8: 0.80,
    -7: 0.90,
    -6: 1.00,
    -5: 1.00,
    -4: 1.00,
    -3: 1.00,
    -2: 1.00,
    -1: 1.00,
    0: 1.00,
    1: 1.00,
    2: 1.00,
    3: 1.00,
    4: 1.00,
    5: 1.00,
    6: 1.05,
    7: 1.10,
    8: 1.15,
    9: 1.20,
    10: 1.25,
    11: 1.30,
    12: 1.35,
    13: 1.40,
    14: 1.45,
    15: 1.50,
}

_MIN_DIFF = min(PENALIDADE_RENEWAL)
_MAX_DIFF = max(PENALIDADE_RENEWAL)


def exp_rate(level_diff: int, tabela: dict[int, float] | None = None) -> float:
    """Multiplicador de EXP para uma diferença de nível (monstro - personagem)."""
    tabela = tabela or PENALIDADE_RENEWAL
    menor, maior = min(tabela), max(tabela)
    if level_diff < menor:
        return tabela[menor]
    if level_diff > maior:
        return tabela[maior]
    return tabela[level_diff]


def exp_por_kill(
    monster: Monster,
    char: Character,
    rates: ServerRates | None = None,
    tabela: dict[int, float] | None = None,
) -> tuple[float, float]:
    """(base_exp, job_exp) de um kill, já com penalidade de nível e rates do servidor."""
    rates = rates or ServerRates()
    fator = exp_rate(monster.level - char.base_level, tabela)
    return (
        monster.base_exp * fator * rates.base_exp,
        monster.job_exp * fator * rates.job_exp,
    )


def kills_por_hora(
    monster: Monster,
    char: Character,
    spawn_amount: int = 1,
    respawn_seconds: float = 0.0,
    crowding: float = 1.0,
) -> tuple[float, bool]:
    """Ritmo sustentável de kills/hora e se o limite vem do respawn do mapa.

    `crowding` é a fatia do mapa que sobra para você (1.0 = mapa vazio,
    0.5 = dividindo com mais alguém).
    """
    if not 0 < crowding <= 1:
        raise ValueError("crowding precisa estar em (0, 1]")

    tempo_de_kill = monster.hp / char.dps
    ciclo = tempo_de_kill + char.seek_seconds
    ritmo = 3600.0 / ciclo

    limitado = False
    if respawn_seconds > 0:
        teto = spawn_amount * 3600.0 / respawn_seconds
        if teto < ritmo:
            ritmo, limitado = teto, True

    return ritmo * crowding, limitado
