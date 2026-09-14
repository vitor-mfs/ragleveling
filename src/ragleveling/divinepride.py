"""Cliente da API do Divine Pride — a única fonte de dados do ragleveling.

A API responde por ID (`/api/database/Monster/<id>`, `/api/database/Skill/<id>`),
com intervalo entre requisições. A lista de IDs vem da listagem do site
(`dp_index.listar_por_nivel`); aqui só se consulta o que já se sabe que existe.

O formato foi conferido contra a API real: os spawns vêm em `spawns`, cada um
com `mapName`, `quantity` e `respawnTime` em milissegundos. A normalização
continua aceitando mais de um nome por campo e nunca levanta exceção por campo
ausente, para sobreviver a mudanças no serviço — `ragleveling dp-check <id>`
mostra o que chegou e o que foi entendido.

Do payload o índice usa, além dos spawns: `expPenaltyTable` (a penalidade de
EXP real, por nível de jogador e por monstro), `elementResistances` (a
resistência já calculada, com os modificadores próprios do monstro) e `skills`
(só o id — o nome canônico vem de `GET Skill/<id>`).

A região e o idioma vão em **headers** (`x-server` e `Accept-Language`), não na
query — foi o que a documentação em /tools/api-doc esclareceu. Com
`x-server: LATAM` e `Accept-Language: pt` os nomes chegam em português.

A mesma documentação pede moderação: guardar o que já foi consultado, respeitar
o `Retry-After` do 429 e **não varrer o banco inteiro** — enumeração em massa
de ids leva à revogação da chave. Por isso o `dp-index` trabalha sobre a faixa
de níveis que você pediu, e nunca sobre o catálogo todo.
"""

from __future__ import annotations

import json
import time
from collections.abc import Callable
from pathlib import Path
from typing import Any

import httpx

from .config import DIVINE_PRIDE_BASE_URL, Settings, get_settings
from .ratelimit import RateLimiter

#: Nomes já vistos para a lista de spawns dentro do payload de um monstro.
_CHAVES_SPAWN = ("spawn", "spawns", "monsterSpawn", "spawnList")

#: Nomes já vistos para cada campo de um spawn.
_CHAVES_MAPA = ("mapname", "map", "mapName", "mapId", "mapid", "name")
_CHAVES_QUANTIDADE = ("amount", "count", "quantity", "qtd")
_CHAVES_RESPAWN = ("respawnTime", "respawn", "delay", "respawnTimeSeconds")


#: Esperas entre as tentativas quando a API responde 429 e não manda
#: `Retry-After`. Quando manda, o valor dela é que vale.
ESPERAS_APOS_429 = (5.0, 15.0, 30.0)

#: Esperas quando a conexão cai antes da resposta (o servidor derruba de vez em
#: quando no meio de uma sequência longa). Sem isso um índice de 20 minutos
#: morria por um soluço da rede.
ESPERAS_APOS_QUEDA = (3.0, 10.0, 30.0)


def _retry_after(resposta: httpx.Response) -> float | None:
    """O `Retry-After` do 429, em segundos, quando a API manda um."""
    bruto = resposta.headers.get("Retry-After")
    if not bruto:
        return None
    try:
        return max(0.0, float(bruto))
    except ValueError:
        return None


class DivinePrideError(RuntimeError):
    """Falha ao consultar o Divine Pride."""


class ChaveAusente(DivinePrideError):
    """Não há chave de API configurada."""


def _primeiro(dados: dict[str, Any], chaves: tuple[str, ...]) -> Any:
    for chave in chaves:
        if chave in dados and dados[chave] not in (None, ""):
            return dados[chave]
    return None


def extrair_nome(payload: dict[str, Any]) -> str | None:
    """Nome do monstro no idioma do servidor consultado (pt-BR no bRO)."""
    nome = _primeiro(payload, ("name", "Name"))
    return str(nome) if nome else None


