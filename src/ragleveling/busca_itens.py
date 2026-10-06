"""Busca de itens por frase: "aumentar dano em insetos", "reduzir dano de dragões",
"aumentar dano da habilidade Lâminas Retalhadoras".

A frase vira uma `Consulta` (o que se quer: aumentar o dano causado ou reduzir o
recebido; contra que raça, propriedade ou tamanho, ou em que habilidade) e cada
item do índice vira uma lista de `Efeito`s. Item que tem um efeito que atende à
consulta entra no resultado, do maior bônus para o menor.

Os efeitos de um item vêm de duas fontes que dizem a mesma coisa com palavras
diferentes, e **as duas são lidas**, porque nem sempre há as duas:

- a **descrição** em português (`Dano físico contra as raças Bruto e Doram +5%.`).
  Muitos itens do LATAM não têm descrição nenhuma;
- os **scripts**, que o Divine Pride mostra já normalizados, em inglês e com
  frases fixas (`Increase damage dealt to Insect race monsters by 10%`).

Convenção de sinal dos efeitos: `dano` é o dano **causado** (positivo = mais
dano); `resistencia` é o dano **recebido** (positivo = menos dano, que é o que
"reduzir dano de dragões" quer; negativo = fraqueza, como em `Resistência a raça
Demônio -5%`).
"""

from __future__ import annotations

from dataclasses import dataclass

#: Nome canônico -> nomes aceitos, sem acento e em minúsculas, em português (como
#: aparece no cliente do LATAM e na frase digitada) e em inglês (como aparece nos
#: scripts do Divine Pride).
RACAS: dict[str, tuple[str, ...]] = {
    "amorfo": ("amorfo", "amorfos", "formless"),
    "morto-vivo": ("morto-vivo", "mortos-vivos", "morto vivo", "mortos vivos", "morto-vivos", "undead"),
    "bruto": ("bruto", "brutos", "brute"),
    "planta": ("planta", "plantas", "plant"),
    "inseto": ("inseto", "insetos", "insect"),
    "peixe": ("peixe", "peixes", "fish"),
    "demonio": ("demonio", "demonios", "demon"),
    "humanoide": ("humanoide", "humanoides", "demi-human", "demi-humano", "demi humano", "demihuman"),
    "anjo": ("anjo", "anjos", "angel"),
    "dragao": ("dragao", "dragoes", "dragon"),
    "humano": ("humano", "humanos", "human player"),
    "doram": ("doram", "dorams", "doram player"),
}

ELEMENTOS: dict[str, tuple[str, ...]] = {
    "neutro": ("neutro", "neutra", "neutral"),
    "agua": ("agua", "water"),
    "terra": ("terra", "earth"),
    "fogo": ("fogo", "fire"),
    "vento": ("vento", "wind"),
    "veneno": ("veneno", "poison"),
    "sagrado": ("sagrado", "holy"),
    "sombrio": ("sombrio", "dark", "shadow"),
    "fantasma": ("fantasma", "ghost"),
    "maldito": ("maldito", "morto-vivo", "undead"),
}

TAMANHOS: dict[str, tuple[str, ...]] = {
    "pequeno": ("pequeno", "pequenos", "small"),
    "medio": ("medio", "medios", "medium"),
    "grande": ("grande", "grandes", "large"),
}

#: Categoria -> vocabulário.
VOCABULARIO = {"raca": RACAS, "elemento": ELEMENTOS, "tamanho": TAMANHOS}

#: Como cada alvo aparece na saída.
ROTULOS = {
    "amorfo": "Amorfo", "morto-vivo": "Morto-Vivo", "bruto": "Bruto", "planta": "Planta", "inseto": "Inseto",
    "peixe": "Peixe", "demonio": "Demônio", "humanoide": "Humanoide", "anjo": "Anjo", "dragao": "Dragão",
    "humano": "Humano", "doram": "Doram", "neutro": "Neutro", "agua": "Água", "terra": "Terra", "fogo": "Fogo",
    "vento": "Vento", "veneno": "Veneno", "sagrado": "Sagrado", "sombrio": "Sombrio", "fantasma": "Fantasma",
    "maldito": "Maldito", "pequeno": "Pequeno", "medio": "Médio", "grande": "Grande", "todas": "Todos",
}  # fmt: skip

#: Alvo que vale para qualquer raça, propriedade ou tamanho.
TODOS = "todas"


class FraseNaoEntendida(ValueError):
    """A frase não diz o que se quer (aumentar ou reduzir) ou contra quem."""


@dataclass(frozen=True)
class Consulta:
    """O que a frase pede."""

    efeito: str  # "aumentar" (dano causado) | "reduzir" (dano recebido)
    categoria: str  # "raca" | "elemento" | "tamanho" | "habilidade"
    alvo: str  # chave canônica, ou o nome da habilidade como foi digitado
    dano: str = "qualquer"  # "fisico" | "magico" | "qualquer"

    @property
    def rotulo(self) -> str:
        verbo = "Aumentar dano" if self.efeito == "aumentar" else "Reduzir dano"
        if self.categoria == "habilidade":
            return f"{verbo} da habilidade {self.alvo}"
        preposicao = "em" if self.efeito == "aumentar" else "de"
        tipo = {"raca": "raça", "elemento": "propriedade", "tamanho": "tamanho"}[self.categoria]
        return f"{verbo} {preposicao} {tipo} {ROTULOS.get(self.alvo, self.alvo)}"


@dataclass(frozen=True)
class Efeito:
    """Uma linha de efeito de um item, já entendida."""

    tipo: str  # "dano" | "resistencia"
    categoria: str  # "raca" | "elemento" | "tamanho" | "habilidade"
    alvos: tuple[str, ...]  # chaves canônicas; `TODOS` vale para qualquer uma. Habilidade: o nome.
    valor: float  # percentual, com sinal
    dano: str  # "fisico" | "magico" | "qualquer"
    condicao: str  # "" quando vale sempre; senão "Conjunto", "Refino +7 ou mais"...
    texto: str  # a linha como estava no item
    fonte: str  # "descricao" | "script"
