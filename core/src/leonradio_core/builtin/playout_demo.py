"""Reproductor SIMULADO (sin audio) para probar editores, historial y eventos.

Se reemplaza por el motor real en F1. Avanza el reloj, registra cada emisión en
`playlog`, publica `playout.now` / `playout.queue` y emite niveles `audio.levels`
(simulados) para los VU. Los datos de muestra vienen de `data/demo_sample.json`.
"""

from __future__ import annotations

import math
import os
import random
import threading
from typing import Any

from .. import sdk
from ..playlog import now_utc


class DemoPlayout:
    def __init__(self, host: Any) -> None:
        self.host = host
        self._lock = threading.RLock()
        self.speed = float(os.environ.get("LEONRADIO_DEMO_SPEED", "1"))
        self.now: dict | None = None
        self.queue: list[dict] = []
        self._started_at: str | None = None
        self._phase = 0.0
        self._lvl = [0.0, 0.0]
        self.aux: list = []          # listas auxiliares (AuxDemo), las crea builtin.register

    # -- carga de cola -------------------------------------------------------
    def _build_queue(self) -> list[dict]:
        with self.host.db_lock:
            rows = self.host.db.execute(
                "SELECT id, kind, title, artist, duration_ms FROM assets "
                "WHERE status='active' AND kind IN ('music','jingle','separador','pisador')").fetchall()
        items = [dict(r) | {"duration_ms": r["duration_ms"] or 30000} for r in rows]
        if not items:
            return [dict(s) for s in sdk.load_json("demo_sample.json")]
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

    def fire_cart(self, asset_id: int) -> dict:
        """Dispara una pieza de la cartuchera (simulado: queda registrada como emisión `cart`)."""
        with self.host.db_lock:
            row = self.host.db.execute("SELECT title, duration_ms FROM assets WHERE id = ?", (asset_id,)).fetchone()
        if row is None:
            raise ValueError(f"asset {asset_id} no existe")
        self.host.record_play(asset_id=asset_id, source="cart", output="all",
                              played_ms=row["duration_ms"], ended_at=now_utc())
        self.host.set_state("cart.last", {"title": row["title"], "at": now_utc()})
        return {"title": row["title"]}

    def add_to(self, target: str, asset_id: int) -> dict:
        """Agrega una pieza de la biblioteca a la emisión (`emision`) o a una auxiliar (`aux1`…`aux4`)."""
        with self.host.db_lock:
            row = self.host.db.execute(
                "SELECT id, kind, title, artist, duration_ms FROM assets WHERE id = ?", (asset_id,)).fetchone()
        if row is None:
            raise ValueError(f"asset {asset_id} no existe")
        item = dict(row) | {"duration_ms": row["duration_ms"] or 30000}
        if target == "emision":
            with self._lock:
                self.queue.append(item)
                self._publish()
        elif target.startswith("aux") and target[3:].isdigit() and 1 <= int(target[3:]) <= len(self.aux):
            self.aux[int(target[3:]) - 1].add(item)
        else:
            raise ValueError(f"destino desconocido: {target}")
        return {"title": item["title"], "target": target}

    # -- niveles simulados -----------------------------------------------------
    def _levels(self, seconds: float) -> tuple[float, float]:
        playing = bool(self.now) and not self.now["paused"]
        self._phase += seconds
        out = []
        for ch in (0, 1):
            if playing:
                beat = 0.5 + 0.5 * math.sin(self._phase * (5.0 + ch * 0.7))
                target = 0.30 + 0.45 * beat * (0.6 + 0.4 * random.random()) + 0.1 * random.random()
            else:
                target = 0.0
            self._lvl[ch] += (target - self._lvl[ch]) * 0.45
            out.append(round(min(1.0, self._lvl[ch]), 3))
        return out[0], out[1]

    def tick(self, seconds: float = 0.1) -> None:
        for a in self.aux:
            a.tick(seconds, self.speed)
        with self._lock:
            lv_l, lv_r = self._levels(seconds)
            self.host.events.emit("audio.levels", {"l": lv_l, "r": lv_r, "simulated": True})
            if not self.now or self.now["paused"]:
                return
            before = int(self.now["elapsed_ms"] // 1000)
            self.now["elapsed_ms"] += int(seconds * 1000 * self.speed)
            if self.now["elapsed_ms"] >= self.now["duration_ms"]:
                self.now["elapsed_ms"] = self.now["duration_ms"]
                self.next("completed")
            elif int(self.now["elapsed_ms"] // 1000) != before:  # publicar 1 vez por segundo
                self.host.set_state("playout.now", dict(self.now))
