"""The dictation key on Linux: every keyboard under /dev/input is read on a thread of its own.

Like on macOS, keys are only observed, never held back, so Esc cancels a dictation and also
reaches the focused app. The events feed the same `KeyFilter` as the Windows hook, with key
codes translated to the Windows ones (see keys.py).
"""
from __future__ import annotations

import logging
import os
import selectors
import threading

from PySide6.QtCore import QObject

from ..hotkey import HotkeyListener, _known_name, key_name
from . import devices, keys

log = logging.getLogger("susurros.linux.hotkey")
RESCAN_S = 3.0   # how often to look for keyboards plugged in (or for the permission to arrive)


class LinuxHotkeyListener(HotkeyListener):
    def __init__(self, parent: QObject | None = None):
        super().__init__(parent)
        self._stop = threading.Event()
        self._down: set[int] = set()   # virtual key codes that are down right now
        self.filter._pressed = self._down.__contains__

    def start(self) -> None:
        if self._thread:
            return
        self._stop.clear()
        self._thread = threading.Thread(target=self._run, name="hotkey-evdev", daemon=True)
        self._thread.start()

    def stop(self) -> None:
        self._stop.set()
        if self._thread:
            self._thread.join(timeout=1)
        self._thread = None

    def describe(self, keys_: list[int], name: str) -> str:
        return " + ".join(keys.linux_name(_known_name(vk) or key_name(vk)) for vk in keys_)

    def _report(self, installed: bool, permission: str) -> None:
        if (installed, permission) != (self.installed, self.needs_permission):
            self.installed, self.needs_permission = installed, permission
            log.info("Keyboard listener %s", "installed" if installed else
                     "waiting for permission to read the keyboard" if permission else "found no keyboard")
            self.stateChanged.emit()

    def _run(self) -> None:
        selector = selectors.DefaultSelector()
        open_devices: dict[str, int] = {}
        try:
            while not self._stop.is_set():
                found, denied = devices.keyboards(skip=set(open_devices))
                for path, fd in found.items():
                    open_devices[path] = fd
                    selector.register(fd, selectors.EVENT_READ, path)
                self._report(bool(open_devices), "input" if denied and not open_devices else "")
                deadline = RESCAN_S
                while deadline > 0 and not self._stop.is_set():
                    deadline -= 0.25
                    for key, _mask in selector.select(timeout=0.25) if open_devices else ():
                        self._read(selector, open_devices, key.fd, key.data)
                    if not open_devices:
                        self._stop.wait(0.25)
        except Exception:
            log.exception("The keyboard listener stopped")
            self.failed = True
            self.stateChanged.emit()
        finally:
            for fd in open_devices.values():
                os.close(fd)
            selector.close()
            self.installed = False

    def _read(self, selector, open_devices: dict[str, int], fd: int, path: str) -> None:
        try:
            events = devices.read_keys(fd)
        except OSError:   # unplugged
            selector.unregister(fd)
            os.close(fd)
            del open_devices[path]
            return
        for code, down in events:
            self.handle(code, down)

    def handle(self, code: int, down: bool) -> None:
        vk = keys.to_vk(code)
        (self._down.add if down else self._down.discard)(vk)
        self.filter.process(vk, code, False, down, not down)
