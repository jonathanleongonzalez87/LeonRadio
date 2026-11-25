"""Deck: una lista de ficheros con su transporte y la lógica de segue / crossfade.

La Emisión y cada Auxiliar son un Deck. Un Deck NO toca la base de datos ni la red: avisa de lo que ocurre
(`notify`) y el Playout lo registra. Así puede ejecutarse dentro del hilo de audio sin bloquearse.
"""

from __future__ import annotations

import time
from datetime import datetime, timezone
from typing import Any, Callable

import numpy as np

from .files import AUDIO, EVENT
from .sources import SAMPLE_RATE as SR
from .sources import SilenceSource, Source

Notify = Callable[[str, str, dict], None]          # (deck, tipo, datos)
Loader = Callable[[dict, bool], "Source | None"]   # (fichero, bloquear) -> fuente | None si aún carga


class LoadError(Exception):
    """El fichero no se pudo preparar (no existe, no se decodifica…)."""


class Play:
    """Un fichero en reproducción, con sus rampas de entrada y salida (equal-power)."""

    def __init__(self, item: dict, source: Source, fade_in: int = 0) -> None:
        self.item, self.source, self.pos, self.fade_in = item, source, 0, int(fade_in)
        self.out_start: int | None = None
        self.out_len = 0
        self.status = "completed"
        self.started = time.time()
        self.released = False

    @property
    def played_ms(self) -> int:
        return int(self.pos * 1000 / SR)

    def gain(self, n: int) -> np.ndarray | None:
        g = None
        if self.pos < self.fade_in:
            t = (self.pos + np.arange(n)) / max(1, self.fade_in)
            g = np.sin(np.clip(t, 0, 1) * np.pi / 2)
        if self.out_start is not None:
            t = (self.pos + np.arange(n) - self.out_start) / max(1, self.out_len)
            go = np.cos(np.clip(t, 0, 1) * np.pi / 2)
            g = go if g is None else g * go
        return g

    def fade_done(self) -> bool:
        return self.out_start is not None and self.pos >= self.out_start + self.out_len


