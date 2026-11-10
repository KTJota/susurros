"""The macOS side. Most of it runs anywhere, against a stand-in for the macOS frameworks;
the tests marked `on_mac` talk to the real ones and only run on a Mac."""
import sys
import types

import numpy as np
import pytest

from susurros.hotkey import VK_ESCAPE
from susurros.mac import keys

on_mac = pytest.mark.skipif(sys.platform != "darwin", reason="needs the macOS frameworks")

RIGHT_COMMAND, LEFT_COMMAND, RIGHT_OPTION, KEY_1, KEY_ESC = 54, 55, 61, 18, 53
VK_RIGHT_WIN, VK_WIN, VK_ALT = 0x5C, 0x5B, 0x12


# -- key tables ---------------------------------------------------------------
def test_mac_keys_become_windows_codes():
    assert keys.to_vk(0) == ord("A") and keys.to_vk(KEY_1) == ord("1")
    assert keys.to_vk(RIGHT_COMMAND) == VK_RIGHT_WIN and keys.to_vk(LEFT_COMMAND) == VK_WIN
    assert keys.to_vk(KEY_ESC) == VK_ESCAPE
    assert keys.to_vk(122) == 0x70   # F1
    assert keys.to_vk(200) == keys.UNMAPPED + 200   # unknown keys still get a code of their own


def test_every_mapped_key_can_be_asked_for():
    assert keys.VK_TO_KEYCODES[VK_RIGHT_WIN] == (RIGHT_COMMAND,)
    assert all(keys.to_vk(code) == vk for vk, codes in keys.VK_TO_KEYCODES.items() for code in codes)


def test_modifier_presses_are_told_from_releases():
    held: set[int] = set()
    assert keys.modifier_is_down(RIGHT_COMMAND, keys.FLAG_COMMAND, held) is True
    assert keys.modifier_is_down(RIGHT_COMMAND, 0, held) is False
    assert held == set()


def test_releasing_one_of_two_twin_modifiers():
    held: set[int] = set()
    assert keys.modifier_is_down(LEFT_COMMAND, keys.FLAG_COMMAND, held) is True
    assert keys.modifier_is_down(RIGHT_COMMAND, keys.FLAG_COMMAND, held) is True
    # The flag stays on because the left one is still down: this is a release all the same.
    assert keys.modifier_is_down(RIGHT_COMMAND, keys.FLAG_COMMAND, held) is False
    assert keys.modifier_is_down(LEFT_COMMAND, 0, held) is False
    assert held == set()


def test_a_missed_release_does_not_leave_a_modifier_stuck():
    held = {RIGHT_COMMAND}   # its release was never seen
    assert keys.modifier_is_down(LEFT_COMMAND, 0, held) is False
    assert held == set()


def test_caps_lock_cannot_be_followed():
    assert keys.modifier_is_down(keys.KEYCODE_CAPS_LOCK, 0x10000, set()) is None


def test_key_names_the_mac_way():
    assert keys.mac_name("Right Win") == "Right Command" and keys.mac_name("Alt") == "Option"
    assert keys.mac_name("F5") == "F5"
    assert keys.label(keys.VK_FN) == "Fn"
    assert keys.label(0xBA, "ñ") == "Ñ" and keys.label(0xBA) == "Key 186"


def test_text_is_split_without_breaking_characters():
    assert keys.utf16_chunks("a" * 45) == ["a" * 20, "a" * 20, "a" * 5]
    assert keys.utf16_chunks("a" * 19 + "😀") == ["a" * 19, "😀"]   # the emoji takes two units
    assert keys.utf16_chunks("") == []


# -- a stand-in for Quartz ---------------------------------------------------
class FakeEvent:
    def __init__(self, keycode=0, down=True, flags=0, text=""):
        self.keycode, self.down, self.flags, self.text, self.user_data = keycode, down, flags, text, 0


