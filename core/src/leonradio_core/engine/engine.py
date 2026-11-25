"""Engine: mezcla las listas (decks) y las voces superpuestas, aplica el ducking y mide el nivel.

``render(frames)`` devuelve el siguiente bloque estéreo ``float32``. Lo llama el hilo de audio (salida real)
o el Playout (salida nula: pruebas y demostración). Es determinista y no depende de ningún dispositivo.
"""

from __future__ import annotations

import collections
import threading
import time
from pathlib import Path

import numpy as np

from .deck import Deck, LoadError
from .sources import SAMPLE_RATE as SR
from .sources import FileSource, SilenceSource, Source, SyntheticSource


class Voice:
    """Sonido superpuesto (botonera, pisador): suena sobre la mezcla y puede bajar la música (ducking)."""

    def __init__(self, item: dict, source: Source, duck_db: float | None) -> None:
        self.item, self.source, self.duck_db = item, source, duck_db
        self.pos = 0
        self.started = time.time()


class Meter:
    """Nivel RMS por canal con constante de tiempo ~100 ms, expresado en la escala del VU de la interfaz."""

    def __init__(self) -> None:
        self._ms = np.zeros(2)
        self.peak = np.zeros(2)

    def update(self, block: np.ndarray) -> None:
        if len(block) == 0:
            return
        a = min(1.0, len(block) / (SR * 0.1))
        self._ms += (np.mean(block.astype(np.float64) ** 2, axis=0) - self._ms) * a
        self.peak = np.maximum(self.peak * 0.9, np.max(np.abs(block), axis=0))

    def levels(self) -> dict:
        db = 10 * np.log10(self._ms + 1e-12)
        vu = np.clip((db + 38.0) / 25.0, 0.0, 1.05)      # 0 VU = -18 dBFS -> 0,8 en la escala de la interfaz
        return {"l": round(float(vu[0]), 3), "r": round(float(vu[1]), 3),
                "db_l": round(float(db[0]), 1), "db_r": round(float(db[1]), 1),
                "peak_l": round(float(self.peak[0]), 3), "peak_r": round(float(self.peak[1]), 3)}


def frames_of(item: dict) -> int:
    return int(float(item.get("duration_ms") or 0) * SR / 1000)


class Engine:
    def __init__(self, crossfade_ms: int = 3000, master: float = 0.9, threaded: bool = False) -> None:
        self.lock = threading.RLock()
        self.decks: dict[str, Deck] = {}
        self.voices: list[Voice] = []
        self.notes: collections.deque = collections.deque()      # avisos hacia el Playout (hilo seguro)
        self.meter = Meter()
        self.crossfade_ms, self.master, self.threaded = crossfade_ms, master, threaded
        self._duck = 1.0
        self._cache: dict[str, Source] = {}
        self._loading: set[str] = set()
        self._errors: dict[str, str] = {}

    # ---------------------------------------------------------------- decks
    def deck(self, name: str) -> Deck:
        if name not in self.decks:
            self.decks[name] = Deck(name, self.load, lambda d, k, data: self.notes.append((d, k, data)),
                                    crossfade_ms=self.crossfade_ms)
        return self.decks[name]

    # ---------------------------------------------------------------- carga de ficheros de audio
    @staticmethod
    def is_synthetic(item: dict) -> bool:
        path = item.get("path")
        return not path or str(path).startswith("demo://")

    def _load_file(self, item: dict) -> Source:
        path = Path(str(item["path"]))
        if not path.is_file():
            raise LoadError(f"no existe el archivo: {path}")
        try:
            return FileSource.load(path)
        except Exception as exc:  # noqa: BLE001 - cualquier fallo de decodificación se reporta igual
            raise LoadError(f"no se pudo decodificar {path.name}: {exc}") from exc

    def load(self, item: dict, block: bool = True) -> Source | None:
        """Fuente lista para `item`. Con hilos y `block=False`, devuelve None mientras se decodifica."""
        uid = item["uid"]
        if uid in self._cache:
            return self._cache.pop(uid)
        if uid in self._errors:
            raise LoadError(self._errors.pop(uid))
        if self.is_synthetic(item):
            return SyntheticSource(frames_of(item), item["title"])
        if block or not self.threaded:
            return self._load_file(item)
        self.prefetch(item)
        return None

    def prefetch(self, item: dict) -> None:
        """Empieza a decodificar `item` en segundo plano (solo con hilos y archivos reales)."""
        uid = item["uid"]
        if (not self.threaded or item["file"] != "audio" or self.is_synthetic(item)
                or uid in self._cache or uid in self._loading or uid in self._errors):
            return
        self._loading.add(uid)

        def work() -> None:
            try:
                self._cache[uid] = self._load_file(item)
            except LoadError as exc:
                self._errors[uid] = str(exc)
            finally:
                self._loading.discard(uid)

        threading.Thread(target=work, daemon=True, name=f"carga-{uid}").start()

    def ensure_loaded(self, item: dict) -> None:
        """Decodifica `item` AHORA (bloqueante) y lo deja en caché. Se llama desde el hilo de control SIN tener
        el candado del motor: así el hilo de audio nunca espera a un archivo que se está leyendo del disco."""
        uid = item["uid"]
        if item["file"] != "audio" or self.is_synthetic(item) or uid in self._cache or uid in self._errors:
            return
        try:
            self._cache[uid] = self._load_file(item)
        except LoadError as exc:
            self._errors[uid] = str(exc)

    def prune(self, keep: set[str]) -> None:
        for uid in [u for u in self._cache if u not in keep]:
            self._cache.pop(uid, None)

    # ---------------------------------------------------------------- voces superpuestas
    def fire(self, item: dict, duck_db: float | None = None) -> Voice:
        src = self.load(item, True)
        assert src is not None
        voice = Voice(item, src, duck_db)
        with self.lock:
            self.voices.append(voice)
        self.notes.append(("voice", "start", {"voice": voice}))
        return voice

    # ---------------------------------------------------------------- mezcla
    def render(self, frames: int) -> np.ndarray:
        with self.lock:
            mix = np.zeros((frames, 2), np.float32)
            for d in self.decks.values():
                mix += d.render(frames)
            # ducking: la música baja mientras suena una voz que lo pide (ataque rápido, liberación lenta)
            want = min((10 ** (v.duck_db / 20) for v in self.voices if v.duck_db), default=1.0)
            tau = 0.12 if want < self._duck else 0.5
            new = want + (self._duck - want) * float(np.exp(-(frames / SR) / tau))
            mix *= np.linspace(self._duck, new, frames, endpoint=False, dtype=np.float32)[:, None]
            self._duck = new
            for v in list(self.voices):
                blk = v.source.read(frames)
                mix[:len(blk)] += blk
                v.pos += len(blk)
                if len(blk) < frames:
                    self.voices.remove(v)
                    self.notes.append(("voice", "end", {"voice": v, "status": "completed", "at": time.time()}))
            mix *= self.master
            np.clip(mix, -1.0, 1.0, out=mix)
            self.meter.update(mix)
            return mix

    @property
    def ducking_db(self) -> float:
        return round(20 * float(np.log10(max(self._duck, 1e-6))), 1)
