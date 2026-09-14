"""Fontes de dados do rAthena: download, parse e índice local.

A API do Divine Pride só responde por ID — não dá para perguntar a ela "quais
monstros existem no nível 70". Quem responde isso é o `mob_db.yml` do rAthena,
que é a mesma base de números que o Divine Pride publica. Daqui sai tudo que o
`ragleveling cacar` precisa:

* `db/re/mob_db.yml` — nível, HP, ATK, DEF, MDEF, elemento, raça, EXP, se é chefe;
* `db/re/mob_skill_db.txt` — as habilidades de cada monstro;
* `db/re/attr_fix.yml` — a tabela oficial de dano por elemento;
* `npc/**/mobs/*.txt` — em que mapa cada monstro nasce, quantos e de quanto em
  quanto tempo. A lista desses arquivos vem dos dois `scripts_monsters.conf`.

Nada disso precisa de chave nem tem limite de requisições.
"""

from __future__ import annotations

import json
import re
import time
from collections.abc import Callable, Iterable
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import httpx
import yaml

from .config import ARQUIVOS_BASE, RATHENA_RAW_BASE, Settings, get_settings

try:  # pyyaml com libyaml é ~5x mais rápido no mob_db (2,3 MB)
    from yaml import CSafeLoader as _Loader  # type: ignore[attr-defined]
except ImportError:  # pragma: no cover - depende do build do pyyaml
    from yaml import SafeLoader as _Loader

VERSAO_INDICE = 2

#: Linha de spawn do rAthena, nas duas formas que os scripts usam:
#:
#:     prt_fild08,50,50,30,30<TAB>monster<TAB>Poring<TAB>1002,40,5000
#:     oz_dun02<TAB>monster<TAB>Lava Toad<TAB>21300,25
#:
#: As coordenadas são opcionais — sem elas o monstro nasce no mapa inteiro, que
#: é como as dungeons dos episódios recentes declaram seus spawns.
_SPAWN_RE = re.compile(
    r"^(?P<map>[a-z0-9_@]+)(?:,\s*\d+,\s*\d+,?[\d,\s]*)?\t"
    r"(?P<kind>monster|boss_monster)\t"
    r"(?P<label>[^\t]*)\t"
    r"(?P<mob>\d+),\s*(?P<amount>\d+)"
    r"(?:,\s*(?P<delay1>\d+))?",
    re.IGNORECASE,
)

#: `mobid,Nome@SKILL,estado,skillid,lv,rate,...`
_SKILL_RE = re.compile(r"^(?P<mob>\d+),[^@]*@(?P<skill>[A-Z0-9_]+),(?P<state>[a-z]+),")

_CLASSES_CHEFE = {"Boss", "Guardian", "Battlefield", "Event"}


class SyncError(RuntimeError):
    """Falha ao baixar ou interpretar uma fonte."""


@dataclass
class SyncResult:
    arquivos_baixados: int
    arquivos_reaproveitados: int
    monstros: int
    monstros_com_spawn: int
    mapas: int
    segundos: float


# --- download ---------------------------------------------------------


def _baixar(
    client: httpx.Client,
    caminho: str,
    destino: Path,
    *,
    force: bool,
) -> bool:
    """Baixa `caminho` do rAthena para `destino`. Devolve True se foi à rede."""
    if destino.exists() and not force:
        return False
    url = f"{RATHENA_RAW_BASE}/{caminho}"
    try:
        resposta = client.get(url)
    except httpx.HTTPError as erro:
        raise SyncError(f"falha ao baixar {url}: {erro}") from erro
    if resposta.status_code >= 400:
        raise SyncError(f"{url} respondeu {resposta.status_code}")
    destino.parent.mkdir(parents=True, exist_ok=True)
    destino.write_bytes(resposta.content)
    return True


def _scripts_de_spawn(texto: str) -> list[str]:
    """Extrai os caminhos `npc: ...` de um `scripts_monsters.conf`."""
    caminhos = []
    for linha in texto.splitlines():
        linha = linha.strip()
        if linha.startswith("//") or not linha.startswith("npc:"):
            continue
        caminho = linha.split(":", 1)[1].strip()
        if caminho:
            caminhos.append(caminho)
    return caminhos


