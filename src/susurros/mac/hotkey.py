"""The dictation key on macOS: an event tap that only listens.

It never holds a key back, so a slow moment in the app cannot delay the keyboard of the whole
system. The price is that Esc, besides cancelling a dictation, also reaches the focused app.
The tap feeds the same `KeyFilter` as the Windows hook, with key codes translated to the
Windows ones (see keys.py).
"""
from __future__ import annotations

import logging
import threading

from PySide6.QtCore import QObject, QTimer

from ..hotkey import HotkeyListener, _known_name
from . import keys, system

log = logging.getLogger("susurros.mac.hotkey")


class MacHotkeyListener(HotkeyListener):
    def __init__(self, parent: QObject | None = None):
        super().__init__(parent)
        self._tap = None
        self._loop = None
        self._callback = None                # kept alive for as long as the tap exists
        self._held: set[int] = set()         # modifier key codes that are down
        self._labels: dict[int, str] = {}    # what the keys pressed while choosing a shortcut type
        self._asked = False
        self._retry = QTimer(self, interval=2000, timeout=self._install)

    def start(self) -> None:
        if not self._thread:
            self._install()

    def stop(self) -> None:
        self._retry.stop()
        if self._thread and self._loop is not None:
            import Quartz
            Quartz.CFRunLoopStop(self._loop)
            self._thread.join(timeout=1)
        self._thread = None

    def describe(self, keys_: list[int], name: str) -> str:
        """Names every key the macOS way, with what it types for the keys only the layout can name."""
        return " + ".join(
            keys.mac_name(known) if (known := _known_name(vk)) else keys.label(vk, self._labels.get(vk, ""))
            for vk in keys_)

    # -- installing the tap ------------------------------------------------
    def _install(self) -> None:
        """Creates the tap, or reports which permission is missing and tries again every two
        seconds: macOS grants permissions in System Settings, while the app is running."""
        prompt, self._asked = not self._asked, True
        if not system.accessibility_granted(prompt=prompt):
            self._waiting("accessibility")
            return
        import Quartz
        mask = (Quartz.CGEventMaskBit(Quartz.kCGEventKeyDown) | Quartz.CGEventMaskBit(Quartz.kCGEventKeyUp)
                | Quartz.CGEventMaskBit(Quartz.kCGEventFlagsChanged))
        self._callback = self._on_event
        tap = Quartz.CGEventTapCreate(Quartz.kCGSessionEventTap, Quartz.kCGHeadInsertEventTap,
                                      Quartz.kCGEventTapOptionListenOnly, mask, self._callback, None)
        if tap is None:
            if self.needs_permission != "input":
                system.request_input_monitoring()
            self._waiting("input")
            return
        self._retry.stop()
        self._tap = tap
        self.filter._pressed = self._is_pressed
        self._thread = threading.Thread(target=self._run, name="hotkey-tap", daemon=True)
        self._thread.start()
        self.installed, self.failed, self.needs_permission = True, False, ""
        log.info("Keyboard listener installed")
        self.stateChanged.emit()

    def _waiting(self, permission: str) -> None:
        if self.needs_permission != permission:
            log.info("Waiting for the %s permission", permission)
            self.needs_permission = permission
            self.stateChanged.emit()
        self._retry.start()

    def _run(self) -> None:
        import Quartz
        source = Quartz.CFMachPortCreateRunLoopSource(None, self._tap, 0)
        self._loop = Quartz.CFRunLoopGetCurrent()
        Quartz.CFRunLoopAddSource(self._loop, source, Quartz.kCFRunLoopCommonModes)
        Quartz.CGEventTapEnable(self._tap, True)
        Quartz.CFRunLoopRun()
        Quartz.CGEventTapEnable(self._tap, False)
        self.installed = False

    # -- events ------------------------------------------------------------
    @staticmethod
    def _is_pressed(vk: int) -> bool:
        import Quartz
        return any(Quartz.CGEventSourceKeyState(Quartz.kCGEventSourceStateHIDSystemState, keycode)
                   for keycode in keys.VK_TO_KEYCODES.get(vk, ()))

    def _on_event(self, _proxy, kind, event, _refcon):
        """Runs on the tap's thread for every key. The return value is ignored by a tap that
        only listens; the event is handed back anyway, as the API asks."""
        try:
            import Quartz
            if kind in (Quartz.kCGEventTapDisabledByTimeout, Quartz.kCGEventTapDisabledByUserInput):
                Quartz.CGEventTapEnable(self._tap, True)   # macOS switched the tap off: back on
                return event
            if Quartz.CGEventGetIntegerValueField(event, Quartz.kCGEventSourceUserData) == keys.OWN_EVENT:
                return event                               # text typed by Susurros itself
            keycode = Quartz.CGEventGetIntegerValueField(event, Quartz.kCGKeyboardEventKeycode)
            if kind == Quartz.kCGEventFlagsChanged:
                down = keys.modifier_is_down(keycode, Quartz.CGEventGetFlags(event), self._held)
                if down is None:
                    return event
            else:
                down = kind == Quartz.kCGEventKeyDown
            vk = keys.to_vk(keycode)
            if down and self.filter.capturing and kind != Quartz.kCGEventFlagsChanged:
                self._labels[vk] = self._typed(event)
            self.filter.process(vk, keycode, False, down, not down)
        except Exception:
            log.exception("Keyboard event failed")
        return event

    @staticmethod
    def _typed(event) -> str:
        """The character a key press types on the current keyboard layout, or ""."""
        try:
            import Quartz
            _length, text = Quartz.CGEventKeyboardGetUnicodeString(event, 4, None, None)
            return text or ""
        except Exception:
            return ""
