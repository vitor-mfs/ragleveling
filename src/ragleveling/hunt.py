"""O fluxo principal: nível + classe -> monstros, mapas e elemento a usar.

1. filtra os monstros da faixa de nível que interessa ao seu base level;
2. descarta chefes, MVPs e quem não nasce em mapa normal;
3. ranqueia por dificuldade (ver `difficulty.py`), do mais fácil ao mais difícil;
4. diz onde cada um nasce e qual elemento usar contra ele.

Tudo sobre o índice do Divine Pride (`dp_index.carregar`): a EXP usa a tabela
de penalidade do próprio monstro e o elemento vem da resistência dele.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any

from .config import url_divine_pride
from .difficulty import Dificuldade, Pesos, calcular
from .elements import ELEMENTO_PT, RACA_PT, TAMANHO_PT, pt, ranking_por_resistencia
from .exp import exp_rate, exp_rate_do_monstro
from .jobs import Perfil, como_aplicar_elemento, perfil_de

#: Faixa padrão: do -5 (sem penalidade) ao +15 (bônus máximo de 150%).
FAIXA_PADRAO = (-5, 15)

#: Mapas de instância/memorial não servem para farm aberto.
_MAPA_INSTANCIA = re.compile(r"@")

#: Mapas onde não se upa: baús de WoE, castelos, provas de classe, arenas,
#: mapas de quest e áreas de GM. Desligável com `--todos-mapas`.
_MAPA_BLOQUEADO = re.compile(
    r"^(treasure|.*g_cas|nguild_|gld_|gld2_|job_|jobtest|ordeal|quiz|arena|poring_w|"
    r"pvp_|guild_vs|force_|sec_pri|sec_in|new_\d|e_tower|dicastes0[12]_|que_)",
    re.IGNORECASE,
)

#: Abaixo disso o mapa é mob raro, não ponto de farm.
MIN_SPAWN_PADRAO = 5


@dataclass
class SpawnInfo:
    map_id: str
    amount: int
    respawn_ms: int

    @property
    def respawn_s(self) -> float:
        return self.respawn_ms / 1000.0


@dataclass
class Alvo:
    """Um monstro recomendado, com tudo que a saída precisa mostrar."""

    id: int
    name: str
    level: int
    level_diff: int
    exp_rate: float
    base_exp: int
    job_exp: int
    hp: int
    defense: int
    magic_defense: int
    attack: int
    race: str
    element: str
    element_level: int
    size: str
    dificuldade: Dificuldade
    spawns: list[SpawnInfo]
    elemento_sugerido: tuple[str, int]
    elementos_a_evitar: list[tuple[str, int]]
    como_aplicar: str

    @property
    def url(self) -> str:
        """Página deste monstro no Divine Pride."""
        return url_divine_pride(self.id)

    @property
    def exp_efetiva(self) -> float:
        """EXP base por kill já com a penalidade/bônus de nível."""
        return self.base_exp * self.exp_rate

    @property
    def elemento_pt(self) -> str:
        return f"{pt(self.element, ELEMENTO_PT)} {self.element_level}"

    @property
    def raca_pt(self) -> str:
        return pt(self.race, RACA_PT)

    @property
    def tamanho_pt(self) -> str:
        return pt(self.size, TAMANHO_PT)

    @property
    def mapa_principal(self) -> SpawnInfo | None:
        """O mapa com mais exemplares — onde faz sentido ir."""
        return max(self.spawns, key=lambda s: s.amount) if self.spawns else None


def _spawns_validos(
    bruto: list[dict[str, Any]],
    *,
    incluir_instancias: bool,
    todos_mapas: bool,
    min_spawn: int,
) -> list[SpawnInfo]:
    spawns = []
    for item in bruto:
        map_id = item.get("map", "")
        if not incluir_instancias and _MAPA_INSTANCIA.search(map_id):
            continue
        if not todos_mapas and _MAPA_BLOQUEADO.match(map_id):
            continue
        quantidade = int(item.get("amount", 0))
        if quantidade < min_spawn:
            continue
        spawns.append(SpawnInfo(map_id=map_id, amount=quantidade, respawn_ms=int(item.get("respawn_ms", 0))))
    return sorted(spawns, key=lambda s: s.amount, reverse=True)


def cacar(
    indice: dict[str, Any],
    base_level: int,
    classe: str | None = None,
    *,
    perfil: Perfil | None = None,
    faixa: tuple[int, int] = FAIXA_PADRAO,
    limite: int = 20,
    ordenar_por: str = "dificuldade",
    incluir_instancias: bool = False,
    todos_mapas: bool = False,
    min_spawn: int = MIN_SPAWN_PADRAO,
    pesos: Pesos | None = None,
) -> list[Alvo]:
    """Monstros recomendados para `base_level`, do mais fácil ao mais difícil.

    `classe` é a chave já canônica do rAthena (use `jobs.canonical_job_key`).
    `perfil` sobrescreve o perfil de dano da classe. `min_spawn` descarta mapas
    onde o monstro é raro demais para render farm.
    """
    if base_level < 1:
        raise ValueError("o base level precisa ser 1 ou mais")
    if faixa[0] > faixa[1]:
        raise ValueError("faixa inválida: o mínimo é maior que o máximo")
    if ordenar_por not in {"dificuldade", "exp", "nivel"}:
        raise ValueError("ordenar_por precisa ser 'dificuldade', 'exp' ou 'nivel'")

    perfil_efetivo = perfil or (perfil_de(classe) if classe else Perfil.MELEE)
    spawns_brutos = indice.get("spawns", {})
    skills = indice.get("skills", {})

    minimo, maximo = base_level + faixa[0], base_level + faixa[1]
    candidatos: list[dict[str, Any]] = []
    spawns_por_mob: dict[int, list[SpawnInfo]] = {}

    for monstro in indice.get("monsters", []):
        nivel = monstro.get("level")
        if monstro.get("boss") or not nivel or not monstro.get("base_exp"):
            continue
        if not minimo <= nivel <= maximo:
            continue
        spawns = _spawns_validos(
            spawns_brutos.get(str(monstro["id"]), []),
            incluir_instancias=incluir_instancias,
            todos_mapas=todos_mapas,
            min_spawn=min_spawn,
        )
        if not spawns:
            continue
        candidatos.append(monstro)
        spawns_por_mob[int(monstro["id"])] = spawns

    dificuldades = calcular(candidatos, skills, perfil_efetivo, pesos)

    alvos: list[Alvo] = []
    for monstro in candidatos:
        mob_id = int(monstro["id"])
        elemento = monstro.get("element", "Neutral")
        nivel_elemento = int(monstro.get("element_level") or 1)

        ranking = ranking_por_resistencia(monstro.get("resist"))
        melhor, pct = ranking[0]
        piores = list(reversed(ranking))[:2]
        melhor_pt = pt(melhor, ELEMENTO_PT)
        diff = int(monstro["level"]) - base_level

        # A tabela do próprio monstro é a do servidor; a genérica só entra sem ela.
        taxa = exp_rate_do_monstro(monstro.get("exp_table"), base_level)
        if taxa is None:
            taxa = exp_rate(diff)

        alvos.append(
            Alvo(
                id=mob_id,
                name=monstro.get("name", ""),
                level=int(monstro["level"]),
                level_diff=diff,
                exp_rate=taxa,
                base_exp=int(monstro.get("base_exp") or 0),
                job_exp=int(monstro.get("job_exp") or 0),
                hp=int(monstro.get("hp") or 0),
                defense=int(monstro.get("defense") or 0),
                magic_defense=int(monstro.get("magic_defense") or 0),
                attack=int(monstro.get("attack") or 0),
                race=monstro.get("race", "Formless"),
                element=elemento,
                element_level=nivel_elemento,
                size=monstro.get("size", "Medium"),
                dificuldade=dificuldades[mob_id],
                spawns=spawns_por_mob[mob_id],
                elemento_sugerido=(melhor_pt, pct),
                elementos_a_evitar=[(pt(e, ELEMENTO_PT), p) for e, p in piores],
                como_aplicar=como_aplicar_elemento(classe, melhor_pt) if classe else f"dano de {melhor_pt}",
            )
        )

    chaves = {
        "dificuldade": lambda a: (a.dificuldade.score, -a.exp_efetiva),
        "exp": lambda a: -a.exp_efetiva,
        "nivel": lambda a: (a.level, a.dificuldade.score),
    }
    alvos.sort(key=chaves[ordenar_por])
    return alvos[:limite]
