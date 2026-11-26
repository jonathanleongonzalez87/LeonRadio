"""Streaming a Icecast 2 (como BUTT): toma la mezcla principal, la codifica a MP3 y la envía; también graba a archivo.

Hilos: el hilo de audio solo copia bloques a una cola (`feed`); un hilo propio codifica y envía, y reconecta solo.
La contraseña del servidor vive solo en la configuración local; nunca se publica en el estado que ve la interfaz.
"""

from __future__ import annotations

import base64
import http.client
import queue
import socket
import ssl
import threading
import time
from datetime import datetime
from pathlib import Path
from typing import Any, Callable
from urllib.parse import quote

import numpy as np

from .sources import SAMPLE_RATE as SR

DEFAULTS: dict[str, Any] = {
    "host": "", "port": 8000, "mount": "/stream", "user": "source", "password": "",
    "name": "", "description": "", "genre": "", "url": "", "bitrate": 128, "public": False,
    "tls": False, "reconnect": True, "record_dir": "",
}
BITRATES = (64, 96, 128, 160, 192, 256, 320)
USER_AGENT = "LeonRadio/0.1"


class StreamError(Exception):
    pass


def _clean(cfg: dict[str, Any]) -> dict[str, Any]:
    c = {**DEFAULTS, **{k: v for k, v in cfg.items() if k in DEFAULTS}}
    c["port"] = int(c["port"] or 8000)
    c["bitrate"] = int(c["bitrate"]) if int(c["bitrate"] or 0) in BITRATES else 128
    mount = str(c["mount"] or "/stream").strip()
    c["mount"] = mount if mount.startswith("/") else "/" + mount
    c["host"] = str(c["host"]).strip()
    return c


def header_value(text: object) -> str:
    """Valor seguro para una cabecera HTTP (sin saltos de línea)."""
    return " ".join(str(text).split())[:200]