@pytest.fixture
def quartz(monkeypatch):
    fake = types.SimpleNamespace(
        kCGEventKeyDown=10, kCGEventKeyUp=11, kCGEventFlagsChanged=12,
        kCGEventTapDisabledByTimeout=0xFFFFFFFE, kCGEventTapDisabledByUserInput=0xFFFFFFFF,
        kCGEventSourceUserData=42, kCGKeyboardEventKeycode=9, kCGHIDEventTap=0,
        kCGEventSourceStateHIDSystemState=1, posted=[], down_keys=set(), enabled=[])
    fake.CGEventGetIntegerValueField = lambda event, field: (
        event.user_data if field == fake.kCGEventSourceUserData else event.keycode)
    fake.CGEventSetIntegerValueField = lambda event, _field, value: setattr(event, "user_data", value)
    fake.CGEventGetFlags = lambda event: event.flags
    fake.CGEventSetFlags = lambda event, flags: setattr(event, "flags", flags)
    fake.CGEventKeyboardGetUnicodeString = lambda event, _max, _a, _b: (len(event.text), event.text)
    fake.CGEventKeyboardSetUnicodeString = lambda event, _length, text: setattr(event, "text", text)
    fake.CGEventCreateKeyboardEvent = lambda _source, keycode, down: FakeEvent(keycode, down)
    fake.CGEventPost = lambda _tap, event: fake.posted.append(event)
    fake.CGEventSourceKeyState = lambda _state, keycode: keycode in fake.down_keys
    fake.CGEventTapEnable = lambda _tap, on: fake.enabled.append(on)
    monkeypatch.setitem(sys.modules, "Quartz", fake)
    return fake


# -- the keyboard listener -----------------------------------------------------
@pytest.fixture
def listener(quartz):
    from PySide6.QtCore import QCoreApplication
    from susurros.mac.hotkey import MacHotkeyListener
    _app = QCoreApplication.instance() or QCoreApplication([])
    heard = []
    tap = MacHotkeyListener()
    tap.filter._pressed = tap._is_pressed
    tap.keyDown.connect(lambda _t: heard.append("down"))
    tap.keyUp.connect(lambda _t: heard.append("up"))
    tap.escapePressed.connect(lambda: heard.append("esc"))
    tap.keysCaptured.connect(lambda captured: heard.append(captured))
    tap.heard = heard

    def press(keycode, down=True, flags=0, text="", kind=None):
        kind = kind or (quartz.kCGEventKeyDown if down else quartz.kCGEventKeyUp)
        (quartz.down_keys.add if down else quartz.down_keys.discard)(keycode)
        return tap._on_event(None, kind, FakeEvent(keycode, down, flags, text), None)

    tap.press = press
    tap.modifier = lambda keycode, flags: (
        (quartz.down_keys.add if flags else quartz.down_keys.discard)(keycode),
        tap._on_event(None, quartz.kCGEventFlagsChanged, FakeEvent(keycode, flags=flags), None))
    return tap


def test_holding_right_command_starts_and_stops(listener):
    listener.filter.set_keys([VK_RIGHT_WIN])
    listener.modifier(RIGHT_COMMAND, keys.FLAG_COMMAND)
    listener.modifier(RIGHT_COMMAND, 0)
    assert listener.heard == ["down", "up"]


def test_left_command_is_not_right_command(listener):
    listener.filter.set_keys([VK_RIGHT_WIN])
    listener.modifier(LEFT_COMMAND, keys.FLAG_COMMAND)
    listener.modifier(LEFT_COMMAND, 0)
    assert listener.heard == []


def test_a_combination_with_option(listener):
    listener.filter.set_keys([VK_ALT, ord("1")])
    listener.modifier(RIGHT_OPTION, keys.FLAG_OPTION)
    listener.press(KEY_1)
    listener.press(KEY_1, down=False)
    listener.modifier(RIGHT_OPTION, 0)
    assert listener.heard == ["down", "up"]


def test_the_listener_never_holds_an_event_back(listener, quartz):
    listener.filter.set_keys([VK_RIGHT_WIN])
    listener.filter.capture_escape = True
    event = FakeEvent(KEY_ESC)
    assert listener._on_event(None, quartz.kCGEventKeyDown, event, None) is event
    assert listener.heard == ["esc"]


