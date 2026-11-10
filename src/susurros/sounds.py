"""Audio cues when recording starts and stops.

There are several sound sets to choose from in Settings. All are almost pure, low sines
with a rounded attack and low volume: no high harmonics, which is what makes a sound grate.
They are synthesised once and saved as WAV files in the data folder.
"""
from __future__ import annotations

import logging
import os
import sys
import wave
from pathlib import Path

import numpy as np

from .config import data_dir

log = logging.getLogger("susurros.sounds")
_RATE = 44_100
_VERSION = "v5"   # changes when the sounds are tweaked, to regenerate the saved WAVs
EVENTS = ("start", "stop", "lock", "cancel")
SETS = [("bubble", "Bubble"), ("chord", "Chord"), ("notes", "Two notes"), ("knock", "Knock")]
DEFAULT_SET = "bubble"


def _tone(f0: float, f1: float | None = None, *, seconds: float, attack: float, decay: float,
          glide: float = 0.06) -> np.ndarray:
    """Sine that fades in with a cosine, decays exponentially and, if `f1` is given, glides the pitch."""
    t = np.arange(int(_RATE * seconds)) / _RATE
    if f1 is None:
        freq = np.full_like(t, f0)
    else:
        freq = f1 + (f0 - f1) * np.exp(-t / (glide / 3))   # reaches f1 in about `glide` seconds
    phase = 2 * np.pi * np.cumsum(freq) / _RATE
    rise = 0.5 - 0.5 * np.cos(np.pi * np.minimum(1.0, t / attack))
    fade = np.minimum(1.0, (seconds - t) / min(0.03, seconds / 3))
    return np.sin(phase) * rise * np.exp(-t / decay) * fade


def _mix(parts: list[tuple[float, np.ndarray]], volume: float = 0.16) -> np.ndarray:
    total = max(start + len(tone) / _RATE for start, tone in parts)
    out = np.zeros(int(_RATE * total) + 1)
    for start, tone in parts:
        offset = int(_RATE * start)
        out[offset:offset + len(tone)] += tone
    return out / np.max(np.abs(out)) * volume


def _bubble(event: str) -> np.ndarray:
    """A short, round "pop" that rises on start and falls on stop."""
    pop = lambda a, b: _tone(a, b, seconds=0.16, attack=0.006, decay=0.05)
    return _mix({
        "start": [(0, pop(300, 600))],
        "stop": [(0, pop(600, 300))],
        "lock": [(0, pop(300, 600)), (0.12, pop(380, 760))],
        "cancel": [(0, pop(320, 200))],
    }[event])


def _chord(event: str) -> np.ndarray:
    """A very soft major chord that opens on start and closes on stop."""
    c4, e4, g4, c5 = 261.63, 329.63, 392.00, 523.25
    note = lambda f: _tone(f, seconds=0.55, attack=0.045, decay=0.2)
    return _mix({
        "start": [(0, note(c4)), (0.045, note(e4)), (0.09, note(g4))],
        "stop": [(0, note(g4)), (0.045, note(e4)), (0.09, note(c4))],
        "lock": [(0, note(c4)), (0.045, note(e4)), (0.09, note(g4)), (0.135, note(c5))],
        "cancel": [(0, note(c4))],
    }[event], volume=0.14)


def _notes(event: str) -> np.ndarray:
    """Two low notes in a row."""
    e4, g4, c5, e5 = 329.63, 392.00, 523.25, 659.25
    note = lambda f: _tone(f, seconds=0.32, attack=0.025, decay=0.11)
    return _mix({
        "start": [(0, note(g4)), (0.10, note(c5))],
        "stop": [(0, note(c5)), (0.10, note(g4))],
        "lock": [(0, note(g4)), (0.09, note(c5)), (0.18, note(e5))],
        "cancel": [(0, note(e4))],
    }[event])


def _knock(event: str) -> np.ndarray:
    """A dull little knock, like tapping on wood."""
    knock = lambda f: _tone(f * 1.5, f, seconds=0.11, attack=0.003, decay=0.028, glide=0.02)
    return _mix({
        "start": [(0, knock(230))],
        "stop": [(0, knock(175))],
        "lock": [(0, knock(230)), (0.10, knock(230))],
        "cancel": [(0, knock(130))],
    }[event], volume=0.2)


_RENDERERS = {"bubble": _bubble, "chord": _chord, "notes": _notes, "knock": _knock}


def _path(sound_set: str, event: str) -> Path:
    if sound_set not in _RENDERERS:
        sound_set = DEFAULT_SET
    folder = data_dir() / "sounds"
    folder.mkdir(exist_ok=True)
    path = folder / f"{sound_set}-{event}-{_VERSION}.wav"
    if not path.exists() or path.stat().st_size < 100:
        for old in folder.glob("*.wav"):          # leftovers from earlier versions
            if not old.name.endswith(f"-{_VERSION}.wav"):
                old.unlink(missing_ok=True)
        samples = (_RENDERERS[sound_set](event) * 32767).astype("<i2")
        partial = path.with_suffix(".tmp")        # written aside: a half-written WAV is never left
        with wave.open(str(partial), "wb") as wav:
            wav.setnchannels(1)
            wav.setsampwidth(2)
            wav.setframerate(_RATE)
            wav.writeframes(samples.tobytes())
        os.replace(partial, path)
    return path


def play(event: str, sound_set: str = DEFAULT_SET) -> None:
    if sys.platform == "darwin":
        try:
            from .mac import system
            system.play_sound(str(_path(sound_set, event)))
        except Exception:
            log.warning("Could not play sound %s/%s", sound_set, event, exc_info=True)
        return
    if sys.platform != "win32":
        return
    import winsound
    try:
        winsound.PlaySound(str(_path(sound_set, event)),
                           winsound.SND_FILENAME | winsound.SND_ASYNC | winsound.SND_NODEFAULT)
    except Exception:
        # An audio cue must never bring down a dictation (disk full, folder without permissions…).
        log.warning("Could not play sound %s/%s", sound_set, event, exc_info=True)