def sync(
    settings: Settings | None = None,
    *,
    force: bool = False,
    client: httpx.Client | None = None,
    progresso: Callable[[str], None] | None = None,
) -> SyncResult:
    """Baixa as fontes do rAthena e regrava o índice local."""
    settings = settings or get_settings()
    inicio = time.monotonic()
    aviso = progresso or (lambda _: None)

    meu_client = client is None
    client = client or httpx.Client(
        timeout=settings.http_timeout,
        headers={"User-Agent": settings.user_agent},
        follow_redirects=True,
    )
    baixados = reaproveitados = 0
    try:
        for nome, caminho in ARQUIVOS_BASE.items():
            aviso(f"baixando {nome}")
            if _baixar(client, caminho, settings.raw_dir / caminho, force=force):
                baixados += 1
            else:
                reaproveitados += 1

        scripts: list[str] = []
        for chave in ("scripts_re", "scripts_pre"):
            conf = (settings.raw_dir / ARQUIVOS_BASE[chave]).read_text(encoding="utf-8", errors="replace")
            scripts.extend(_scripts_de_spawn(conf))

        for i, caminho in enumerate(scripts, start=1):
            aviso(f"spawns {i}/{len(scripts)}")
            try:
                if _baixar(client, caminho, settings.raw_dir / caminho, force=force):
                    baixados += 1
                else:
                    reaproveitados += 1
            except SyncError:
                # Um script listado pode não existir mais no master; não é fatal.
                continue
    finally:
        if meu_client:
            client.close()

    aviso("montando índice")
    indice = construir_indice(settings, scripts)
    settings.index_path.parent.mkdir(parents=True, exist_ok=True)
    settings.index_path.write_text(json.dumps(indice, ensure_ascii=False), encoding="utf-8")

    com_spawn = sum(1 for m in indice["monsters"] if str(m["id"]) in indice["spawns"])
    mapas = {s["map"] for lista in indice["spawns"].values() for s in lista}
    return SyncResult(
        arquivos_baixados=baixados,
        arquivos_reaproveitados=reaproveitados,
        monstros=len(indice["monsters"]),
        monstros_com_spawn=com_spawn,
        mapas=len(mapas),
        segundos=time.monotonic() - inicio,
    )


# --- parse ------------------------------------------------------------


def parse_mob_db(texto: str) -> list[dict[str, Any]]:
    """Achata o `mob_db.yml` nos campos que o ragleveling usa."""
    dados = yaml.load(texto, Loader=_Loader) or {}
    corpo = dados.get("Body") or []
    monstros = []
    for bruto in corpo:
        if not isinstance(bruto, dict) or "Id" not in bruto:
            continue
        modes = bruto.get("Modes") or {}
        monstros.append(
            {
                "id": int(bruto["Id"]),
                "aegis_name": bruto.get("AegisName", ""),
                "name": bruto.get("Name", ""),
                "level": bruto.get("Level"),
                "hp": bruto.get("Hp"),
                "base_exp": bruto.get("BaseExp") or 0,
                "job_exp": bruto.get("JobExp") or 0,
                "attack": bruto.get("Attack") or 0,
                "magic_attack": bruto.get("Attack2") or 0,
                "defense": bruto.get("Defense") or 0,
                "magic_defense": bruto.get("MagicDefense") or 0,
                "attack_range": bruto.get("AttackRange") or 1,
                "race": bruto.get("Race", "Formless"),
                "element": bruto.get("Element", "Neutral"),
                "element_level": bruto.get("ElementLevel") or 1,
                "size": bruto.get("Size", "Medium"),
                "classe": bruto.get("Class", "Normal"),
                "mvp": bool(modes.get("Mvp")),
                "boss": bruto.get("Class") in _CLASSES_CHEFE or bool(modes.get("Mvp")),
            }
        )
    return monstros


def parse_attr_fix(texto: str) -> dict[int, dict[str, dict[str, int]]]:
    """Tabela elemental: nível do elemento defensivo -> ataque -> defesa -> %."""
    dados = yaml.load(texto, Loader=_Loader) or {}
    tabela: dict[int, dict[str, dict[str, int]]] = {}
    for entrada in dados.get("Body") or []:
        nivel = int(entrada.get("Level", 1))
        por_ataque: dict[str, dict[str, int]] = {}
        for chave, valor in entrada.items():
            if chave == "Level" or not isinstance(valor, dict):
                continue
            por_ataque[chave] = {alvo: int(pct) for alvo, pct in valor.items()}
        tabela[nivel] = por_ataque
    return tabela


def parse_mob_skills(texto: str) -> dict[int, list[dict[str, str]]]:
    """Habilidades por monstro, a partir do `mob_skill_db.txt`."""
    por_mob: dict[int, list[dict[str, str]]] = {}
    vistos: set[tuple[int, str]] = set()
    for linha in texto.splitlines():
        linha = linha.strip()
        if not linha or linha.startswith("//"):
            continue
        achado = _SKILL_RE.match(linha)
        if not achado:
            continue
        mob = int(achado.group("mob"))
        skill = achado.group("skill")
        if (mob, skill) in vistos:
            continue
        vistos.add((mob, skill))
        por_mob.setdefault(mob, []).append({"name": skill, "state": achado.group("state")})
    return por_mob


def parse_spawns(texto: str) -> dict[int, list[dict[str, Any]]]:
    """Spawns por monstro, a partir de um script de mobs do rAthena."""
    por_mob: dict[int, list[dict[str, Any]]] = {}
    for linha in texto.splitlines():
        if "\t" not in linha or linha.lstrip().startswith("//"):
            continue
        achado = _SPAWN_RE.match(linha.strip())
        if not achado or achado.group("kind").lower() != "monster":
            continue
        mob = int(achado.group("mob"))
        delay = achado.group("delay1")
        por_mob.setdefault(mob, []).append(
            {
                "map": achado.group("map"),
                "amount": int(achado.group("amount")),
                "respawn_ms": int(delay) if delay else 0,
            }
        )
    return por_mob


