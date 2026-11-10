"""Ties together hotkey, microphone, transcription, cleanup, pasting and history."""
from __future__ import annotations

import logging
import queue
import sys
import threading
import time

import numpy as np
from PySide6.QtCore import QEvent, QObject, Qt, QTimer, Signal
from PySide6.QtGui import QAction, QCursor
from PySide6.QtNetwork import QLocalServer, QLocalSocket
from PySide6.QtWidgets import QApplication, QMenu, QSystemTrayIcon

from . import cleaner, config, i18n, injector, sounds
from .audio import SAMPLE_RATE, Recorder, has_input
from .db import Store
from .streaming import StreamState, Word
from .hotkey import HOLD_MS, VK_ESCAPE, TapMachine, combo_name, create_listener, normalize_combo, parse_keys
from .i18n import tr
from .transcriber import create as create_transcriber
from .ui import theme
from .ui.main_window import MainWindow
from .ui.pill import Pill

log = logging.getLogger("susurros.app")

MIN_SECONDS = 0.35          # below this there is nothing to transcribe
SILENCE_PEAK = 0.012        # highest peak of a silent recording
NOTHING_HEARD_MS = 1200     # short notice: the indicator goes back to rest right away
MAX_SECONDS = 20 * 60       # a forgotten hands-free session ends on its own
SERVER_NAME = "susurros-single-instance"


class Worker(QObject):
    """Loads the model and processes dictations on its own thread, one at a time."""
    modelReady = Signal(str)
    modelFailed = Signal(str)
    finished = Signal(dict)
    liveChunk = Signal(int, str)   # session, newly confirmed text ("" if none yet)

    def __init__(self, model_name: str):
        super().__init__()
        self._transcriber = create_transcriber(model_name)
        self._live: tuple[int, StreamState] = (0, StreamState())
        self._jobs: queue.Queue[dict | None] = queue.Queue()
        self._thread = threading.Thread(target=self._run, name="transcriber", daemon=True)

    def start(self) -> None:
        self._thread.start()

    def submit(self, job: dict) -> None:
        self._jobs.put(job)

    def stop(self) -> None:
        """Asks the thread to finish after the current job and gives it a moment to do so."""
        self._jobs.put(None)
        if self._thread.is_alive():
            self._thread.join(timeout=3)

    def _run(self) -> None:
        try:
            self.modelReady.emit(self._transcriber.load())
        except Exception as exc:
            log.exception("Could not load the model")
            self.modelFailed.emit(str(exc))
            return
        while (job := self._jobs.get()) is not None:
            if job.get("kind") in ("tick", "final"):
                self._run_live(job)
                continue
            result = {**job, "audio": None, "text": "", "raw": "", "engine": "", "note": "", "error": ""}
            try:
                started = time.monotonic()
                raw, language, speech, doubtful = self._transcriber.transcribe(
                    job["audio"], job["language"], job["vocabulary"])
                heard = time.monotonic()
                cleaned = cleaner.clean(raw, api_key=job["api_key"], llm_enabled=job["llm_enabled"],
                                        vocabulary=job["vocabulary"], doubtful=doubtful)
                log.info("Dictation of %.1fs: transcription %.2fs, cleanup %.2fs (%s)",
                         job["duration"], heard - started, time.monotonic() - heard, cleaned.engine)
                result.update(raw=raw, text=cleaned.text, engine=cleaned.engine,
                              note=cleaned.note, language=language, raw_words=cleaned.raw_words,
                              fillers=cleaned.fillers, fixes=cleaned.fixes, speech=speech)
            except Exception as exc:
                log.exception("Failed to process the dictation")
                result["error"] = str(exc)
            self.finished.emit(result)

    # -- live typing -------------------------------------------------------
    def _run_live(self, job: dict) -> None:
        session, final = job["session"], job["kind"] == "final"
        if self._live[0] != session:
            self._live = (session, StreamState())
        state = self._live[1]
        chunk, error = "", ""
        try:
            audio = job["audio"]
            total = len(audio) / SAMPLE_RATE
            tail = audio[int(state.trim_s * SAMPLE_RATE):]
            if len(tail) >= SAMPLE_RATE // 2:
                # A prompt for Whisper, not interface text: same wording as transcriber.py.
                vocabulary = ", ".join(job["vocabulary"]) + ". " if job["vocabulary"] else ""
                # One language for the whole dictation: detecting it again on a short piece makes it flip.
                found, detected = self._transcriber.transcribe_words(
                    tail, state.language or job["language"], vocabulary + state.prompt,
                    offset=state.trim_s, fast=not final)
                state.language = state.language or detected
                words = [] if cleaner.is_hallucination("".join(w for _, _, w in found)) \
                    else [Word(*w) for w in found]
                agreed = state.update(words, final=final or state.overdue(total))
            else:
                # Hardly any audio left after the last trim: on closing, the pending hypothesis is accepted.
                agreed = state.flush() if final else []
            chunk = cleaner.clean_live_chunk("".join(w.text for w in agreed), state.typed)
            state.typed += chunk
            state.trim(total)
        except Exception as exc:
            log.exception("Live typing pass failed")
            error = str(exc)
        if not final:
            self.liveChunk.emit(session, chunk)
            return
        raw = "".join(w.text for w in state.committed)
        fillers = cleaner.count_fillers(raw)
        speech = state.committed[-1].end - state.committed[0].start if state.committed else 0.0
        log.info("Live dictation of %.1fs: %d words", job["duration"], len(state.committed))
        self.finished.emit({**job, "audio": None, "live": True, "tail": chunk, "text": state.typed.strip(),
                            "raw": raw.strip(), "engine": "live", "note": "", "error": error,
                            "language": state.language or job["language"],
                            "raw_words": len(state.committed), "fillers": fillers, "fixes": fillers,
                            "speech": min(speech, job["duration"])})