class StreamService:
    def __init__(self, load_config: Callable[[], dict], save_config: Callable[[dict], None]) -> None:
        self._load, self._save = load_config, save_config
        self.frames: queue.Queue = queue.Queue(maxsize=400)
        self._lock = threading.Lock()
        self._thread: threading.Thread | None = None
        self._stop = threading.Event()
        self._want_live = False
        self._want_record = False
        self._state = "stopped"
        self._message = ""
        self._since = 0.0
        self._bytes = 0
        self._record_path = ""
        self._song = ""
        self._pending_song = False
        self.record_check: Callable[[str], Path] | None = None   # valida la carpeta de grabación (la fija quien lo crea)

    # ------------------------------------------------------------- configuración
    def config(self) -> dict[str, Any]:
        return _clean(self._load() or {})

    def public_config(self) -> dict[str, Any]:
        c = self.config()
        pw = bool(c.pop("password"))
        return {**c, "has_password": pw}

    def set_config(self, **fields: Any) -> None:
        cur = self._load() or {}
        for k, v in fields.items():
            if k not in DEFAULTS:
                raise ValueError(f"campo desconocido: {k}")
            if k == "password" and not str(v):
                continue                              # un campo vacío no borra la contraseña guardada
            cur[k] = v
        _clean(cur)                                   # valida
        self._save(cur)

    # ------------------------------------------------------------- audio (hilo de audio: rápido y sin bloquear)
    def feed(self, mix: np.ndarray) -> None:
        if not (self._want_live or self._want_record):
            return
        try:
            self.frames.put_nowait(mix.copy())
        except queue.Full:                            # el envío va atrasado: se descarta lo más viejo
            try:
                self.frames.get_nowait()
                self.frames.put_nowait(mix.copy())
            except (queue.Empty, queue.Full):
                pass

    # ------------------------------------------------------------- control
    def connect(self) -> None:
        c = self.config()
        if not c["host"]:
            raise ValueError("Falta la dirección del servidor (en la pestaña Servidor)")
        if not c["password"]:
            raise ValueError("Falta la contraseña del servidor")
        self._want_live = True
        self._ensure_thread()

    def disconnect(self) -> None:
        self._want_live = False
        self._wake()

    def record(self, on: bool) -> None:
        if on:
            self._want_record = True
            self._ensure_thread()
        else:
            self._want_record = False
            self._wake()

    def set_song(self, artist: str | None, title: str | None) -> None:
        song = " - ".join(x for x in (artist, title) if x)
        if not song or song == self._song:
            return
        self._song = song
        self._pending_song = True

    def shutdown(self) -> None:
        self._want_live = self._want_record = False
        self._stop.set()
        if self._thread:
            self._thread.join(timeout=3)

    def status(self) -> dict[str, Any]:
        secs = int(time.time() - self._since) if self._state == "live" and self._since else 0
        return {"state": self._state, "message": self._message, "seconds": secs, "kb": self._bytes // 1024,
                "recording": self._want_record and bool(self._record_path), "record_path": self._record_path,
                "song": self._song}

    # ------------------------------------------------------------- hilo de envío
    def _wake(self) -> None:
        try:
            self.frames.put_nowait(None)              # despierta al hilo si espera datos
        except queue.Full:
            pass

    def _ensure_thread(self) -> None:
        with self._lock:
            if self._thread and self._thread.is_alive():
                return
            self._stop.clear()
            self._thread = threading.Thread(target=self._run, name="leonradio-stream", daemon=True)
            self._thread.start()

    def _set(self, state: str, message: str = "") -> None:
        self._state, self._message = state, message

    def _encoder(self, bitrate: int) -> Any:
        try:
            import lameenc
        except ImportError as exc:
            raise StreamError("Falta el codificador MP3: ejecuta  pip install lameenc  (o reinicia con iniciar-leonradio.bat)") from exc
        enc = lameenc.Encoder()
        enc.set_bit_rate(bitrate)
        enc.set_in_sample_rate(SR)
        enc.set_channels(2)
        enc.set_quality(2)
        return enc

    def _run(self) -> None:
        sock: socket.socket | None = None
        rec = None
        enc = None
        backoff = 2.0
        retry_at = 0.0
        try:
            while not self._stop.is_set() and (self._want_live or self._want_record or sock or rec):
                c = self.config()
                if enc is None:
                    enc = self._encoder(c["bitrate"])
                # --- conexión / desconexión
                if self._want_live and sock is None and time.time() >= retry_at:
                    self._set("connecting", f"Conectando con {c['host']}:{c['port']}…")
                    try:
                        sock = self._open(c)
                        self._since, self._bytes = time.time(), 0
                        self._set("live", f"En el aire · {c['host']}{c['mount']}")
                        self._pending_song = bool(self._song)
                        backoff = 2.0
                    except StreamError as exc:
                        sock = None
                        if not c["reconnect"] or "contraseña" in str(exc).lower():
                            self._want_live = False
                            self._set("error", str(exc))
                        else:
                            self._set("reconnecting", f"{exc} · reintentando en {int(backoff)} s")
                            retry_at = time.time() + backoff
                            backoff = min(30.0, backoff * 2)
                if not self._want_live and sock is not None:
                    self._close(sock)
                    sock = None
                    self._set("stopped", "Desconectado")
                # --- grabación
                if self._want_record and rec is None:
                    rec = self._open_record(c)
                if not self._want_record and rec is not None:
                    rec.close()
                    rec, self._record_path = None, ""
                # --- audio
                try:
                    mix = self.frames.get(timeout=0.25)
                except queue.Empty:
                    mix = None
                if mix is None:
                    continue
                pcm = (np.clip(mix, -1.0, 1.0) * 32767).astype("<i2")
                data = enc.encode(pcm.tobytes())
                if not data:
                    continue
                if rec is not None:
                    rec.write(data)
                    rec.flush()                           # si el programa se cierra mal, lo grabado queda en disco
                if sock is not None:
                    try:
                        sock.sendall(data)
                        self._bytes += len(data)
                        if self._pending_song:
                            self._pending_song = False
                            threading.Thread(target=self._send_song, args=(c, self._song), daemon=True).start()
                    except OSError as exc:
                        self._close(sock)
                        sock = None
                        if c["reconnect"] and self._want_live:
                            self._set("reconnecting", f"Se cortó la conexión ({exc.strerror or exc}) · reintentando…")
                            retry_at = time.time() + 2.0
                        else:
                            self._want_live = False
                            self._set("error", f"Se cortó la conexión: {exc.strerror or exc}")
        except StreamError as exc:
            self._want_live = self._want_record = False
            self._set("error", str(exc))
        except Exception as exc:  # noqa: BLE001 - un fallo de red/codec no debe tumbar el programa
            self._want_live = self._want_record = False
            self._set("error", f"{type(exc).__name__}: {exc}")
        finally:
            if sock is not None:
                self._close(sock)
            if rec is not None:
                rec.close()
                self._record_path = ""
            if self._state in ("live", "connecting", "reconnecting"):
                self._set("stopped", "Desconectado")
            while not self.frames.empty():
                try:
                    self.frames.get_nowait()
                except queue.Empty:
                    break

    @staticmethod
    def _close(sock: socket.socket) -> None:
        try:
            sock.close()
        except OSError:
            pass

    def _open_record(self, c: dict[str, Any]) -> Any:
        folder = Path.home() / "Music" / "LeonRadio grabaciones"
        if c["record_dir"]:
            try:                                  # la config podría venir de un config.json editado a mano: se revalida
                folder = self.record_check(c["record_dir"]) if self.record_check else Path(c["record_dir"])
            except ValueError:
                self._set(self._state, "La carpeta de grabaciones no está permitida: se graba en la carpeta por defecto")
        folder.mkdir(parents=True, exist_ok=True)
        path = folder / f"LeonRadio {datetime.now():%Y-%m-%d %H-%M-%S}.mp3"
        self._record_path = str(path)
        return open(path, "ab")

    def _open(self, c: dict[str, Any]) -> socket.socket:
        """Conecta y se presenta al servidor (PUT de Icecast 2; si no lo admite, SOURCE de Icecast 1)."""
        auth = base64.b64encode(f"{c['user'] or 'source'}:{c['password']}".encode("utf-8")).decode()
        head = [
            f"Authorization: Basic {auth}", f"User-Agent: {USER_AGENT}", "Content-Type: audio/mpeg",
            f"ice-name: {header_value(c['name'] or 'LeonRadio')}", f"ice-description: {header_value(c['description'])}",
            f"ice-genre: {header_value(c['genre'])}", f"ice-url: {header_value(c['url'])}",
            f"ice-public: {1 if c['public'] else 0}", f"ice-bitrate: {c['bitrate']}",
            f"ice-audio-info: ice-samplerate={SR};ice-bitrate={c['bitrate']};ice-channels=2",
        ]
        last = ""
        for method, extra in (("PUT", ["Expect: 100-continue"]), ("SOURCE", [])):
            try:
                raw = socket.create_connection((c["host"], c["port"]), timeout=8)
                sock: socket.socket = (ssl.create_default_context().wrap_socket(raw, server_hostname=c["host"])
                                       if c["tls"] else raw)
            except (OSError, ssl.SSLError) as exc:
                raise StreamError(f"No se pudo conectar con {c['host']}:{c['port']} ({getattr(exc, 'strerror', None) or exc})") from exc
            req = [f"{method} {c['mount']} HTTP/1.1", f"Host: {c['host']}:{c['port']}", *head, *extra, "", ""]
            try:
                sock.sendall("\r\n".join(req).encode("utf-8"))
                sock.settimeout(8)
                reply = sock.recv(1024).decode("latin-1", "replace")
            except OSError as exc:
                self._close(sock)
                raise StreamError(f"El servidor no respondió ({exc})") from exc
            line = reply.split("\r\n", 1)[0]
            code = line.split(" ")[1] if line.count(" ") >= 1 else ""
            if code in ("100", "200"):
                sock.settimeout(10)
                return sock
            self._close(sock)
            last = line
            if code in ("401", "403"):
                raise StreamError("El servidor rechazó la contraseña o el usuario (Icecast usa «source» por defecto)")
            if code not in ("400", "405", "501"):
                break
        raise StreamError(f"El servidor respondió: {last or 'sin respuesta'}")

    def _send_song(self, c: dict[str, Any], song: str) -> None:
        """Título y artista de lo que suena (admin/metadata de Icecast); fallar aquí no corta la transmisión."""
        try:
            conn_cls = http.client.HTTPSConnection if c["tls"] else http.client.HTTPConnection
            conn = conn_cls(c["host"], c["port"], timeout=6)
            auth = base64.b64encode(f"{c['user'] or 'source'}:{c['password']}".encode("utf-8")).decode()
            conn.request("GET", f"/admin/metadata?mode=updinfo&mount={quote(c['mount'])}&song={quote(song)}",
                         headers={"Authorization": f"Basic {auth}", "User-Agent": USER_AGENT})
            conn.getresponse().read()
            conn.close()
        except Exception:  # noqa: BLE001
            pass
