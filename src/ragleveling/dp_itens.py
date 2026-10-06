"""O índice de itens do LATAM, construído só com o Divine Pride.

Como no índice de monstros, a API não tem busca nem listagem — só consulta por
id — então a lista de quem existe vem do site, em duas etapas:

1. a **listagem** (`/database/item/<categoria>?page=`) devolve, de 20 em 20, o id,
   o tipo, o subtipo e **um selo por servidor** em que o item existe — sem chave
   de API. Só entra no índice quem tem o selo do servidor configurado (LATAM). Os
   filtros do próprio site (`subTypes`, `function`, `description`, `query`) vão
   na mesma requisição, o que permite indexar só o que interessa em vez da
   categoria inteira;
2. a **API** (`/api/database/Item/<id>`) completa cada um com a descrição, o
   peso, as classes e os scripts de efeito.

A listagem com `Accept-Language: pt` já vem restrita ao LATAM (17.322 itens);
sem isso são 23.815, a maioria de outros servidores. A checagem do selo continua
sendo o filtro de verdade — o recorte por idioma é só economia de páginas.

As colunas da listagem mudam por categoria (arma tem ATK, carta não tem nível
requerido), então elas são lidas pelo cabeçalho, nunca pela posição. O nome na
listagem quase sempre vem vazio; quem dá o nome é a API.

**Local de equipar.** O que se sabe do site: a página do item mostra `Location`
com `Upper`, `Middle`, `Lower`, `Body`, `Garment`, `Shoes`, `Accessory`, `Left
Hand` (escudo), `Bothhand` (arma) e, nos trajes e sombras, `Upper (Costume)` e
`Right Shadow Accessory`. `normalizar_local` entende esses nomes. O que ainda
não foi conferido é o campo equivalente no JSON da API, por isso o payload é
lido por mais de um nome e o `dp-item` mostra o que chegou. Item de equipamento
sem local entendido aparece no resumo do `dp-itens`, nunca em silêncio.
"""

from __future__ import annotations

import json
import re
import time
import unicodedata
from collections.abc import Callable, Iterable
from html.parser import HTMLParser
from typing import Any

import httpx

from .config import DIVINE_PRIDE_BASE_URL, Settings, get_settings
from .divinepride import ChaveAusente, DivinePrideClient, DivinePrideError
from .dp_index import total_de_resultados
from .ratelimit import RateLimiter

VERSAO_INDICE_ITENS = 1

#: A listagem devolve 20 por página.
POR_PAGINA = 20

#: Teto de páginas por consulta, para um filtro largo demais não virar laço
#: infinito se o site mudar de comportamento. A maior categoria do LATAM tem 179.
MAX_PAGINAS = 400

#: Categorias da listagem (`/database/item/<categoria>`).
CATEGORIAS = ("weapon", "armor", "card", "costume", "shadow", "ammo", "consumable", "other")

#: `type` que, quando o item não traz local, indicam que faltou informação — o
#: resto (carta, consumível, etc.) não se equipa, então não ter local é normal.
TIPOS_EQUIPAVEIS = {"armor", "weapon", "costume", "shadow equipment"}

_ID_NA_LINHA = re.compile(r"/database/item/(\d+)")
_PAGINA_DE_TOTAL = re.compile(r"Page\s+(\d+)\s+of\s+(\d+)", re.IGNORECASE)

#: Sílabas do alfabeto coreano — sinal de que a API não tinha tradução.
_HANGUL = re.compile(r"[가-힯]")

#: Código de cor da descrição do cliente: `^FF0000texto^000000`.
_COR_NA_DESCRICAO = re.compile(r"\^[0-9a-fA-F]{6}")

#: Cabeçalho da listagem -> chave. As colunas que não estão aqui são ignoradas.
_COLUNAS_POR_CABECALHO = {
    "name": "name",
    "type": "type",
    "subtype": "subtype",
    "required level": "required_level",
    "atk": "atk",
    "sell price": "sell_price",
    "server": "servers",
}

