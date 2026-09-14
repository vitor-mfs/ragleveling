"""Fórmula de EXP: penalidade por diferença de nível e EXP por kill.

Há duas tabelas possíveis:

* a **do monstro**, que o Divine Pride entrega em `expPenaltyTable` — o
  percentual real por nível do jogador, naquele servidor. É o que o `cacar` usa
  (`exp_rate_do_monstro`).
* a **genérica** abaixo, o padrão do Renewal, que só a rota sobre catálogo YAML
  ainda usa. Não confie nela onde a do monstro existir.
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


def exp_rate_do_monstro(tabela: list[dict] | dict[int, int] | None, nivel_jogador: int) -> float | None:
    """Multiplicador de EXP para um jogador, pela tabela do próprio monstro.

    O Divine Pride lista só os níveis em que o percentual muda; entre dois
    pontos vale o anterior, abaixo do primeiro vale o primeiro e acima do último
    vale o último. Devolve None sem tabela.
    """
    if not tabela:
        return None
    if isinstance(tabela, dict):
        pontos = sorted((int(nivel), int(pct)) for nivel, pct in tabela.items())
    else:
        pontos = sorted(
            (int(item["level"]), int(item["percent"]))
            for item in tabela
            if isinstance(item, dict) and "level" in item and "percent" in item
        )
    if not pontos:
        return None
    vigente = pontos[0][1]
    for nivel, pct in pontos:
        if nivel > nivel_jogador:
            break
        vigente = pct
    return vigente / 100.0


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
