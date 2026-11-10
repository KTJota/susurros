"""The Linux side. Runs on Linux only; the tests marked `with_uinput` also need a kernel
that lets this user create a virtual keyboard and read it back (the build on GitHub does)."""
import os
import sys
import time

import pytest

pytestmark = pytest.mark.skipif(not sys.platform.startswith("linux"), reason="Linux only")

if sys.platform.startswith("linux"):
    from susurros.linux import devices, keys

KEY_CAPSLOCK, KEY_ESC, KEY_LEFTALT, KEY_1, KEY_LEFTMETA = 58, 1, 56, 2, 125
VK_CAPITAL, VK_ALT = 0x14, 0x12


def _uinput_usable() -> bool:
    return (sys.platform.startswith("linux") and os.access("/dev/uinput", os.W_OK)
            and os.path.isdir("/dev/input"))


with_uinput = pytest.mark.skipif(not _uinput_usable(), reason="needs access to /dev/uinput and /dev/input")


def test_kernel_keys_become_windows_codes():
    assert keys.to_vk(KEY_CAPSLOCK) == VK_CAPITAL and keys.to_vk(KEY_ESC) == 0x1B
    assert keys.to_vk(keys.KEY_A) == ord("A") and keys.to_vk(KEY_1) == ord("1")
    assert keys.to_vk(KEY_LEFTMETA) == 0x5B and keys.to_vk(59) == 0x70 and keys.to_vk(183) == 0x7C
    assert keys.to_vk(240) == keys.UNMAPPED + 240
    assert keys.linux_name("Win") == "Super" and keys.linux_name("Alt") == "Alt"


def test_key_events_are_parsed_and_auto_repeat_is_dropped():
    reader, writer = os.pipe()
    os.set_blocking(reader, False)
    assert devices.read_keys(reader) == []
    for kind, code, value in ((1, KEY_CAPSLOCK, 1), (0, 0, 0), (1, KEY_CAPSLOCK, 2), (4, 4, 30),
                              (1, KEY_CAPSLOCK, 0)):
        os.write(writer, devices.EVENT.pack(0, 0, kind, code, value))
    assert devices.read_keys(reader) == [(KEY_CAPSLOCK, True), (KEY_CAPSLOCK, False)]
    os.close(reader)
    os.close(writer)


@pytest.fixture
def listener():
    from PySide6.QtCore import QCoreApplication
    from susurros.linux.hotkey import LinuxHotkeyListener
    _app = QCoreApplication.instance() or QCoreApplication([])
    heard = []
    reader = LinuxHotkeyListener()
    reader.keyDown.connect(lambda _t: heard.append("down"))
    reader.keyUp.connect(lambda _t: heard.append("up"))
    reader.escapePressed.connect(lambda: heard.append("esc"))
    reader.keysCaptured.connect(heard.append)
    reader.heard = heard
    return reader


def test_holding_caps_lock_starts_and_stops(listener):
    listener.handle(KEY_CAPSLOCK, True)
    listener.handle(KEY_CAPSLOCK, False)
    assert listener.heard == ["down", "up"]


def test_a_combination_needs_all_its_keys(listener):
    listener.filter.set_keys([VK_ALT, ord("1")])
    listener.handle(KEY_1, True)
    listener.handle(KEY_1, False)
    assert listener.heard == []
    listener.handle(KEY_LEFTALT, True)
    listener.handle(KEY_1, True)
    listener.handle(KEY_1, False)
    listener.handle(KEY_LEFTALT, False)
    assert listener.heard == ["down", "up"]


def test_escape_cancels_while_dictating(listener):
    listener.filter.capture_escape = True
    listener.handle(KEY_ESC, True)
    assert listener.heard == ["esc"]


def test_choosing_a_shortcut_names_it_the_linux_way(listener):
    from susurros.hotkey import normalize_combo
    listener.filter.begin_capture()
    listener.handle(KEY_LEFTMETA, True)
    listener.handle(KEY_1, True)
    listener.handle(KEY_1, False)
    chosen, name = normalize_combo(listener.heard[-1])
    assert chosen == [0x5B, ord("1")]
    assert listener.describe(chosen, name) == "Super + 1"


def test_start_at_login_writes_and_removes_a_desktop_entry(tmp_path, monkeypatch):
    from susurros.linux import system
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path))
    assert not system.autostart_enabled()
    system.set_autostart(True)
    entry = (tmp_path / "autostart" / "susurros.desktop").read_text()
    assert "-m susurros --hidden" in entry and entry.startswith("[Desktop Entry]")
    assert system.autostart_enabled()
    (tmp_path / "autostart" / "susurros.desktop").write_text("[Desktop Entry]\nExec=/old/python -m susurros\n")
    assert system.autostart_enabled()   # an entry of another install is corrected
    assert (tmp_path / "autostart" / "susurros.desktop").read_text() == system._entry()
    system.set_autostart(False)
    assert not system.autostart_enabled()


def test_pasting_falls_back_to_the_clipboard_without_a_virtual_keyboard(monkeypatch):
    from PySide6.QtGui import QGuiApplication
    from PySide6.QtWidgets import QApplication
    from susurros import injector
    from susurros.linux import system
    _app = QApplication.instance() or QApplication([])
    monkeypatch.setattr(injector, "_paster", None)
    monkeypatch.setattr(system, "prepare_keyboard", lambda: False)
    injector.paste("hola")
    assert QGuiApplication.clipboard().text() == "hola"


@with_uinput
def test_a_real_virtual_keyboard_is_heard_by_the_real_listener(listener):
    """End to end through the kernel: what the virtual keyboard presses comes back through
    /dev/input. The listener skips the app's own keyboard by name, so this one has another."""
    from PySide6.QtCore import QCoreApplication

    class TestKeyboard(devices.VirtualKeyboard):
        KEYS = (KEY_CAPSLOCK, keys.KEY_A, keys.KEY_ENTER)

    original = devices.VIRTUAL_NAME
    devices.VIRTUAL_NAME = "Susurros test keyboard"
    try:
        keyboard = TestKeyboard()
    finally:
        devices.VIRTUAL_NAME = original
    try:
        time.sleep(0.5)   # the device node appears a moment later
        listener.start()
        deadline = time.monotonic() + 8
        while not listener.installed and time.monotonic() < deadline:
            time.sleep(0.1)
            QCoreApplication.processEvents()
        assert listener.installed and not listener.needs_permission
        keyboard.press(KEY_CAPSLOCK)
        deadline = time.monotonic() + 3
        while listener.heard != ["down", "up"] and time.monotonic() < deadline:
            time.sleep(0.05)
            QCoreApplication.processEvents()
        assert listener.heard == ["down", "up"]
    finally:
        listener.stop()
        keyboard.close()


@with_uinput
def test_the_apps_own_keyboard_is_not_listened_to():
    keyboard = devices.VirtualKeyboard()
    try:
        time.sleep(0.5)
        found, _denied = devices.keyboards()
        names = [devices.device_name(fd) for fd in found.values()]
        for fd in found.values():
            os.close(fd)
        assert devices.VIRTUAL_NAME not in names
    finally:
        keyboard.close()
