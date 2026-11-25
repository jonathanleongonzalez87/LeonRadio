"""Pruebas del motor de audio SIN dispositivo: todo se renderiza en memoria y es determinista."""

import wave
from datetime import datetime, timezone

import numpy as np
import pytest

from leonradio_core.engine import (AUDIO, Engine, FileSource, Source, audio_file, event_file, other_file)
from leonradio_core.engine.files import copy_of, from_template
from leonradio_core.engine.sources import SAMPLE_RATE as SR


class Const(Source):
    """Fuente de amplitud constante: permite comprobar las ganancias exactas de las rampas."""

    def __init__(self, frames, value):
        self.duration_frames, self.value, self.pos = frames, value, 0

    def read(self, n):
        n = max(0, min(n, self.duration_frames - self.pos))
        self.pos += n
        return np.full((n, 2), self.value, np.float32)


def item(title, seconds, kind="music", **extra):
    return audio_file({"id": None, "kind": kind, "title": title, "artist": None,
                       "duration_ms": int(seconds * 1000), "path": None, **extra})


def make(value=0.5, master=1.0, crossfade_ms=2000):
    eng = Engine(crossfade_ms=crossfade_ms, master=master)
    eng.load = lambda it, block=True: Const(int(it["duration_ms"] * SR / 1000), value)   # antes de crear decks
    return eng, eng.deck("emision")


def run(eng, seconds, block=441):
    """Renderiza `seconds` y devuelve la mezcla concatenada."""
    out = [eng.render(block) for _ in range(int(seconds * SR / block))]
    return np.concatenate(out)


def notes(eng):
    out = []
    while eng.notes:
        out.append(eng.notes.popleft())
    return out


def starts_ends(ns):
    return [(k, d["play"].item["title"]) for _, k, d in ns if k in ("start", "end")]


def test_plays_in_order_with_exact_duration_and_no_gap():
    eng, deck = make()
    deck.add(item("A", 1, "jingle")); deck.add(item("B", 1, "jingle"))     # jingles: sin superposición
    deck.play()
    mix = run(eng, 2.5)
    ns = notes(eng)
    assert starts_ends(ns) == [("start", "A"), ("end", "A"), ("start", "B"), ("end", "B")]
    ends = [d["play"].played_ms for _, k, d in ns if k == "end"]
    assert ends == [1000, 1000]                                           # duración exacta
    assert np.allclose(mix[441: 2 * SR], 0.5) and np.allclose(mix[2 * SR:], 0)   # sin hueco entre A y B (el 1.er bloque sube sin clic)
    assert ("emision", "idle", {}) in ns


def test_crossfade_between_songs_is_equal_power_and_starts_on_time():
    eng, deck = make(value=0.5, crossfade_ms=2000)
    deck.add(item("A", 10)); deck.add(item("B", 10))
    deck.play()
    m = run(eng, 12)
    t = lambda s: int(s * SR)
    assert np.allclose(m[t(7.9)], 0.5, atol=1e-3)                         # antes del solape: solo A
    mid = m[t(9.0)][0]                                                    # mitad del solape: 0,5*(sin(pi/4)+cos(pi/4))
    assert mid == pytest.approx(0.5 * np.sqrt(2), abs=0.01)
    assert np.allclose(m[t(10.5)], 0.5, atol=1e-3)                        # después: solo B
    assert m.max() <= 0.5 * np.sqrt(2) + 1e-3
    assert starts_ends(notes(eng))[:3] == [("start", "A"), ("start", "B"), ("end", "A")]


def test_outro_marker_sets_when_next_enters():
    eng, deck = make(crossfade_ms=500)
    deck.add(item("A", 10, outro_ms=7000)); deck.add(item("B", 10))        # B entra a los 7 s (3 s de solape)
    deck.play()
    started_at = None
    for i in range(int(8 * SR / 441)):
        eng.render(441)
        for _, k, d in notes(eng):
            if k == "start" and d["play"].item["title"] == "B" and started_at is None:
                started_at = i * 441 / SR
    assert started_at == pytest.approx(7.0, abs=0.02)


def test_skip_fades_out_and_logs_skipped():
    eng, deck = make()
    deck.add(item("A", 10)); deck.add(item("B", 10))
    deck.play()
    run(eng, 1)
    notes(eng)
    deck.skip()
    run(eng, 0.5)
    ns = notes(eng)
    kinds = starts_ends(ns)
    assert ("start", "B") in kinds and ("end", "A") in kinds
    end_a = next(d for _, k, d in ns if k == "end")
    assert end_a["status"] == "skipped"


def test_pause_resume_freezes_position_without_click():
    eng, deck = make()
    deck.add(item("A", 5)); deck.play()
    run(eng, 1)
    deck.pause()
    eng.render(441)                                                       # bloque de rampa a cero
    pos = deck.current.pos
    silent = run(eng, 0.5)
    assert np.allclose(silent, 0) and deck.current.pos == pos
    deck.play()
    assert run(eng, 0.2)[-1][0] == pytest.approx(0.5)
    assert deck.current.pos > pos


