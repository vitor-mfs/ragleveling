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

import re
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
    alvos: tuple[str, ...]  # chaves canônicas (qualquer uma serve) ou o nome da habilidade como foi digitado
    dano: str = "qualquer"  # "fisico" | "magico" | "qualquer"
    #: Só para propriedade, ao aumentar o dano: "alvo" (dano contra monstros da propriedade),
    #: "ataque" (dano dos ataques da propriedade) ou "" quando a frase não decide e valem as duas.
    como: str = ""
    #: Outros nomes da mesma habilidade (o nome interno `GC_CROSSRIPPERSLASHER`, que é como os
    #: scripts do Divine Pride a citam), resolvidos fora daqui.
    apelidos: tuple[str, ...] = ()

    @property
    def rotulo(self) -> str:
        verbo = "Aumentar dano" if self.efeito == "aumentar" else "Reduzir dano"
        if self.categoria == "habilidade":
            return f"{verbo} da habilidade {self.alvos[0]}"
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

_REDUZIR = re.compile(r"\b(reduz\w*|diminu\w*|menos|menor|menores|mitig\w*)\b")
#: Estas palavras decidem sozinhas: "aumentar resistência a dragões" quer menos dano recebido.
_RESISTENCIA = re.compile(r"\b(resist\w*|toler\w*|protec\w*|proteg\w*|defes\w*|defend\w*)\b")
_AUMENTAR = re.compile(r"\b(aument\w*|ganh\w*|bonus|mais|maior|maiores|elev\w*|increment\w*|potencializ\w*|extra)\b")
_MAGICO = re.compile(r"\b(magic[oa]s?|matk|magias?)\b")
_FISICO = re.compile(r"\b(fisic[oa]s?|atk|melee|corpo a corpo|a distancia)\b")
_HABILIDADE = re.compile(r"\b(?:habilidades?|skills?)\s+(?:d[aeo]s?\s+)?(?P<nome>.+)$")
_DANO_DE = re.compile(r"\bdano\s+(?:magico\s+|fisico\s+)?(?:d[aeo]s?|em|contra|a|para)\s+(?P<resto>.+)$")
_CRITICO = re.compile(r"\bcritic\w*")
_DISTANCIA = re.compile(r"\b(a distancia|distancia|longa distancia|ranged)\b")
_CORPO_A_CORPO = re.compile(r"\b(corpo a corpo|melee|curta distancia)\b")
#: Palavras da frase que não dizem contra quem é o dano; sobrando só isto, é dano geral.
_PALAVRAS_SOLTAS = re.compile(
    r"\b(aument\w*|reduz\w*|dano|danos|de|do|da|em|o|a|os|as|um|uma|no|na|mais|bonus|ataque|ataques|tipo|"
    r"fisic\w*|magic\w*|critic\w*|distancia|longa|curta|corpo|melee|ranged|e|ou)\b"
)
_CUE_ALVO = re.compile(r"\b(contra|em|nos?|nas?|monstros?|oponentes?|inimigos?|alvos?)\b")
_CUE_ATAQUE = re.compile(r"\b(ataques?|magias?|elemental|usando|com)\b")
_GATILHOS = (
    ("elemento", re.compile(r"\b(propriedades?|elementos?|elemental)\b")),
    ("tamanho", re.compile(r"\btamanhos?\b")),
)


def _norm(texto: str) -> str:
    """Minúsculas, sem acento, espaços simples. Mantém a pontuação que as linhas de item usam."""
    return " ".join(sem_acento(texto).split())


def _alvos_em(texto: str, categoria: str) -> tuple[str, ...]:
    """Os alvos da categoria que o texto (já normalizado) cita, sem repetir."""
    achados: list[str] = []
    if re.search(r"(?<![\w-])(todas?|todos?|all)(?![\w-])", texto):
        achados.append(TODOS)
    for chave, nomes in VOCABULARIO[categoria].items():
        # Plural e flexão simples: "sagrado" também é "sagrados", "dragão" é "dragões" (já listado).
        if any(re.search(rf"(?<![\w-]){re.escape(nome)}(?:e?s)?(?![\w-])", texto) for nome in nomes):
            achados.append(chave)
    return tuple(dict.fromkeys(achados))


