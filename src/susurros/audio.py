"""Microphone capture at 16 kHz mono, which is what Whisper expects."""
from __future__ import annotations

import logging
import threading

import numpy as np
from PySide6.QtCore import QObject, Signal

SAMPLE_RATE = 16_000
log = logging.getLogger("susurros.audio")


def input_devices() -> list[str]:
    """Names of the microphones of the default audio API (no duplicates)."""
    try:
        import sounddevice as sd
        default_api = sd.default.hostapi
        names = []
        for dev in sd.query_devices():
            if dev["max_input_channels"] > 0 and dev["hostapi"] == default_api:
                if dev["name"] not in names:
                    names.append(dev["name"])
        return names
    except Exception:
        log.exception("Could not list the microphones")
        return []


def has_input() -> bool:
    """Is there any microphone that Windows offers as an input?"""
    try:
        import sounddevice as sd
        return sd.query_devices(kind="input")["max_input_channels"] > 0
    except Exception:
        return False


def _resolve_device(name: str) -> int | None:
    if not name:
        return None
    import sounddevice as sd
    for index, dev in enumerate(sd.query_devices()):
        if dev["name"] == name and dev["max_input_channels"] > 0 and dev["hostapi"] == sd.default.hostapi:
            return index
    return None  # the saved microphone is gone: the default one is used


class Recorder(QObject):
    level = Signal(float)  # 0..1, to animate the pill

    def __init__(self, parent: QObject | None = None):
        super().__init__(parent)
        self._stream = None
        self._chunks: list[np.ndarray] = []
        self._rate = SAMPLE_RATE
        self._lock = threading.Lock()

    @property
    def recording(self) -> bool:
        return self._stream is not None

    def start(self, device_name: str = "") -> None:
        import sounddevice as sd
        if self._stream is not None:
            return
        self._chunks = []
        try:
            self._open(device_name)
        except sd.PortAudioError:
            # PortAudio fixes its device list at start-up: if a microphone has been plugged in
            # or removed since then, it has to be restarted and tried again.
            log.info("Could not open the microphone; restarting PortAudio and retrying")
            sd._terminate()
            sd._initialize()
            self._open(device_name)

    def _open(self, device_name: str) -> None:
        import sounddevice as sd
        device = _resolve_device(device_name)

        def callback(indata, frames, time_info, status):
            mono = indata[:, 0].copy()
            with self._lock:
                self._chunks.append(mono)
            rms = float(np.sqrt(np.mean(mono * mono))) if len(mono) else 0.0
            self.level.emit(min(1.0, (rms * 14) ** 0.7))

        try:
            self._rate = SAMPLE_RATE
            stream = sd.InputStream(samplerate=SAMPLE_RATE, channels=1, dtype="float32",
                                    device=device, blocksize=256, latency="low", callback=callback)
        except sd.PortAudioError:
            # The device does not accept 16 kHz: record at its own rate and resample on stop.
            info = sd.query_devices(device if device is not None else sd.default.device[0])
            self._rate = int(info["default_samplerate"])
            stream = sd.InputStream(samplerate=self._rate, channels=1, dtype="float32",
                                    device=device, blocksize=768, latency="low", callback=callback)
        stream.start()
        self._stream = stream

    def stop(self) -> np.ndarray:
        """Closes the microphone and returns the audio as float32 at 16 kHz."""
        stream, self._stream = self._stream, None
        if stream is not None:
            try:
                stream.stop()
                stream.close()
            except Exception:
                log.exception("Error closing the microphone")
        return self._collect(clear=True)

    def snapshot(self) -> np.ndarray:
        """Copy of what has been recorded so far, without stopping the recording."""
        return self._collect(clear=False)

    def _collect(self, clear: bool) -> np.ndarray:
        with self._lock:
            chunks = list(self._chunks)
            if clear:
                self._chunks = []
        if not chunks:
            return np.zeros(0, dtype=np.float32)
        audio = np.concatenate(chunks)
        if self._rate != SAMPLE_RATE:
            n_out = int(len(audio) * SAMPLE_RATE / self._rate)
            audio = np.interp(np.linspace(0, len(audio) - 1, n_out),
                              np.arange(len(audio)), audio).astype(np.float32)
        return audio