class Controller(QObject):
    def __init__(self, app: QApplication, start_hidden: bool = False):
        super().__init__()
        self.app = app
        self.store = Store()
        i18n.set_language(i18n.resolve(self.store.get("ui_language")))   # before any window is built
        self.api_key = config.get_api_key()
        self.model_ready = False
        self.model_error = ""
        self._quitting = False
        self.paused = False
        self._pending = 0
        self._mode = "hold"
        self._target_app = ""
        self._rec_started = 0.0
        self._live = False          # the current dictation is typed as it is spoken
        self._session = 0
        self._tick_busy = False
        self._live_job: dict = {}
        self._live_timer = QTimer(self, interval=900, timeout=self._live_tick)
        self._capture_timer = QTimer(self, singleShot=True, interval=8000, timeout=self._cancel_capture)

        self.window = self._make_window()
        self.pill = Pill()
        self.pill.hotkey_name = self._hotkey_name()
        self.pill.mic_ok = has_input()
        self.pill.positionChosen.connect(self._on_hud_dragged)
        self.pill.collapsedChanged.connect(lambda value: self.store.set("hud_collapsed", value))
        self.pill.closeRequested.connect(self._on_hud_closed)
        self._apply_hud()
        self.recorder = Recorder(self)
        self.recorder.level.connect(self.pill.set_level)

        self._tap_timer = QTimer(self, singleShot=True)
        self.machine = TapMachine(
            on_start=self._start, on_stop=self._stop, on_cancel=self._cancel, on_lock=self._lock,
            set_timer=self._tap_timer.start, cancel_timer=self._tap_timer.stop)
        self._tap_timer.timeout.connect(self.machine.timeout)
        self._max_timer = QTimer(self, singleShot=True, interval=MAX_SECONDS * 1000,
                                 timeout=self.machine.force_stop)

        self.hotkey = create_listener(self)
        self.hotkey.stateChanged.connect(self._refresh_status)
        self.hotkey.filter.set_keys(parse_keys(self.store.get("hotkey_keys") or self.store.get("hotkey_vk")))
        self.hotkey.keyDown.connect(self.machine.down)
        self.hotkey.keyUp.connect(self.machine.up)
        self.hotkey.escapePressed.connect(self.machine.cancel)
        self.hotkey.keysCaptured.connect(self._on_keys_captured)
        # The hook is installed once the model is loaded (see _on_model_ready).

        self.worker = Worker(self.store.get("model"))
        self.worker.modelReady.connect(self._on_model_ready)
        self.worker.modelFailed.connect(self._on_model_failed)
        self.worker.finished.connect(self._on_finished)
        self.worker.liveChunk.connect(self._on_live_chunk)
        self.worker.start()

        self._build_tray()
        if not start_hidden:
            self.window.show()
        if self.store.recovered_from:
            log.error("The database was damaged; copy kept at %s", self.store.recovered_from)
            self.tray.showMessage(
                "Susurros", tr("The history was damaged and a new one has been started. "
                               "The previous file is kept as {file}.", file=self.store.recovered_from.name),
                QSystemTrayIcon.Warning, 10000)

    # -- main window and interface language ------------------------------
    def _make_window(self) -> MainWindow:
        """Builds the main window in the current interface language and wires its signals."""
        window = MainWindow(self.store, self._hotkey_name())
        window.apiKeyChanged.connect(self._reload_key)
        window.hudChanged.connect(self._apply_hud)
        window.hotkeyCaptureRequested.connect(self._begin_capture)
        window.hotkeyCaptureAbandoned.connect(self._cancel_capture)
        window.languageChanged.connect(self._on_language_changed)
        return window

    def _hotkey_keys(self) -> list[int]:
        return parse_keys(self.store.get("hotkey_keys") or self.store.get("hotkey_vk"))

    def _hotkey_name(self) -> str:
        """The shortcut as shown to the user, in the current interface language. The stored name
        is only the fallback for keys that just the keyboard layout can name."""
        translate = tr
        if sys.platform == "darwin":
            from .mac.keys import mac_name   # the shared key names are the Windows ones
            translate = lambda name: tr(mac_name(name))   # noqa: E731
        return combo_name(self._hotkey_keys(), translate, self.store.get("hotkey_name"))

    def _on_language_changed(self) -> None:
        """Every label is created with the language active at that moment, so the main window
        is built again; the indicator reads its texts when it shows them and needs no rebuild."""
        i18n.set_language(i18n.resolve(self.store.get("ui_language")))
        self._cancel_capture()
        old = self.window
        # From here on the old window must not reach the controller: hiding it would otherwise
        # report an abandoned key capture against the new window.
        old.blockSignals(True)
        self.window = self._make_window()
        self.window.restoreGeometry(old.saveGeometry())
        self.window.set_page(old.stack.currentIndex())
        if old.isVisible():
            self.window.show()
            # The language row sits at the bottom of Settings: stay there instead of jumping to the
            # top. Deferred, because the scroll range is only known once the new page is laid out.
            scroll = old.settings_scroll()
            QTimer.singleShot(0, self.window, lambda: self.window.set_settings_scroll(scroll))
        old.hide()
        old.deleteLater()
        self._retranslate_tray()
        self.pill.hotkey_name = self._hotkey_name()
        self._refresh_status()

    # -- tray ------------------------------------------------------------
    def _build_tray(self) -> None:
        self.tray = QSystemTrayIcon(theme.make_icon(), self)
        self.tray.setToolTip("Susurros")
        menu = QMenu()
        # Through `self.window`, looked up on each use: the window is replaced when the language changes.
        self._open_action = menu.addAction("", lambda: self.window.bring_to_front())
        self._pause_action = QAction("", menu, checkable=True)
        self._pause_action.toggled.connect(self._set_paused)
        menu.addAction(self._pause_action)
        menu.addSeparator()
        self._quit_action = menu.addAction("", self.quit)
        self._menu = menu
        self._retranslate_tray()
        self.tray.setContextMenu(menu)
        if sys.platform != "darwin":   # on macOS a click on the menu bar icon opens its menu
            self.tray.activated.connect(
                lambda reason: self.window.bring_to_front()
                if reason in (QSystemTrayIcon.Trigger, QSystemTrayIcon.DoubleClick) else None)
        self.tray.show()

    def _retranslate_tray(self) -> None:
        self._open_action.setText(tr("Open Susurros"))
        self._pause_action.setText(tr("Pause dictation"))
        self._quit_action.setText(tr("Quit"))

    def _set_paused(self, paused: bool) -> None:
        self.paused = paused
        self.hotkey.filter.set_enabled(not paused)
        if paused:
            self.machine.cancel()
        self._refresh_status()

    def _refresh_status(self) -> None:
        if self.paused:
            self.window.set_status(tr("Paused. {key} does not start a dictation.", key=self._hotkey_name()), "off")
        elif self.model_error:
            self.window.set_status(tr("Couldn't load the speech model: {error}", error=self.model_error), "error")
        elif not self.model_ready:
            self.window.set_status(tr("Loading the speech model…"), "busy")
        elif self.hotkey.needs_permission == "accessibility":
            self.window.set_status(
                tr("Allow Susurros in System Settings › Privacy & Security › Accessibility."), "error")
        elif self.hotkey.needs_permission:
            self.window.set_status(
                tr("Allow Susurros in System Settings › Privacy & Security › Input Monitoring."), "error")
        elif sys.platform == "win32" and self.hotkey.failed:
            self.window.set_status(tr("Couldn't capture the dictation key."), "error")
        else:
            device = "GPU" if self._device in ("cuda", "mlx") else "CPU"
            self.window.set_status(tr("Ready to dictate · {device}", device=device), "ok")

    def _reload_key(self) -> None:
        self.api_key = config.get_api_key()

    def _apply_hud(self) -> None:
        self.pill.configure(self.store.get("hud_position"), self.store.get_bool("hud_always"),
                            self.store.get_bool("hud_collapsed"))

    def _on_hud_closed(self) -> None:
        """Closing the indicator: it stops being always visible (it still appears while dictating)."""
        self.window.set_hud_always(False)   # the switch in Settings stores and applies the change

    def _on_hud_dragged(self, position: str) -> None:
        self.store.set("hud_position", position)
        self.window.sync_hud_position(position)

    # -- changing the key ------------------------------------------------
    def _begin_capture(self) -> None:
        self.machine.cancel()
        self.hotkey.filter.begin_capture()
        self._capture_timer.start()

    def _cancel_capture(self) -> None:
        """No key within a few seconds, or the window loses focus: the previous one stays.
        Otherwise the next key pressed in any program would become the dictation key."""
        self._capture_timer.stop()
        if self.hotkey.filter.capturing:
            self.hotkey.filter.cancel_capture()
            self.window.set_hotkey_name(self._hotkey_name())

    def _on_keys_captured(self, captured: list) -> None:
        """`captured`: the keys that were down together, as (vk, scan code, extended)."""
        self._capture_timer.stop()
        keys, name = normalize_combo(captured)
        name = self.hotkey.describe(keys, name)
        if keys != [VK_ESCAPE]:  # Esc alone cancels the change and keeps the previous shortcut
            self.store.set("hotkey_keys", ",".join(str(k) for k in keys))
            self.store.set("hotkey_name", name)
            self.hotkey.filter.set_keys(keys)
            self.pill.hotkey_name = self._hotkey_name()
        self.window.set_hotkey_name(self._hotkey_name())
        self._refresh_status()

    # -- model -----------------------------------------------------------
    def _on_model_ready(self, device: str) -> None:
        self.model_ready, self._device = True, device
        # Now, and not earlier: while the model and its DLLs load, the interpreter stalls at
        # times, and Windows silently removes a keyboard hook that is slow to respond.
        self.hotkey.start()
        QTimer.singleShot(400, self._refresh_status)   # once the hook has reported whether it installed
        self._refresh_status()

    def _on_model_failed(self, error: str) -> None:
        self.model_error = error
        self._refresh_status()

    # -- life of a dictation ---------------------------------------------
    def _beep(self, name: str) -> None:
        if self.store.get_bool("sounds"):
            sounds.play(name, self.store.get("sound_set"))

    def _start(self) -> bool:
        """Starts recording. Returns False if it cannot, so the key does not change state."""
        if not self.model_ready:
            self._message(tr("Couldn't load the speech model") if self.model_error
                          else tr("The speech model is still loading"))
            return False
        self._mode = "hold"
        self._target_app = injector.foreground_app()
        try:
            self.recorder.start(self.store.get("mic_device"))
        except Exception as exc:
            log.exception("Could not open the microphone")
            self.pill.mic_ok = False
            self._message(tr("Can't access the microphone"), 2600)
            self.window.set_status(tr("Microphone unavailable: {error}", error=exc), "error")
            return False
        self._rec_started = time.monotonic()
        self._live = self.store.get_bool("live_typing")
        if self._live:
            self._session += 1
            self._tick_busy = False
            # Settings are read once per dictation, not on every pass.
            self._live_job = {"session": self._session, "language": self.store.get("language"),
                              "vocabulary": self.store.words()}
            self._live_timer.start()
        if not self.pill.mic_ok:
            self.pill.mic_ok = True
            self._refresh_status()   # clears the "microphone unavailable" notice
        self.hotkey.filter.capture_escape = True
        self._max_timer.start()
        self.pill.show_recording()
        # The start sound waits until the press is clearly a hold: a quick tap (which will be
        # handed back to Windows as a normal key press) should not beep.
        started = self._rec_started
        QTimer.singleShot(HOLD_MS, lambda: self._beep_start(started))
        return True

    def _beep_start(self, started: float) -> None:
        if self.recorder.recording and self._rec_started == started and self.machine.state == "pressed":
            self._beep("start")

    def _lock(self) -> None:
        if not self.recorder.recording:
            return
        self._mode = "hands-free"
        self.pill.show_locked()
        self._beep("lock")

    # -- live typing ----------------------------------------------------
    def _live_tick(self) -> None:
        """Every 0.9 s sends what has been recorded so far to be transcribed (if the previous pass is done)."""
        if not self.recorder.recording or self._tick_busy:
            return
        audio = self.recorder.snapshot()
        if len(audio) < SAMPLE_RATE:
            return
        self._tick_busy = True
        self.worker.submit({"kind": "tick", "audio": audio, **self._live_job})

    def _on_live_chunk(self, session: int, text: str) -> None:
        if session != self._session:
            return   # pass from a cancelled or already closed dictation: nothing is typed
        self._tick_busy = False
        if text and self.store.get_bool("auto_paste"):
            injector.type_text(text)

    def _end_recording(self) -> np.ndarray:
        self._live_timer.stop()
        self.hotkey.filter.capture_escape = False
        self._max_timer.stop()
        self.pill.set_level(0.0)
        return self.recorder.stop()

    def _cancel(self) -> None:
        if not self.recorder.recording:
            return
        long_enough = time.monotonic() - self._rec_started > 1.0
        self._end_recording()
        if self._live:
            self._session += 1   # invalidates passes in flight: nothing more is typed after cancelling
        if long_enough:  # a stray tap is dropped silently; an Esc is acknowledged
            self._beep("cancel")
            self._message(tr("Dictation cancelled"), 1200)
        else:
            self._hide_pill_if_idle()

    def _stop(self) -> None:
        if not self.recorder.recording:
            return
        audio = self._end_recording()
        duration = len(audio) / SAMPLE_RATE
        if duration < MIN_SECONDS or float(np.max(np.abs(audio))) < SILENCE_PEAK:
            self._message(tr("Nothing heard"), NOTHING_HEARD_MS)
            return
        self._pending += 1
        self.pill.show_processing()
        if self._live:
            # Last pass: confirms what was still pending and closes the dictation.
            self.worker.submit({"kind": "final", "audio": audio, "duration": duration,
                                "mode": self._mode, "app": self._target_app, **self._live_job})
        else:
            self.worker.submit({
                "audio": audio, "duration": duration, "mode": self._mode, "app": self._target_app,
                "language": self.store.get("language"), "vocabulary": self.store.words(),
                "llm_enabled": self.store.get_bool("llm_enabled"), "api_key": self.api_key,
            })
        self._beep("stop")   # after queueing: a sound failure must not lose the dictation

    def _message(self, text: str, ms: int = 1500) -> None:
        """Notice on the indicator, which goes back to rest unless a dictation is being recorded
        or transcribed; in that case it keeps showing that state."""
        if self.recorder.recording:
            self.pill.show_message(text, ms, rest=False)
        elif self._pending:
            self.pill.show_processing()
            self.pill.show_message(text, ms, rest=False)
        else:
            self.pill.show_message(text, ms)

    def _hide_pill_if_idle(self) -> None:
        if self.recorder.recording:
            return
        if self._pending:
            self.pill.show_processing()
        else:
            self.pill.hide_pill()

    def _on_finished(self, result: dict) -> None:
        self._pending -= 1
        if result["error"]:
            self._message(tr("Couldn't transcribe"), 2600)
            return
        text = result["text"]
        if not text:
            if not self.recorder.recording:
                self._message(tr("Nothing heard"), NOTHING_HEARD_MS)
            return
        space = " " if self.store.get_bool("trailing_space") else ""
        if not self.store.get_bool("auto_paste"):
            pass
        elif result.get("live"):
            injector.type_text(result["tail"] + space)   # the rest was typed along the way
        else:
            injector.paste(text + space)
        note = tr(result["note"])   # cleanup notices are English source strings (see cleaner.py)
        try:
            self.store.add_transcription(
                text, raw_text=result["raw"] if self.store.get_bool("keep_raw") else None,
                # Pace is measured on time spent speaking, not on the silences of a forgotten hands-free session.
                duration_s=result.get("speech") or result["duration"], language=result.get("language", ""),
                mode=result["mode"], app=result["app"], engine=result["engine"],
                raw_words=result["raw_words"], fillers=result["fillers"], fixes=result["fixes"])
            self.window.refresh_history()
        except Exception:
            log.exception("Could not save the dictation to the history")
            note = tr("Couldn't save the dictation to the history")
        if note:
            self._message(note, 3200)
        else:
            self._hide_pill_if_idle()

    def quit(self) -> None:
        if self._quitting:
            return
        self._quitting = self.window.quitting = True
        self.machine.cancel()
        self.hotkey.stop()
        self.pill.always = False
        self.pill.hide_pill()
        self.tray.hide()
        self.worker.stop()        # lets the transcription in progress finish before closing
        self.app.processEvents()  # and delivers its result, if there was one
        self.store.close()
        self.app.quit()


