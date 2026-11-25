"""Salidas de audio: la nula (pruebas y demostración) y la real por sounddevice (WASAPI en Windows)."""

from __future__ import annotations

from typing import Any

import numpy as np

from .sources import SAMPLE_RATE as SR


class NullOutput:
    """Sin dispositivo: el Playout renderiza el audio por tiempo (`tick`). Nada suena."""

    name = "sin salida de audio (simulada)"
    simulated = True
    driven = True            # el Playout mueve el reloj

    def start(self, engine: Any) -> None:
        self.engine = engine

    def stop(self) -> None:
        pass


def _wasapi(sd: Any) -> tuple[int | None, Any]:
    """Índice del dispositivo de salida por defecto de WASAPI (baja latencia) y sus ajustes, si existe."""
    for i, api in enumerate(sd.query_hostapis()):
        if "WASAPI" in api["name"] and api["default_output_device"] >= 0:
            return api["default_output_device"], sd.WasapiSettings(auto_convert=True)
    return None, None


class SoundDeviceOutput:
    """Salida real. El hilo de audio de PortAudio llama a `engine.render` en cada bloque."""

    simulated = False
    driven = False

    def __init__(self, device: int | str | None = None, blocksize: int = 1024) -> None:
        self.device, self.blocksize = device, blocksize
        self.name = "dispositivo de audio"
        self.latency_ms = 0.0
        self._stream: Any = None

    def _resolve(self, sd: Any) -> tuple[int | None, Any]:
        if self.device is None:
            return _wasapi(sd)
        if isinstance(self.device, int) or str(self.device).isdigit():
            idx = int(self.device)
        else:
            wanted = str(self.device).lower()
            idx = next((d["index"] for d in list_devices() if wanted in d["name"].lower()), None)
            if idx is None:
                raise RuntimeError(f"no encuentro un dispositivo de salida que contenga «{self.device}»")
        api = sd.query_hostapis(sd.query_devices(idx)["hostapi"])["name"]
        return idx, (sd.WasapiSettings(auto_convert=True) if "WASAPI" in api else None)

    def start(self, engine: Any) -> None:
        import sounddevice as sd

        self.engine = engine
        idx, extra = self._resolve(sd)
        info = sd.query_devices(idx if idx is not None else sd.default.device[1])
        self.name = f"{info['name']} · {sd.query_hostapis(info['hostapi'])['name']}"
        self._stream = sd.OutputStream(samplerate=SR, channels=2, dtype="float32", blocksize=self.blocksize,
                                       device=idx, latency="low", extra_settings=extra, callback=self._callback)
        self._stream.start()
        self.latency_ms = round(self._stream.latency * 1000, 1)

    def _callback(self, outdata: np.ndarray, frames: int, time_info: Any, status: Any) -> None:
        try:
            outdata[:] = self.engine.render(frames)
        except Exception:  # noqa: BLE001 - el hilo de audio nunca debe lanzar: se calla y sigue
            outdata[:] = 0

    def stop(self) -> None:
        if self._stream is not None:
            self._stream.stop()
            self._stream.close()
            self._stream = None


def list_devices() -> list[dict]:
    import sounddevice as sd

    apis = sd.query_hostapis()
    default_out = sd.default.device[1]
    return [{"index": i, "name": d["name"], "hostapi": apis[d["hostapi"]]["name"],
             "channels": d["max_output_channels"], "default_samplerate": d["default_samplerate"],
             "is_default": i == default_out}
            for i, d in enumerate(sd.query_devices()) if d["max_output_channels"] > 0]


def make_output(kind: str = "device", device: int | str | None = None) -> NullOutput | SoundDeviceOutput:
    return NullOutput() if kind == "null" else SoundDeviceOutput(device)


def beep(device: int | str | None = None, seconds: float = 1.0) -> str:
    """Tono de 440 Hz por el canal izquierdo y luego el derecho. Devuelve el dispositivo usado."""
    import sounddevice as sd

    out = SoundDeviceOutput(device)
    idx, extra = out._resolve(sd)
    t = np.arange(int(SR * seconds)) / SR
    tone = (0.25 * np.sin(2 * np.pi * 440 * t)).astype(np.float32)
    stereo = np.zeros((2 * len(t), 2), np.float32)
    stereo[: len(t), 0] = tone
    stereo[len(t):, 1] = tone
    sd.play(stereo, SR, device=idx, extra_settings=extra)
    sd.wait()
    return sd.query_devices(idx if idx is not None else sd.default.device[1])["name"]