def test_text_typed_by_the_app_is_not_heard(listener, quartz):
    listener.filter.set_keys([ord("A")])
    own = FakeEvent(0)
    own.user_data = keys.OWN_EVENT
    listener._on_event(None, quartz.kCGEventKeyDown, own, None)
    assert listener.heard == []


def test_a_tap_switched_off_by_macos_is_switched_back_on(listener, quartz):
    listener._on_event(None, quartz.kCGEventTapDisabledByTimeout, None, None)
    assert quartz.enabled == [True]


def test_choosing_a_shortcut_names_it_the_mac_way(listener):
    listener.filter.begin_capture()
    listener.modifier(RIGHT_OPTION, keys.FLAG_OPTION)
    listener.press(41, text="ñ")           # the key right of L, on a Spanish keyboard
    listener.press(41, down=False)
    captured = listener.heard[-1]
    from susurros.hotkey import normalize_combo
    chosen, name = normalize_combo(captured)
    assert chosen == [VK_ALT, 0xBA]
    assert listener.describe(chosen, name) == "Option + Ñ"


def test_the_stored_default_shortcut_reads_right_command():
    from susurros.hotkey import combo_name
    assert combo_name([VK_RIGHT_WIN], keys.mac_name) == "Right Command"


# -- typing and pasting ------------------------------------------------------
def test_typing_sends_marked_events_without_modifiers(quartz):
    from susurros.mac import injector
    injector.type_text("hola " * 5 + "\nfin")
    texts = [e.text for e in quartz.posted if e.down and e.text]
    assert "".join(texts) == "hola " * 5 + "fin" and all(len(t) <= 20 for t in texts)
    assert any(e.keycode == keys.KEYCODE_RETURN and not e.text for e in quartz.posted)
    assert all(e.flags == 0 and e.user_data == keys.OWN_EVENT for e in quartz.posted)


def test_pasting_is_command_v(quartz):
    from susurros.mac import injector
    injector.send_cmd_v()
    assert [(e.keycode, e.down, e.flags) for e in quartz.posted] == [
        (keys.KEYCODE_V, True, keys.FLAG_COMMAND), (keys.KEYCODE_V, False, keys.FLAG_COMMAND)]


# -- start at login ----------------------------------------------------------
def test_start_at_login_writes_and_removes_a_launch_agent(tmp_path, monkeypatch):
    import plistlib
    from pathlib import Path
    from susurros.mac import system
    monkeypatch.setattr(Path, "home", lambda: tmp_path)
    assert not system.autostart_enabled()
    system.set_autostart(True)
    agent = plistlib.loads((tmp_path / "Library/LaunchAgents" / f"{system.BUNDLE_ID}.plist").read_bytes())
    assert agent["ProgramArguments"][-1] == "--hidden" and agent["RunAtLoad"] is True
    assert system.autostart_enabled()
    system.set_autostart(False)
    assert not system.autostart_enabled()


def test_a_launch_agent_of_another_copy_is_corrected(tmp_path, monkeypatch):
    import plistlib
    from pathlib import Path
    from susurros.mac import system
    monkeypatch.setattr(Path, "home", lambda: tmp_path)
    system.set_autostart(True)
    path = tmp_path / "Library/LaunchAgents" / f"{system.BUNDLE_ID}.plist"
    path.write_bytes(plistlib.dumps({"Label": system.BUNDLE_ID, "ProgramArguments": ["/old/Susurros"]}))
    assert system.autostart_enabled()
    assert plistlib.loads(path.read_bytes())["ProgramArguments"] == system._program()


# -- the speech engine ---------------------------------------------------------
def test_times_are_mapped_back_over_the_removed_silences():
    from susurros.mac.transcriber import restore_time
    spans = [(16_000, 32_000), (64_000, 80_000)]   # speech at 1-2 s and at 4-5 s
    assert restore_time(0.5, spans) == pytest.approx(1.5)
    assert restore_time(1.5, spans) == pytest.approx(4.5)
    assert restore_time(9.0, spans) == pytest.approx(5.0)
    assert restore_time(0.7, []) == pytest.approx(0.7)


