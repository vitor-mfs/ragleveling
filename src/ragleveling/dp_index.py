"""Índice construído só com o Divine Pride.

O `mob_db.yml` do rAthena não acompanha os episódios recentes: dos 14 monstros
que nascem no `clock_01`, nenhum existe lá. Como o índice do rAthena também é a
lista de IDs que o `dp-spawns` consulta, esses monstros nunca apareciam — não
por falta de dados no Divine Pride, mas porque o programa não sabia que eles
existiam.

Aqui a lista vem do próprio Divine Pride, em duas etapas:

1. a **listagem** (`/database/monster?minLevel=&maxLevel=&page=`) devolve, de 50
   em 50, o id, o nome, o nível, o HP, a EXP, o elemento, a raça e o tamanho de
   todos os monstros da faixa — sem chave de API;
2. a **API** (`/api/database/Monster/<id>`) completa cada um com DEF, MDEF,
   ataque, habilidades, resistências elementais e, o que mais importa, os
   spawns.

A etapa 2 é uma requisição por monstro no limite da API, então é trabalho de
minutos para uma faixa larga. O resultado fica em `index-dp.json` e o `cacar
--fonte dp` lê dali, instantâneo.
"""

from __future__ import annotations

import json
import re
import time
from collections.abc import Callable, Iterable
from html.parser import HTMLParser
from typing import Any

import httpx

from .config import DIVINE_PRIDE_BASE_URL, Settings, get_settings
from .divinepride import DivinePrideClient, agregar_spawns, extrair_nome, extrair_spawns
from .ratelimit import RateLimiter

VERSAO_INDICE_DP = 1

#: A listagem devolve 50 por página.
POR_PAGINA = 50

#: Teto de páginas por consulta, para um filtro largo demais não virar um laço
#: infinito se o site mudar de comportamento.
MAX_PAGINAS = 200

_ID_NA_LINHA = re.compile(r"/database/monster/(\d+)")

#: Colunas da listagem, na ordem em que aparecem.
_COLUNAS = ("name", "level", "hp", "base_exp", "job_exp", "element", "race", "size", "type")

#: `type` na listagem; só "Normal" serve para upar.
TIPOS_CHEFE = {"Boss", "MVP", "Mini-Boss", "Guardian"}


class _TabelaDeMonstros(HTMLParser):
    """Lê as linhas da tabela de resultados da listagem."""

    def __init__(self) -> None:
        super().__init__()
        self.linhas: list[dict[str, Any]] = []
        self._atual: dict[str, Any] | None = None
        self._na_celula = False
        self._buffer: list[str] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        atributos = dict(attrs)
        if tag == "tr":
            achado = _ID_NA_LINHA.search(atributos.get("onclick") or "")
            if achado:
                self._atual = {"id": int(achado.group(1)), "cols": []}
        elif tag == "td" and self._atual is not None:
            self._na_celula = True
            self._buffer = []

    def handle_data(self, data: str) -> None:
        if self._na_celula:
            self._buffer.append(data)

    def handle_endtag(self, tag: str) -> None:
        if tag == "td" and self._atual is not None and self._na_celula:
            self._atual["cols"].append(" ".join("".join(self._buffer).split()))
            self._na_celula = False
        elif tag == "tr" and self._atual is not None:
            self.linhas.append(self._atual)
            self._atual = None


def _numero(texto: str) -> int:
    """`22.410.484 22.4m` -> 22410484.

    A listagem repete cada número na forma abreviada, então vale só o primeiro
    pedaço. O ponto é separador de milhar, não decimal.
    """
    primeiro = texto.strip().split(" ")[0]
    digitos = re.sub(r"[^\d]", "", primeiro)
    return int(digitos) if digitos else 0


def parse_listagem(html_texto: str) -> list[dict[str, Any]]:
    """Converte uma página da listagem nas linhas que interessam."""
    parser = _TabelaDeMonstros()
    parser.feed(html_texto)

    monstros = []
    for linha in parser.linhas:
        colunas = linha["cols"]
        if len(colunas) < len(_COLUNAS):
            continue
        bruto = dict(zip(_COLUNAS, colunas, strict=False))
        elemento, _, nivel_elemento = bruto["element"].partition(" ")
        monstros.append(
            {
                "id": linha["id"],
                "name": bruto["name"],
                "level": int(bruto["level"] or 0),
                "hp": _numero(bruto["hp"]),
                "base_exp": _numero(bruto["base_exp"]),
                "job_exp": _numero(bruto["job_exp"]),
                "element": elemento or "Neutral",
                "element_level": int(nivel_elemento) if nivel_elemento.isdigit() else 1,
                "race": bruto["race"],
                "size": bruto["size"],
                "type": bruto["type"],
            }
        )
    return monstros


def total_de_resultados(html_texto: str) -> int | None:
    """O `N results` que a listagem mostra, quando aparece."""
    achado = re.search(r"([\d.,]+)\s*results", html_texto, re.IGNORECASE)
    return _numero(achado.group(1)) if achado else None