def _fundir_spawns(destino: dict[str, list[dict[str, Any]]], novos: dict[int, list[dict[str, Any]]]) -> None:
    """Soma spawns do mesmo monstro no mesmo mapa (um mapa aparece em várias linhas)."""
    for mob, lista in novos.items():
        chave = str(mob)
        atual = destino.setdefault(chave, [])
        por_mapa = {s["map"]: s for s in atual}
        for spawn in lista:
            existente = por_mapa.get(spawn["map"])
            if existente is None:
                atual.append(spawn)
                por_mapa[spawn["map"]] = spawn
            else:
                existente["amount"] += spawn["amount"]
                if spawn["respawn_ms"] and (
                    not existente["respawn_ms"] or spawn["respawn_ms"] < existente["respawn_ms"]
                ):
                    existente["respawn_ms"] = spawn["respawn_ms"]


def construir_indice(settings: Settings, scripts: Iterable[str]) -> dict[str, Any]:
    """Lê os arquivos brutos já baixados e devolve o índice normalizado."""
    raw = settings.raw_dir

    def ler(caminho: str) -> str:
        arquivo = raw / caminho
        if not arquivo.exists():
            raise SyncError(f"arquivo ausente: {arquivo}. Rode `ragleveling sync` primeiro.")
        return arquivo.read_text(encoding="utf-8", errors="replace")

    monstros = parse_mob_db(ler(ARQUIVOS_BASE["mob_db"]))
    skills = parse_mob_skills(ler(ARQUIVOS_BASE["mob_skill_db"]))
    attr_fix = parse_attr_fix(ler(ARQUIVOS_BASE["attr_fix"]))

    spawns: dict[str, list[dict[str, Any]]] = {}
    for caminho in scripts:
        arquivo = raw / caminho
        if not arquivo.exists():
            continue
        _fundir_spawns(spawns, parse_spawns(arquivo.read_text(encoding="utf-8", errors="replace")))

    return {
        "version": VERSAO_INDICE,
        "generated_at": time.time(),
        "monsters": monstros,
        "skills": {str(k): v for k, v in skills.items()},
        "spawns": spawns,
        "attr_fix": {str(k): v for k, v in attr_fix.items()},
    }


def carregar_spawns_extra(caminho: Path) -> dict[str, list[dict[str, Any]]]:
    """Lê o complemento de spawns e devolve no formato do índice.

    O rAthena leva tempo para portar os mapas de episódios recentes: o mapa
    existe no `map_index.txt` e os monstros existem no `mob_db`, mas nenhum
    script declara onde eles nascem. Este arquivo preenche essa lacuna à mão,
    a partir do Divine Pride, e cada spawn daqui fica marcado com `extra`.
    """
    if not caminho.is_file():
        return {}

    dados = yaml.safe_load(caminho.read_text(encoding="utf-8")) or {}
    mapas = dados.get("mapas") or {}
    if not isinstance(mapas, dict):
        raise SyncError(f"{caminho}: `mapas` precisa ser um mapeamento de mapa para spawns")

    por_mob: dict[str, list[dict[str, Any]]] = {}
    for map_id, entrada in mapas.items():
        spawns = (entrada or {}).get("spawns") or []
        for spawn in spawns:
            try:
                mob = int(spawn["monster_id"])
                quantidade = int(spawn["amount"])
            except (KeyError, TypeError, ValueError) as erro:
                raise SyncError(f"{caminho}: spawn inválido em {map_id}: {spawn!r}") from erro
            por_mob.setdefault(str(mob), []).append(
                {
                    "map": str(map_id),
                    "amount": quantidade,
                    "respawn_ms": int(float(spawn.get("respawn_s", 0)) * 1000),
                    "extra": True,
                }
            )
    return por_mob


def carregar_indice(settings: Settings | None = None) -> dict[str, Any]:
    """Lê o índice do cache. Levanta `SyncError` se ainda não existir."""
    settings = settings or get_settings()
    if not settings.index_path.exists():
        raise SyncError(f"índice não encontrado em {settings.index_path}. Rode `ragleveling sync`.")
    dados = json.loads(settings.index_path.read_text(encoding="utf-8"))
    if dados.get("version") != VERSAO_INDICE:
        raise SyncError(
            "índice de uma versão antiga. Rode `ragleveling sync` para reconstruí-lo "
            "(os arquivos já baixados são reaproveitados)."
        )

    # O complemento é aplicado na leitura, não no sync: editar o YAML tem efeito
    # imediato, sem reconstruir o índice.
    for mob, spawns in carregar_spawns_extra(settings.spawns_extra_path).items():
        dados["spawns"].setdefault(mob, []).extend(spawns)
    return dados
