"""Console utilities for installing and diagnosing.

  susurros-cli icon PATH.ico        writes the icon (used by the installer)
  susurros-cli transcribe AUDIO.wav transcribes and cleans a 16 kHz mono WAV
  susurros-cli shots FOLDER         renders the UI to PNG with sample data
  susurros-cli iconset FOLDER       writes the PNGs of a macOS icon set (used by the macOS build)
  susurros-cli smoke FOLDER         starts the real app for a moment and reports how it went

SUSURROS_MODEL picks another Whisper model for `transcribe` and `smoke` (e.g. "tiny");
SUSURROS_LANGUAGE, the language `transcribe` expects (Spanish by default).
"""
from __future__ import annotations

import os
import sys
import time
import wave
from pathlib import Path

import numpy as np


def _icon(path: str) -> int:
    from PySide6.QtGui import QGuiApplication
    from .ui import theme
    _app = QGuiApplication.instance() or QGuiApplication([])
    ok = theme.make_pixmap(256).save(path, "ICO")
    return 0 if ok else 1


def _read_wav(path: str) -> np.ndarray:
    with wave.open(path, "rb") as wav:
        if wav.getframerate() != 16_000 or wav.getnchannels() != 1 or wav.getsampwidth() != 2:
            raise SystemExit("The WAV must be 16 kHz, mono and 16-bit")
        frames = wav.readframes(wav.getnframes())
    return np.frombuffer(frames, dtype=np.int16).astype(np.float32) / 32768


def _transcribe(path: str) -> int:
    from . import cleaner, config
    from .transcriber import create
    audio = _read_wav(path)
    transcriber = create(os.environ.get("SUSURROS_MODEL") or config.DEFAULTS["model"])
    t0 = time.monotonic()
    device = transcriber.load()
    print(f"model loaded on {device} ({time.monotonic() - t0:.1f}s)")
    t0 = time.monotonic()
    raw, language, _speech, _doubtful = transcriber.transcribe(audio, os.environ.get("SUSURROS_LANGUAGE", "es"))
    print(f"{len(audio) / 16000:.1f}s of audio transcribed in {time.monotonic() - t0:.2f}s [{language}]")
    print("raw:", raw)
    t0 = time.monotonic()
    result = cleaner.clean(raw, api_key=config.get_api_key(allow_env=True))
    print(f"clean ({result.engine}, {time.monotonic() - t0:.2f}s):", result.text, result.note)
    return 0


def _shots(folder: str) -> int:
    import tempfile
    scratch = tempfile.TemporaryDirectory(prefix="susurros-shots-")
    os.environ["SUSURROS_DATA_DIR"] = scratch.name
    from PySide6.QtWidgets import QApplication
    from . import i18n
    from .db import Store
    from .hotkey import combo_name, parse_keys
    from .i18n import tr
    from .ui.main_window import MainWindow
    from .ui.pill import Pill

    i18n.set_language(os.environ.get("SUSURROS_SHOTS_LANG", "en"))
    out = Path(folder)
    out.mkdir(parents=True, exist_ok=True)
    app = QApplication.instance() or QApplication([])
    store = Store()
    samples = [
        ("Quedamos el miércoles a las diez para revisar la propuesta antes de enviársela al cliente.", 7.2, "OUTLOOK", "claude"),
        ("Añade un índice sobre la columna created_at y vuelve a lanzar la migración.", 5.1, "Code", "claude"),
        ("Vale, perfecto.", 1.4, "slack", "rules"),
        ("Recuérdame que mañana tengo que llamar al gestor para lo de las facturas del trimestre.", 6.3, "chrome", "claude"),
    ]
    if i18n.language() == "en":
        samples = [
            ("Let's meet on Wednesday at ten to go over the proposal before we send it to the client.", 7.2, "OUTLOOK", "claude"),
            ("Add an index on the created_at column and run the migration again.", 5.1, "Code", "claude"),
            ("Sounds good, thanks.", 1.4, "slack", "rules"),
            ("Remind me to call the accountant tomorrow about this quarter's invoices.", 6.3, "chrome", "claude"),
        ]
    for text, seconds, app_name, engine in reversed(samples):
        words = len(text.split())
        store.add_transcription(text, duration_s=seconds, app=app_name, engine=engine, mode="hold",
                                raw_words=words + 3, fillers=1, fixes=3)
    for word in ("PySide", "kubectl", "Whisper"):
        store.add_word(word)
    keys = parse_keys(store.get("hotkey_keys") or store.get("hotkey_vk"))
    window = MainWindow(store, combo_name(keys, tr, store.get("hotkey_name")))
    ready = tr("Ready to dictate · {device}", device="GPU")
    window.set_status(ready, "ok")
    window.resize(980, 680)
    for mode in ("dark", "light"):
        window.set_theme(mode)
        window.set_status(ready, "ok")
        for index, name in enumerate(("history", "insights", "dictionary", "settings")):
            window.set_page(index)
            window.resize(980, 680)
            window.refresh_history(force=True)
            app.processEvents()
            window.grab().save(str(out / (f"{name}.png" if mode == "dark" else f"{name}-light.png")))
    pill = Pill()
    for state in ("idle", "recording", "locked", "processing"):
        pill.state = state
        pill._level, pill._bars = 0.7, list(0.25 + abs(np.sin(np.arange(9) * 0.9)) * 0.7)
        pill.grab().save(str(out / f"pill-{state}.png"))
    pill.position, pill.state = "left", "recording"
    pill._layout()
    pill.grab().save(str(out / "pill-vertical.png"))
    pill.state, pill._hover = "idle", True
    pill._layout()
    pill._controls.grab().save(str(out / "pill-controls-vertical.png"))
    pill.position = "bottom"
    pill._layout()
    pill._controls.grab().save(str(out / "pill-controls.png"))
    pill.collapsed, pill._hover = True, False
    pill._layout()
    pill.grab().save(str(out / "pill-sliver.png"))
    pill.collapsed = False
    pill._layout()
    pill._controls.hide()
    pill._caption.show_text(tr("Nothing heard"), pill.geometry(), "bottom")
    pill._caption.grab().save(str(out / "pill-caption.png"))
    pill._caption.hide()
    overlay = pill._overlay
    overlay.active = "top"
    overlay.open(app.primaryScreen())
    overlay.grab().save(str(out / "overlay.png"))
    overlay.hide()
    print("screenshots in", out)
    store.close()
    scratch.cleanup()
    return 0