def listar_por_nivel(
    nivel_min: int,
    nivel_max: int,
    *,
    settings: Settings | None = None,
    client: httpx.Client | None = None,
    limiter: RateLimiter | None = None,
    progresso: Callable[[str], None] | None = None,
) -> list[dict[str, Any]]:
    """Todos os monstros da faixa, segundo a listagem do Divine Pride."""
    settings = settings or get_settings()
    aviso = progresso or (lambda _: None)
    limiter = limiter or RateLimiter(settings.divine_pride_rate_limit)

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

    monstros: dict[int, dict[str, Any]] = {}
    try:
        for pagina in range(1, MAX_PAGINAS + 1):
            limiter.acquire()
            resposta = client.get(
                "/database/monster",
                params={"minLevel": nivel_min, "maxLevel": nivel_max, "page": pagina},
            )
            if resposta.status_code >= 400:
                raise RuntimeError(f"a listagem respondeu {resposta.status_code} na página {pagina}")

            linhas = parse_listagem(resposta.text)
            if not linhas:
                break

            for monstro in linhas:
                monstros.setdefault(monstro["id"], monstro)

            total = total_de_resultados(resposta.text)
            alvo = f"/{total}" if total else ""
            aviso(f"listagem: {len(monstros)}{alvo} monstros (página {pagina})")

            if len(linhas) < POR_PAGINA:
                break
    finally:
        if meu_client:
            client.close()

    return sorted(monstros.values(), key=lambda m: m["level"])


def _resistencias(payload: dict[str, Any]) -> dict[str, int]:
    """`elementResistances` -> {elemento: percentual de dano}."""
    bruto = payload.get("elementResistances")
    if not isinstance(bruto, list):
        return {}
    resistencias = {}
    for item in bruto:
        if isinstance(item, dict) and item.get("element") is not None:
            try:
                resistencias[str(item["element"])] = int(item.get("percentage", 100))
            except (TypeError, ValueError):
                continue
    return resistencias


def _skills(payload: dict[str, Any]) -> list[dict[str, Any]]:
    """As habilidades do payload, pelo id — o nome vem em coreano."""
    bruto = payload.get("skills")
    if not isinstance(bruto, list):
        return []
    vistas: dict[int, dict[str, Any]] = {}
    for item in bruto:
        if not isinstance(item, dict) or item.get("skillId") is None:
            continue
        try:
            skill_id = int(item["skillId"])
        except (TypeError, ValueError):
            continue
        vistas.setdefault(skill_id, {"id": skill_id, "state": item.get("state") or ""})
    return list(vistas.values())


def completar(
    monstros: Iterable[dict[str, Any]],
    cliente: DivinePrideClient,
    *,
    progresso: Callable[[str], None] | None = None,
    refresh: bool = False,
) -> dict[str, Any]:
    """Consulta a API por ID e monta o índice no formato que o `hunt` consome."""
    aviso = progresso or (lambda _: None)
    monstros = list(monstros)

    completos: list[dict[str, Any]] = []
    spawns: dict[str, list[dict[str, Any]]] = {}
    skills: dict[str, list[dict[str, Any]]] = {}

    for i, basico in enumerate(monstros, start=1):
        aviso(f"{i}/{len(monstros)} — {basico['name']}")
        payload = cliente.monstro(basico["id"], refresh=refresh)

        chave = str(basico["id"])
        do_mapa = agregar_spawns(extrair_spawns(payload))
        if do_mapa:
            spawns[chave] = [
                {
                    "map": s["map"],
                    "amount": s["amount"],
                    "respawn_ms": int(s["respawn_s"] * 1000),
                }
                for s in do_mapa
            ]
        habilidades = _skills(payload)
        if habilidades:
            skills[chave] = habilidades

        # O nome da API respeita o `Accept-Language`; o da listagem, não.
        nome = extrair_nome(payload) or basico["name"]

        completos.append(
            {
                **basico,
                "name": nome,
                "attack": _ataque(payload),
                "defense": _inteiro(payload.get("def")),
                "magic_defense": _inteiro(payload.get("mDef")),
                "boss": str(basico.get("type", "")) in TIPOS_CHEFE,
                "mvp": str(basico.get("type", "")) == "MVP",
                "aegis_name": payload.get("spriteName", ""),
                "resist": _resistencias(payload),
            }
        )

    return {
        "version": VERSAO_INDICE_DP,
        "fonte": "divine-pride",
        "generated_at": time.time(),
        "monsters": completos,
        "spawns": spawns,
        "skills": skills,
        "attr_fix": {},
    }


def _inteiro(valor: Any) -> int:
    try:
        return int(valor)
    except (TypeError, ValueError):
        return 0


def _ataque(payload: dict[str, Any]) -> int:
    """O dano de ataque do monstro, pelo maior dos dois valores.

    `attackRange` é o dano mínimo e máximo ("12.247 - 18.134"), não o alcance —
    o alcance em células é o campo `range`.
    """
    bruto = payload.get("attackRange")
    if isinstance(bruto, int | float):
        return int(bruto)
    if not isinstance(bruto, str):
        return 0
    numeros = [_numero(parte) for parte in bruto.split("-")]
    return max(numeros) if numeros else 0


def gravar(settings: Settings, indice: dict[str, Any]) -> None:
    caminho = settings.index_dp_path
    caminho.parent.mkdir(parents=True, exist_ok=True)
    caminho.write_text(json.dumps(indice, ensure_ascii=False), encoding="utf-8")


def carregar(settings: Settings | None = None) -> dict[str, Any]:
    """Lê o índice do Divine Pride, com o complemento de spawns aplicado."""
    from .rathena import SyncError, carregar_spawns_extra

    settings = settings or get_settings()
    caminho = settings.index_dp_path
    if not caminho.is_file():
        raise SyncError(
            f"índice do Divine Pride não encontrado em {caminho}. "
            "Rode `ragleveling dp-index --de <nível> --ate <nível>`."
        )
    dados = json.loads(caminho.read_text(encoding="utf-8"))
    if dados.get("version") != VERSAO_INDICE_DP:
        raise SyncError("índice do Divine Pride de uma versão antiga. Rode `ragleveling dp-index` de novo.")

    for mob, extras in carregar_spawns_extra(settings.spawns_extra_path).items():
        dados["spawns"].setdefault(mob, []).extend(extras)
    return dados
