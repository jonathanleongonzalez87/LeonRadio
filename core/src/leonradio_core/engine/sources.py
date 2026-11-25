"""Fuentes de audio: de dónde salen las muestras que mezcla el motor.

Todas devuelven bloques estéreo ``float32`` de forma ``(n, 2)`` a ``SAMPLE_RATE`` Hz.
"""

from __future__ import annotations

import zlib
from pathlib import Path

import numpy as np

SAMPLE_RATE = 44100


class Source:
    duration_frames: int | None = 0      # None = sin fin (silencio de espera)
    pos = 0

    def read(self, n: int) -> np.ndarray:  # pragma: no cover - interfaz
        raise NotImplementedError

    def close(self) -> None:
        pass


class FileSource(Source):
    """Archivo decodificado en memoria (int16). El decodificador es miniaudio (mp3, wav, flac, ogg…)."""

    def __init__(self, samples: np.ndarray) -> None:
        self._a = samples
        self.pos = 0
        self.duration_frames = int(len(samples))

    @classmethod
    def load(cls, path: str | Path, sample_rate: int = SAMPLE_RATE) -> "FileSource":
        import miniaudio

        # Se leen los bytes desde Python: miniaudio no abre bien rutas con tildes en Windows (p. ej. «Música»).
        data = Path(path).read_bytes()
        decoded = miniaudio.decode(data, output_format=miniaudio.SampleFormat.SIGNED16,
                                   nchannels=2, sample_rate=sample_rate)
        return cls(np.frombuffer(decoded.samples, dtype=np.int16).reshape(-1, 2))

    def read(self, n: int) -> np.ndarray:
        chunk = self._a[self.pos:self.pos + n]
        self.pos += len(chunk)
        return chunk.astype(np.float32) / 32768.0


class SyntheticSource(Source):
    """Sonido sintético con pulso (no son archivos reales): para la demostración en el navegador y las pruebas."""

    def __init__(self, duration_frames: int, seed: str, sample_rate: int = SAMPLE_RATE) -> None:
        self.duration_frames = int(duration_frames)
        self.pos = 0
        self._sr = sample_rate
        h = zlib.crc32(seed.encode("utf-8"))
        self._f = [110.0 * 2 ** (((h >> s) % 24) / 12) for s in (0, 5, 10)]   # tres notas de la semilla
        self._beat = 1.6 + (h % 20) / 10                                        # pulsos por segundo
        self._seed = h

    def read(self, n: int) -> np.ndarray:
        n = max(0, min(n, self.duration_frames - self.pos))
        if n == 0:
            return np.zeros((0, 2), np.float32)
        t = (self.pos + np.arange(n)) / self._sr
        tone = (0.16 * np.sin(2 * np.pi * self._f[0] * t) + 0.10 * np.sin(2 * np.pi * self._f[1] * t)
                + 0.06 * np.sin(2 * np.pi * self._f[2] * t))
        noise = 0.04 * np.random.default_rng((self._seed, self.pos)).standard_normal(n)
        env = 0.55 + 0.45 * np.sin(np.pi * self._beat * t) ** 2
        mono = ((tone + noise) * env).astype(np.float32)
        self.pos += n
        return np.stack([mono, np.roll(mono, 7)], axis=1)       # leve diferencia L/R


class SilenceSource(Source):
    """Silencio: de duración fija (pausa) o sin fin hasta que se libere (esperar hasta una hora)."""

    def __init__(self, duration_frames: int | None) -> None:
        self.duration_frames = duration_frames
        self.pos = 0

    def read(self, n: int) -> np.ndarray:
        if self.duration_frames is not None:
            n = max(0, min(n, self.duration_frames - self.pos))
        self.pos += n
        return np.zeros((n, 2), np.float32)
