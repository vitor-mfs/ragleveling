"""Configuração: diretórios de cache e credenciais lidas do ambiente."""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

RATHENA_RAW_BASE = "https://raw.githubusercontent.com/rathena/rathena/master"

#: Arquivos-base do rAthena. Os scripts de spawn são descobertos a partir dos
#: dois `scripts_monsters.conf`, que listam os arquivos realmente carregados.
ARQUIVOS_BASE: dict[str, str] = {
    "mob_db": "db/re/mob_db.yml",
    "mob_skill_db": "db/re/mob_skill_db.txt",
    "attr_fix": "db/re/attr_fix.yml",
    "scripts_re": "npc/re/scripts_monsters.conf",
    "scripts_pre": "npc/scripts_monsters.conf",
}

DIVINE_PRIDE_BASE_URL = "https://www.divine-pride.net"
DEFAULT_SERVER = "bRO"


def url_divine_pride(monster_id: int) -> str:
    """Página do monstro no Divine Pride — onde ver drops, sprite e detalhes."""
    return f"{DIVINE_PRIDE_BASE_URL}/database/monster/{monster_id}"

"""O cliente LATAM usa a base publicada como bRO no Divine Pride."""


def _cache_dir_padrao() -> Path:
    env = os.environ.get("RAGLEVELING_CACHE_DIR")
    if env:
        return Path(env).expanduser()
    xdg = os.environ.get("XDG_CACHE_HOME")
    base = Path(xdg).expanduser() if xdg else Path.home() / ".cache"
    return base / "ragleveling"


@dataclass(frozen=True)
class Settings:
    """Configuração efetiva do processo."""

    cache_dir: Path
    divine_pride_api_key: str | None = None
    divine_pride_server: str = DEFAULT_SERVER
    divine_pride_rate_limit: float = 1.0
    """A API do Divine Pride aceita no máximo 1 requisição por segundo."""
    http_timeout: float = 30.0
    user_agent: str = "ragleveling/0.1 (+https://github.com/vitor-mfs/ragleveling)"

    @property
    def raw_dir(self) -> Path:
        """Arquivos do rAthena como vieram da rede."""
        return self.cache_dir / "rathena"

    @property
    def index_path(self) -> Path:
        """Índice normalizado gerado a partir dos arquivos brutos."""
        return self.cache_dir / "index.json"

    @property
    def spawns_extra_path(self) -> Path:
        """Complemento de spawns que o rAthena ainda não tem.

        Procura `./data/spawns_extra.yaml` a partir do diretório atual e cai no
        arquivo que acompanha o projeto.
        """
        env = os.environ.get("RAGLEVELING_SPAWNS_EXTRA")
        if env:
            return Path(env).expanduser()
        local = Path.cwd() / "data" / "spawns_extra.yaml"
        if local.is_file():
            return local
        return Path(__file__).resolve().parents[2] / "data" / "spawns_extra.yaml"

    @property
    def dp_cache_path(self) -> Path:
        """Cache das respostas do Divine Pride."""
        return self.cache_dir / "divinepride.json"

    @classmethod
    def from_env(cls) -> Settings:
        return cls(
            cache_dir=_cache_dir_padrao(),
            divine_pride_api_key=os.environ.get("DIVINE_PRIDE_API_KEY") or None,
            divine_pride_server=os.environ.get("RAGLEVELING_DP_SERVER", DEFAULT_SERVER),
        )


_settings: Settings | None = None


def get_settings() -> Settings:
    global _settings
    if _settings is None:
        _settings = Settings.from_env()
    return _settings


def set_settings(settings: Settings) -> None:
    """Sobrescreve a configuração global (usado em testes e na CLI)."""
    global _settings
    _settings = settings