#: Colunas da listagem quando a página não traz cabeçalho.
_CABECALHO_PADRAO = ("Name", "Type", "SubType", "Required Level", "Sell Price", "Server")

#: Nomes já vistos (e prováveis) para o local no payload da API.
_CHAVES_LOCAL = ("location", "locations", "equipLocation", "equipLocations", "equipmentLocation")
_CHAVES_NIVEL = ("requiredLevel", "equipLevelMin")

#: Local canônico -> como aparece na saída.
LOCAIS = {
    "topo": "Topo",
    "meio": "Meio",
    "baixo": "Baixo",
    "armadura": "Armadura",
    "arma": "Arma",
    "escudo": "Escudo",
    "capa": "Capa",
    "calcado": "Calçado",
    "acessorio": "Acessório",
    "traje-topo": "Traje (topo)",
    "traje-meio": "Traje (meio)",
    "traje-baixo": "Traje (baixo)",
    "traje-capa": "Traje (capa)",
    "sombra-arma": "Sombra (arma)",
    "sombra-armadura": "Sombra (armadura)",
    "sombra-escudo": "Sombra (escudo)",
    "sombra-calcado": "Sombra (calçado)",
    "sombra-brinco": "Sombra (brinco)",
    "sombra-pingente": "Sombra (pingente)",
}

#: Subtipo -> local, para quando o payload não traz local. Só vale para armadura
#: (Headgear fica de fora de propósito: topo, meio e baixo só o local diz) e arma.
_LOCAL_POR_SUBTIPO = {
    "shield": "escudo",
    "garment": "capa",
    "shoes": "calcado",
    "accessory": "acessorio",
    "armor": "armadura",
}


class IndiceIndisponivel(RuntimeError):
    """O índice de itens ainda não foi montado, ou é de uma versão antiga."""


def sem_acento(texto: str) -> str:
    """Minúsculas e sem acento, para comparar o que o usuário digita com o texto do jogo."""
    decomposto = unicodedata.normalize("NFD", texto)
    return "".join(c for c in decomposto if not unicodedata.combining(c)).casefold()


def local_digitado(texto: str) -> str | None:
    """O que o usuário digitou (`Calçado`, `acessório`) -> chave canônica, ou None."""
    chave = sem_acento(texto).strip().replace(" ", "-").replace("_", "-")
    return chave if chave in LOCAIS else None


# --- listagem ---


class _TabelaDeItens(HTMLParser):
    """Lê as linhas da tabela de resultados da listagem de itens.

    Cada célula guarda o texto inteiro e também os pedaços de texto separados:
    os selos de servidor são `<span>` um ao lado do outro, e nada garante que
    haja espaço entre eles no HTML.
    """

    def __init__(self) -> None:
        super().__init__()
        self.cabecalho: list[str] = []
        self.linhas: list[dict[str, Any]] = []
        self._no_cabecalho = False
        self._na_celula_do_cabecalho = False
        self._atual: dict[str, Any] | None = None
        self._na_celula = False
        self._pedacos: list[str] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        atributos = dict(attrs)
        if tag == "thead":
            self._no_cabecalho = True
        elif tag == "th" and self._no_cabecalho:
            self._na_celula_do_cabecalho = True
            self._pedacos = []
        elif tag == "tr":
            achado = _ID_NA_LINHA.search(atributos.get("onclick") or "")
            if achado:
                self._atual = {"id": int(achado.group(1)), "cols": [], "pedacos": []}
        elif tag == "td" and self._atual is not None:
            self._na_celula = True
            self._pedacos = []

    def handle_data(self, data: str) -> None:
        if (self._na_celula or self._na_celula_do_cabecalho) and data.strip():
            self._pedacos.append(" ".join(data.split()))

    def handle_endtag(self, tag: str) -> None:
        if tag == "thead":
            self._no_cabecalho = False
        elif tag == "th" and self._na_celula_do_cabecalho:
            self.cabecalho.append(" ".join(self._pedacos))
            self._na_celula_do_cabecalho = False
        elif tag == "td" and self._atual is not None and self._na_celula:
            self._atual["cols"].append(" ".join(self._pedacos))
            self._atual["pedacos"].append(self._pedacos)
            self._na_celula = False
        elif tag == "tr" and self._atual is not None:
            self.linhas.append(self._atual)
            self._atual = None


