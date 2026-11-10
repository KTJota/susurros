"""The controller end to end, with the transcriber, microphone and keyboard faked.
The `controller` fixture runs the interface in Spanish, so UI text is asserted in Spanish."""
import sys

import pytest
from PySide6.QtCore import QPoint, Qt
from PySide6.QtTest import QTest


def ready(ctl):
    ctl.model_ready, ctl._device = True, "cuda"


def finish(ctl, **extra):
    """Hands the controller the result of the last queued job."""
    job = ctl.jobs[-1]
    result = {**job, "audio": None, "text": "Hola mundo.", "raw": "eh hola mundo", "engine": "rules",
              "note": "", "error": "", "language": "es", "raw_words": 3, "fillers": 1, "fixes": 1,
              "speech": 1.2, **extra}
    ctl._on_finished(result)


def test_hold_dictation_is_pasted_and_saved(controller):
    ready(controller)
    controller.machine.down(0.0)
    assert controller.recorder.recording and controller.pill.state == "recording"
    controller.machine.up(1.5)
    assert controller.pill.state == "processing" and len(controller.jobs) == 1
    finish(controller)
    assert controller.pasted == ["Hola mundo. "]
    row = controller.store.list_transcriptions()[0]
    assert (row["text"], row["mode"], row["fixes"], row["duration_s"]) == ("Hola mundo.", "hold", 1, 1.2)
    assert controller.pill.state == "idle" and controller._pending == 0


def test_key_does_not_get_stuck_while_the_model_loads(controller):
    controller.machine.down(0.0); controller.machine.up(0.08)
    controller.machine.down(0.2); controller.machine.up(0.28)      # double tap too early
    assert controller.machine.state == "idle" and not controller.recorder.recording
    ready(controller)
    controller.machine.down(5.0); controller.machine.up(7.0)
    assert len(controller.jobs) == 1                                # the next dictation works


def test_microphone_failure_is_reported_and_recoverable(controller):
    ready(controller)
    controller.recorder.fail = True
    controller.machine.down(0.0); controller.machine.up(2.0)
    assert controller.machine.state == "idle" and controller.jobs == [] and not controller.pill.mic_ok
    controller.recorder.fail = False
    controller.machine.down(5.0)
    assert controller.recorder.recording and controller.pill.mic_ok


def test_silent_recording_is_not_transcribed(controller):
    ready(controller)
    controller.recorder.audio = controller.recorder.audio * 0.001
    controller.machine.down(0.0); controller.machine.up(2.0)
    assert controller.jobs == [] and controller.pill._caption.text == "No se ha oído nada"


def test_silent_hands_free_session_ends_cleanly(controller):
    """Double tap, nothing is said, double tap: the indicator goes back to rest
    (without the hands-free border) and the next dictation works."""
    ready(controller)
    controller.recorder.audio = controller.recorder.audio * 0.001
    m, pill = controller.machine, controller.pill
    m.down(0.0); m.up(0.08); m.down(0.2); m.up(0.28)
    assert pill.state == "locked"
    m.down(5.0); m.up(5.08); m.down(5.2); m.up(5.28)
    assert m.state == "idle" and not controller.recorder.recording
    assert pill.state == "idle" and not pill._tick.isActive()
    assert pill._caption.text == "No se ha oído nada" and controller.jobs == []
    m.down(9.0)                                           # and dictation works again
    assert controller.recorder.recording and pill.state == "recording"


def test_silent_hold_returns_the_pill_to_rest(controller):
    ready(controller)
    controller.recorder.audio = controller.recorder.audio * 0.001
    controller.machine.down(0.0); controller.machine.up(2.0)
    assert controller.pill.state == "idle"


def test_cancelled_dictation_returns_the_pill_to_rest(controller):
    ready(controller)
    m = controller.machine
    m.down(0.0); m.up(0.08); m.down(0.2); m.up(0.28)
    controller._rec_started -= 5                           # it has been recording for a while
    m.cancel()
    assert controller.pill.state == "idle" and controller.pill._caption.text == "Dictado cancelado"


def test_double_tap_goes_hands_free_until_the_next_double_tap(controller):
    ready(controller)
    m = controller.machine
    m.down(0.0); m.up(0.08); m.down(0.2); m.up(0.28)
    assert controller.pill.state == "locked" and controller.recorder.recording
    m.down(9.0); m.up(9.08); m.down(9.2)
    assert not controller.recorder.recording and controller.jobs[-1]["mode"] == "hands-free"


