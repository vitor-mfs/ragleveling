"""Configuração: diretórios de cache e credenciais lidas do ambiente."""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

DIVINE_PRIDE_BASE_URL = "https://www.divine-pride.net"

DEFAULT_SERVER = "LATAM"
"""Região consultada no Divine Pride, enviada no header `x-server`.

Aliases válidos: bRO, cRO, dpRO, idRO, GGH, GZero, iRO, jRO, kROM, kROZ, LATAM,
ropEU, ropRU, thROC, thROG, twRO, twROZ. Sem o header, o padrão da API é kROM.
"""

DEFAULT_LANGUAGE = "pt"
"""Idioma dos nomes, enviado no header `Accept-Language`.

Valores aceitos: en, ko, ja, pt, ru, fr, de, es, th, cn.
"""


def url_divine_pride(monster_id: int) -> str:
    """Página do monstro no Divine Pride — onde ver drops, sprite e detalhes."""
    return f"{DIVINE_PRIDE_BASE_URL}/database/monster/{monster_id}"


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
    divine_pride_language: str = DEFAULT_LANGUAGE
    divine_pride_rate_limit: float = 1.5
    """Intervalo entre requisições ao Divine Pride, em segundos.

    A documentação fala em 1 req/s, mas na prática exatamente 1,0 s ainda leva
    429 — daí a folga. Ajustável por `RAGLEVELING_DP_RATE`.
    """
    http_timeout: float = 30.0
    user_agent: str = "ragleveling/0.1 (+https://github.com/vitor-mfs/ragleveling)"

    @property
    def index_path(self) -> Path:
        """O índice de monstros, montado por `ragleveling dp-index`."""
        return self.cache_dir / "index-dp.json"

    @classmethod
    def from_env(cls) -> Settings:
        return cls(
            cache_dir=_cache_dir_padrao(),
            divine_pride_api_key=os.environ.get("DIVINE_PRIDE_API_KEY") or None,
            divine_pride_server=os.environ.get("RAGLEVELING_DP_SERVER", DEFAULT_SERVER),
            divine_pride_language=os.environ.get("RAGLEVELING_DP_LANG", DEFAULT_LANGUAGE),
            divine_pride_rate_limit=float(os.environ.get("RAGLEVELING_DP_RATE", 1.5)),
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