def _inteiro(texto: str) -> int:
    digitos = re.sub(r"[^\d]", "", texto.strip().split(" ")[0])
    return int(digitos) if digitos else 0


def parse_listagem(html_texto: str) -> list[dict[str, Any]]:
    """Converte uma página da listagem nas linhas que interessam.

    `servers` é a lista dos selos da última coluna (`bRO`, `LATAM`, `iRO`...).
    """
    parser = _TabelaDeItens()
    parser.feed(html_texto)

    cabecalho = parser.cabecalho or list(_CABECALHO_PADRAO)
    chaves = [_COLUNAS_POR_CABECALHO.get(nome.strip().casefold()) for nome in cabecalho]

    itens = []
    for linha in parser.linhas:
        bruto = {chave: valor for chave, valor in zip(chaves, linha["cols"], strict=False) if chave}
        selos = dict(zip(chaves, linha["pedacos"], strict=False)).get("servers", [])
        itens.append(
            {
                "id": linha["id"],
                "name": bruto.get("name", ""),
                "type": bruto.get("type", ""),
                "subtype": bruto.get("subtype", ""),
                "required_level": _inteiro(bruto.get("required_level", "")),
                "servers": selos,
            }
        )
    return itens


def listar(
    categoria: str,
    *,
    subtipos: Iterable[str] = (),
    funcao: int | None = None,
    descricao: str | None = None,
    busca: str | None = None,
    limite: int | None = None,
    settings: Settings | None = None,
    client: httpx.Client | None = None,
    limiter: RateLimiter | None = None,
    progresso: Callable[[str], None] | None = None,
) -> list[dict[str, Any]]:
    """Os itens da categoria que existem no servidor configurado (LATAM), segundo a listagem.

    `subtipos`, `funcao`, `descricao` e `busca` são os filtros do próprio site
    (`subTypes`, `function`, `description`, `query`). `limite` corta a lista
    depois de tantos itens do servidor — serve para um teste curto.
    """
    if categoria not in CATEGORIAS:
        raise ValueError(f"categoria inválida: {categoria}. Use: {', '.join(CATEGORIAS)}.")

    settings = settings or get_settings()
    aviso = progresso or (lambda _: None)
    limiter = limiter or RateLimiter(settings.divine_pride_rate_limit)

    filtros: list[tuple[str, str | int]] = [("subTypes", subtipo) for subtipo in subtipos]
    if funcao is not None:
        filtros.append(("function", funcao))
    if descricao:
        filtros.append(("description", descricao))
    if busca:
        filtros.append(("query", busca))

    meu_client = client is None
    client = client or httpx.Client(
        base_url=DIVINE_PRIDE_BASE_URL,
        timeout=settings.http_timeout,
        headers={
            "User-Agent": settings.user_agent,
            "x-server": settings.divine_pride_server,
            "Accept-Language": settings.divine_pride_language,
        },
        follow_redirects=True,
    )

    itens: dict[int, dict[str, Any]] = {}
    try:
        for pagina in range(1, MAX_PAGINAS + 1):
            limiter.acquire()
            resposta = client.get(f"/database/item/{categoria}", params=[*filtros, ("page", pagina)])
            if resposta.status_code >= 400:
                raise RuntimeError(f"a listagem respondeu {resposta.status_code} na página {pagina}")

            linhas = parse_listagem(resposta.text)
            if not linhas:
                break

            for item in linhas:
                if settings.divine_pride_server in item["servers"]:
                    itens.setdefault(item["id"], item)

            total = total_de_resultados(resposta.text)
            alvo = f"/{total}" if total else ""
            aviso(f"listagem {categoria}: {len(itens)}{alvo} itens (página {pagina})")

            if limite is not None and len(itens) >= limite:
                break
            achado = _PAGINA_DE_TOTAL.search(resposta.text)
            if len(linhas) < POR_PAGINA or (achado and pagina >= int(achado.group(2))):
                break
    finally:
        if meu_client:
            client.close()

    lista = list(itens.values())
    return lista[:limite] if limite is not None else lista


