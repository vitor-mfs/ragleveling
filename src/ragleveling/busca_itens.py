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

O script do Divine Pride lista todos os degraus de refino e de grau soltos e **sem
condição** ("These information ignore any conditions"), então ele nunca decide sozinho
quando a descrição já fala do mesmo efeito: a descrição sabe a condição, o script só
entra pelo que ela não diz (e nos itens sem descrição, onde não há condição conhecida).

Convenção de sinal dos efeitos: `dano` é o dano **causado** (positivo = mais
dano); `resistencia` é o dano **recebido** (positivo = menos dano, que é o que
"reduzir dano de dragões" quer; negativo = fraqueza, como em `Resistência a raça
Demônio -5%`).
"""

from __future__ import annotations

import re
from collections.abc import Iterable
from dataclasses import dataclass
from typing import Any

from .dp_itens import sem_acento

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
    "veneno": ("veneno", "venenoso", "venenosa", "poison"),
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

#: Só valem quando a frase fala de propriedade, tamanho ou criaturas ("propriedade sombria").
#: Sem esse contexto "sombra" ou "santo" podem ser parte do nome de uma habilidade.
SINONIMOS_COM_CONTEXTO = {"sombrio": ("sombra", "trevas", "escuro"), "sagrado": ("santo", "santa")}

#: Raças de jogador: "todas as raças de monstros" não as inclui.
RACAS_DE_JOGADOR = ("humano", "doram")

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

#: Os alvos de `geral`: o dano sem alvo nenhum (`Dano mágico +10%`).
ROTULOS_GERAIS = {
    "fisico": "físico",
    "magico": "mágico",
    "critico": "crítico",
    "distancia": "físico à distância",
    "corpo-a-corpo": "físico corpo a corpo",
}

#: Alvo que vale para qualquer raça, propriedade ou tamanho.
TODOS = "todas"


class FraseNaoEntendida(ValueError):
    """A frase não diz o que se quer (aumentar ou reduzir) ou contra quem."""


@dataclass(frozen=True)
class Consulta:
    """O que a frase pede."""

    efeito: str  # "aumentar" (dano causado) | "reduzir" (dano recebido)
    categoria: str  # "raca" | "elemento" | "tamanho" | "habilidade" | "geral"
    alvos: tuple[str, ...]  # chaves canônicas (qualquer uma serve) ou os nomes (normalizados) da habilidade
    dano: str = "qualquer"  # "fisico" | "magico" | "qualquer"
    #: Só para propriedade, ao aumentar o dano: "alvo" (dano contra monstros da propriedade),
    #: "ataque" (dano dos ataques da propriedade) ou "" quando a frase não decide e valem as duas.
    como: str = ""
    #: Outros nomes da mesma habilidade (o nome interno `GC_CROSSRIPPERSLASHER`, que é como os
    #: scripts do Divine Pride a citam), resolvidos fora daqui.
    apelidos: tuple[str, ...] = ()
    #: Como a habilidade foi escrita na frase, com acento e maiúsculas, para a saída.
    nomes: tuple[str, ...] = ()

    @property
    def rotulo(self) -> str:
        verbo = "Aumentar dano" if self.efeito == "aumentar" else "Reduzir dano"
        if self.categoria == "habilidade":
            return f"{verbo} da habilidade {' ou '.join(self.nomes or self.alvos)}"
        if self.categoria == "geral":
            return f"{verbo} {' ou '.join(ROTULOS_GERAIS.get(a, a) for a in self.alvos)}"
        preposicao = "em" if self.efeito == "aumentar" else "de"
        tipo = {"raca": "raça", "elemento": "propriedade", "tamanho": "tamanho"}[self.categoria]
        if self.categoria == "elemento" and self.como == "ataque":
            tipo = "ataques de propriedade"
        nomes = " ou ".join(ROTULOS.get(a, a) for a in self.alvos)
        magico = " mágico" if self.dano == "magico" else " físico" if self.dano == "fisico" else ""
        return f"{verbo}{magico} {preposicao} {tipo} {nomes}"


@dataclass(frozen=True)
class Efeito:
    """Uma linha de efeito de um item, já entendida."""

    tipo: str  # "dano" | "resistencia"
    #: "raca" | "elemento" (dano contra a propriedade) | "elemento-ataque" (dano dos ataques da
    #: propriedade) | "tamanho" | "habilidade" | "geral"
    categoria: str
    #: Chaves canônicas; `TODOS` vale para qualquer uma. Habilidade: os nomes. Geral: a que ataques se aplica.
    alvos: tuple[str, ...]
    valor: float  # percentual, com sinal
    dano: str  # "fisico" | "magico" | "qualquer"
    condicao: str  # "" quando vale sempre; senão "Conjunto", "Refino +7 ou mais"...
    texto: str  # a linha como estava no item
    fonte: str  # "descricao" | "script"
    adicional: bool = False  # "+20% adicional": soma ao que o item já dava, não substitui


@dataclass(frozen=True)
class Resultado:
    """Um item que atende à consulta, com o efeito que o fez entrar."""

    item: dict[str, Any]
    efeito: Efeito  # o melhor efeito que atende: sem condição primeiro, depois o maior
    tambem: tuple[Efeito, ...]  # os outros que atendem e dizem algo diferente

    @property
    def valor(self) -> float:
        return self.efeito.valor


# --- a frase ---

_REDUZIR = re.compile(r"\b(reduz\w*|reduc\w*|diminu\w*|menor|menores|mitig\w*)\b|(?<!pelo )(?<!ao )\bmenos\b")
#: Estas palavras decidem sozinhas: "aumentar resistência a dragões" quer menos dano recebido.
_RESISTENCIA = re.compile(r"\b(resist\w*|toler\w*|protec\w*|proteg\w*)\b|\bdefesa\s+(?:contra|de|a|ao|aos|as)\b")
_AUMENTAR = re.compile(r"\b(aument\w*|ganh\w*|bonus|mais|maior|maiores|elev\w*|increment\w*|potencializ\w*|extra)\b")
#: Sobre o que a busca sabe falar: sem uma destas palavras a frase é de outro assunto (EXP, HP, cura).
_ASSUNTO = re.compile(r"\b(dano|danos|dmg|resist\w*|toler\w*|protec\w*|proteg\w*|defesa|ataques?|matk|atk|critic\w*)\b")
_IGNORAR = re.compile(r"\b(ignor\w*|perfur\w*|penetr\w*|atravess\w*|pierc\w*)\b")
_RECEBIDO = re.compile(r"\b(recebid\w*|sofrid\w*)\b")
_MAGICO = re.compile(r"\b(magic[oa]s?|matk|magias?)\b")
_FISICO = re.compile(r"\b(fisic[oa]s?|atk|melee|corpo a corpo|a distancia)\b")
_MARCADOR_DE_HABILIDADE = re.compile(r"\b(?:habilidades?|skills?|pericias?|tecnicas?)\s+(?:d[aeo]s?\s+)?(?P<nome>.+)$")
_DANO_DE_NOME = re.compile(r"\bdano\s+(?:magico\s+|fisico\s+)?d[aeo]s?\s+(?P<resto>.+)$")
_DANO_CONTRA = re.compile(r"\bdano\s+(?:magico\s+|fisico\s+)?(?:em|contra|a|para)\s+(?P<resto>.+)$")
_CRITICO = re.compile(r"\bcritic\w*")
_DISTANCIA = re.compile(r"\b(a distancia|distancia|longa distancia|ranged)\b")
_CORPO_A_CORPO = re.compile(r"\b(corpo a corpo|melee|curta distancia)\b")
_CUE_ALVO = re.compile(r"\b(contra|monstros?|oponentes?|inimigos?|alvos?)\b")
_CUE_ATAQUE = re.compile(r"\b(ataques?|magias?|elemental|usando|com)\b")
#: Com estas palavras na frase "sagrada", "pequena" e "sombra" são adjetivo, não nome de habilidade.
_CONTEXTO_DE_FLEXAO = re.compile(
    r"\b(propriedades?|elementos?|elemental|tamanhos?|criaturas?|magias?|ataques?|monstros?)\b"
)
_GATILHOS = (
    ("elemento", re.compile(r"\b(propriedades?|elementos?|elemental)\b")),
    ("tamanho", re.compile(r"\btamanhos?\b")),
)
_FIM_DO_NOME = re.compile(r"\s+(?:contra|em|para|pra|por favor|quando)\b|\s+\d")
_GENERICO = re.compile(r"^(habilidades?|skills?|magias?|feiticos?)$")
#: Palavras que, abrindo o "nome", mostram que a frase é de outro assunto (chefes, jogadores).
_NAO_E_NOME = frozenset(
    {"chefe", "chefes", "boss", "mvp", "jogador", "jogadores", "player", "players", "geral", "tudo"}
)
#: Palavras que não dizem contra quem é o dano. Sobrando só estas, o dano é geral;
#: sobrando outras, é uma habilidade.
_SOLTAS = frozenset(
    "de do da dos das em no na nos nas a o as os um uma e ou para pra por com contra sobre que quero preciso "
    "itens item meu minha seu sua algo qualquer muito mais bonus extra aumentar aumenta aumente aumento reduzir "
    "reduz reduza monstro monstros oponente oponentes inimigo inimigos alvo alvos criatura criaturas tipo raca "
    "racas propriedade propriedades elemento elementos tamanho tamanhos porte ataque ataques magia magias fisico "
    "fisica magico magica critico critica corpo distancia melee ranged longa curta dano danos todas todos".split()
)  # fmt: skip


def _norm(texto: str) -> str:
    """Minúsculas, sem acento, espaços simples. Mantém a pontuação que as linhas de item usam."""
    return " ".join(sem_acento(texto).split())


def _flexoes(nome: str) -> list[str]:
    """`sagrado` -> `sagrada`; `medio` -> `media`."""
    return [nome[:-1] + "a"] if nome.endswith("o") and len(nome) > 4 else []


def _alvos_em(texto: str, categoria: str, *, flexao: bool = False) -> tuple[str, ...]:
    """Os alvos da categoria que o texto (já normalizado) cita, sem repetir.

    `flexao` aceita o adjetivo no feminino e os sinônimos de contexto; só vale numa frase que já
    fala de propriedade, tamanho ou criaturas.
    """
    achados: list[str] = []
    if re.search(r"(?<![\w-])(todas?|todos?|all)(?![\w-])", texto):
        achados.append(TODOS)
    for chave, nomes in VOCABULARIO[categoria].items():
        candidatos = list(nomes)
        if flexao:
            candidatos += [f for nome in nomes for f in _flexoes(nome)]
            candidatos += SINONIMOS_COM_CONTEXTO.get(chave, ()) if categoria == "elemento" else ()
        # Plural e flexão simples: "sagrado" também é "sagrados", "dragão" é "dragões" (já listado).
        if any(re.search(rf"(?<![\w-]){re.escape(nome)}(?:e?s)?(?![\w-])", texto) for nome in candidatos):
            achados.append(chave)
    return tuple(dict.fromkeys(achados))


def _palavras_do_vocabulario() -> frozenset[str]:
    """Toda palavra de raça, propriedade ou tamanho, no singular e com as flexões."""
    palavras: set[str] = set()
    for vocab in VOCABULARIO.values():
        for chave, nomes in vocab.items():
            for nome in (*nomes, *SINONIMOS_COM_CONTEXTO.get(chave, ())):
                for parte in re.split(r"[\s-]+", nome):
                    palavras.update((parte, parte + "s", parte + "es", *_flexoes(parte)))
    return frozenset(palavras)


_VOCABULO = _palavras_do_vocabulario()


def _palavras_extras(resto: str) -> list[str]:
    """As palavras de `resto` que não são do vocabulário nem de ligação: sobrando alguma, é nome de habilidade."""
    return [p for p in re.findall(r"[a-z0-9_]+", resto) if p not in _SOLTAS and p not in _VOCABULO and not p.isdigit()]


def _como(texto: str, efeito: str, categoria: str, dano: str) -> str:
    """Propriedade ao aumentar o dano: contra monstros da propriedade, ou ataques dela?"""
    if categoria != "elemento" or efeito != "aumentar":
        return ""
    # "em magias de fogo" é ataque; "em monstros de fogo" e "contra fogo" são alvo.
    if _CUE_ATAQUE.search(texto) and not re.search(r"\b(monstros?|oponentes?|inimigos?|alvos?|contra)\b", texto):
        return "ataque"
    if _CUE_ALVO.search(texto) or re.search(r"\bem\b", texto):
        return "alvo"
    return "ataque" if dano == "magico" else ""


def _alvos_gerais_da_frase(texto: str) -> tuple[str, ...]:
    """A que ataques se refere um pedido sem alvo ("dano mágico", "dano à distância"). Citar dois vale pelos dois."""
    alvos: list[str] = []
    if _CRITICO.search(texto):
        alvos.append("critico")
    longe, perto = _DISTANCIA.search(texto), _CORPO_A_CORPO.search(texto)
    if longe:
        alvos.append("distancia")
    if perto:
        alvos.append("corpo-a-corpo")
    if _MAGICO.search(texto):
        alvos.append("magico")
    if not longe and not perto and _FISICO.search(texto):
        alvos.append("fisico")
    return tuple(alvos)


def _nome_valido(nome: str) -> bool:
    palavras = nome.split()
    return bool(palavras) and not _GENERICO.match(nome) and palavras[0] not in _NAO_E_NOME and not nome.isdigit()


def _nomes_da_habilidade(bruto: str, originais: list[str]) -> tuple[tuple[str, ...], tuple[str, ...]]:
    """`laminas retalhadoras e laminas de loki em 20` -> (nomes normalizados, nomes como foram escritos).

    O nome acaba onde a frase muda de assunto ("contra", "em", um número). `e` e `ou` separam
    habilidades; o nome inteiro também vale, porque há habilidade com "e" no nome.
    """
    cortado = _FIM_DO_NOME.split(" " + bruto, 1)[0].strip()
    palavras = cortado.split()
    escritas = originais[: len(palavras)]
    partes: list[tuple[str, str]] = []
    atual: tuple[list[str], list[str]] = ([], [])
    for norm_, orig in zip(palavras, escritas, strict=False):
        if norm_ in ("e", "ou") and atual[0]:
            partes.append((" ".join(atual[0]), " ".join(atual[1])))
            atual = ([], [])
        else:
            atual[0].append(norm_)
            atual[1].append(orig)
    if atual[0]:
        partes.append((" ".join(atual[0]), " ".join(atual[1])))
    partes = [(n, o) for n, o in partes if _nome_valido(n)]
    if not partes:
        raise FraseNaoEntendida("Qual habilidade? Por exemplo: aumentar dano da habilidade Lâminas Retalhadoras.")
    normalizados = tuple(dict.fromkeys([cortado, *(n for n, _ in partes)] if len(partes) > 1 else [partes[0][0]]))
    return normalizados, tuple(o for _, o in partes)


def _habilidade_conhecida_na_frase(texto: str, conhecidas: Iterable[str]) -> tuple[str, ...] | None:
    """Nomes de habilidade que o índice conhece e a frase cita por inteiro, o mais longo primeiro."""
    palavras = [_singular(p) for p in re.findall(r"[a-z0-9_]+", texto)]
    achados: list[str] = []
    for nome in sorted(set(conhecidas), key=lambda n: (-len(n.split()), n)):
        fichas = [_singular(p) for p in re.findall(r"[a-z0-9_]+", nome)]
        if not fichas or all(f in _VOCABULO or f in _SOLTAS for f in fichas):
            continue  # "Fogo" sozinho é a propriedade
        if any(palavras[i : i + len(fichas)] == fichas for i in range(len(palavras) - len(fichas) + 1)):
            achados.append(nome)
    return tuple(achados) or None


def _singular(palavra: str) -> str:
    return palavra[:-1] if len(palavra) > 3 and palavra.endswith("s") else palavra


def _escrita_na_frase(nome: str, texto: str, originais: list[str]) -> str:
    """Como o usuário escreveu `nome` (com acento e maiúsculas); o próprio nome se não achar."""
    fichas = [_singular(p) for p in nome.split()]
    palavras = [_singular(p) for p in texto.split()]
    for i in range(len(palavras) - len(fichas) + 1):
        if palavras[i : i + len(fichas)] == fichas:
            return " ".join(originais[i : i + len(fichas)])
    return nome


def interpretar(frase: str, habilidades: Iterable[str] = ()) -> Consulta:
    """A frase digitada -> o que se quer.

    `aumentar dano em insetos`, `reduzir dano de dragões`, `aumentar dano mágico
    contra demônios`, `aumentar dano da habilidade Lâminas Retalhadoras`.

    `habilidades` são os nomes (normalizados) de habilidade que o índice conhece; com eles,
    "aumentar dano de Lanças de Fogo" é a habilidade, não a propriedade Fogo.
    """
    limpa = re.sub(r"[^\w\s\-]", " ", re.sub(r"\s*[,;]\s*", " e ", frase))
    texto = _norm(limpa)
    originais = limpa.split()
    if not texto:
        raise FraseNaoEntendida("Escreva o que procura, por exemplo: aumentar dano em insetos.")
    if _IGNORAR.search(texto):
        raise FraseNaoEntendida("Ignorar ou perfurar defesa ainda não é coberto: a busca entende dano e resistência.")

    efeito = _direcao(texto)
    dano = _dano_da_frase(texto)

    def habilidade(bruto: str) -> Consulta:
        if efeito == "reduzir":
            raise FraseNaoEntendida("Só busco itens que aumentam o dano de uma habilidade, não que o reduzem.")
        deslocamento = len(texto.split()) - len(bruto.split())
        normalizados, escritos = _nomes_da_habilidade(bruto, originais[deslocamento:])
        return Consulta(efeito or "aumentar", "habilidade", normalizados, dano, nomes=escritos)

    if efeito is None:
        # "dano de Lâminas Retalhadoras": sem verbo, só o nome de uma habilidade dispensa o "aumentar".
        resto = _DANO_DE_NOME.search(texto)
        if resto and not any(_alvos_em(texto, c) for c in VOCABULARIO) and not _alvos_gerais_da_frase(texto):
            efeito = "aumentar"
            return habilidade(resto.group("resto"))
        raise FraseNaoEntendida("Diga se quer aumentar ou reduzir o dano, por exemplo: reduzir dano de dragões.")
    if not _ASSUNTO.search(texto):
        raise FraseNaoEntendida(
            "A busca entende dano e resistência (por exemplo: aumentar dano em insetos). "
            "EXP, HP, cura e recarga ainda não."
        )

    marcada = _MARCADOR_DE_HABILIDADE.search(texto)
    if marcada:
        return habilidade(marcada.group("nome"))
    conhecida = _habilidade_conhecida_na_frase(texto, habilidades)
    if conhecida:
        # O nome conhecido mais longo manda; o resto da frase pode citar outras habilidades.
        escritos = tuple(_escrita_na_frase(nome, texto, originais) for nome in conhecida)
        return Consulta(efeito, "habilidade", conhecida, dano, nomes=escritos)
    de_nome = _DANO_DE_NOME.search(texto)
    if de_nome and _palavras_extras(de_nome.group("resto")):
        return habilidade(de_nome.group("resto"))

    flexao = bool(_CONTEXTO_DE_FLEXAO.search(texto))
    for categoria, gatilho in _GATILHOS:
        if gatilho.search(texto):
            alvos = _alvos_em(texto, categoria, flexao=flexao)
            especificos = tuple(a for a in alvos if a != TODOS)
            if especificos or alvos:
                return Consulta(efeito, categoria, especificos or alvos, dano, _como(texto, efeito, categoria, dano))
    for categoria in ("raca", "tamanho", "elemento"):
        alvos = _alvos_em(texto, categoria, flexao=flexao)
        especificos = tuple(a for a in alvos if a != TODOS)
        if especificos:
            return Consulta(efeito, categoria, especificos, dano, _como(texto, efeito, categoria, dano))
    if re.search(r"\b(todas?|todos?)\s+(?:as\s+|os\s+)?(?:racas?|monstros?)\b", texto):
        return Consulta(efeito, "raca", (TODOS,), dano)

    geral = _alvos_gerais_da_frase(texto)
    if geral and not _palavras_extras(texto):
        if efeito == "reduzir":
            raise FraseNaoEntendida("Para reduzir dano, diga de quem: raça (dragões), propriedade (fogo) ou tamanho.")
        return Consulta(efeito, "geral", geral)

    contra = _DANO_CONTRA.search(texto)
    extras = _palavras_extras(contra.group("resto")) if contra else []
    if extras:
        raise FraseNaoEntendida(
            f'Não conheço "{" ".join(extras)}". Cite uma raça (insetos), uma propriedade (fogo), um tamanho (grande) '
            "ou uma habilidade (da habilidade Lâminas Retalhadoras)."
        )
    raise FraseNaoEntendida(
        "Não achei contra quem. Cite uma raça (insetos), uma propriedade (fogo), um tamanho (grande) "
        "ou uma habilidade (da habilidade Lâminas Retalhadoras)."
    )


def _direcao(texto: str) -> str | None:
    """ "aumentar" (dano causado), "reduzir" (dano recebido) ou None quando a frase não diz."""
    if _RESISTENCIA.search(texto):
        return "reduzir"
    reduzir, aumentar = _REDUZIR.search(texto), _AUMENTAR.search(texto)
    if not reduzir and not aumentar:
        return None
    if aumentar and _RECEBIDO.search(texto) and not reduzir:
        raise FraseNaoEntendida(
            'Para ganhar proteção escreva "reduzir dano de" (por exemplo: reduzir dano de dragões).'
        )
    return "reduzir" if reduzir and (not aumentar or reduzir.start() < aumentar.start()) else "aumentar"


def _dano_da_frase(texto: str) -> str:
    """Citar os dois tipos de dano é pedir qualquer um dos dois."""
    magico, fisico = _MAGICO.search(texto), _FISICO.search(texto)
    if magico and fisico:
        return "qualquer"
    return "magico" if magico else "fisico" if fisico else "qualquer"


# --- os efeitos de um item ---

_NUM = r"(?P<sinal>[+-])?\s*(?P<n>\d+(?:[.,]\d+)?)\s*%"
_MODO = r"(?:\s+(?:a distancia|corpo a corpo)(?:\s+e\s+(?:a distancia|corpo a corpo))?)?"

_KIND = r"(?P<kind>fisico e magico|fisico|magico)"
_D_DANO_CONTRA = re.compile(rf"^dano\s*{_KIND}?{_MODO}\s+contra\s+(?P<alvo>.+?)\s+{_NUM}")
_D_ELEMENTO_ATAQUE = re.compile(rf"^dano\s*{_KIND}?\s+de\s+(?P<alvo>(?:todas as\s+)?propriedades?\b.*?)\s+{_NUM}")
_D_GERAL = re.compile(
    rf"^dano\s+(?P<tipo>fisico e magico|fisico|magico|critico)(?P<modo>\s+(?:a distancia|corpo a corpo)"
    rf"(?:\s+e\s+(?:a distancia|corpo a corpo))?)?\s+{_NUM}"
)
_D_RESISTENCIA = re.compile(rf"^resistencia\s+(?:a|as|ao|aos)\s+(?P<alvo>.+?)\s+{_NUM}")
_NOME_ENTRE_COLCHETES = r"\[[^\]]+\]"
#: O cliente separa as habilidades com vírgula, com "e" ou só com espaço: "[A] [B] [C] e [D]".
_D_HABILIDADE = re.compile(
    rf"^dano\s+d[aeo]s?\s+(?P<lista>{_NOME_ENTRE_COLCHETES}(?:\s*(?:,|e)?\s*{_NOME_ENTRE_COLCHETES})*)\s+{_NUM}"
)

_SEPARADOR = re.compile(r"^[-=_ ]{4,}$")
#: Cabeçalho de condição e a profundidade dele: uma condição mais funda não sobrevive a uma mais rasa.
_CABECALHOS = (
    (0, re.compile(r"^grau\b")),
    (1, re.compile(r"^nv\.?\s")),
    (2, re.compile(r"^soma dos refinos")),
    (3, re.compile(r"^(refino\b|a cada\b)")),
)


def _numero(texto: str) -> float:
    return float(texto.replace(",", "."))


def _dano_da_linha(kind: str | None) -> str:
    """`fisico` e `magico` restringem; `fisico e magico` (ou nada) vale para os dois."""
    return kind if kind in ("fisico", "magico") else "qualquer"


def _alvos_gerais(tipo: str, modo: str) -> tuple[str, ...]:
    """A que ataques o dano geral se aplica. Dano físico sem modo vale para os dois alcances."""
    if tipo == "critico":
        return ("critico",)
    alvos: list[str] = []
    if "fisico" in tipo:
        if not modo:
            alvos += ["fisico", "distancia", "corpo-a-corpo"]
        if "distancia" in modo:
            alvos.append("distancia")
        if "corpo" in modo:
            alvos.append("corpo-a-corpo")
    if "magico" in tipo:
        alvos.append("magico")
    return tuple(alvos)


def _categoria_do_alvo(alvo: str) -> str | None:
    if re.search(r"\bracas?\b", alvo):
        return "raca"
    if re.search(r"\btamanhos?\b", alvo):
        return "tamanho"
    if re.search(r"\bpropriedades?\b", alvo):
        return "elemento"
    return None


def _efeito_de_linha(linha: str, condicao: str) -> Efeito | None:
    """Uma linha da descrição em português, se for um efeito que a busca conhece."""
    n = _norm(linha)
    adicional = bool(re.search(r"\badicional\b", n))

    def feito(tipo: str, categoria: str, alvos: tuple[str, ...], dano: str) -> Efeito | None:
        if not alvos:
            return None
        valor = (-1 if achado["sinal"] == "-" else 1) * _numero(achado["n"])
        return Efeito(tipo, categoria, alvos, valor, dano, condicao, linha, "descricao", adicional)

    achado = _D_HABILIDADE.match(n)
    if achado:
        nomes = tuple(_norm(nome) for nome in re.findall(r"\[([^\]]+)\]", achado["lista"]))
        return feito("dano", "habilidade", nomes, "qualquer")

    achado = _D_GERAL.match(n)
    if achado:
        return feito(
            "dano", "geral", _alvos_gerais(achado["tipo"], achado["modo"] or ""), _dano_da_linha(achado["tipo"])
        )

    achado = _D_ELEMENTO_ATAQUE.match(n)
    if achado:
        alvos = _alvos_em(achado["alvo"], "elemento")
        return feito("dano", "elemento-ataque", alvos, _dano_da_linha(achado["kind"]))

    tipo = "dano"
    achado = _D_DANO_CONTRA.match(n)
    if not achado:
        achado = _D_RESISTENCIA.match(n)
        tipo = "resistencia"
    if not achado:
        return None
    categoria = _categoria_do_alvo(achado["alvo"])
    alvos = _alvos_em(achado["alvo"], categoria) if categoria else ()
    kind = achado.groupdict().get("kind")
    return feito(tipo, categoria, alvos, _dano_da_linha(kind))


def efeitos_da_descricao(descricao: str) -> list[Efeito]:
    """Os efeitos da descrição em português, cada um com a condição em que vale.

    Linha de `Conjunto`, `Refino +7 ou mais:`, `A cada 2 refinos:`, `Grau D ou mais:`
    e afins deixam a condição preenchida; o que está solto vale sempre.
    """
    efeitos: list[Efeito] = []
    pilha: list[tuple[int, str]] = []
    conjunto = False
    for bruto in descricao.split("\n"):
        linha = bruto.strip()
        if not linha:
            continue
        if _SEPARADOR.match(linha):
            pilha, conjunto = [], False
            continue
        n = _norm(linha)
        if n == "conjunto":
            pilha, conjunto = [], True
            continue
        if conjunto and linha.startswith("[") and linha.endswith("]"):
            continue  # o nome do outro item do conjunto
        if linha.endswith(":"):
            nivel = next((rank for rank, padrao in _CABECALHOS if padrao.match(n)), 3)
            while pilha and pilha[-1][0] >= nivel:
                pilha.pop()
            pilha.append((nivel, linha.rstrip(":")))
            continue
        condicao = " · ".join((["Conjunto"] if conjunto else []) + [texto for _, texto in pilha])
        efeito = _efeito_de_linha(linha, condicao)
        if efeito:
            efeitos.append(efeito)
    return efeitos


# --- scripts do Divine Pride (inglês, frases fixas) ---

_SN = r"(?P<n>\d+(?:[.,]\d+)?)\s*%"
_SNS = r"(?P<sinal>[+-]?)\s*(?P<n>\d+(?:[.,]\d+)?)"
_S_RACA = re.compile(rf"^increase damage dealt to (?P<alvo>.+?) race monsters by {_SN}", re.I)
_S_RACA_MAGICO = re.compile(rf"^increases? magic(?:al)? attack damage to (?P<alvo>.+?) race by {_SN}", re.I)
_S_TAMANHO = re.compile(rf"^increases? physical damage dealt on (?P<alvo>.+?) size monsters by {_SN}", re.I)
_S_TAMANHO_MAGICO = re.compile(rf"^increases? magic(?:al)? attack damage to (?P<alvo>.+?) size by {_SN}", re.I)
_S_RESIST_TAMANHO = re.compile(
    rf"^(?:decrease|reduce) physical damage taken from (?P<alvo>.+?) size monsters by {_SN}", re.I
)
#: A função 27 do site é o dano físico contra a propriedade (bAddEle); o mágico é a 689.
_S_ELEMENTO = re.compile(rf"^(?P<verbo>increase|reduce) damage dealt to an? (?P<alvo>.+?) property by {_SN}", re.I)
_S_ELEMENTO_MAGICO = re.compile(
    rf"^increases magical damage (?P<sentido>dealt to|taken from) (?P<alvo>.+?) property monsters by {_SN}", re.I
)
_S_ATAQUE_ELEMENTO = re.compile(rf"^increases (?P<alvo>.+?) property magical damage by {_SN}", re.I)
_S_RESIST_ELEMENTO = re.compile(
    rf"^(?P<verbo>reduce|increase) damage taken from an? (?P<alvo>.+?) property by {_SN}", re.I
)
_S_RESIST_RACA = re.compile(rf"^(?P<verbo>reduce|increase) damage taken from (?P<alvo>.+?) monsters by {_SN}", re.I)
#: O site escreve o nome da habilidade em português (com espaços) ou o interno (`GC_CROSSRIPPERSLASHER`).
#: Valor em fórmula ("by 5 + Refine%", "by temp * 3") não casa: o `$` exige o número e o `%` no fim.
_S_HABILIDADE = re.compile(rf"^increase damage of (?P<alvo>.+?) by {_SN}$", re.I)
_S_GERAL = (
    (re.compile(rf"^ATK % {_SNS}$", re.I), ("fisico", "distancia", "corpo-a-corpo"), "fisico"),
    (re.compile(rf"^MATK % {_SNS}%$", re.I), ("magico",), "magico"),
    (re.compile(rf"^increase damage dealt with ranged attacks by {_SNS}%$", re.I), ("distancia",), "fisico"),
    (re.compile(rf"^increase melee physical damage by {_SNS}%$", re.I), ("corpo-a-corpo",), "fisico"),
    (re.compile(rf"^inflict {_SNS}% more damage with critical attack$", re.I), ("critico",), "qualquer"),
)


def _textos_do_script(valor: Any, profundidade: int = 0) -> list[str]:
    """Todas as frases de um campo `scripts`, seja qual for o formato (texto, lista ou objetos)."""
    if isinstance(valor, str):
        return [valor] if valor.strip() else []
    if profundidade > 3:
        return []
    if isinstance(valor, dict):
        valor = list(valor.values())
    if isinstance(valor, list | tuple):
        return [t for item in valor for t in _textos_do_script(item, profundidade + 1)]
    return []


def _efeito_de_script(texto: str) -> Efeito | None:
    texto = " ".join(texto.split())

    def feito(tipo: str, categoria: str, alvos: tuple[str, ...], valor: float, dano: str = "qualquer") -> Efeito | None:
        return Efeito(tipo, categoria, alvos, valor, dano, "", texto, "script") if alvos else None

    for padrao, categoria, dano in ((_S_RACA, "raca", "fisico"), (_S_RACA_MAGICO, "raca", "magico")):
        achado = padrao.match(texto)
        if achado:
            return feito("dano", categoria, _alvos_em(_norm(achado["alvo"]), categoria), _numero(achado["n"]), dano)
    for padrao, dano in ((_S_TAMANHO, "fisico"), (_S_TAMANHO_MAGICO, "magico")):
        achado = padrao.match(texto)
        if achado:
            return feito("dano", "tamanho", _alvos_em(_norm(achado["alvo"]), "tamanho"), _numero(achado["n"]), dano)
    achado = _S_RESIST_TAMANHO.match(texto)
    if achado:
        alvos = _alvos_em(_norm(achado["alvo"]), "tamanho")
        return feito("resistencia", "tamanho", alvos, _numero(achado["n"]), "fisico")

    achado = _S_ELEMENTO.match(texto)
    if achado:
        sinal = 1 if achado["verbo"].lower() == "increase" else -1
        alvos = _alvos_em(_norm(achado["alvo"]), "elemento")
        return feito("dano", "elemento", alvos, sinal * _numero(achado["n"]), "fisico")
    achado = _S_ELEMENTO_MAGICO.match(texto)
    if achado:
        alvos = _alvos_em(_norm(achado["alvo"]), "elemento")
        if achado["sentido"].lower() == "dealt to":
            return feito("dano", "elemento", alvos, _numero(achado["n"]), "magico")
        return feito("resistencia", "elemento", alvos, -_numero(achado["n"]), "magico")
    achado = _S_ATAQUE_ELEMENTO.match(texto)
    if achado:
        alvos = _alvos_em(_norm(achado["alvo"]), "elemento")
        return feito("dano", "elemento-ataque", alvos, _numero(achado["n"]), "magico")

    for padrao, categoria in ((_S_RESIST_ELEMENTO, "elemento"), (_S_RESIST_RACA, "raca")):
        achado = padrao.match(texto)
        if achado:
            sinal = 1 if achado["verbo"].lower() == "reduce" else -1
            alvos = _alvos_em(_norm(achado["alvo"]), categoria)
            return feito("resistencia", categoria, alvos, sinal * _numero(achado["n"]))

    for padrao, alvos_gerais, dano in _S_GERAL:
        achado = padrao.match(texto)
        if achado:
            valor = (-1 if achado["sinal"] == "-" else 1) * _numero(achado["n"])
            return feito("dano", "geral", alvos_gerais, valor, dano)

    achado = _S_HABILIDADE.match(texto)
    if achado:
        return feito("dano", "habilidade", (_norm(achado["alvo"]),), _numero(achado["n"]))
    return None


def efeitos_dos_scripts(scripts: Any) -> list[Efeito]:
    """Os efeitos do campo `scripts` do item, que o Divine Pride já escreve em frases fixas."""
    return [e for e in map(_efeito_de_script, _textos_do_script(scripts)) if e]


def _ja_dito(script: Efeito, descricao: list[Efeito]) -> bool:
    """A descrição já trata deste efeito? Então ela manda: só ela sabe a condição.

    O script lista todos os degraus de refino e de grau soltos, sem condição, e às vezes com
    valores que a descrição só dá em conjunto. Se ele valesse junto, um bônus de Refino +11 subiria
    na lista como se valesse sempre.
    """
    for d in descricao:
        if (d.tipo, d.categoria) != (script.tipo, script.categoria):
            continue
        if "qualquer" not in (d.dano, script.dano) and d.dano != script.dano:
            continue
        if script.categoria == "habilidade":
            return True  # o script cita a habilidade pelo nome interno ou traduzido: não dá para casar com [Nome]
        if script.categoria == "geral":
            if set(script.alvos) & set(d.alvos):
                return True
            continue
        if TODOS in d.alvos or set(script.alvos) <= set(d.alvos):
            return True
    return False


def efeitos_do_item(item: dict[str, Any]) -> list[Efeito]:
    """Todos os efeitos que se entendem de um item do índice: a descrição, mais o que só o script diz."""
    da_descricao = efeitos_da_descricao(item.get("description") or "")
    dos_scripts = [e for e in efeitos_dos_scripts(item.get("scripts")) if not _ja_dito(e, da_descricao)]
    return [*da_descricao, *dos_scripts]


# --- achar os itens ---


def _fichas(nome: str) -> set[str]:
    """Palavras de um nome de habilidade, sem plural: `lâminas retalhadoras` -> {lamina, retalhadora}."""
    palavras = re.findall(r"[a-z0-9]+", _norm(nome.replace("_", " ")))
    return {_singular(p) for p in palavras}


def _mesma_habilidade(nome_do_efeito: str, consulta: Consulta) -> bool:
    do_efeito = _fichas(nome_do_efeito)
    for candidato in (*consulta.alvos, *consulta.apelidos):
        buscado = _fichas(candidato)
        if buscado and buscado <= do_efeito:
            return True
    return False


def atende(efeito: Efeito, consulta: Consulta) -> bool:
    """O efeito dá o que a consulta pede?"""
    if efeito.valor <= 0:
        return False
    if consulta.categoria == "elemento" and consulta.efeito == "aumentar":
        aceitas = {"alvo": ("elemento",), "ataque": ("elemento-ataque",)}.get(
            consulta.como, ("elemento", "elemento-ataque")
        )
        if efeito.categoria not in aceitas:
            return False
    elif efeito.categoria != consulta.categoria:
        return False
    if efeito.tipo != ("dano" if consulta.efeito == "aumentar" else "resistencia"):
        return False
    if consulta.dano != "qualquer" and efeito.dano not in (consulta.dano, "qualquer"):
        return False
    if consulta.categoria == "habilidade":
        return any(_mesma_habilidade(nome, consulta) for nome in efeito.alvos)
    if consulta.categoria == "geral":
        return any(a in efeito.alvos for a in consulta.alvos)
    if any(a in efeito.alvos for a in consulta.alvos):
        return True
    # "Todas as raças de monstros" não inclui as raças de jogador (humano, doram).
    if consulta.categoria == "raca":
        return TODOS in efeito.alvos and any(a not in RACAS_DE_JOGADOR for a in consulta.alvos)
    return TODOS in efeito.alvos


def nomes_de_habilidades(efeitos_por_item: Iterable[list[Efeito]]) -> set[str]:
    """Os nomes (normalizados) de habilidade que algum item do índice cita num efeito de dano."""
    return {nome for efeitos in efeitos_por_item for e in efeitos if e.categoria == "habilidade" for nome in e.alvos}


def buscar(
    indice: dict[str, Any],
    consulta: Consulta | str,
    *,
    local: str | None = None,
    limite: int | None = None,
) -> list[Resultado]:
    """Os itens do índice que atendem à consulta, do maior bônus para o menor.

    O efeito sem condição vem antes do condicionado (conjunto, refino...), mesmo
    quando o condicionado é maior: é o que o item dá sem exigir mais nada.
    """
    itens = indice.get("items", [])
    efeitos = [efeitos_do_item(item) for item in itens]
    if isinstance(consulta, str):
        consulta = interpretar(consulta, nomes_de_habilidades(efeitos))

    resultados: list[Resultado] = []
    for item, do_item in zip(itens, efeitos, strict=True):
        if local is not None and local not in item.get("locations", []):
            continue
        servem = [e for e in do_item if atende(e, consulta)]
        if not servem:
            continue
        servem.sort(key=lambda e: (bool(e.condicao), -e.valor, e.fonte != "descricao"))
        principal = servem[0]
        # Efeitos que dizem a mesma coisa (mesmo valor e condição) não se repetem em `tambem`.
        vistos = {(principal.valor, principal.condicao)}
        tambem = []
        for efeito in servem[1:]:
            chave = (efeito.valor, efeito.condicao)
            if chave not in vistos:
                vistos.add(chave)
                tambem.append(efeito)
        resultados.append(Resultado(item, principal, tuple(tambem)))

    resultados.sort(key=lambda r: (bool(r.efeito.condicao), -r.valor, sem_acento(r.item["name"])))
    return resultados[:limite] if limite is not None else resultados


def funcoes_do_site(consulta: Consulta) -> tuple[int, ...]:
    """Ids do filtro "Função" da listagem do Divine Pride que cobrem a consulta.

    É o que permite `dp-itens` indexar só o recorte que a frase pede. Os ids vêm do que o site
    mostra nas páginas de item (21 dano contra raça, 411 dano mágico contra raça, 25 resistência
    racial, 27 e 689 dano físico e mágico contra a propriedade, 582 dano mágico dos ataques da
    propriedade, 23 e 28 resistência à propriedade, 29 e 30 tamanho, 33 dano de habilidade).
    """
    magico = consulta.dano in ("magico", "qualquer")
    fisico = consulta.dano in ("fisico", "qualquer")
    if consulta.categoria == "raca":
        if consulta.efeito == "reduzir":
            return (25,)
        return (*((21,) if fisico else ()), *((411,) if magico else ()))
    if consulta.categoria == "elemento":
        if consulta.efeito == "reduzir":
            return (23, 28)
        alvo = (*((27,) if fisico else ()), *((689,) if magico else ()))
        ataque = (582,) if magico else ()
        return {"alvo": alvo, "ataque": ataque}.get(consulta.como, (*alvo, *ataque))
    if consulta.categoria == "tamanho":
        return (30,) if consulta.efeito == "reduzir" else (29,)
    if consulta.categoria == "geral":
        return ()
    return (33,)
