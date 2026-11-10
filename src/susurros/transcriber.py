"""Local speech-to-text with faster-whisper (GPU if CUDA is available, CPU otherwise)."""
from __future__ import annotations

import importlib.util
import logging
import os
import sys
from pathlib import Path
from typing import NamedTuple

import numpy as np

log = logging.getLogger("susurros.transcriber")


def _add_cuda_dll_dirs() -> None:
    """cuBLAS and cuDNN come as pip packages; their libraries must be made findable
    before CTranslate2 loads them."""
    if sys.platform.startswith("linux"):
        _preload_linux_cuda()
        return
    if sys.platform != "win32":
        return
    for module in ("nvidia.cublas", "nvidia.cudnn"):
        try:
            spec = importlib.util.find_spec(module)
        except ModuleNotFoundError:
            spec = None
        if not spec or not spec.submodule_search_locations:
            continue
        for location in spec.submodule_search_locations:
            bin_dir = Path(location) / "bin"
            if bin_dir.is_dir():
                os.add_dll_directory(str(bin_dir))
                os.environ["PATH"] = str(bin_dir) + os.pathsep + os.environ.get("PATH", "")


def _preload_linux_cuda() -> None:
    """On Linux the optional pip packages with cuBLAS and cuDNN are not on the library path.
    Loading them here first means CTranslate2 finds them already in the process."""
    import ctypes
    for module in ("nvidia.cublas", "nvidia.cudnn"):
        try:
            spec = importlib.util.find_spec(module)
        except ModuleNotFoundError:
            spec = None
        if not spec or not spec.submodule_search_locations:
            continue
        for location in spec.submodule_search_locations:
            for library in sorted((Path(location) / "lib").glob("lib*.so.*")):
                try:
                    ctypes.CDLL(str(library), mode=ctypes.RTLD_GLOBAL)
                except OSError:
                    log.info("Could not preload %s", library.name)


def _warm_up(model) -> None:
    """Two short passes. With the voice detector, so the first dictation does not pay for
    loading it; and without it, because the detector discards this quiet noise before it
    reaches the model, and only a real inference shows whether the GPU libraries load."""
    warmup = (np.random.default_rng(0).standard_normal(16_000) * 0.01).astype(np.float32)
    list(model.transcribe(warmup, language="es", beam_size=1, vad_filter=True)[0])
    list(model.transcribe(warmup, language="es", beam_size=1, vad_filter=False)[0])


class Transcript(NamedTuple):
    text: str
    language: str
    speech_seconds: float   # duration of the audio that contained speech, silences excluded
    doubtful: bool          # barely any speech detected: a short stock phrase will be made up


class Transcriber:
    def __init__(self, model_name: str = "large-v3-turbo"):
        self.model_name = model_name
        self.model = None
        self.device = ""

    def load(self) -> str:
        """Loads the model and runs a test pass. Returns "cuda" or "cpu"."""
        _add_cuda_dll_dirs()
        from faster_whisper import WhisperModel

        try:
            model = WhisperModel(self.model_name, device="cuda", compute_type="float16")
            _warm_up(model)   # the CUDA libraries are loaded at inference, not at construction
            self.model, self.device = model, "cuda"
        except Exception as exc:
            log.warning("GPU not available (%s); using the CPU", exc)
            model = WhisperModel(self.model_name, device="cpu", compute_type="int8")
            _warm_up(model)
            self.model, self.device = model, "cpu"
        log.info("Model %s loaded on %s", self.model_name, self.device)
        return self.device

    def transcribe(self, audio: np.ndarray, language: str = "",
                   vocabulary: list[str] | None = None) -> Transcript:
        if self.model is None:
            raise RuntimeError("The model is not loaded yet")
        prompt = None
        if vocabulary:
            prompt = ", ".join(vocabulary) + "."
        segments, info = self.model.transcribe(
            audio,
            language=language or None,
            beam_size=5,
            vad_filter=True,                               # trims silences: fewer hallucinations
            vad_parameters={"min_silence_duration_ms": 600},
            condition_on_previous_text=False,
            initial_prompt=prompt,
        )
        segments = list(segments)
        text = " ".join(seg.text.strip() for seg in segments).strip()
        # Doubtful: Whisper sees no clear speech in any segment (typical of its made-up phrases).
        doubtful = bool(segments) and all(
            seg.no_speech_prob > 0.6 or seg.avg_logprob < -1.0 for seg in segments)
        return Transcript(text, info.language, float(info.duration_after_vad), doubtful)

    def transcribe_words(self, audio: np.ndarray, language: str = "", prompt: str = "",
                         offset: float = 0.0, fast: bool = False
                         ) -> tuple[list[tuple[float, float, str]], str]:
        """Like `transcribe`, but returns (start, end, word) with `offset` added.
        `fast` uses greedy decoding: for the intermediate passes of live dictation."""
        if self.model is None:
            raise RuntimeError("The model is not loaded yet")
        segments, info = self.model.transcribe(
            audio, language=language or None, beam_size=1 if fast else 5, vad_filter=True,
            vad_parameters={"min_silence_duration_ms": 600}, condition_on_previous_text=False,
            initial_prompt=prompt or None, word_timestamps=True)
        words = [(w.start + offset, w.end + offset, w.word) for seg in segments for w in seg.words or []]
        return words, info.language


def create(model_name: str = "large-v3-turbo"):
    """The speech engine for this system: MLX first on macOS, faster-whisper everywhere else."""
    if sys.platform == "darwin":
        from .mac.transcriber import MacTranscriber
        return MacTranscriber(model_name)
    return Transcriber(model_name)