# --- local de equipar ---


def _textos(valor: Any) -> list[str]:
    """Os textos de um campo que pode ser string, lista ou objeto com `name`."""
    if isinstance(valor, str):
        return [valor] if valor.strip() else []
    if isinstance(valor, list):
        return [texto for item in valor for texto in _textos(item)]
    if isinstance(valor, dict):
        return _textos(valor.get("name") or valor.get("location") or valor.get("key"))
    return []


def locais_brutos(payload: dict[str, Any]) -> list[str]:
    """O local como a API mandou, sem interpretar (`Upper`, `Left Hand`...)."""
    for chave in _CHAVES_LOCAL:
        textos = _textos(payload.get(chave))
        if textos:
            return textos
    return []


def normalizar_local(bruto: str, tipo: str = "") -> str | None:
    """`Upper (Costume)` -> `traje-topo`; nome que não se reconhece volta None.

    `tipo` desempata `Left Hand`: é o escudo numa armadura e a arma da mão
    esquerda numa adaga.
    """
    texto = re.sub(r"[_\-\s]+", " ", sem_acento(bruto)).strip()
    if not texto or texto == "none":
        return None

    if "shadow" in texto or "sombr" in texto:
        if "accessory" in texto or "acessorio" in texto:
            if "right" in texto or "direit" in texto:
                return "sombra-brinco"
            if "left" in texto or "esquerd" in texto:
                return "sombra-pingente"
            return None
        for chave, palavras in (
            ("sombra-calcado", ("shoes", "calcado")),
            ("sombra-escudo", ("shield", "escudo")),
            # "armadura" contém "arma": a armadura tem de ser testada antes.
            ("sombra-armadura", ("armor", "armadura")),
            ("sombra-arma", ("weapon", "arma")),
        ):
            if any(p in texto for p in palavras):
                return chave
        return None

    traje = "costume" in texto or "traje" in texto
    for chave, palavras in (
        ("topo", ("upper", "head top", "topo")),
        ("meio", ("middle", "head mid", "meio")),
        ("baixo", ("lower", "head low", "baixo")),
        ("capa", ("garment", "robe", "capa")),
    ):
        if any(p in texto for p in palavras):
            return f"traje-{chave}" if traje else chave
    if traje:
        return None

    if "shoes" in texto or "calcado" in texto:
        return "calcado"
    if "accessory" in texto or "acessorio" in texto:
        return "acessorio"
    if "left hand" in texto:
        return "arma" if tipo.casefold() == "weapon" else "escudo"
    if "shield" in texto or "escudo" in texto:
        return "escudo"
    if "body" in texto or "armor" in texto or "armadura" in texto:
        return "armadura"
    if "hand" in texto or "weapon" in texto or "arma" in texto:
        return "arma"
    return None


def locais_do_item(brutos: Iterable[str], tipo: str, subtipo: str) -> list[str]:
    """Locais canônicos de um item, na ordem em que a API os deu, sem repetir.

    Sem local no payload, armadura e arma ainda têm o subtipo como pista (escudo,
    capa, calçado...). Headgear não: topo, meio ou baixo só o local diz.
    """
    achados: list[str] = []
    for bruto in brutos:
        # Um campo só pode trazer vários locais ("Upper, Middle").
        for parte in re.split(r"[,;|+/]", bruto):
            local = normalizar_local(parte, tipo)
            if local and local not in achados:
                achados.append(local)
    if achados:
        return achados

    if tipo.casefold() == "weapon":
        return ["arma"]
    if tipo.casefold() == "armor":
        local = _LOCAL_POR_SUBTIPO.get(subtipo.casefold())
        return [local] if local else []
    return []