def test_live_mode_types_chunks_and_drops_them_after_cancel(controller):
    ready(controller)
    controller.store.set("live_typing", True)
    controller.store.add_word("Zaragoza")
    controller.machine.down(0.0)
    controller._live_tick()
    tick = controller.jobs[-1]
    assert tick["kind"] == "tick" and tick["vocabulary"] == ["Zaragoza"]
    controller._live_tick()
    assert len(controller.jobs) == 1                    # no new pass is queued while one is in flight
    controller._on_live_chunk(tick["session"], "Hola")
    assert controller.typed == ["Hola"]
    controller._live_tick()
    controller.machine.cancel()                         # Esc with a pass in flight
    controller._on_live_chunk(controller.jobs[-1]["session"], " mundo")
    assert controller.typed == ["Hola"]                 # what arrives afterwards is not typed


def test_live_mode_final_pass_types_only_the_tail(controller):
    ready(controller)
    controller.store.set("live_typing", True)
    controller.machine.down(0.0); controller.machine.up(3.0)
    assert controller.jobs[-1]["kind"] == "final"
    finish(controller, live=True, tail=" mundo.", text="Hola mundo.", engine="live")
    assert controller.typed == [" mundo. "] and controller.pasted == []
    assert controller.store.list_transcriptions()[0]["engine"] == "live"


def test_history_write_failure_does_not_swallow_the_dictation(controller, monkeypatch):
    ready(controller)
    controller.machine.down(0.0); controller.machine.up(1.5)

    def boom(*_a, **_k):
        raise OSError("disk full")

    monkeypatch.setattr(controller.store, "add_transcription", boom)
    finish(controller)
    assert controller.pasted == ["Hola mundo. "] and controller._pending == 0
    assert "historial" in controller.pill._caption.text


@pytest.mark.skipif(sys.platform == "darwin", reason="asserts the Windows key names; test_mac.py covers the macOS ones")
def test_hotkey_capture_is_cancelled_when_the_window_goes_away(controller):
    controller.window.show()
    window = controller.window
    window._capture_hotkey()                             # what the button does (only enabled on Windows)
    assert controller.hotkey.filter.capturing
    window.hide()                                        # sent to the tray without pressing any key
    assert not controller.hotkey.filter.capturing
    # The name is computed from the stored keys in the interface language, not read from the store.
    assert controller.store.get("hotkey_name") == "Caps Lock"
    assert window._hotkey_button.text() == "Bloq Mayús" and controller.pill.hotkey_name == "Bloq Mayús"
    window._capture_hotkey()
    controller._on_keys_captured([(0x77, 0x42, False)])  # F8
    assert controller.store.get("hotkey_name") == "F8" and controller.hotkey.filter.keys == (0x77,)
    assert window._hotkey_button.text() == "F8"
    window._capture_hotkey()
    controller._on_keys_captured([(0xA0, 0x2A, False)])  # left Shift alone: stored in English, shown in Spanish
    assert controller.store.get("hotkey_name") == "Left Shift"
    assert window._hotkey_button.text() == "Mayús izquierda" and controller.pill.hotkey_name == "Mayús izquierda"
    window._capture_hotkey()
    controller._on_keys_captured([(0xA4, 0x38, False), (0x31, 0x02, False)])   # left Alt and 1
    assert controller.store.get("hotkey_name") == "Alt + 1" and controller.store.get("hotkey_keys") == "18,49"
    assert controller.hotkey.filter.keys == (0x12, 0x31) and "Alt + 1" in window._history_subtitle.text()
    assert window._settings_hint.text() == "Esc cancela un dictado en curso."
    window._capture_hotkey()
    controller._on_keys_captured([(0x1B, 0x01, False)])  # Esc: stays as it was
    assert controller.store.get("hotkey_name") == "Alt + 1" and window._hotkey_button.text() == "Alt + 1"


def test_unnameable_key_falls_back_to_the_stored_name(controller):
    """A key only the keyboard layout can name is shown with the name Windows gave when it was chosen."""
    controller.store.set("hotkey_keys", "220")
    controller.store.set("hotkey_name", "º")
    assert controller._hotkey_name() == "º"


