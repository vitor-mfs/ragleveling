"""Limitador de taxa: a API do Divine Pride aceita 1 requisição por segundo.

Só as chamadas que realmente vão à rede passam por aqui — resposta em cache não
espera nada.
"""

from __future__ import annotations

import threading
import time
from collections.abc import Callable


class RateLimiter:
    """Garante um intervalo mínimo entre operações.

    `sleep` e `monotonic` são injetáveis para os testes não esperarem de verdade.
    """

    def __init__(
        self,
        min_interval: float,
        *,
        sleep: Callable[[float], None] = time.sleep,
        monotonic: Callable[[], float] = time.monotonic,
    ) -> None:
        self.min_interval = max(0.0, min_interval)
        self._sleep = sleep
        self._monotonic = monotonic
        self._lock = threading.Lock()
        self._proxima = 0.0

    def acquire(self) -> float:
        """Bloqueia até a próxima chamada ser permitida. Devolve quanto esperou."""
        if self.min_interval <= 0:
            return 0.0
        with self._lock:
            agora = self._monotonic()
            espera = self._proxima - agora
            if espera > 0:
                self._sleep(espera)
                agora = self._proxima
            else:
                espera = 0.0
            self._proxima = agora + self.min_interval
        return espera
