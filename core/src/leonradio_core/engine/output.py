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

    def __init__(self, device: int | str | None = None, blocksize: int = 1024,
                 buses: "frozenset[str] | None" = None) -> None:
        self.device, self.blocksize, self.buses = device, blocksize, buses
        self.name = "dispositivo de audio"
        self.latency_ms = 0.0
        self._stream: Any = None

    def _resolve(self, sd: Any) -> tuple[int | None, Any]:
        if self.device is None:
            return _wasapi(sd)
        if isinstance(self.device, str) and "|" in self.device:           # id estable «nombre|interfaz»
            idx = next((d["index"] for d in list_devices() if d["id"] == self.device), None)
            if idx is None:
                raise RuntimeError(f"el dispositivo «{self.device.split('|')[0]}» ya no está disponible")
            api = sd.query_hostapis(sd.query_devices(idx)["hostapi"])["name"]
            return idx, (sd.WasapiSettings(auto_convert=True) if "WASAPI" in api else None)
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
            outdata[:] = self.engine.render(frames, self.buses)
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
    return [{"index": i, "id": f"{d['name']}|{apis[d['hostapi']]['name']}", "name": d["name"],
             "hostapi": apis[d["hostapi"]]["name"],
             "channels": d["max_output_channels"], "default_samplerate": d["default_samplerate"],
             "is_default": i == default_out}
            for i, d in enumerate(sd.query_devices())
            if d["max_output_channels"] > 0 and "WDM-KS" not in apis[d["hostapi"]]["name"]]   # WDM-KS no abre en muchos equipos


def list_inputs() -> list[dict]:
    import sounddevice as sd

    apis = sd.query_hostapis()
    return [{"index": i, "id": f"{d['name']}|{apis[d['hostapi']]['name']}", "name": d["name"],
             "hostapi": apis[d["hostapi"]]["name"], "channels": d["max_input_channels"]}
            for i, d in enumerate(sd.query_devices())
            if d["max_input_channels"] > 0 and "WDM-KS" not in apis[d["hostapi"]]["name"]]


# Destinos configurables (como en las preferencias de audio de un automatizador): cada uno puede salir por una
# tarjeta distinta. «cue» (escucha previa) aún no tiene bus propio: se guarda la elección para cuando exista.
DESTINATIONS = ("main", "cue", "aux1", "aux2", "aux3", "aux4", "cart")
ENGINE_BUSES = ("main", "aux1", "aux2", "aux3", "aux4", "cart")


def plan_groups(routes: dict) -> dict:
    """Agrupa los buses por dispositivo: lo que no tiene dispositivo propio sale por el principal.
    Devuelve {dispositivo (None = predeterminado): frozenset de buses}."""
    main = routes.get("main") or None
    groups: dict = {}
    for bus in ENGINE_BUSES:
        dev = routes.get(bus) or main
        groups.setdefault(dev, set()).add(bus)
    return {dev: frozenset(b) for dev, b in groups.items()}


class RoutedOutput:
    """Salida real con varias tarjetas: un flujo por dispositivo distinto, cada uno con sus destinos."""

    simulated = False
    driven = False

    def __init__(self, routes: dict | None = None, blocksize: int = 1024) -> None:
        self.routes = {k: v for k, v in (routes or {}).items() if v}
        self.blocksize = blocksize
        self.streams: list[SoundDeviceOutput] = []
        self.warnings: list[str] = []
        self.name = "dispositivo de audio"
        self.latency_ms = 0.0
        self.engine: Any = None

    def start(self, engine: Any) -> None:
        self.engine = engine
        try:
            self._open()
        except Exception as exc:  # noqa: BLE001
            if not self.routes.get("main"):
                raise
            # La salida guardada ya no está (p. ej. unos auriculares desconectados): se usa la predeterminada de Windows
            # en vez de quedar en modo simulado, y se avisa. Lo guardado no se borra: vuelve a valer al reconectarla.
            lost = str(self.routes["main"]).split("|")[0]
            self.routes = {k: v for k, v in self.routes.items() if k != "main"}
            self._open()
            self.warnings.insert(0, f"No se pudo abrir «{lost}» ({exc}). Uso la salida predeterminada de Windows.")

    def _open(self) -> None:
        self.warnings = []
        groups = plan_groups(self.routes)
        main_dev = self.routes.get("main") or None
        opened: list[SoundDeviceOutput] = []
        extra: set[str] = set()                       # destinos cuya tarjeta falló: pasan al dispositivo principal
        try:
            for dev, buses in sorted(groups.items(), key=lambda kv: kv[0] != main_dev):   # el principal primero
                out = SoundDeviceOutput(dev, self.blocksize, buses | frozenset(extra) if dev == main_dev else buses)
                try:
                    out.start(self.engine)
                except Exception as exc:  # noqa: BLE001
                    if dev == main_dev:
                        raise
                    extra |= set(buses)
                    self.warnings.append(f"No se pudo abrir «{str(dev).split('|')[0]}»: {exc}. Sale por el principal.")
                    continue
                opened.append(out)
        except Exception:
            for o in opened:
                o.stop()
            raise
        if extra and opened:                          # el principal ya estaba abierto: reabrirlo con los destinos extra
            opened[0].buses = opened[0].buses | frozenset(extra)
        self.streams = opened
        self.name = " + ".join(dict.fromkeys(o.name for o in opened))
        self.latency_ms = max((o.latency_ms for o in opened), default=0.0)

    def reconfigure(self, routes: dict) -> None:
        old = self.routes
        for o in self.streams:
            o.stop()
        self.streams = []
        self.routes = {k: v for k, v in routes.items() if v}
        try:
            self._open()
        except Exception:
            self.routes = old
            self._open()                              # vuelve a la configuración anterior, que sí funcionaba
            raise

    def stop(self) -> None:
        for o in self.streams:
            o.stop()
        self.streams = []


def make_output(kind: str = "device", device: int | str | None = None,
                routes: dict | None = None) -> "NullOutput | RoutedOutput":
    if kind == "null":
        return NullOutput()
    merged = dict(routes or {})
    if device is not None:                            # --device / LEONRADIO_DEVICE manda sobre lo guardado
        merged["main"] = device
    return RoutedOutput(merged)


def test_tone(device: int | str | None = None, seconds: float = 0.7) -> str:
    """Tono corto y suave (440 Hz) por un dispositivo, sin bloquear. Para el botón «Probar» de las preferencias."""
    import sounddevice as sd

    out = SoundDeviceOutput(device)
    idx, extra = out._resolve(sd)
    t = np.arange(int(SR * seconds)) / SR
    env = np.minimum(1.0, np.minimum(t, seconds - t) / 0.05)          # entrada y salida suaves, sin clics
    tone = (0.12 * env * np.sin(2 * np.pi * 440 * t)).astype(np.float32)
    sd.play(np.stack([tone, tone], axis=1), SR, device=idx, extra_settings=extra)
    return sd.query_devices(idx if idx is not None else sd.default.device[1])["name"]


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