def test_switching_the_interface_language_rebuilds_the_window(controller):
    from PySide6.QtWidgets import QApplication
    from susurros import i18n

    old = controller.window
    old.show()
    old.resize(790, 560)                                 # fits the 800 px offscreen screen
    old.set_page(3)
    assert old._nav.button(0).text() == "Historial" and controller._open_action.text() == "Abrir Susurros"
    assert "Mantén pulsado Bloq Mayús" in old._history_subtitle.text()

    combo = old._ui_language_combo
    combo.setCurrentIndex(combo.findData("en"))          # what choosing "English" in Settings does
    new = controller.window
    assert new is not old and i18n.language() == "en" and controller.store.get("ui_language") == "en"
    assert new._nav.button(0).text() == "History" and new._nav.button(3).text() == "Settings"
    assert "Hold Caps Lock to dictate" in new._history_subtitle.text()
    assert controller._open_action.text() == "Open Susurros" and controller._pause_action.text() == "Pause dictation"
    assert controller.pill.hotkey_name == "Caps Lock"
    assert new._status_text.text() == "Loading the speech model…"
    # Same place on screen, same page, still visible; the old window is gone.
    assert new.stack.currentIndex() == 3 and new._nav.button(3).isChecked()
    assert new.isVisible() and new.size() == old.size() and not old.isVisible()
    assert new._ui_language_combo.currentData() == "en"

    # The old window no longer reaches the controller, and the new one is fully wired.
    new._capture_hotkey()
    old.hotkeyCaptureAbandoned.emit()
    assert controller.hotkey.filter.capturing
    new.hide()
    assert not controller.hotkey.filter.capturing
    QApplication.sendPostedEvents(None, 0x34)            # QEvent.DeferredDelete: the old window is destroyed
    ready(controller)
    controller._pause_action.setChecked(True)            # status goes to the window that exists
    assert new._status_text.text() == "Paused. Caps Lock does not start a dictation."

    combo = new._ui_language_combo
    combo.setCurrentIndex(combo.findData("es"))          # and back
    assert controller.window._nav.button(0).text() == "Historial" and controller._quit_action.text() == "Salir"
    assert controller.window._status_text.text() == "En pausa. Bloq Mayús no inicia el dictado."
    assert not controller.window.isVisible()             # it was hidden when the language changed


def test_pill_caption_follows_the_interface_language(controller):
    from susurros import i18n

    ready(controller)
    controller.recorder.audio = controller.recorder.audio * 0.001
    controller.machine.down(0.0); controller.machine.up(2.0)
    assert controller.pill._caption.text == "No se ha oído nada"
    controller.store.set("ui_language", "en")
    controller._on_language_changed()
    assert i18n.language() == "en"
    controller.machine.down(5.0); controller.machine.up(7.0)
    assert controller.pill._caption.text == "Nothing heard"
    m = controller.machine
    m.down(10.0); m.up(10.08); m.down(10.2); m.up(10.28)
    assert controller.pill._caption.text == "Hands-free · double Caps Lock to finish"


def test_cleanup_notice_is_shown_in_the_interface_language(controller):
    ready(controller)
    controller.machine.down(0.0); controller.machine.up(1.5)
    finish(controller, note="The Anthropic API key is not valid")
    assert controller.pill._caption.text == "La clave de Anthropic no es válida"


def test_pause_cancels_and_releases_the_key(controller):
    ready(controller)
    controller.machine.down(0.0)
    controller._pause_action.setChecked(True)
    assert not controller.recorder.recording and not controller.hotkey.filter.enabled
    controller._pause_action.setChecked(False)
    assert controller.hotkey.filter.enabled


def test_pill_click_does_not_dim_the_screen_but_a_drag_does(controller):
    pill = controller.pill
    assert pill.state == "idle" and pill.size().toTuple() == (84, 28)
    QTest.mousePress(pill, Qt.LeftButton, pos=QPoint(40, 14))
    assert not pill._overlay.isVisible()
    QTest.mouseRelease(pill, Qt.LeftButton, pos=QPoint(40, 14))
    assert not pill._dragging and not pill._overlay.isVisible()


def test_pill_is_vertical_on_side_edges_and_collapses_to_a_sliver(controller):
    pill = controller.pill
    controller.window._position_combo.setCurrentIndex(2)             # left
    assert pill.size().toTuple() == (28, 84)
    pill._hover = True; pill._layout()
    assert pill._controls.isVisible()
    pill._controls.collapseClicked.emit()
    assert pill.size().toTuple() == (6, 84) and pill.x() == 0 and controller.store.get_bool("hud_collapsed")
    pill._poll_hover()                                                # the mouse has not left: it does not peek out again
    assert pill._sliver