# --- normalização do payload ---


def limpar_descricao(texto: Any) -> str:
    """A descrição sem os códigos de cor (`^FF0000`) do cliente, com quebras de linha normais."""
    if not isinstance(texto, str):
        return ""
    texto = _COR_NA_DESCRICAO.sub("", texto.replace("\r\n", "\n").replace("\r", "\n"))
    return "\n".join(linha.rstrip() for linha in texto.split("\n")).strip()


def _nome_de_aegis(aegis: Any) -> str | None:
    """`Elegant_Flower` -> `Elegant Flower`."""
    if not isinstance(aegis, str) or not aegis.strip():
        return None
    return " ".join(parte for parte in aegis.strip().split("_") if parte)


def _nome(payload: dict[str, Any], basico: dict[str, Any]) -> str:
    """Nome da API (pt) -> nome da listagem -> nome Aegis.

    Sem tradução o nome vem em coreano, vazio ou igual ao id; aí o Aegis ainda
    identifica o item.
    """
    for candidato in (payload.get("name"), basico.get("name")):
        if isinstance(candidato, str):
            candidato = candidato.strip()
            if candidato and candidato != str(basico["id"]) and not _HANGUL.search(candidato):
                return candidato
    return _nome_de_aegis(payload.get("aegisName")) or str(basico["id"])


def _numero(valor: Any) -> int:
    try:
        return int(valor)
    except (TypeError, ValueError):
        return 0


def normalizar_item(payload: dict[str, Any], basico: dict[str, Any]) -> dict[str, Any]:
    """Junta o payload da API e a linha da listagem no formato do índice.

    Nunca levanta exceção por campo ausente: o que faltar vira vazio, e o
    `dp-item` mostra o que chegou e o que foi entendido.
    """
    tipo = str(payload.get("type") or basico.get("type") or "")
    subtipo = str(payload.get("subType") or basico.get("subtype") or "")
    brutos = locais_brutos(payload)

    nivel = basico.get("required_level") or next(
        (_numero(payload[c]) for c in _CHAVES_NIVEL if payload.get(c) not in (None, "")), 0
    )
    jobs = payload.get("allowedJobIds")

    return {
        "id": basico["id"],
        "name": _nome(payload, basico),
        "aegis_name": str(payload.get("aegisName") or ""),
        "type": tipo,
        "subtype": subtipo,
        "locations": locais_do_item(brutos, tipo, subtipo),
        "location_raw": brutos,
        "required_level": nivel,
        "weight": _numero(payload.get("weight")),
        "description": limpar_descricao(payload.get("description")),
        "all_jobs": bool(payload.get("allJobsAllowed")),
        "job_ids": [j for j in jobs if isinstance(j, int)] if isinstance(jobs, list) else [],
        "scripts": payload.get("scripts") if isinstance(payload.get("scripts"), list) else [],
        "icon_url": str(payload.get("iconUrl") or ""),
    }


def sem_local(item: dict[str, Any]) -> bool:
    """Equipamento para o qual não se entendeu o local — o filtro por local não o acharia."""
    return item["type"].casefold() in TIPOS_EQUIPAVEIS and not item["locations"]


# --- índice ---


