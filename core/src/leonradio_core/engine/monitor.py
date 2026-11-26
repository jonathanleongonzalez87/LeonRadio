"""Monitoreo remoto: reparte la mezcla principal (PCM de 16 bits) a los navegadores que la escuchan por WebSocket.

El hilo de audio solo llama a `feed`; si nadie escucha, no hace nada. Cada oyente tiene una cola acotada: si un
dispositivo va lento se descartan bloques viejos (el retraso nunca crece más de ~1 s).
"""

from __future__ import annotations

import asyncio
import threading

import numpy as np

MAX_QUEUED = 40            # bloques por oyente (~1 s con bloques de 1024 fotogramas)


class MonitorHub:
    def __init__(self) -> None:
        self._clients: list[tuple[asyncio.Queue, asyncio.AbstractEventLoop]] = []
        self._lock = threading.Lock()

    @property
    def listeners(self) -> int:
        return len(self._clients)

    def add(self, queue: asyncio.Queue, loop: asyncio.AbstractEventLoop) -> None:
        with self._lock:
            self._clients.append((queue, loop))

    def remove(self, queue: asyncio.Queue) -> None:
        with self._lock:
            self._clients = [c for c in self._clients if c[0] is not queue]

    def feed(self, mix: np.ndarray) -> None:
        """Hilo de audio: copia el bloque a cada oyente. Rápido y sin bloquear."""
        if not self._clients:
            return
        data = (np.clip(mix, -1.0, 1.0) * 32767).astype("<i2").tobytes()
        with self._lock:
            clients = list(self._clients)
        for queue, loop in clients:
            try:
                loop.call_soon_threadsafe(self._push, queue, data)
            except RuntimeError:                  # el bucle del servidor ya se cerró
                self.remove(queue)

    @staticmethod
    def _push(queue: asyncio.Queue, data: bytes) -> None:
        if queue.qsize() >= MAX_QUEUED:
            try:
                queue.get_nowait()
            except asyncio.QueueEmpty:
                pass
        queue.put_nowait(data)
