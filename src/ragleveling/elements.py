"""Tabela elemental do Renewal: qual elemento usar contra cada monstro.

Os números vêm do `db/re/attr_fix.yml` do rAthena — a mesma tabela que o
servidor usa para calcular dano — e não de estimativa. Um monstro Água nível 2
apanha 175% de Vento e só 25% de Água; é isso que `melhor_elemento` devolve.
"""

from __future__ import annotations

from typing import Any

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
    "Angel": "Anjo",
    "Dragon": "Dragão",
    "Player": "Jogador",
}

TAMANHO_PT: dict[str, str] = {"Small": "Pequeno", "Medium": "Médio", "Large": "Grande"}


def pt(nome: str, tabela: dict[str, str]) -> str:
    """Tradução com o nome original como fallback."""
    return tabela.get(nome, nome)


def ranking_por_resistencia(resistencias: dict[str, int]) -> list[tuple[str, int]]:
    """Ordena os elementos de ataque pela resistência já calculada do monstro.

    É o `elementResistances` do Divine Pride: o percentual de dano que cada
    elemento causa naquele monstro, com os modificadores próprios dele.
    """
    pares = [
        (elemento, int(resistencias[elemento]))
        for elemento in ELEMENTOS
        if elemento in resistencias
    ]
    if not pares:
        raise ValueError("nenhuma resistência elemental conhecida para este monstro")
    return sorted(pares, key=lambda par: (-par[1], ELEMENTOS.index(par[0])))


class TabelaElemental:
    """Consulta `attr_fix`: quanto um elemento de ataque rende contra uma defesa."""

    def __init__(self, bruto: dict[str, Any]) -> None:
        # O índice guarda as chaves de nível como string (JSON).
        self._por_nivel: dict[int, dict[str, dict[str, int]]] = {
            int(nivel): dados for nivel, dados in bruto.items()
        }

    def niveis(self) -> list[int]:
        return sorted(self._por_nivel)

    def modificador(self, elemento_ataque: str, elemento_defesa: str, nivel_defesa: int) -> int:
        """Percentual de dano de `elemento_ataque` contra `elemento_defesa` nível N."""
        nivel = self._nivel_valido(nivel_defesa)
        return self._por_nivel[nivel].get(elemento_ataque, {}).get(elemento_defesa, 100)

    def ranking(self, elemento_defesa: str, nivel_defesa: int) -> list[tuple[str, int]]:
        """Todos os elementos de ataque contra essa defesa, do melhor para o pior."""
        nivel = self._nivel_valido(nivel_defesa)
        tabela = self._por_nivel[nivel]
        pares = [
            (ataque, tabela.get(ataque, {}).get(elemento_defesa, 100))
            for ataque in ELEMENTOS
            if ataque in tabela
        ]
        return sorted(pares, key=lambda par: (-par[1], ELEMENTOS.index(par[0])))

    def melhor_elemento(self, elemento_defesa: str, nivel_defesa: int) -> tuple[str, int]:
        """O elemento de ataque mais eficaz e o percentual que ele causa."""
        return self.ranking(elemento_defesa, nivel_defesa)[0]

    def piores(self, elemento_defesa: str, nivel_defesa: int, limite: int = 2) -> list[tuple[str, int]]:
        """Os elementos a evitar contra essa defesa."""
        return list(reversed(self.ranking(elemento_defesa, nivel_defesa)))[:limite]

    def _nivel_valido(self, nivel: int) -> int:
        if nivel in self._por_nivel:
            return nivel
        disponiveis = self.niveis()
        if not disponiveis:
            raise ValueError("tabela elemental vazia: rode `ragleveling sync`")
        return min(disponiveis, key=lambda n: abs(n - nivel))