def extrair_spawns(payload: dict[str, Any]) -> list[dict[str, Any]]:
    """Spawns do payload: mapa, quantidade e respawn em segundos.

    Devolve lista vazia quando o payload não traz spawns — o que é informação,
    não erro: o monstro pode mesmo não nascer em mapa aberto.
    """
    bruto = _primeiro(payload, _CHAVES_SPAWN)
    if not isinstance(bruto, list):
        return []

    spawns: list[dict[str, Any]] = []
    for item in bruto:
        if not isinstance(item, dict):
            continue
        mapa = _primeiro(item, _CHAVES_MAPA)
        if not mapa:
            continue
        quantidade = _primeiro(item, _CHAVES_QUANTIDADE)
        respawn = _primeiro(item, _CHAVES_RESPAWN)
        try:
            quantidade = int(quantidade) if quantidade is not None else 0
        except (TypeError, ValueError):
            quantidade = 0
        spawns.append(
            {
                "map": str(mapa),
                "amount": quantidade,
                "respawn_s": _respawn_em_segundos(respawn),
                "respawn_bruto": respawn,
            }
        )
    return spawns


#: A partir daqui o respawn é lido como milissegundos.
#:
#: A unidade não vem declarada no payload e os dois casos existem no mundo real.
#: O corte em 1.000 segue os próprios dados do rAthena, onde o respawn de campo
#: é escrito em milissegundos e 5000 (5 s) é de longe o valor mais comum —
#: enquanto um respawn legítimo de 5.000 segundos (83 minutos) seria exótico.
#: `ragleveling dp-check` mostra o valor cru ao lado do convertido, para você
#: conferir contra um monstro que já conhece.
LIMIAR_MILISSEGUNDOS = 1_000