@pytest.fixture
def mlx_engine(monkeypatch):
    from susurros.mac import transcriber
    calls = []

    def fake_transcribe(audio, **options):
        calls.append((len(audio), options))
        words = [{"word": " hola", "start": 0.2, "end": 0.6}, {"word": " mundo", "start": 1.2, "end": 1.6}]
        return {"language": "es", "segments": [{
            "text": " hola mundo", "no_speech_prob": 0.01, "avg_logprob": -0.2,
            "words": words if options["word_timestamps"] else []}]}

    monkeypatch.setattr(transcriber, "speech_spans", lambda audio: [(16_000, 32_000), (64_000, 80_000)])
    engine = transcriber.MlxTranscriber("large-v3-turbo")
    engine._mlx = types.SimpleNamespace(transcribe=fake_transcribe)
    engine.calls = calls
    return engine


def test_mlx_transcribes_only_the_speech(mlx_engine):
    text, language, speech, doubtful = mlx_engine.transcribe(np.zeros(96_000, np.float32), "es", ["PySide"])
    assert (text, language, speech, doubtful) == ("hola mundo", "es", 2.0, False)
    length, options = mlx_engine.calls[0]
    assert length == 32_000 and options["initial_prompt"] == "PySide." and options["language"] == "es"
    assert options["path_or_hf_repo"] == "mlx-community/whisper-large-v3-turbo"


def test_mlx_word_times_refer_to_the_recording(mlx_engine):
    words, language = mlx_engine.transcribe_words(np.zeros(96_000, np.float32), offset=10.0, fast=True)
    assert language == "es"
    assert words[0] == (pytest.approx(11.2), pytest.approx(11.6), " hola")
    assert words[1] == (pytest.approx(14.2), pytest.approx(14.6), " mundo")   # past the removed silence
    assert mlx_engine.calls[0][1]["temperature"] == 0.0


def test_mlx_returns_nothing_for_a_recording_without_speech(mlx_engine, monkeypatch):
    from susurros.mac import transcriber
    monkeypatch.setattr(transcriber, "speech_spans", lambda audio: [])
    assert mlx_engine.transcribe(np.zeros(16_000, np.float32), "es").text == ""
    assert mlx_engine.transcribe_words(np.zeros(16_000, np.float32)) == ([], "")
    assert mlx_engine.calls == []


class _CpuEngine:
    def __init__(self, _name):
        pass

    def load(self):
        return "cpu"

    def transcribe(self, *_args):
        return "from the cpu"


def test_without_mlx_the_shared_engine_is_used(monkeypatch):
    from susurros.mac import transcriber
    monkeypatch.setattr(transcriber, "mlx_usable", lambda: False)
    monkeypatch.setattr(transcriber, "Transcriber", _CpuEngine)
    engine = transcriber.MacTranscriber("tiny")
    with pytest.raises(RuntimeError):
        engine.transcribe(np.zeros(1, np.float32))
    assert engine.load() == "cpu"
    assert engine.transcribe(np.zeros(1, np.float32)) == "from the cpu"


def test_an_mlx_that_fails_to_load_falls_back_to_the_cpu(monkeypatch):
    from susurros.mac import transcriber

    def broken(self):
        raise OSError("no model")

    monkeypatch.setattr(transcriber, "mlx_usable", lambda: True)
    monkeypatch.setattr(transcriber.MlxTranscriber, "load", broken)
    monkeypatch.setattr(transcriber, "Transcriber", _CpuEngine)
    assert transcriber.MacTranscriber("tiny").load() == "cpu"


def test_the_voice_detector_finds_no_speech_in_silence():
    from susurros.mac.transcriber import speech_spans
    assert speech_spans(np.zeros(32_000, np.float32)) == []


