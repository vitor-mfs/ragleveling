"""Ranking de spots e montagem da rota de level up."""

from __future__ import annotations

from .catalog import Catalog
from .exp import exp_por_kill, exp_rate, kills_por_hora
from .models import Character, RouteLeg, ServerRates, Spot


def avaliar_spots(
    catalog: Catalog,
    char: Character,
    rates: ServerRates | None = None,
    crowding: float = 1.0,
    tabela_penalidade: dict[int, float] | None = None,
    criterio: str = "base",
) -> list[Spot]:
    """Todos os pares mapa+monstro viáveis para o personagem, do melhor para o pior.

    `criterio` decide a ordenação: "base", "job" ou "total".
    """
    if criterio not in {"base", "job", "total"}:
        raise ValueError("criterio precisa ser 'base', 'job' ou 'total'")

    spots: list[Spot] = []
    for mapa in catalog.maps:
        for spawn in mapa.spawns:
            monstro = catalog.monster(spawn.monster_id)
            if monstro is None or monstro.mvp:
                continue
            diff = monstro.level - char.base_level
            if diff > char.max_level_gap:
                continue

            ritmo, limitado = kills_por_hora(
                monstro,
                char,
                spawn_amount=spawn.amount,
                respawn_seconds=spawn.respawn_seconds,
                crowding=crowding,
            )
            base, job = exp_por_kill(monstro, char, rates, tabela_penalidade)
            spots.append(
                Spot(
                    map_id=mapa.id,
                    map_name=mapa.name,
                    monster_id=monstro.id,
                    monster_name=monstro.name,
                    monster_level=monstro.level,
                    level_diff=diff,
                    exp_rate=exp_rate(diff, tabela_penalidade),
                    kills_per_hour=ritmo,
                    base_exp_per_hour=base * ritmo,
                    job_exp_per_hour=job * ritmo,
                    limited_by_respawn=limitado,
                )
            )

    return sorted(spots, key=lambda s: _peso(s, criterio), reverse=True)


def _peso(spot: Spot, criterio: str) -> float:
    if criterio == "base":
        return spot.base_exp_per_hour
    if criterio == "job":
        return spot.job_exp_per_hour
    return spot.base_exp_per_hour + spot.job_exp_per_hour


def montar_rota(
    catalog: Catalog,
    char: Character,
    até_o_nivel: int,
    rates: ServerRates | None = None,
    crowding: float = 1.0,
    tabela_penalidade: dict[int, float] | None = None,
    criterio: str = "base",
    histerese: float = 0.10,
) -> list[RouteLeg]:
    """Rota do nível atual até `até_o_nivel`, um trecho por troca de spot.

    A cada nível o melhor spot é recalculado, mas só se troca de lugar quando o
    novo ganha do atual por mais que `histerese` (padrão 10%) — evita uma rota
    que manda você trocar de mapa a cada nível por 1% de EXP.

    `hours` só é preenchido quando o catálogo traz `exp_table`.
    """
    if até_o_nivel <= char.base_level:
        raise ValueError("o nível alvo precisa ser maior que o nível atual")
    if not 0 <= histerese < 10:
        raise ValueError("histerese precisa estar em [0, 10)")

    pernas: list[RouteLeg] = []
    atual: Spot | None = None

    for nivel in range(char.base_level, até_o_nivel):
        no_nivel = char.model_copy(update={"base_level": nivel})
        candidatos = avaliar_spots(catalog, no_nivel, rates, crowding, tabela_penalidade, criterio)
        if not candidatos:
            raise ValueError(f"nenhum spot viável no nível {nivel}: revise o catálogo ou max_level_gap")

        melhor = candidatos[0]
        if atual is not None:
            mesmo = next(
                (s for s in candidatos if s.map_id == atual.map_id and s.monster_id == atual.monster_id),
                None,
            )
            if mesmo is not None and _peso(melhor, criterio) < _peso(mesmo, criterio) * (1 + histerese):
                melhor = mesmo

        horas = _horas_do_nivel(catalog, nivel, melhor, criterio)

        anterior = pernas[-1] if pernas else None
        if (
            anterior is not None
            and anterior.spot.map_id == melhor.map_id
            and anterior.spot.monster_id == melhor.monster_id
        ):
            anterior.to_level = nivel + 1
            if anterior.hours is not None and horas is not None:
                anterior.hours += horas
            else:
                anterior.hours = None
        else:
            pernas.append(RouteLeg(from_level=nivel, to_level=nivel + 1, spot=melhor, hours=horas))

        atual = melhor

    return pernas


def _horas_do_nivel(catalog: Catalog, nivel: int, spot: Spot, criterio: str) -> float | None:
    necessaria = catalog.exp_para_subir(nivel)
    if necessaria is None:
        return None
    por_hora = spot.job_exp_per_hour if criterio == "job" else spot.base_exp_per_hour
    if por_hora <= 0:
        return None
    return necessaria / por_hora