def agregar_spawns(spawns: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Junta as linhas repetidas do mesmo mapa.

    O Divine Pride lista cada grupo de spawn separadamente — um monstro pode
    aparecer quatro vezes no mesmo mapa (70 com respawn de 5 s, mais três de 5
    com respawn de 10 s). Para decidir onde caçar o que importa é o total no
    mapa, então as quantidades somam e fica o menor respawn.
    """
    por_mapa: dict[str, dict[str, Any]] = {}
    for spawn in spawns:
        atual = por_mapa.get(spawn["map"])
        if atual is None:
            por_mapa[spawn["map"]] = dict(spawn)
            continue
        atual["amount"] += spawn["amount"]
        if spawn["respawn_s"] and (not atual["respawn_s"] or spawn["respawn_s"] < atual["respawn_s"]):
            atual["respawn_s"] = spawn["respawn_s"]
    return list(por_mapa.values())


def _respawn_em_segundos(valor: Any) -> float:
    """Converte o respawn para segundos, decidindo a unidade pelo tamanho."""
    try:
        numero = float(valor)
    except (TypeError, ValueError):
        return 0.0
    if numero <= 0:
        return 0.0
    return numero / 1000.0 if numero >= LIMIAR_MILISSEGUNDOS else numero


class DivinePrideClient:
    """Consulta monstros no Divine Pride, com cache em disco e 1 req/s."""

    def __init__(
        self,
        settings: Settings | None = None,
        *,
        client: httpx.Client | None = None,
        limiter: RateLimiter | None = None,
        sleep: Callable[[float], None] = time.sleep,
    ) -> None:
        self.settings = settings or get_settings()
        self._meu_client = client is None
        self._client = client or httpx.Client(
            base_url=DIVINE_PRIDE_BASE_URL,
            timeout=self.settings.http_timeout,
            headers=self.headers(),
            follow_redirects=True,
        )
        self.limiter = limiter or RateLimiter(self.settings.divine_pride_rate_limit)
        self._sleep = sleep

    def __enter__(self) -> DivinePrideClient:
        return self

    def __exit__(self, *exc: object) -> None:
        self.close()

    def close(self) -> None:
        if self._meu_client:
            self._client.close()

    def headers(self) -> dict[str, str]:
        """Região e idioma vão em headers; a query só leva a chave."""
        return {
            "User-Agent": self.settings.user_agent,
            "x-server": self.settings.divine_pride_server,
            "Accept-Language": self.settings.divine_pride_language,
        }

    @property
    def cache_dir(self) -> Path:
        return (
            self.settings.cache_dir
            / "divinepride"
            / f"{self.settings.divine_pride_server}-{self.settings.divine_pride_language}"
        )

    def _caminho_cache(self, monster_id: int) -> Path:
        return self.cache_dir / f"monster-{monster_id}.json"

    def skill(self, skill_id: int, *, refresh: bool = False) -> dict[str, Any]:
        """Payload cru de uma habilidade; `databaseName` traz o nome canônico."""
        return self._entidade("Skill", skill_id, refresh=refresh)

    def _buscar_com_retry(self, tipo: str, entity_id: int, chave: str) -> httpx.Response:
        """Uma requisição, repetida com espera crescente em 429 e em queda de conexão."""
        quedas = list(ESPERAS_APOS_QUEDA)
        esperas_429 = list(ESPERAS_APOS_429)
        while True:
            self.limiter.acquire()
            try:
                resposta = self._client.get(
                    f"/api/database/{tipo}/{entity_id}",
                    params={"apiKey": chave},
                    headers=self.headers(),
                )
            except httpx.HTTPError as erro:
                if not quedas:
                    raise DivinePrideError(f"falha ao consultar {tipo} {entity_id}: {erro}") from erro
                self._sleep(quedas.pop(0))
                continue

            if resposta.status_code != 429 or not esperas_429:
                return resposta
            self._sleep(_retry_after(resposta) or esperas_429.pop(0))
        raise AssertionError("inalcançável")  # pragma: no cover

    def monstro(self, monster_id: int, *, refresh: bool = False) -> dict[str, Any]:
        """Payload cru de um monstro. Usa o cache em disco quando possível."""
        return self._entidade("Monster", monster_id, refresh=refresh)

    def _entidade(self, tipo: str, entity_id: int, *, refresh: bool = False) -> dict[str, Any]:
        cache = self.cache_dir / f"{tipo.lower()}-{entity_id}.json"
        if cache.is_file() and not refresh:
            try:
                return json.loads(cache.read_text(encoding="utf-8"))
            except json.JSONDecodeError:
                pass  # cache corrompido: refaz a consulta

        chave = self.settings.divine_pride_api_key
        if not chave:
            raise ChaveAusente(
                "Falta a chave da API do Divine Pride. Pegue a sua em "
                "https://www.divine-pride.net/account e exporte DIVINE_PRIDE_API_KEY."
            )

        resposta = self._buscar_com_retry(tipo, entity_id, chave)

        if resposta.status_code == 404:
            raise DivinePrideError(f"{tipo} {entity_id} não existe no Divine Pride")
        if resposta.status_code in (401, 403):
            raise ChaveAusente("chave da API recusada (401/403). Confira DIVINE_PRIDE_API_KEY.")
        if resposta.status_code == 429:
            raise DivinePrideError(
                "a API continuou respondendo 429 depois de esperar. Tente de novo mais tarde ou "
                "aumente o intervalo com RAGLEVELING_DP_RATE."
            )
        if resposta.status_code >= 400:
            raise DivinePrideError(f"Divine Pride respondeu {resposta.status_code} para {tipo} {entity_id}")

        try:
            payload = resposta.json()
        except json.JSONDecodeError as erro:
            raise DivinePrideError(f"resposta de {tipo} {entity_id} não é JSON: {erro}") from erro
        if not isinstance(payload, dict):
            raise DivinePrideError(f"resposta inesperada para {tipo} {entity_id}")

        cache.parent.mkdir(parents=True, exist_ok=True)
        cache.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
        return payload
