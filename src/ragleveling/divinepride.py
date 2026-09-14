"""Cliente do Divine Pride: de onde vêm os spawns que o rAthena ainda não tem.

A API responde por ID (`/api/database/Monster/<id>`), uma requisição por segundo.
Como a lista de IDs já vem do `mob_db.yml`, não é preciso varrer o banco inteiro:
o `ragleveling dp-spawns` consulta só os monstros que estão sem mapa.

Sobre o formato do JSON: a normalização abaixo aceita mais de um nome para cada
campo e nunca levanta exceção por campo ausente. Isso é deliberado — o formato
não pôde ser conferido contra o serviço real durante o desenvolvimento (a rede
de onde o código foi escrito não alcança o divine-pride.net). Use
`ragleveling dp-check <id>` para ver o que chegou e o que foi entendido; se
algum campo vier vazio, é o primeiro lugar para olhar.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import httpx
import yaml

from .config import DIVINE_PRIDE_BASE_URL, Settings, get_settings
from .ratelimit import RateLimiter

#: Nomes já vistos para a lista de spawns dentro do payload de um monstro.
_CHAVES_SPAWN = ("spawn", "spawns", "monsterSpawn", "spawnList")

#: Nomes já vistos para cada campo de um spawn.
_CHAVES_MAPA = ("mapname", "map", "mapName", "mapId", "mapid", "name")
_CHAVES_QUANTIDADE = ("amount", "count", "quantity", "qtd")
_CHAVES_RESPAWN = ("respawnTime", "respawn", "delay", "respawnTimeSeconds")


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
    """Spawns do payload, no formato do `data/spawns_extra.yaml`.

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
    ) -> None:
        self.settings = settings or get_settings()
        self._meu_client = client is None
        self._client = client or httpx.Client(
            base_url=DIVINE_PRIDE_BASE_URL,
            timeout=self.settings.http_timeout,
            headers={"User-Agent": self.settings.user_agent},
            follow_redirects=True,
        )
        self.limiter = limiter or RateLimiter(self.settings.divine_pride_rate_limit)

    def __enter__(self) -> DivinePrideClient:
        return self

    def __exit__(self, *exc: object) -> None:
        self.close()

    def close(self) -> None:
        if self._meu_client:
            self._client.close()

    @property
    def cache_dir(self) -> Path:
        return self.settings.cache_dir / "divinepride" / self.settings.divine_pride_server

    def _caminho_cache(self, monster_id: int) -> Path:
        return self.cache_dir / f"monster-{monster_id}.json"

    def monstro(self, monster_id: int, *, refresh: bool = False) -> dict[str, Any]:
        """Payload cru de um monstro. Usa o cache em disco quando possível."""
        cache = self._caminho_cache(monster_id)
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

        self.limiter.acquire()
        try:
            resposta = self._client.get(
                f"/api/database/Monster/{monster_id}",
                params={"apiKey": chave, "server": self.settings.divine_pride_server},
            )
        except httpx.HTTPError as erro:
            raise DivinePrideError(f"falha ao consultar o monstro {monster_id}: {erro}") from erro

        if resposta.status_code == 404:
            raise DivinePrideError(f"monstro {monster_id} não existe no Divine Pride")
        if resposta.status_code in (401, 403):
            raise ChaveAusente("chave da API recusada (401/403). Confira DIVINE_PRIDE_API_KEY.")
        if resposta.status_code == 429:
            raise DivinePrideError("limite de 1 requisição por segundo excedido (429)")
        if resposta.status_code >= 400:
            raise DivinePrideError(f"Divine Pride respondeu {resposta.status_code} para {monster_id}")

        try:
            payload = resposta.json()
        except json.JSONDecodeError as erro:
            raise DivinePrideError(f"resposta do monstro {monster_id} não é JSON: {erro}") from erro
        if not isinstance(payload, dict):
            raise DivinePrideError(f"resposta inesperada para o monstro {monster_id}")

        cache.parent.mkdir(parents=True, exist_ok=True)
        cache.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
        return payload


CABECALHO_OVERLAY = """\
# Spawns que o rAthena ainda não tem.
#
# Parte deste arquivo é escrita por `ragleveling dp-spawns`, que consulta o
# Divine Pride pelos monstros sem mapa. Entradas feitas à mão são preservadas:
# o comando só substitui os spawns do mesmo mapa e mesmo monstro.
#
# Formato:
#
#   mapas:
#     clock_01:
#       fonte: https://www.divine-pride.net/database/map/clock_01
#       spawns:
#         - { monster_id: 20940, amount: 30, respawn_s: 5 }
#
# Todo spawn daqui aparece marcado — `*` na CLI, `manual` no detalhe da web —
# para não se confundir com o que veio do servidor.
"""


def mesclar_overlay(
    atual: dict[str, Any],
    novos_por_mapa: dict[str, list[dict[str, Any]]],
    *,
    fonte_base: str = f"{DIVINE_PRIDE_BASE_URL}/database/map",
) -> dict[str, Any]:
    """Junta os spawns vindos do Divine Pride ao conteúdo já existente.

    A chave é o par (mapa, monstro): um spawn novo substitui o antigo do mesmo
    monstro naquele mapa e deixa o resto intacto.
    """
    mapas = dict(atual.get("mapas") or {})

    for map_id, spawns in novos_por_mapa.items():
        entrada = dict(mapas.get(map_id) or {})
        existentes = list(entrada.get("spawns") or [])
        por_monstro = {int(s["monster_id"]): dict(s) for s in existentes if "monster_id" in s}
        for spawn in spawns:
            por_monstro[int(spawn["monster_id"])] = dict(spawn)
        entrada["spawns"] = [por_monstro[mid] for mid in sorted(por_monstro)]
        entrada.setdefault("fonte", f"{fonte_base}/{map_id}")
        mapas[map_id] = entrada

    return {"mapas": dict(sorted(mapas.items()))}


def gravar_overlay(caminho: Path, dados: dict[str, Any]) -> None:
    """Escreve o arquivo de complemento com o cabeçalho explicativo."""
    caminho.parent.mkdir(parents=True, exist_ok=True)
    corpo = yaml.safe_dump(dados, allow_unicode=True, sort_keys=False, default_flow_style=False)
    caminho.write_text(CABECALHO_OVERLAY + "\n" + corpo, encoding="utf-8")


def ler_overlay(caminho: Path) -> dict[str, Any]:
    """Lê o complemento atual; devolve a estrutura vazia se ele não existir."""
    if not caminho.is_file():
        return {"mapas": {}}
    dados = yaml.safe_load(caminho.read_text(encoding="utf-8")) or {}
    if not isinstance(dados.get("mapas"), dict):
        dados["mapas"] = {}
    return dados