def _como(texto: str, efeito: str, categoria: str, dano: str) -> str:
    """Propriedade ao aumentar o dano: contra monstros da propriedade, ou ataques dela?"""
    if categoria != "elemento" or efeito != "aumentar":
        return ""
    if _CUE_ALVO.search(texto):
        return "alvo"
    return "ataque" if dano == "magico" or _CUE_ATAQUE.search(texto) else ""


def _alvos_gerais_da_frase(texto: str) -> tuple[str, ...]:
    if _CRITICO.search(texto):
        return ("critico",)
    if _DISTANCIA.search(texto):
        return ("distancia",)
    if _CORPO_A_CORPO.search(texto):
        return ("corpo-a-corpo",)
    if _MAGICO.search(texto):
        return ("magico",)
    if _FISICO.search(texto):
        return ("fisico",)
    return ()


def interpretar(frase: str) -> Consulta:
    """A frase digitada -> o que se quer.

    `aumentar dano em insetos`, `reduzir dano de dragões`, `aumentar dano mágico
    contra demônios`, `aumentar dano da habilidade Lâminas Retalhadoras`.
    """
    texto = _norm(re.sub(r"[^\w\s\-]", " ", frase))
    if not texto:
        raise FraseNaoEntendida("Escreva o que procura, por exemplo: aumentar dano em insetos.")

    if _RESISTENCIA.search(texto):
        efeito = "reduzir"
    else:
        reduzir, aumentar = _REDUZIR.search(texto), _AUMENTAR.search(texto)
        if not reduzir and not aumentar:
            raise FraseNaoEntendida("Diga se quer aumentar ou reduzir o dano, por exemplo: reduzir dano de dragões.")
        efeito = "reduzir" if reduzir and (not aumentar or reduzir.start() < aumentar.start()) else "aumentar"

    dano = "magico" if _MAGICO.search(texto) else "fisico" if _FISICO.search(texto) else "qualquer"

    habilidade = _HABILIDADE.search(texto)
    if habilidade:
        return Consulta(efeito, "habilidade", (habilidade.group("nome").strip(),), dano)

    for categoria, gatilho in _GATILHOS:
        if gatilho.search(texto):
            alvos = tuple(a for a in _alvos_em(texto, categoria) if a != TODOS)
            if alvos:
                return Consulta(efeito, categoria, alvos, dano, _como(texto, efeito, categoria, dano))
    for categoria in ("raca", "tamanho", "elemento"):
        alvos = tuple(a for a in _alvos_em(texto, categoria) if a != TODOS)
        if alvos:
            return Consulta(efeito, categoria, alvos, dano, _como(texto, efeito, categoria, dano))

    geral = _alvos_gerais_da_frase(texto)
    if geral and not _PALAVRAS_SOLTAS.sub(" ", texto).strip():
        if efeito == "reduzir":
            raise FraseNaoEntendida("Para reduzir dano, diga de quem: raça (dragões), propriedade (fogo) ou tamanho.")
        return Consulta(efeito, "geral", geral)

    # "dano de Lâminas Retalhadoras": nada do vocabulário, então o resto é uma habilidade.
    resto = _DANO_DE.search(texto)
    if resto:
        return Consulta(efeito, "habilidade", (resto.group("resto").strip(),), dano)
    raise FraseNaoEntendida(
        "Não achei contra quem. Cite uma raça (insetos), uma propriedade (fogo), um tamanho (grande) "
        "ou uma habilidade (da habilidade Lâminas Retalhadoras)."
    )


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
_D_HABILIDADE = re.compile(
    rf"^dano\s+d[aeo]s?\s+(?P<lista>{_NOME_ENTRE_COLCHETES}(?:\s*(?:,|e)\s*{_NOME_ENTRE_COLCHETES})*)\s+{_NUM}"
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

    def feito(tipo: str, categoria: str, alvos: tuple[str, ...], dano: str) -> Efeito | None:
        if not alvos:
            return None
        valor = (-1 if achado["sinal"] == "-" else 1) * _numero(achado["n"])
        return Efeito(tipo, categoria, alvos, valor, dano, condicao, linha, "descricao")

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
_S_RACA = re.compile(rf"^increase damage dealt to (?P<alvo>.+?) race monsters by {_SN}", re.I)
_S_RACA_MAGICO = re.compile(rf"^increases? magic(?:al)? attack damage to (?P<alvo>.+?) race by {_SN}", re.I)
_S_TAMANHO = re.compile(rf"^increases? physical damage dealt on (?P<alvo>.+?) size monsters by {_SN}", re.I)
_S_TAMANHO_MAGICO = re.compile(rf"^increases? magic(?:al)? attack damage to (?P<alvo>.+?) size by {_SN}", re.I)
_S_ELEMENTO = re.compile(rf"^(?P<verbo>increase|reduce) damage dealt to an? (?P<alvo>.+?) property by {_SN}", re.I)
_S_RESIST_ELEMENTO = re.compile(
    rf"^(?P<verbo>reduce|increase) damage taken from an? (?P<alvo>.+?) property by {_SN}", re.I
)
_S_RESIST_RACA = re.compile(rf"^(?P<verbo>reduce|increase) damage taken from (?P<alvo>.+?) monsters by {_SN}", re.I)
_S_HABILIDADE = re.compile(rf"^increase damage of (?P<alvo>\S+) by {_SN}", re.I)


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

    achado = _S_ELEMENTO.match(texto)
    if achado:
        sinal = 1 if achado["verbo"].lower() == "increase" else -1
        return feito("dano", "elemento", _alvos_em(_norm(achado["alvo"]), "elemento"), sinal * _numero(achado["n"]))

    for padrao, categoria in ((_S_RESIST_ELEMENTO, "elemento"), (_S_RESIST_RACA, "raca")):
        achado = padrao.match(texto)
        if achado:
            sinal = 1 if achado["verbo"].lower() == "reduce" else -1
            alvos = _alvos_em(_norm(achado["alvo"]), categoria)
            return feito("resistencia", categoria, alvos, sinal * _numero(achado["n"]))

    achado = _S_HABILIDADE.match(texto)
    if achado:
        return feito("dano", "habilidade", (_norm(achado["alvo"]),), _numero(achado["n"]))
    return None


def efeitos_dos_scripts(scripts: Any) -> list[Efeito]:
    """Os efeitos do campo `scripts` do item, que o Divine Pride já escreve em frases fixas."""
    return [e for e in map(_efeito_de_script, _textos_do_script(scripts)) if e]


def efeitos_do_item(item: dict[str, Any]) -> list[Efeito]:
    """Todos os efeitos que se entendem de um item do índice: descrição e scripts."""
    return [*efeitos_da_descricao(item.get("description") or ""), *efeitos_dos_scripts(item.get("scripts"))]


# --- achar os itens ---


def _fichas(nome: str) -> set[str]:
    """Palavras de um nome de habilidade, sem plural: `lâminas retalhadoras` -> {lamina, retalhadora}."""
    palavras = re.findall(r"[a-z0-9]+", _norm(nome.replace("_", " ")))
    return {p[:-1] if len(p) > 3 and p.endswith("s") else p for p in palavras}


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
    return TODOS in efeito.alvos or any(a in efeito.alvos for a in consulta.alvos)


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
    if isinstance(consulta, str):
        consulta = interpretar(consulta)

    resultados: list[Resultado] = []
    for item in indice.get("items", []):
        if local is not None and local not in item.get("locations", []):
            continue
        servem = [e for e in efeitos_do_item(item) if atende(e, consulta)]
        if not servem:
            continue
        servem.sort(key=lambda e: (bool(e.condicao), -e.valor, e.fonte != "descricao"))
        principal = servem[0]
        # O script repete o que a descrição já disse; só fica o que acrescenta algo.
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

    É o que permite `dp-itens` indexar só o recorte que a frase pede.
    """
    magico = consulta.dano in ("magico", "qualquer")
    fisico = consulta.dano in ("fisico", "qualquer")
    if consulta.categoria == "raca":
        if consulta.efeito == "reduzir":
            return (25,)
        return (*((21,) if fisico else ()), *((411,) if magico else ()))
    if consulta.categoria == "elemento":
        return (23,) if consulta.efeito == "reduzir" else ((27,) if consulta.como != "ataque" else ())
    if consulta.categoria == "geral":
        return ()
    if consulta.categoria == "tamanho":
        return () if consulta.efeito == "reduzir" else (29,)
    return (33,)
