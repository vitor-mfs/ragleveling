"""Carga do catálogo (monstros, mapas e tabela de EXP por nível) a partir de YAML."""

from __future__ import annotations

from pathlib import Path

import yaml
from pydantic import BaseModel, Field

from .models import GameMap, Monster


class Catalog(BaseModel):
    """Tudo que a rota precisa saber sobre o mundo."""

    monsters: dict[int, Monster] = Field(default_factory=dict)
    maps: list[GameMap] = Field(default_factory=list)
    exp_table: dict[int, int] = Field(default_factory=dict)
    """nível -> EXP base necessária para sair DESSE nível para o próximo."""

    def monster(self, monster_id: int) -> Monster | None:
        return self.monsters.get(monster_id)

    def exp_para_subir(self, level: int) -> int | None:
        return self.exp_table.get(level)


def carregar(caminho: str | Path) -> Catalog:
    """Lê um YAML de catálogo. Aceita um arquivo único ou um diretório de YAMLs."""
    caminho = Path(caminho)
    arquivos = sorted(caminho.glob("*.yaml")) + sorted(caminho.glob("*.yml")) if caminho.is_dir() else [caminho]
    if not arquivos:
        raise FileNotFoundError(f"nenhum YAML encontrado em {caminho}")

    monsters: dict[int, Monster] = {}
    maps: list[GameMap] = []
    exp_table: dict[int, int] = {}

    for arquivo in arquivos:
        dados = yaml.safe_load(arquivo.read_text(encoding="utf-8")) or {}
        if not isinstance(dados, dict):
            raise ValueError(f"{arquivo}: o YAML precisa ser um mapeamento no topo")

        for bruto in dados.get("monsters", []) or []:
            monstro = Monster.model_validate(bruto)
            monsters[monstro.id] = monstro

        for bruto in dados.get("maps", []) or []:
            maps.append(GameMap.model_validate(bruto))

        for nivel, exp in (dados.get("exp_table", {}) or {}).items():
            exp_table[int(nivel)] = int(exp)

    faltando = {
        spawn.monster_id
        for mapa in maps
        for spawn in mapa.spawns
        if spawn.monster_id not in monsters
    }
    if faltando:
        ids = ", ".join(str(i) for i in sorted(faltando))
        raise ValueError(f"spawns apontam para monstros ausentes do catálogo: {ids}")

    return Catalog(monsters=monsters, maps=maps, exp_table=exp_table)
