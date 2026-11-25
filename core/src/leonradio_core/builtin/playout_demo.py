"""Reproductor SIMULADO (sin audio) para probar editores, historial y eventos.

Se reemplaza por el motor real en F1. Avanza el reloj, registra cada emisión en
`playlog` y publica el estado en `playout.now` / `playout.queue`.
"""

from __future__ import annotations

import os
import random
import threading
from typing import Any

from ..playlog import now_utc

SAMPLE = [
    {"id": None, "kind": "jingle", "title": "RRC Jingle 1", "artist": "Rockland Radio", "duration_ms": 8000},
    {"id": None, "kind": "music", "title": "Muestra A", "artist": "Artista A", "duration_ms": 30000},
    {"id": None, "kind": "music", "title": "Muestra B", "artist": "Artista B", "duration_ms": 30000},
]


class DemoPlayout:
    def __init__(self, host: Any) -> None:
        self.host = host
        self._lock = threading.RLock()
        self.speed = float(os.environ.get("LEONRADIO_DEMO_SPEED", "1"))
        self.now: dict | None = None
        self.queue: list[dict] = []
        self._started_at: str | None = None

    # -- carga de cola -------------------------------------------------------
    def _build_queue(self) -> list[dict]:
        with self.host.db_lock:
            rows = self.host.db.execute(
                "SELECT id, kind, title, artist, duration_ms FROM assets "
                "WHERE status='active' AND kind IN ('music','jingle','separador','pisador')").fetchall()
        items = [dict(r) | {"duration_ms": r["duration_ms"] or 30000} for r in rows]
        if not items:
            return [dict(s) for s in SAMPLE]
        music = [i for i in items if i["kind"] == "music"]
        fillers = [i for i in items if i["kind"] in ("jingle", "separador")]
        random.shuffle(music)
        out: list[dict] = []
        for n, m in enumerate(music):
            out.append(m)
            if fillers and n % 3 == 2:
                out.append(random.choice(fillers))
        return out or items

    def start(self) -> None:
        with self._lock:
            self.queue = self._build_queue()
            self._load_next()

    # -- ciclo ---------------------------------------------------------------
    def _load_next(self) -> None:
        if not self.queue:
            self.queue = self._build_queue()
        item = self.queue.pop(0)
        self.now = item | {"elapsed_ms": 0, "paused": False}
        self._started_at = now_utc()
        self._publish()

    def _publish(self) -> None:
        self.host.set_state("playout.now", dict(self.now) if self.now else None)
        self.host.set_state("playout.queue", list(self.queue))

    def _log_current(self, status: str) -> None:
        if not self.now:
            return
        self.host.record_play(
            asset_id=self.now.get("id"), started_at=self._started_at, ended_at=now_utc(),
            played_ms=int(self.now["elapsed_ms"]), status=status, source="auto", output="all",
            **({} if self.now.get("id") else {k: self.now[k] for k in ("kind", "title", "artist")}),
        )

    def next(self, status: str = "completed") -> None:
        with self._lock:
            self._log_current(status)
            self._load_next()

    def toggle_pause(self) -> None:
        with self._lock:
            if self.now:
                self.now["paused"] = not self.now["paused"]
                self._publish()

    def tick(self, seconds: float = 1.0) -> None:
        with self._lock:
            if not self.now or self.now["paused"]:
                return
            self.now["elapsed_ms"] += int(seconds * 1000 * self.speed)
            if self.now["elapsed_ms"] >= self.now["duration_ms"]:
                self.now["elapsed_ms"] = self.now["duration_ms"]
                self.next("completed")
            else:
                self.host.set_state("playout.now", dict(self.now))
