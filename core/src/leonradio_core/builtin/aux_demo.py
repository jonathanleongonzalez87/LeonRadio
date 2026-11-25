"""Listas Auxiliares (4) SIMULADAS: cada una con su cola y su transporte (play, pausa, stop, siguiente).

Como el reproductor principal, avanzan el reloj pero no emiten audio hasta F1.
"""

from __future__ import annotations

import threading
from typing import Any

N_AUX = 4


class AuxDemo:
    def __init__(self, host: Any, n: int) -> None:
        self.host, self.n = host, n
        self._lock = threading.RLock()
        self.queue: list[dict] = []
        self.now: dict | None = None
        self.playing = False

    @property
    def key(self) -> str:
        return f"aux.{self.n}"

    def publish(self) -> None:
        self.host.set_state(self.key, {"now": dict(self.now) if self.now else None,
                                       "queue": list(self.queue), "playing": self.playing})

    def add(self, item: dict) -> None:
        with self._lock:
            self.queue.append(item)
            self.publish()

    def _load_next(self) -> None:
        if self.queue:
            self.now = self.queue.pop(0) | {"elapsed_ms": 0}
        else:
            self.now, self.playing = None, False

    def play(self) -> None:
        with self._lock:
            if self.now is None:
                self._load_next()
            self.playing = self.now is not None
            self.publish()

    def pause(self) -> None:
        with self._lock:
            self.playing = False
            self.publish()

    def stop(self) -> None:
        with self._lock:
            self.playing = False
            if self.now:
                self.now["elapsed_ms"] = 0
            self.publish()

    def next(self) -> None:
        with self._lock:
            was_playing = self.playing
            self._load_next()
            self.playing = was_playing and self.now is not None
            self.publish()

    def clear(self) -> None:
        with self._lock:
            self.queue.clear()
            self.publish()

    def tick(self, seconds: float, speed: float = 1.0) -> None:
        with self._lock:
            if not (self.playing and self.now):
                return
            before = int(self.now["elapsed_ms"] // 1000)
            self.now["elapsed_ms"] += int(seconds * 1000 * speed)
            if self.now["elapsed_ms"] >= self.now["duration_ms"]:
                self.next()
            elif int(self.now["elapsed_ms"] // 1000) != before:   # publicar 1 vez por segundo
                self.publish()