def _iconset(folder: str) -> int:
    """The sizes `iconutil` expects, each one also at double resolution."""
    from PySide6.QtGui import QGuiApplication
    from .ui import theme
    _app = QGuiApplication.instance() or QGuiApplication([])
    out = Path(folder)
    out.mkdir(parents=True, exist_ok=True)
    ok = True
    for size in (16, 32, 128, 256, 512):
        ok &= theme.make_pixmap(size).save(str(out / f"icon_{size}x{size}.png"), "PNG")
        ok &= theme.make_pixmap(size * 2).save(str(out / f"icon_{size}x{size}@2x.png"), "PNG")
    return 0 if ok else 1


def _smoke(folder: str) -> int:
    """Starts the whole app on a throwaway profile, waits for the speech model, saves what the
    window and the indicator look like plus a short report, and quits. For the build checks:
    it exercises the packaged app on a real desktop, which the unit tests cannot."""
    import logging
    import tempfile
    scratch = tempfile.TemporaryDirectory(prefix="susurros-smoke-", ignore_cleanup_errors=True)
    os.environ["SUSURROS_DATA_DIR"] = scratch.name
    from PySide6.QtCore import QTimer
    from PySide6.QtWidgets import QApplication
    from . import config
    from .app import Controller
    from .db import Store

    out = Path(folder)
    out.mkdir(parents=True, exist_ok=True)
    config.setup_logging()
    seed = Store()
    seed.set("model", os.environ.get("SUSURROS_MODEL") or config.DEFAULTS["model"])
    seed.set("ui_language", "en")
    seed.close()
    app = QApplication.instance() or QApplication([])
    app.setQuitOnLastWindowClosed(False)
    controller = Controller(app)
    started = time.monotonic()
    outcome = {"code": 1}

    def finish() -> None:
        ready = controller.model_ready
        if not ready and not controller.model_error and time.monotonic() - started < 600:
            return
        poll.stop()
        app.processEvents()
        controller.window.grab().save(str(out / "window.png"))
        controller.window.set_page(3)
        app.processEvents()
        controller.window.grab().save(str(out / "settings.png"))
        controller.pill.show_recording()
        app.processEvents()
        controller.pill.grab().save(str(out / "pill.png"))
        hotkey = controller.hotkey
        report = [
            f"platform: {sys.platform} ({app.platformName()})",
            f"model ready: {ready}  device: {getattr(controller, '_device', '')}  error: {controller.model_error}",
            f"shortcut: {controller._hotkey_name()}",
            f"listener installed: {hotkey.installed}  failed: {hotkey.failed}  "
            f"missing permission: {hotkey.needs_permission or 'none'}",
            f"tray visible: {controller.tray.isVisible()}",
            f"seconds: {time.monotonic() - started:.1f}",
        ]
        (out / "report.txt").write_text("\n".join(report) + "\n", encoding="utf-8")
        print("\n".join(report))
        outcome["code"] = 0 if ready else 1
        QTimer.singleShot(1500, controller.quit)   # leaves the listener a moment to report its state

    poll = QTimer(interval=500, timeout=finish)
    poll.start()
    app.exec()
    log_file = config.data_dir() / "susurros.log"
    if log_file.exists():
        (out / "susurros.log").write_text(log_file.read_text(encoding="utf-8"), encoding="utf-8")
    logging.shutdown()
    scratch.cleanup()
    return outcome["code"]


def main() -> None:
    args = sys.argv[1:]
    commands = {"icon": _icon, "transcribe": _transcribe, "shots": _shots, "iconset": _iconset,
                "smoke": _smoke}
    if len(args) != 2 or args[0] not in commands:
        print(__doc__)
        sys.exit(2)
    sys.exit(commands[args[0]](args[1]))


if __name__ == "__main__":
    main()
