"""Score de dificuldade de um monstro, do mais fácil ao mais difícil.

O que pesa: vida, defesa (DEF ou MDEF conforme o seu perfil de dano), o ataque
do monstro, quantas habilidades ele tem e quão perigosas são essas habilidades.

A escala é **relativa à sua faixa de nível**: o score é normalizado entre os
candidatos daquela consulta, então 0 é o mais fácil dos monstros que apareceram
e 100 o mais difícil. Comparar scores de duas consultas diferentes não
significa nada.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any

from .jobs import Perfil


@dataclass(frozen=True)
class Pesos:
    """Quanto cada componente vale no score final. A soma não precisa ser 1."""

    hp: float = 0.30
    defesa: float = 0.20
    ataque: float = 0.20
    skills_perigosas: float = 0.20
    quantidade_skills: float = 0.10


#: (categoria, padrão no nome da skill do rAthena, peso de perigo).
#: A primeira que casar é a categoria da skill.
CATEGORIAS_SKILL: tuple[tuple[str, str, float], ...] = (
    ("invocação", r"SUMMON", 3.0),
    ("cura/reviver", r"HEAL|REBIRTH|RESURRECTION|RECALL", 2.5),
    ("área", r"^NPC_WIDE|^WZ_|^MG_(?!.*BOLT$)|EARTHQUAKE|PULSESTRIKE|STORMGUST|METEOR|VERMILION", 2.5),
    ("status", r"STUN|SLEEP|CURSE|BLIND|SILENCE|PETRIFY|FREEZE|STONE|CHAOS|CONFUSE|BLEEDING|POISON", 2.0),
    ("buff próprio", r"POWERUP|AGIUP|DEFENDER|BARRIER|INCREASE|STOP|PROVOKE", 1.0),
    ("dano forte", r"CRITICAL|GUIDEDATTACK|PIERCING|COMBO|DARKSTRIKE|MAGICALATTACK|BREAK", 1.0),
)

_COMPILADAS = tuple((nome, re.compile(padrao), peso) for nome, padrao, peso in CATEGORIAS_SKILL)

LIMIAR_FACIL = 33.0
LIMIAR_MEDIO = 66.0


@dataclass
class Dificuldade:
    """Resultado do score para um monstro."""

    score: float
    rotulo: str
    categorias: dict[str, int] = field(default_factory=dict)
    total_skills: int = 0
    peso_skills: float = 0.0

    @property
    def perigos(self) -> str:
        """Categorias de habilidade perigosa, em uma linha."""
        relevantes = [nome for nome in self.categorias if nome not in ("dano forte", "buff próprio")]
        return ", ".join(relevantes)


def classificar_skills(skills: list[dict[str, str]]) -> tuple[dict[str, int], float]:
    """Agrupa as habilidades por categoria e soma o peso de perigo."""
    categorias: dict[str, int] = {}
    peso = 0.0
    for skill in skills:
        nome = skill.get("name", "")
        for categoria, padrao, valor in _COMPILADAS:
            if padrao.search(nome):
                categorias[categoria] = categorias.get(categoria, 0) + 1
                peso += valor
                break
        else:
            peso += 0.5  # habilidade não classificada ainda incomoda um pouco
    return categorias, peso


def _normalizar(valores: list[float]) -> list[float]:
    """Min-max para [0, 1]. Tudo igual vira 0 — nada diferencia os candidatos."""
    if not valores:
        return []
    menor, maior = min(valores), max(valores)
    if maior <= menor:
        return [0.0 for _ in valores]
    return [(v - menor) / (maior - menor) for v in valores]


def _rotulo(score: float) -> str:
    if score < LIMIAR_FACIL:
        return "fácil"
    if score < LIMIAR_MEDIO:
        return "médio"
    return "difícil"


def calcular(
    monstros: list[dict[str, Any]],
    skills_por_mob: dict[str, list[dict[str, str]]],
    perfil: Perfil,
    pesos: Pesos | None = None,
) -> dict[int, Dificuldade]:
    """Score de 0 (mais fácil da lista) a 100 (mais difícil) para cada monstro."""
    pesos = pesos or Pesos()
    if not monstros:
        return {}

    chave_defesa = "magic_defense" if perfil is Perfil.MAGIC else "defense"

    classificacoes = [classificar_skills(skills_por_mob.get(str(m["id"]), [])) for m in monstros]

    hp = _normalizar([float(m.get("hp") or 0) for m in monstros])
    defesa = _normalizar([float(m.get(chave_defesa) or 0) for m in monstros])
    ataque = _normalizar([float(m.get("attack") or 0) for m in monstros])
    perigo = _normalizar([peso for _, peso in classificacoes])
    quantidade = _normalizar([float(len(cats)) for cats, _ in classificacoes])

    soma_pesos = (
        pesos.hp + pesos.defesa + pesos.ataque + pesos.skills_perigosas + pesos.quantidade_skills
    )
    if soma_pesos <= 0:
        raise ValueError("a soma dos pesos precisa ser positiva")

    resultado: dict[int, Dificuldade] = {}
    for i, monstro in enumerate(monstros):
        bruto = (
            hp[i] * pesos.hp
            + defesa[i] * pesos.defesa
            + ataque[i] * pesos.ataque
            + perigo[i] * pesos.skills_perigosas
            + quantidade[i] * pesos.quantidade_skills
        ) / soma_pesos
        score = round(bruto * 100, 1)
        categorias, peso_skills = classificacoes[i]
        resultado[int(monstro["id"])] = Dificuldade(
            score=score,
            rotulo=_rotulo(score),
            categorias=categorias,
            total_skills=len(skills_por_mob.get(str(monstro["id"]), [])),
            peso_skills=peso_skills,
        )
    return resultado
