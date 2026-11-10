"""Synthetic keyboard input on macOS (needs the Accessibility permission)."""
from __future__ import annotations

import logging
import time

from . import keys

log = logging.getLogger("susurros.mac.injector")


def _post(keycode: int, down: bool, flags: int = 0, text: str = "") -> None:
    import Quartz
    event = Quartz.CGEventCreateKeyboardEvent(None, keycode, down)
    if event is None:
        raise OSError("macOS did not create the keyboard event")
    if text:
        Quartz.CGEventKeyboardSetUnicodeString(event, len(text.encode("utf-16-le")) // 2, text)
    # The flags are set outright: a modifier still held (the dictation key, while typing on the
    # fly) must not turn the typed text into shortcuts.
    Quartz.CGEventSetFlags(event, flags)
    Quartz.CGEventSetIntegerValueField(event, Quartz.kCGEventSourceUserData, keys.OWN_EVENT)
    Quartz.CGEventPost(Quartz.kCGHIDEventTap, event)


def send_cmd_v() -> None:
    _post(keys.KEYCODE_V, True, keys.FLAG_COMMAND)
    _post(keys.KEYCODE_V, False, keys.FLAG_COMMAND)


def type_text(text: str) -> None:
    """Types `text` into the active app without using the clipboard."""
    for index, line in enumerate(text.split("\n")):
        if index:
            _post(keys.KEYCODE_RETURN, True)
            _post(keys.KEYCODE_RETURN, False)
        for chunk in keys.utf16_chunks(line):
            _post(0, True, text=chunk)
            _post(0, False, text=chunk)
            time.sleep(0.002)   # a breath between pieces: some apps drop text that arrives in a burst