# -- against the real macOS frameworks -------------------------------------------
@on_mac
def test_the_frameworks_offer_everything_the_app_calls():
    import AppKit
    import ApplicationServices
    import AVFoundation
    import Quartz
    wanted = {
        Quartz: ["CGEventTapCreate", "CGEventTapEnable", "CGEventMaskBit", "CGEventPost",
                 "CGEventCreateKeyboardEvent", "CGEventKeyboardSetUnicodeString",
                 "CGEventKeyboardGetUnicodeString", "CGEventGetIntegerValueField",
                 "CGEventSetIntegerValueField", "CGEventGetFlags", "CGEventSetFlags",
                 "CGEventSourceKeyState", "CFMachPortCreateRunLoopSource", "CFRunLoopGetCurrent",
                 "CFRunLoopAddSource", "CFRunLoopRun", "CFRunLoopStop", "kCFRunLoopCommonModes",
                 "kCGSessionEventTap", "kCGHeadInsertEventTap", "kCGEventTapOptionListenOnly",
                 "kCGEventKeyDown", "kCGEventKeyUp", "kCGEventFlagsChanged", "kCGHIDEventTap",
                 "kCGEventTapDisabledByTimeout", "kCGEventTapDisabledByUserInput",
                 "kCGEventSourceUserData", "kCGKeyboardEventKeycode", "kCGEventSourceStateHIDSystemState"],
        AppKit: ["NSSound", "NSWorkspace", "NSPanel", "NSStatusWindowLevel",
                 "NSWindowCollectionBehaviorCanJoinAllSpaces", "NSWindowCollectionBehaviorStationary",
                 "NSWindowCollectionBehaviorFullScreenAuxiliary", "NSWindowCollectionBehaviorIgnoresCycle",
                 "NSWindowStyleMaskNonactivatingPanel"],
        ApplicationServices: ["AXIsProcessTrusted", "AXIsProcessTrustedWithOptions", "kAXTrustedCheckOptionPrompt"],
        AVFoundation: ["AVCaptureDevice", "AVMediaTypeAudio"],
    }
    missing = [f"{module.__name__}.{name}" for module, names in wanted.items()
               for name in names if not hasattr(module, name)]
    assert missing == []


@on_mac
def test_real_events_carry_the_flags_and_text_the_app_sets():
    import Quartz
    event = Quartz.CGEventCreateKeyboardEvent(None, 0, True)
    Quartz.CGEventKeyboardSetUnicodeString(event, 4, "añ€x")
    Quartz.CGEventSetFlags(event, keys.FLAG_COMMAND)
    Quartz.CGEventSetIntegerValueField(event, Quartz.kCGEventSourceUserData, keys.OWN_EVENT)
    from susurros.mac.hotkey import MacHotkeyListener
    assert MacHotkeyListener._typed(event) == "añ€x"
    assert Quartz.CGEventGetFlags(event) & keys.FLAG_COMMAND
    assert Quartz.CGEventGetIntegerValueField(event, Quartz.kCGEventSourceUserData) == keys.OWN_EVENT
    # The modifier bits the key tables rely on are the ones macOS uses.
    assert (keys.FLAG_SHIFT, keys.FLAG_CONTROL, keys.FLAG_OPTION, keys.FLAG_COMMAND, keys.FLAG_FN) == (
        Quartz.kCGEventFlagMaskShift, Quartz.kCGEventFlagMaskControl, Quartz.kCGEventFlagMaskAlternate,
        Quartz.kCGEventFlagMaskCommand, Quartz.kCGEventFlagMaskSecondaryFn)


@on_mac
def test_real_system_services_answer(tmp_path):
    from susurros import sounds
    from susurros.mac import system
    assert isinstance(system.accessibility_granted(), bool)
    assert isinstance(system.frontmost_app(), str)
    assert isinstance(MacKeyState.pressed(), bool)
    system.play_sound(str(sounds._path("bubble", "start")))


class MacKeyState:
    @staticmethod
    def pressed() -> bool:
        from susurros.mac.hotkey import MacHotkeyListener
        return MacHotkeyListener._is_pressed(VK_RIGHT_WIN)