def test_ducking_lowers_music_while_a_voice_plays_then_recovers():
    eng, deck = make(value=0.4)
    deck.add(item("Musica", 30)); deck.play()
    run(eng, 1)
    eng.fire(item("Pisador", 1, "pisador"), duck_db=-12.0)
    during = run(eng, 1)                                                  # la voz dura 1 s
    assert eng.ducking_db < -3                                            # ya bajó
    tail = run(eng, 2.5)
    assert eng.ducking_db > -1.5                                          # y se recupera
    # la música sola durante la voz queda por debajo de 0,4 (más la voz): comprobamos el mínimo de ganancia
    assert during[SR // 2:].mean() < 0.4 + 0.4                            # sin saturar
    assert tail[-1][0] == pytest.approx(0.4, abs=0.02)


def test_events_pause_marker_command_and_other():
    eng, deck = make()
    deck.add(item("A", 1, "jingle"))
    deck.add(event_file("pause", "Pausa 2 s", seconds=2))
    deck.add(event_file("marker", "Inicio de tanda"))
    deck.add(event_file("command", "Siguiente aux", command="aux.next", args={"n": 1}))
    deck.add(other_file("note", "Nota para el locutor"))
    deck.add(item("B", 1, "jingle"))
    deck.play()
    mix = run(eng, 4.5)
    ns = notes(eng)
    # A (1 s) + pausa (2 s) en silencio + B (1 s)
    assert np.allclose(mix[441: SR], 0.5) and np.allclose(mix[SR: 3 * SR], 0) and np.allclose(mix[3 * SR: 4 * SR], 0.5)
    instants = [d["item"]["title"] for _, k, d in ns if k == "instant"]
    assert instants == ["Inicio de tanda", "Siguiente aux", "Nota para el locutor"]
    assert [d["command"] for _, k, d in ns if k == "command"] == ["aux.next"]
    assert ("start", "Pausa 2 s") in starts_ends(ns)


def test_wait_until_holds_in_silence_until_the_minute():
    clock = {"minute": 10}
    eng, deck = make()
    deck.clock = lambda: datetime(2026, 1, 1, 12, clock["minute"], tzinfo=timezone.utc)
    deck.add(event_file("wait_until", "Esperar :30", minute=30)); deck.add(item("A", 1, "jingle"))
    deck.play()
    assert np.allclose(run(eng, 3), 0)
    assert deck.current.item["title"] == "Esperar :30"
    clock["minute"] = 30
    assert run(eng, 0.5)[-1][0] == pytest.approx(0.5)                      # liberó y suena A


def test_missing_file_is_reported_and_the_list_continues(tmp_path):
    eng = Engine()
    deck = eng.deck("emision")
    deck.add(item("Falta", 1, "jingle", path=str(tmp_path / "no-existe.mp3")))
    deck.add(item("Sintetico", 1, "jingle"))
    deck.play()
    run(eng, 0.1)
    ns = notes(eng)
    failed = [d for _, k, d in ns if k == "failed"]
    assert len(failed) == 1 and "no existe" in failed[0]["error"]
    assert ("start", "Sintetico") in starts_ends(ns)


def test_meter_scale_matches_the_vu_face():
    eng, deck = make(value=0.125)                                          # -18 dBFS = 0 VU
    deck.add(item("A", 3, "jingle")); deck.play()
    run(eng, 1)
    assert eng.meter.levels()["l"] == pytest.approx(0.8, abs=0.01)


def test_decks_mix_together_and_master_applies():
    eng, deck = make(value=0.2, master=0.5)
    aux = eng.deck("aux1")
    deck.add(item("A", 2, "jingle")); aux.add(item("X", 2, "jingle"))
    deck.play(); aux.play()
    assert run(eng, 1)[-1][0] == pytest.approx((0.2 + 0.2) * 0.5)


def test_files_model_and_templates():
    a = item("T", 1)
    assert a["file"] == AUDIO and a["event"] is None and copy_of(a)["uid"] != a["uid"]
    e = from_template("pausa-5s")
    assert e["file"] == "event" and e["duration_ms"] == 5000 and e["event"]["type"] == "pause"
    assert from_template("nota-locutor")["file"] == "other"
    with pytest.raises(ValueError):
        event_file("inventado", "x")


def test_real_decoding_handles_accented_folders(tmp_path):
    pytest.importorskip("miniaudio")
    folder = tmp_path / "Música" / "década 20s"                           # tildes: fallaba al abrir por ruta
    folder.mkdir(parents=True)
    path = folder / "Tono ¡Ay!.wav"
    t = np.arange(11025) / 22050
    pcm = (0.5 * 32767 * np.sin(2 * np.pi * 440 * t)).astype("<i2")
    with wave.open(str(path), "wb") as w:
        w.setnchannels(1); w.setsampwidth(2); w.setframerate(22050); w.writeframes(pcm.tobytes())
    src = FileSource.load(path)
    assert src.duration_frames == pytest.approx(22050, abs=50)            # 0,5 s remuestreado a 44,1 kHz estéreo
    blk = src.read(1000)
    assert blk.shape == (1000, 2) and abs(blk).max() > 0.1
    eng = Engine()
    deck = eng.deck("emision")
    deck.add(audio_file({"id": 1, "kind": "jingle", "title": "Tono", "artist": None, "duration_ms": 500,
                         "path": str(path)}))
    deck.play()
    assert abs(eng.render(2000)).max() > 0.05                              # suena de verdad desde el archivo