def completar(
    itens: Iterable[dict[str, Any]],
    cliente: DivinePrideClient,
    *,
    progresso: Callable[[str], None] | None = None,
    refresh: bool = False,
) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    """Consulta a API por id e monta o índice. Devolve também os ids que a API recusou.

    Um id que a listagem mostra mas a API não tem (404) não derruba as horas de
    consulta já feitas — vai para a lista de falhas. Chave recusada derruba, pois
    nenhuma consulta seguinte vai funcionar.
    """
    aviso = progresso or (lambda _: None)
    itens = list(itens)

    completos: list[dict[str, Any]] = []
    falhas: list[dict[str, Any]] = []
    for i, basico in enumerate(itens, start=1):
        aviso(f"{i}/{len(itens)} — item {basico['id']}")
        try:
            payload = cliente.item(basico["id"], refresh=refresh)
        except ChaveAusente:
            raise
        except DivinePrideError as erro:
            falhas.append({"id": basico["id"], "erro": str(erro)})
            continue
        completos.append(normalizar_item(payload, basico))

    indice = {
        "version": VERSAO_INDICE_ITENS,
        "fonte": "divine-pride",
        "servidor": cliente.settings.divine_pride_server,
        "generated_at": time.time(),
        "items": completos,
    }
    return indice, falhas


def fundir(antigo: dict[str, Any], novo: dict[str, Any]) -> dict[str, Any]:
    """Junta dois índices, com o novo tendo a palavra final (cada `dp-itens` cobre um recorte)."""
    itens = {i["id"]: i for i in antigo.get("items", [])}
    itens.update({i["id"]: i for i in novo.get("items", [])})
    return {**novo, "items": sorted(itens.values(), key=lambda i: i["id"])}


def gravar(settings: Settings, indice: dict[str, Any], *, acumular: bool = True) -> dict[str, Any]:
    """Grava o índice, somando ao que já estava lá quando `acumular`."""
    caminho = settings.items_index_path
    if acumular and caminho.is_file():
        try:
            antigo = json.loads(caminho.read_text(encoding="utf-8"))
            if antigo.get("version") == VERSAO_INDICE_ITENS:
                indice = fundir(antigo, indice)
        except json.JSONDecodeError:
            pass  # índice corrompido: recomeça deste

    caminho.parent.mkdir(parents=True, exist_ok=True)
    caminho.write_text(json.dumps(indice, ensure_ascii=False), encoding="utf-8")
    return indice


def carregar(settings: Settings | None = None) -> dict[str, Any]:
    """Lê o índice montado pelo `dp-itens`."""
    settings = settings or get_settings()
    caminho = settings.items_index_path
    if not caminho.is_file():
        raise IndiceIndisponivel(
            f"índice de itens não encontrado em {caminho}. Rode `ragleveling dp-itens --categoria <categoria>`."
        )
    dados = json.loads(caminho.read_text(encoding="utf-8"))
    if dados.get("version") != VERSAO_INDICE_ITENS:
        raise IndiceIndisponivel(
            "índice de itens de uma versão antiga. Rode `ragleveling dp-itens` de novo "
            "(as consultas já feitas vêm do cache)."
        )
    return dados


def filtrar(
    indice: dict[str, Any],
    *,
    local: str | None = None,
    tipo: str | None = None,
    nome: str | None = None,
    texto: str | None = None,
    item_id: int | None = None,
) -> list[dict[str, Any]]:
    """Os itens do índice que passam em todos os filtros dados, por ordem de nome.

    `tipo` casa com o tipo ou o subtipo (`armor`, `headgear`, `card`); `nome` com
    o nome ou o nome Aegis; `texto` com a descrição — todas as palavras, sem
    acento e sem importar a caixa.
    """
    palavras = sem_acento(texto).split() if texto else []
    achados = []
    for item in indice.get("items", []):
        if item_id is not None and item["id"] != item_id:
            continue
        if local is not None and local not in item["locations"]:
            continue
        if tipo and not any(sem_acento(tipo) in sem_acento(campo) for campo in (item["type"], item["subtype"])):
            continue
        if nome and not any(sem_acento(nome) in sem_acento(campo) for campo in (item["name"], item["aegis_name"])):
            continue
        if palavras:
            descricao = sem_acento(item["description"])
            if not all(p in descricao for p in palavras):
                continue
        achados.append(item)
    return sorted(achados, key=lambda i: (sem_acento(i["name"]), i["id"]))