def test_closing_the_pill_hides_it_even_with_a_caption_showing(controller):
    pill = controller.pill
    pill.show_message("No se ha oído nada")
    pill._close()
    assert not pill.isVisible() and not pill._caption.isVisible()
    assert not controller.store.get_bool("hud_always") and not controller.window._hud_always.isChecked()
    ready(controller)
    controller.machine.down(0.0)
    assert pill.isVisible() and pill.state == "recording"            # it still appears while dictating


def test_message_does_not_hide_a_dictation_still_being_transcribed(controller):
    ready(controller)
    controller.machine.down(0.0); controller.machine.up(1.5)
    controller._message("No se ha oído nada")
    assert controller.pill.state == "processing"


def test_theme_switch_is_remembered(controller):
    from susurros.ui import theme
    controller.window.set_theme("light")
    assert controller.store.get("theme") == "light" and theme.BG == theme.LIGHT["BG"]
    controller.window.set_theme("dark")
    assert theme.BG == theme.DARK["BG"]


def test_history_refresh_waits_until_the_window_is_shown(controller):
    ready(controller)
    controller.machine.down(0.0); controller.machine.up(1.5)
    finish(controller)
    assert controller.window._history_dirty                          # hidden in the tray: no rebuild
    controller.window.show()
    assert not controller.window._history_dirty and not controller.window._history_empty


def test_collapsed_pill_shows_the_voice_level_while_dictating(controller):
    """Collapsed, the line does not just change colour: its bright stretch grows with the voice."""
    from PySide6.QtGui import QColor
    from susurros.ui.pill import DARK

    pill = controller.pill
    pill.collapsed = True
    ready(controller)
    controller.machine.down(0.0)
    assert pill._sliver and pill.state == "recording" and pill._tick.isActive()
    accent = QColor(DARK["ACCENT"]).rgb()

    def lit(level):
        pill._level = level
        image = pill.grab().toImage()
        row = image.height() // 2
        return sum(1 for col in range(image.width()) if image.pixelColor(col, row).rgb() == accent)

    quiet, loud = lit(0.0), lit(0.9)
    assert 0 < quiet < 20 and loud > 60


def test_collapsed_pill_gets_an_intense_border_in_hands_free(controller):
    from PySide6.QtGui import QColor
    from susurros.ui.pill import LOCK_ORANGE

    pill = controller.pill
    pill.collapsed = True
    ready(controller)
    m = controller.machine
    m.down(0.0)
    plain = pill.grab().toImage()
    assert pill.height() == 6
    m.up(0.08); m.down(0.2); m.up(0.28)                  # double tap: hands-free
    assert pill.state == "locked" and pill._sliver and pill.height() == 9
    locked = pill.grab().toImage()
    lock = QColor(LOCK_ORANGE).rgb()
    count = lambda image: sum(image.pixelColor(x, y).rgb() == lock
                              for x in range(image.width()) for y in range(image.height()))
    assert count(plain) == 0 and count(locked) > 100    # the border surrounds the whole line
    m.down(9.0); m.up(9.08); m.down(9.2)                 # when it ends it goes back to its thickness
    assert pill.height() == 6


def test_level_animation_is_frame_rate_independent(controller):
    """The meter reaches the same place in the same time at 60 as at 144 frames per second."""
    pill = controller.pill

    def after(seconds, fps, start, target):
        value = start
        for _ in range(round(seconds * fps)):
            value = pill._approach(value, target, 1 / fps)
        return value

    assert abs(after(0.1, 60, 0.0, 1.0) - after(0.1, 144, 0.0, 1.0)) < 0.01
    assert after(0.06, 144, 0.0, 1.0) > 0.85            # rises almost instantly when speaking…
    assert 0.2 < after(0.2, 144, 1.0, 0.0) < 0.4        # …and falls gently when going quiet
    ready(controller)
    controller.machine.down(0.0)
    assert pill._tick.interval() <= 17                  # one frame per refresh, at least 60 Hz


def test_lone_tap_is_discarded_and_the_key_is_not_replayed(controller, monkeypatch):
    """A quick single tap is not a dictation. Windows already received the key (the shortcut
    is only observed, never swallowed), so replaying it would toggle Caps Lock twice."""
    import susurros.app as appmod
    replayed = []
    monkeypatch.setattr(appmod.injector, "tap_key", replayed.append, raising=False)
    ready(controller)
    m = controller.machine
    m.down(0.0); m.up(0.08); m.timeout()
    assert m.state == "idle" and not controller.recorder.recording
    assert controller.jobs == [] and replayed == []
