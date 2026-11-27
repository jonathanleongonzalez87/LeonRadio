"""Playout: une el motor de audio con el resto de LeonRadio.

* controla la Emisión y las 4 Auxiliares (transporte, agregar/quitar ficheros, cargar listas `.m3u`),
* lleva el reloj (`tick`) y publica el estado y los niveles para la interfaz,
* registra en el historial (`playlog`) TODO lo que sonó: audios, eventos y otros ficheros.

El hilo de audio solo deja avisos en una cola; aquí (hilo de control) se leen y se escriben en la base de datos,
para que ningún bloqueo de disco o de red llegue nunca al audio.
"""

from __future__ import annotations

import random
import re
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from .. import library, meta, paths, sdk, settings
from . import files
from .engine import Engine
from .stream import StreamService
from .files import AUDIO, EVENT
from .sources import SAMPLE_RATE as SR

DECKS = ("emision", "aux1", "aux2", "aux3", "aux4")
SOURCE_OF = {"emision": "auto"}                       # las auxiliares las lanza el operador: «live»
DUCK_DB = {"pisador": -10.0, "separador": -10.0, "voice": -10.0, "jingle": -6.0}   # ducking por tipo de pieza
MAX_STATE_ITEMS = 200


def iso(ts: float) -> str:
    return datetime.fromtimestamp(ts, timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.%fZ")


def brief(item: dict) -> dict:
    return {k: item.get(k) for k in ("uid", "file", "kind", "title", "artist", "duration_ms", "id")}


class Playout:
    def __init__(self, host: sdk.Host, output: Any, *, autoplay: bool = False, crossfade_ms: int = 3000) -> None:
        self.host, self.output, self.autoplay = host, output, autoplay
        self.engine = Engine(crossfade_ms=crossfade_ms, threaded=not output.driven)
        for name in DECKS:
            self.engine.deck(name)
        self._last: dict[str, Any] = {}
        self._frac = 0.0
        self._prefetch_at = 0.0
        self.stream = StreamService(lambda: settings.load().get("stream", {}), self._save_stream)
        self.engine.taps.append(self.stream.feed)
        self._stream_at = 0.0
        self._selected: tuple[str, str] | None = None
        self._meta_key: tuple | None = None

    # ------------------------------------------------------------------ ciclo de vida
    def start(self) -> None:
        try:
            self.output.start(self.engine)
        except Exception as exc:  # noqa: BLE001 - sin dispositivo / dispositivo ocupado: se sigue en simulado
            from .output import NullOutput

            self.output = NullOutput()
            self.engine.threaded = False
            self.output.start(self.engine)
            self._set("playout.message", f"No se pudo abrir el audio ({exc}). Sigo en modo simulado.")
        self._audio_info()
        self._set("stream.config", self.stream.public_config())
        self._set("stream.status", self.stream.status())
        self._set("audio.inputs", settings.load().get("audio", {}).get("inputs", {}))
        with self.engine.lock:
            for item in self._initial_queue():
                self.engine.deck("emision").add(item)
        if self.autoplay:
            self._preload("emision")
            with self.engine.lock:
                self.engine.deck("emision").play(False)
        self._prefetch(force=True)
        self._publish()

    @staticmethod
    def _save_stream(cfg: dict) -> None:
        allc = settings.load(strict=True)
        allc["stream"] = cfg
        settings.save(allc)

    def stream_set(self, **fields: Any) -> dict:
        self.stream.set_config(**fields)
        self._set("stream.config", self.stream.public_config())
        return {"ok": True}

    def stream_do(self, verb: str) -> dict:
        if verb == "connect":
            self.stream.connect()
        elif verb == "disconnect":
            self.stream.disconnect()
        elif verb == "record":
            self.stream.record(not self.stream._want_record)
        else:
            raise ValueError(f"orden desconocida: {verb}")
        time.sleep(0.05)
        self._publish_stream(force=True)
        return self.stream.status()

    def _publish_stream(self, force: bool = False) -> None:
        now = time.time()
        if not force and now < self._stream_at:
            return
        self._stream_at = now + 1.0                      # una vez por segundo: el estado cambia sin parar
        self._set("stream.status", self.stream.status())

    def _audio_info(self) -> None:
        o = self.output
        self._set("audio.info", {"backend": "null" if o.simulated else "device", "device": o.name,
                                 "simulated": o.simulated, "sample_rate": SR,
                                 "latency_ms": getattr(o, "latency_ms", 0.0),
                                 "routes": dict(getattr(o, "routes", {})),
                                 "warnings": list(getattr(o, "warnings", []))})

    def set_route(self, dest: str, device: str | None) -> dict:
        """Cambia la tarjeta de sonido de un destino (principal, aux 1–4, botonera…) sin reiniciar, y la recuerda."""
        from .output import DESTINATIONS

        if dest not in DESTINATIONS:
            raise ValueError(f"destino desconocido: {dest}")
        if not hasattr(self.output, "reconfigure"):
            raise ValueError("No hay salida de audio real (modo simulado): arranca sin --audio null")
        routes = dict(self.output.routes)
        if device:
            routes[dest] = str(device)
        else:
            routes.pop(dest, None)
        self.output.reconfigure(routes)
        cfg = settings.load()
        cfg.setdefault("audio", {})["routes"] = routes
        settings.save(cfg)
        self._audio_info()
        return {"dest": dest, "device": device}

    def set_input(self, line: str, device: str | None) -> dict:
        """Entrada de línea (micrófono, consola…): por ahora solo se guarda la elección."""
        if line not in ("line1", "line2"):
            raise ValueError(f"entrada desconocida: {line}")
        cfg = settings.load()
        inputs = cfg.setdefault("audio", {}).setdefault("inputs", {})
        if device:
            inputs[line] = str(device)
        else:
            inputs.pop(line, None)
        settings.save(cfg)
        self._set("audio.inputs", dict(inputs))
        return {"line": line, "device": device}

    def stop(self) -> None:
        self.stream.shutdown()
        self.output.stop()

    def _initial_queue(self) -> list[dict]:
        with self.host.db_lock:
            rows = self.host.db.execute(
                "SELECT id, kind, title, artist, duration_ms, path, intro_ms, outro_ms FROM assets "
                "WHERE status='active' AND kind IN ('music','jingle','separador','pisador')").fetchall()
        items = [dict(r) for r in rows]
        if not items:
            return [files.audio_file({"id": None, "path": None, **s}) for s in sdk.load_json("demo_sample.json")]
        music = [i for i in items if i["kind"] == "music"]
        fillers = [i for i in items if i["kind"] in ("jingle", "separador")]
        random.shuffle(music)
        out: list[dict] = []
        for n, m in enumerate(music):
            out.append(files.audio_file(m))
            if fillers and n % 3 == 2:
                out.append(files.audio_file(random.choice(fillers)))
        return out or [files.audio_file(i) for i in items]

    # ------------------------------------------------------------------ listas
    def deck(self, name: str):
        if name not in DECKS:
            raise ValueError(f"lista desconocida: {name}")
        return self.engine.deck(name)

    def _asset(self, asset_id: int) -> dict:
        with self.host.db_lock:
            row = self.host.db.execute(
                "SELECT id, kind, title, artist, duration_ms, path, intro_ms, outro_ms FROM assets WHERE id = ?",
                (asset_id,)).fetchone()
        if row is None:
            raise ValueError(f"asset {asset_id} no existe")
        return dict(row)

    def add(self, target: str, item: dict, index: int | None = None) -> dict:
        with self.engine.lock:
            self.deck(target).add(item, index)
        self._prefetch(force=True)
        self._publish()
        return {"title": item["title"], "target": target, "file": item["file"]}

    def add_to(self, target: str, spec: int | str) -> dict:
        """`spec`: id de un audio de la biblioteca (int) o clave de una plantilla de evento/otro (str)."""
        if isinstance(spec, str) and not spec.isdigit():
            return self.add(target, files.from_template(spec))
        return self.add(target, files.audio_file(self._asset(int(spec))))

    def remove(self, target: str, uid: str) -> bool:
        with self.engine.lock:
            ok = self.deck(target).remove(uid)
        self._prefetch(force=True)
        self._publish()
        return ok

    def move(self, target: str, uid: str, delta: int) -> bool:
        with self.engine.lock:
            ok = self.deck(target).move(uid, int(delta))
        if ok:
            self._prefetch(force=True)
        self._publish()
        return ok

    def move_to(self, target: str, uid: str, index: int) -> bool:
        with self.engine.lock:
            ok = self.deck(target).move_to(uid, int(index))
        if ok:
            self._prefetch(force=True)
        self._publish()
        return ok

    def seek(self, target: str, ms: float) -> bool:
        with self.engine.lock:
            ok = self.deck(target).seek(ms)
        self._publish()
        return ok

    def add_path(self, target: str, path: str) -> dict:
        """Carga un archivo de audio de cualquier carpeta del disco: lo registra en la biblioteca y lo agrega a la lista."""
        aid = library.add_file(self.host.db, path, self.host.db_lock)
        return self.add_to(target, aid)

    def add_folder(self, target: str, folder: str) -> dict:
        """Agrega a la lista todos los audios de una carpeta (sin entrar en subcarpetas), por orden de nombre."""
        added = 0
        for p in sorted(Path(folder).iterdir(), key=lambda q: q.name.lower()):
            if p.is_file() and p.suffix.lower() in library.AUDIO_EXT:
                try:
                    self.add_path(target, str(paths.check(str(p), self.host.path_roots(), must="file")))   # un enlace hacia fuera no entra
                    added += 1
                except (OSError, ValueError) as exc:
                    self._set("playout.message", f"No se pudo leer «{p.name}»: {exc}")
        self._set("playout.message", f"{added} audio(s) de «{Path(folder).name or folder}» agregados a la lista")
        return {"added": added}

    def select(self, target: str, uid: str) -> None:
        """Fichero elegido en una lista: sus metadatos se muestran en el panel Metadatos."""
        self._selected = (target, uid)
        self._set("list.selected", {"target": target, "uid": uid})
        self._publish()

    def clear(self, target: str) -> None:
        with self.engine.lock:
            self.deck(target).clear()
        self._publish()

    def _preload(self, target: str, count: int = 2) -> None:
        """Decodifica las primeras piezas de la lista fuera del candado (puede tardar décimas de segundo)."""
        with self.engine.lock:
            heads = list(self.deck(target).queue[:count])
        for it in heads:
            self.engine.ensure_loaded(it)

    def transport(self, target: str, verb: str) -> None:
        if verb in ("play", "toggle", "next"):
            self._preload(target)
        with self.engine.lock:
            d = self.deck(target)
            if verb == "play":
                d.play(False)
            elif verb == "pause":
                d.pause()
            elif verb == "toggle":
                d.toggle(False)
            elif verb == "stop":
                d.stop()
            elif verb == "next":
                d.skip(False)
            elif verb == "stop_after":
                d.stop_after = not d.stop_after and d.current is not None
            else:
                raise ValueError(f"orden desconocida: {verb}")
        self._drain()
        self._publish()

    def fire_cart(self, asset_id: int) -> dict:
        """Dispara una pieza de la botonera: suena encima de la mezcla y baja la música según su tipo."""
        if self.engine.stop_voice(asset_id):              # pulsar de nuevo una pieza que suena la detiene
            self._drain()
            self._publish()
            return {"stopped": True}
        item = files.audio_file(self._asset(asset_id))
        self.engine.fire(item, DUCK_DB.get(item["kind"]))
        self._set("cart.last", {"title": item["title"], "at": iso(time.time())})
        self._publish()
        return {"title": item["title"]}

    def load_m3u(self, target: str, path: str) -> dict:
        """Agrega a una lista los audios de un `.m3u`. Las rutas del `.m3u` suelen ser de otra máquina:
        se resuelven por el nombre del archivo dentro de la biblioteca."""
        p = Path(path).resolve()
        root = Path(self.host.library_dir).resolve() if self.host.library_dir else None
        if root is None or not (p == root or root in p.parents):
            raise ValueError("la lista debe estar dentro de la carpeta de la emisora")
        added = missing = 0
        for line in p.read_text(encoding="utf-8-sig", errors="replace").splitlines():
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            name = re.split(r"[\\/]", line)[-1]
            with self.host.db_lock:
                row = self.host.db.execute(
                    "SELECT id FROM assets WHERE path LIKE ? AND status='active' LIMIT 1", (f"%{name}",)).fetchone()
            if row is None:
                missing += 1
                continue
            with self.engine.lock:
                self.deck(target).add(files.audio_file(self._asset(row["id"])))
            added += 1
        msg = f"Lista «{p.stem}»: {added} ficheros agregados" + (f", {missing} no encontrados" if missing else "")
        self._set("playout.message", msg)
        self._prefetch(force=True)
        self._publish()
        return {"added": added, "missing": missing}

    # ------------------------------------------------------------------ reloj
    def tick(self, dt: float = 0.05) -> None:
        if self.output.driven:                         # sin dispositivo: el audio avanza por tiempo
            self._frac += dt * SR
            frames = int(self._frac)
            self._frac -= frames
            while frames > 0:
                n = min(frames, 4410)
                self.engine.render(n)
                frames -= n
        self._drain()
        lv = self.engine.meter.levels()
        self.host.events.emit("audio.levels", {**lv, "simulated": self.output.simulated})
        self._prefetch()
        self._publish()
        self._publish_stream()

    def _prefetch(self, force: bool = False) -> None:
        now = time.time()
        if not force and now < self._prefetch_at:
            return
        self._prefetch_at = now + 0.5
        keep: set[str] = set()
        with self.engine.lock:
            for d in self.engine.decks.values():
                for it in d.queue[:2]:
                    keep.add(it["uid"])
                    self.engine.prefetch(it)
        self.engine.prune(keep)

    # ------------------------------------------------------------------ avisos del motor -> historial y comandos
    def _drain(self) -> None:
        notes = self.engine.notes
        while notes:
            deck, kind, data = notes.popleft()
            try:
                self._handle(deck, kind, data)
            except Exception:  # noqa: BLE001 - un aviso defectuoso no debe frenar al resto
                sdk.log.exception("aviso del motor falló: %s %s", deck, kind)

    def _handle(self, deck: str, kind: str, data: dict) -> None:
        if deck == "voice":                            # botonera / pisadores superpuestos
            if kind == "end":
                v = data["voice"]
                self._log(v.item, v.started, data["at"], int(v.pos * 1000 / SR), data.get("status", "completed"), "cart")
            return
        source = SOURCE_OF.get(deck, "live")
        if deck == "emision" and kind == "start":          # título y artista para los oyentes del streaming
            it = data["play"].item
            if it.get("file") == "audio":
                self.stream.set_song(it.get("artist"), it.get("title"))
        if kind == "end":
            play = data["play"]
            self._log(play.item, play.started, data["at"], play.played_ms, data["status"], source)
        elif kind == "instant":
            it = data["item"]
            self._log(it, data["at"], data["at"], 0, "completed", source)
        elif kind == "command":
            try:
                self.host.run_command(data["command"], data.get("args") or {})
            except Exception as exc:  # noqa: BLE001
                self._set("playout.message", f"El evento no pudo ejecutar «{data['command']}»: {exc}")
        elif kind == "failed":
            self._log(data["item"], data["at"], data["at"], 0, "failed", source)
            self._set("playout.message", f"No se pudo reproducir «{data['item']['title']}»: {data['error']}")
        elif kind == "idle" and deck == "emision":
            self._set("playout.message", "La emisión llegó al final de la lista.")

    def _log(self, item: dict, started: float, ended: float, played_ms: int, status: str, source: str) -> None:
        kw: dict[str, Any] = {"started_at": iso(started), "ended_at": iso(ended), "played_ms": played_ms,
                              "source": source, "status": status, "file_type": item["file"]}
        if item.get("id") is not None:
            kw["asset_id"] = item["id"]
        else:
            kw.update(kind=item["kind"], title=item["title"], artist=item.get("artist"))
        self.host.record_play(**kw)

    # ------------------------------------------------------------------ estado para la interfaz
    def _set(self, key: str, value: Any) -> None:
        if self._last.get(key) != value:
            self._last[key] = value
            self.host.set_state(key, value)

    @staticmethod
    def _now(deck: Any) -> dict | None:
        n = deck.now()
        if n:
            n["elapsed_ms"] = n["elapsed_ms"] // 1000 * 1000        # se publica una vez por segundo
        return n

    def _publish(self) -> None:
        with self.engine.lock:
            main = self.engine.decks["emision"]
            self._set("playout.now", self._now(main))
            self._set("playout.queue", [brief(i) for i in main.queue[:MAX_STATE_ITEMS]])
            self._set("playout.queue_total", len(main.queue))
            self._set("playout.playing", main.playing)
            self._set("playout.stop_after", main.stop_after)
            self._set("cart.active", self.engine.active_voice_ids())
            self._publish_meta()
            for n in range(1, 5):
                d = self.engine.decks[f"aux{n}"]
                self._set(f"aux.{n}", {"now": self._now(d), "queue": [brief(i) for i in d.queue[:MAX_STATE_ITEMS]],
                                       "playing": d.playing, "stop_after": d.stop_after})

    def _publish_meta(self) -> None:
        """Metadatos del fichero elegido en una lista; si no hay, del que suena o del primero de la Emisión."""
        item = None
        if self._selected:
            tgt, uid = self._selected
            d = self.engine.decks.get(tgt)
            if d is not None:
                item = next((i for i in d.queue if i["uid"] == uid), None)
                if item is None and d.current is not None and d.current.item["uid"] == uid:
                    item = d.current.item
        if item is None:
            main = self.engine.decks["emision"]
            item = main.current.item if main.current else (main.queue[0] if main.queue else None)
        key = (item["uid"],) if item else None
        if key == self._meta_key:
            return
        self._meta_key = key
        if item is None:
            self._set("meta.info", None)
            return
        info: dict[str, Any] = {"uid": item["uid"], "file": item["file"], "kind": item["kind"], "title": item["title"],
                                "artist": item.get("artist") or "", "album": "", "year": "", "genre": "",
                                "comment": "", "path": "", "cover": None}
        if item.get("id") is not None:
            try:
                path = self._asset(item["id"])["path"]
            except ValueError:
                path = ""
            if path and not path.startswith("demo://"):
                info["path"] = path
                tags = meta.read_tags(path)
                for k in ("album", "year", "genre", "comment"):
                    info[k] = tags[k]
                info["title"] = tags["title"] or info["title"]
                info["artist"] = tags["artist"] or info["artist"]
                info["cover"] = f"/api/cover/{item['id']}"
        self._set("meta.info", info)
