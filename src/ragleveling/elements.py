"""Elementos: qual usar contra cada monstro, a partir da resistência dele.

O Divine Pride entrega `elementResistances` já calculado por monstro — o
percentual de dano que cada elemento de ataque causa nele, com os modificadores
próprios daquele monstro. Não há tabela genérica aqui: se o monstro não trouxe
resistências, tudo vale 100%.
"""

from __future__ import annotations

ELEMENTOS = (
    "Neutral",
    "Water",
    "Earth",
    "Fire",
    "Wind",
    "Poison",
    "Holy",
    "Dark",
    "Ghost",
    "Undead",
)

ELEMENTO_PT: dict[str, str] = {
    "Neutral": "Neutro",
    "Water": "Água",
    "Earth": "Terra",
    "Fire": "Fogo",
    "Wind": "Vento",
    "Poison": "Veneno",
    "Holy": "Sagrado",
    "Dark": "Sombrio",
    "Ghost": "Fantasma",
    "Undead": "Morto-vivo",
}

RACA_PT: dict[str, str] = {
    "Formless": "Amorfo",
    "Undead": "Morto-vivo",
    "Brute": "Bruto",
    "Plant": "Planta",
    "Insect": "Inseto",
    "Fish": "Peixe",
    "Demon": "Demônio",
    "DemiHuman": "Demi-humano",
    "Demi-Human": "Demi-humano",
    "Angel": "Anjo",
    "Dragon": "Dragão",
    "Player": "Jogador",
}

TAMANHO_PT: dict[str, str] = {"Small": "Pequeno", "Medium": "Médio", "Large": "Grande"}


def pt(nome: str, tabela: dict[str, str]) -> str:
    """Tradução com o nome original como fallback."""
    return tabela.get(nome, nome)


def ranking_por_resistencia(resistencias: dict[str, int] | None) -> list[tuple[str, int]]:
    """Elementos de ataque do que rende mais ao que rende menos.

    Sem resistências conhecidas, todo elemento vale 100% — é o que acontece com
    os poucos monstros-placeholder do banco.
    """
    if not resistencias:
        return [(elemento, 100) for elemento in ELEMENTOS]
    pares = [(elemento, int(resistencias[elemento])) for elemento in ELEMENTOS if elemento in resistencias]
    if not pares:
        return [(elemento, 100) for elemento in ELEMENTOS]
    return sorted(pares, key=lambda par: (-par[1], ELEMENTOS.index(par[0])))


def melhor_elemento(resistencias: dict[str, int] | None) -> tuple[str, int]:
    return ranking_por_resistencia(resistencias)[0]


def piores_elementos(resistencias: dict[str, int] | None, limite: int = 2) -> list[tuple[str, int]]:
    return list(reversed(ranking_por_resistencia(resistencias)))[:limite]