class _QuitFilter(QObject):
    """macOS asks the app to quit (Cmd+Q, the Dock menu, logging out) with an event of its own.
    It is routed through `Controller.quit`, which stops the worker and closes the database."""

    def __init__(self, app: QApplication, controller: Controller):
        super().__init__(app)
        self._app, self._controller = app, controller

    def eventFilter(self, watched, event) -> bool:
        if watched is self._app and event.type() == QEvent.Quit and not self._controller._quitting:
            self._controller.quit()
            return True
        return False


def _mac_integration(app: QApplication, controller: Controller) -> None:
    from .mac import system
    system.request_microphone()
    app.installEventFilter(_QuitFilter(app, controller))
    started = time.monotonic()

    def reopen(state) -> None:
        """A click on the Dock icon activates the app: with its window closed, that opens it.
        Not right after starting (it may have been started hidden at login), and not when the
        activation comes from a click on the floating indicator."""
        if (state == Qt.ApplicationState.ApplicationActive and not controller.window.isVisible()
                and time.monotonic() - started > 3 and app.topLevelAt(QCursor.pos()) is None):
            controller.window.bring_to_front()

    app.applicationStateChanged.connect(reopen)


def run(argv: list[str]) -> int:
    config.setup_logging()
    app = QApplication(argv)
    app.setApplicationName(config.APP_NAME)
    app.setQuitOnLastWindowClosed(False)
    app.setWindowIcon(theme.make_icon())

    # Single instance: if one is already running, ask it to show its window.
    probe = QLocalSocket()
    probe.connectToServer(SERVER_NAME)
    if probe.waitForConnected(300):
        probe.write(b"show")
        probe.waitForBytesWritten(300)
        return 0
    QLocalServer.removeServer(SERVER_NAME)
    server = QLocalServer()
    server.listen(SERVER_NAME)

    controller = Controller(app, start_hidden="--hidden" in argv)
    server.newConnection.connect(
        lambda: (server.nextPendingConnection().close(), controller.window.bring_to_front()))
    if sys.platform == "darwin":
        _mac_integration(app, controller)
    log.info("Susurros started")
    return app.exec()