class Deck:
    def __init__(self, name: str, loader: Loader, notify: Notify, crossfade_ms: int = 3000,
                 clock: Callable[[], datetime] | None = None) -> None:
        self.name, self.loader, self.notify = name, loader, notify
        self.crossfade_ms = crossfade_ms
        self.clock = clock or (lambda: datetime.now(timezone.utc))
        self.queue: list[dict] = []
        self.current: Play | None = None
        self.fading: list[Play] = []
        self.playing = False
        self._gate = 0.0

    # ---------------------------------------------------------------- lista
    def add(self, item: dict, index: int | None = None) -> None:
        if index is None:
            self.queue.append(item)
        else:
            self.queue.insert(index, item)

    def remove(self, uid: str) -> bool:
        for i, it in enumerate(self.queue):
            if it["uid"] == uid:
                del self.queue[i]
                return True
        return False

    def clear(self) -> None:
        self.queue.clear()

    # ---------------------------------------------------------------- transporte
    def play(self, block: bool = True) -> None:
        self.playing = True
        if self.current is None and self.queue:
            self._start_next(0, block)

    def pause(self) -> None:
        self.playing = False

    def toggle(self, block: bool = True) -> None:
        self.pause() if self.playing else self.play(block)

    def stop(self) -> None:
        """Detiene y deja el fichero actual al inicio de la lista."""
        self.playing = False
        if self.current is not None:
            item = self.current.item
            self._end(self.current, "interrupted")
            self.current = None
            self.queue.insert(0, item)
        for p in self.fading:
            self._end(p, p.status)
        self.fading.clear()

    def skip(self, block: bool = True, fade_ms: int = 300) -> None:
        """Pasa al siguiente con un fundido corto (sin cortes secos)."""
        cur = self.current
        if cur is None:
            self.play(block)
            return
        ov = int(fade_ms * SR / 1000)
        cur.status = "skipped"
        if self.queue and self._start_next(ov, block):
            return
        if self.current is cur:          # no hay siguiente: solo se apaga el actual
            cur.out_start, cur.out_len = cur.pos, ov
            self.fading.append(cur)
            self.current = None

    # ---------------------------------------------------------------- lógica de lista
    def _overlap(self, cur: Play, nxt: dict) -> int:
        """Fotogramas de superposición entre `cur` y el siguiente fichero."""
        if cur.item["file"] != AUDIO or nxt["file"] != AUDIO:
            return 0
        dur = cur.source.duration_frames or 0
        outro = cur.item.get("outro_ms")
        if outro:                                    # la marca de salida manda: el siguiente entra ahí
            ov = dur - int(outro * SR / 1000)
        elif cur.item["kind"] == "music" and nxt["kind"] == "music":
            ov = int(self.crossfade_ms * SR / 1000)  # crossfade por defecto entre canciones
        else:
            ov = 0                                   # jingles, pisadores…: sin superposición
        nxt_frames = int(nxt["duration_ms"] * SR / 1000)
        return max(0, min(ov, dur // 2, nxt_frames // 2))

    def _start_next(self, ov: int, block: bool) -> bool:
        """Arranca el siguiente fichero reproducible. `ov` > 0: entra superpuesto al actual."""
        for _ in range(500):                          # tope de seguridad con muchos eventos seguidos
            if not self.queue:
                break
            item = self.queue[0]
            if item["file"] == AUDIO:
                try:
                    src = self.loader(item, block)
                except LoadError as exc:
                    self.queue.pop(0)
                    self.notify(self.name, "failed", {"item": item, "error": str(exc), "at": time.time()})
                    continue
                if src is None:                       # todavía cargando: se reintenta en el próximo bloque
                    return False
                self.queue.pop(0)
                play = Play(item, src)
            elif item["file"] == EVENT:
                self.queue.pop(0)
                ev = item.get("event") or {}
                etype = ev.get("type")
                if etype == "pause":
                    play = Play(item, SilenceSource(int(float(ev.get("seconds", 0)) * SR)))
                elif etype == "wait_until":
                    play = Play(item, SilenceSource(None))
                else:                                 # marker / command: instantáneos
                    if etype == "command":
                        self.notify(self.name, "command", {"command": ev.get("command"), "args": ev.get("args", {})})
                    self.notify(self.name, "instant", {"item": item, "at": time.time()})
                    continue
            else:                                     # otros (nota…): se muestran y se pasa al siguiente
                self.queue.pop(0)
                self.notify(self.name, "instant", {"item": item, "at": time.time()})
                continue
            cur = self.current
            if cur is not None and ov > 0 and cur.source.duration_frames is not None:
                n = min(ov, max(1, cur.source.duration_frames - cur.pos))
                cur.out_start, cur.out_len = cur.pos, n
                self.fading.append(cur)
                play.fade_in = n
            elif cur is not None:
                self._end(cur, cur.status)            # corte seco
            self.current = play
            self.notify(self.name, "start", {"play": play})
            return True
        if self.current is None:
            self.notify(self.name, "idle", {})
        return False

    def _end(self, play: Play, status: str) -> None:
        self.notify(self.name, "end", {"play": play, "status": status, "at": time.time()})
        play.source.close()

    def _minute_reached(self, minute: Any) -> bool:
        return minute is None or self.clock().minute == int(minute)

    def _process_transitions(self, block: bool) -> None:
        cur = self.current
        if cur is None:
            if self.playing and self.queue:
                self._start_next(0, block)
            return
        dur = cur.source.duration_frames
        if dur is None:                               # esperar hasta una hora
            if cur.released or self._minute_reached((cur.item.get("event") or {}).get("minute")):
                self._end(cur, "completed")
                self.current = None
                self._start_next(0, block)
            return
        if cur.pos >= dur:
            self._end(cur, cur.status)
            self.current = None
            self._start_next(0, block)
            return
        if self.queue:
            ov = self._overlap(cur, self.queue[0])
            if ov > 0 and dur - cur.pos <= ov:
                self._start_next(ov, block)

    def _frames_until_event(self, n: int) -> int:
        cur = self.current
        if cur is None:
            return n
        dur = cur.source.duration_frames
        if dur is None:
            return min(n, SR // 20)                   # espera: revisar el reloj cada 50 ms
        limit = dur - cur.pos
        if self.queue:
            ov = self._overlap(cur, self.queue[0])
            if ov > 0 and limit > ov:
                limit -= ov
        return min(n, max(1, limit))

    # ---------------------------------------------------------------- audio
    def _render_chunk(self, n: int) -> np.ndarray:
        out = np.zeros((n, 2), np.float32)
        plays = ([self.current] if self.current else []) + self.fading
        for p in plays:
            blk = p.source.read(n)
            m = len(blk)
            if m:
                g = p.gain(m)
                if g is not None:
                    blk = blk * g[:, None].astype(np.float32)
                out[:m] += blk
            p.pos += m
        for p in list(self.fading):
            if p.fade_done() or (p.source.duration_frames is not None and p.pos >= p.source.duration_frames):
                self.fading.remove(p)
                self._end(p, p.status)
        return out

    def render(self, frames: int, block: bool = False) -> np.ndarray:
        if not self.playing and self._gate <= 0.0:
            return np.zeros((frames, 2), np.float32)
        out = np.zeros((frames, 2), np.float32)
        filled = 0
        while filled < frames:
            self._process_transitions(block)
            n = self._frames_until_event(frames - filled)
            out[filled:filled + n] = self._render_chunk(n)
            filled += n
        target = 1.0 if self.playing else 0.0         # pausa / reanudar sin clic: rampa de un bloque
        if self._gate != target:
            ramp = np.linspace(self._gate, target, frames, endpoint=False, dtype=np.float32)
            out *= ramp[:, None]
            self._gate = target
        return out

    # ---------------------------------------------------------------- estado para la UI
    def now(self) -> dict | None:
        c = self.current
        if c is None:
            return None
        it = c.item
        return {"uid": it["uid"], "file": it["file"], "kind": it["kind"], "title": it["title"],
                "artist": it.get("artist"), "id": it.get("id"),
                "duration_ms": (c.source.duration_frames * 1000 // SR) if c.source.duration_frames is not None
                else int(it.get("duration_ms") or 0),
                "elapsed_ms": c.played_ms, "paused": not self.playing}
