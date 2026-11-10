"""Speech-to-text on Apple Silicon with MLX (the Mac's GPU), falling back to the shared
faster-whisper engine on the CPU when MLX cannot be used.

faster-whisper has no GPU support on a Mac, so the same Whisper model runs through
mlx-whisper instead. Silences are cut out first with the same voice detector the Windows
engine uses, which is what keeps Whisper from making up text over a quiet recording.
"""
from __future__ import annotations

import logging
import platform
import subprocess
import sys

import numpy as np

from ..transcriber import Transcriber, Transcript

log = logging.getLogger("susurros.mac.transcriber")
RATE = 16_000
PROBE_FLAG = "--probe-mlx"
_REPOS = {"large-v3-turbo": "mlx-community/whisper-large-v3-turbo", "tiny": "mlx-community/whisper-tiny"}
_FALLBACK_TEMPERATURES = (0.0, 0.2, 0.4, 0.6, 0.8, 1.0)


def probe() -> int:
    """Runs one small computation on the GPU. Called in a separate process (see `mlx_usable`)."""
    import mlx.core as mx
    mx.eval(mx.ones((8, 8)) @ mx.ones((8, 8)))
    return 0


def mlx_usable() -> bool:
    """Whether MLX works on this Mac. Checked in a child process, because where MLX cannot
    reach the GPU it does not raise an error: it ends the whole process."""
    if platform.machine() != "arm64":
        return False
    command = [sys.executable, PROBE_FLAG] if getattr(sys, "frozen", False) \
        else [sys.executable, "-m", "susurros", PROBE_FLAG]
    try:
        return subprocess.run(command, timeout=120, capture_output=True).returncode == 0
    except Exception:
        log.warning("The MLX check did not finish", exc_info=True)
        return False


def speech_spans(audio: np.ndarray) -> list[tuple[int, int]]:
    """(first sample, last sample) of every stretch of the recording that contains speech."""
    from faster_whisper.vad import VadOptions, get_speech_timestamps
    found = get_speech_timestamps(audio, VadOptions(min_silence_duration_ms=600))
    return [(int(span["start"]), int(span["end"])) for span in found]


def restore_time(seconds: float, spans: list[tuple[int, int]]) -> float:
    """Converts a time measured on the audio with the silences removed back to the recording."""
    passed = 0.0
    for start, end in spans:
        length = (end - start) / RATE
        if seconds <= passed + length:
            return start / RATE + (seconds - passed)
        passed += length
    return spans[-1][1] / RATE if spans else seconds


class MlxTranscriber:
    def __init__(self, model_name: str = "large-v3-turbo"):
        self.repo = _REPOS.get(model_name, f"mlx-community/whisper-{model_name}-mlx")
        self._mlx = None

    def load(self) -> str:
        import mlx_whisper
        self._mlx = mlx_whisper
        warmup = (np.random.default_rng(0).standard_normal(RATE) * 0.01).astype(np.float32)
        speech_spans(warmup)                                   # loads the voice detector
        self._run(warmup, "es", "", words=True, fast=True)     # downloads and loads the model
        log.info("Model %s loaded with MLX", self.repo)
        return "mlx"

    def _run(self, audio: np.ndarray, language: str, prompt: str, *, words: bool, fast: bool) -> dict:
        return self._mlx.transcribe(
            audio, path_or_hf_repo=self.repo, language=language or None, initial_prompt=prompt or None,
            condition_on_previous_text=False, word_timestamps=words, verbose=None,
            # mlx-whisper decodes greedily; a low-confidence result is retried at higher temperatures
            temperature=0.0 if fast else _FALLBACK_TEMPERATURES)

    def _speech(self, audio: np.ndarray) -> tuple[np.ndarray, list[tuple[int, int]]]:
        spans = speech_spans(audio)
        if not spans:
            return audio[:0], spans
        return np.concatenate([audio[start:end] for start, end in spans]), spans

    def transcribe(self, audio: np.ndarray, language: str = "",
                   vocabulary: list[str] | None = None) -> Transcript:
        if self._mlx is None:
            raise RuntimeError("The model is not loaded yet")
        speech, spans = self._speech(audio)
        if not spans:
            return Transcript("", language, 0.0, False)
        prompt = ", ".join(vocabulary) + "." if vocabulary else ""
        result = self._run(speech, language, prompt, words=False, fast=False)
        segments = result["segments"]
        text = " ".join(seg["text"].strip() for seg in segments).strip()
        doubtful = bool(segments) and all(
            seg["no_speech_prob"] > 0.6 or seg["avg_logprob"] < -1.0 for seg in segments)
        return Transcript(text, result["language"] or language, len(speech) / RATE, doubtful)

    def transcribe_words(self, audio: np.ndarray, language: str = "", prompt: str = "",
                         offset: float = 0.0, fast: bool = False
                         ) -> tuple[list[tuple[float, float, str]], str]:
        if self._mlx is None:
            raise RuntimeError("The model is not loaded yet")
        speech, spans = self._speech(audio)
        if not spans:
            return [], language
        result = self._run(speech, language, prompt, words=True, fast=fast)
        words = [(restore_time(w["start"], spans) + offset, restore_time(w["end"], spans) + offset, w["word"])
                 for seg in result["segments"] for w in seg.get("words") or []]
        return words, result["language"] or language


class MacTranscriber:
    """MLX when this Mac can run it; otherwise the shared faster-whisper engine on the CPU."""

    def __init__(self, model_name: str = "large-v3-turbo"):
        self._model_name = model_name
        self._engine: MlxTranscriber | Transcriber | None = None

    def load(self) -> str:
        if mlx_usable():
            try:
                engine = MlxTranscriber(self._model_name)
                device = engine.load()
                self._engine = engine
                return device
            except Exception:
                log.warning("MLX could not load the model; using the CPU", exc_info=True)
        else:
            log.info("MLX is not available on this Mac; using the CPU")
        engine = Transcriber(self._model_name)
        device = engine.load()
        self._engine = engine
        return device

    def _loaded(self) -> MlxTranscriber | Transcriber:
        if self._engine is None:
            raise RuntimeError("The model is not loaded yet")
        return self._engine

    def transcribe(self, audio: np.ndarray, language: str = "",
                   vocabulary: list[str] | None = None) -> Transcript:
        return self._loaded().transcribe(audio, language, vocabulary)

    def transcribe_words(self, audio: np.ndarray, language: str = "", prompt: str = "",
                         offset: float = 0.0, fast: bool = False
                         ) -> tuple[list[tuple[float, float, str]], str]:
        return self._loaded().transcribe_words(audio, language, prompt, offset=offset, fast=fast)
