"""The kernel's input devices, read and written directly (no extra libraries).

`keyboards()` finds the keyboards under /dev/input; `VirtualKeyboard` is a keyboard of our
own, created through /dev/uinput, used to press the paste shortcut.
"""
from __future__ import annotations

import fcntl
import glob
import os
import struct
import time

from . import keys

EVENT = struct.Struct("llHHi")   # struct input_event: seconds, microseconds, type, code, value
EV_SYN, EV_KEY = 0, 1
KEY_LEFTSHIFT = 42
VIRTUAL_NAME = "Susurros virtual keyboard"
UINPUT = "/dev/uinput"


def _ioc(direction: int, kind: str, number: int, size: int) -> int:
    return (direction << 30) | (size << 16) | (ord(kind) << 8) | number


_READ, _WRITE = 2, 1
_UI_DEV_CREATE, _UI_DEV_DESTROY = _ioc(0, "U", 1, 0), _ioc(0, "U", 2, 0)
_UI_SET_EVBIT, _UI_SET_KEYBIT = _ioc(_WRITE, "U", 100, 4), _ioc(_WRITE, "U", 101, 4)
_SETUP = struct.Struct("HHHH80sI")   # struct uinput_setup: bus, vendor, product, version, name, effects
_UI_DEV_SETUP = _ioc(_WRITE, "U", 3, _SETUP.size)


def device_name(fd: int) -> str:
    buffer = bytearray(256)
    try:
        fcntl.ioctl(fd, _ioc(_READ, "E", 0x06, len(buffer)), buffer)
    except OSError:
        return ""
    return buffer.split(b"\0", 1)[0].decode("utf-8", "replace")


def is_keyboard(fd: int) -> bool:
    """A device that has the A and Enter keys (a mouse or a power button does not)."""
    bits = bytearray(96)
    try:
        fcntl.ioctl(fd, _ioc(_READ, "E", 0x20 + EV_KEY, len(bits)), bits)
    except OSError:
        return False
    return all(bits[code // 8] & (1 << (code % 8)) for code in (keys.KEY_A, keys.KEY_ENTER))


def keyboards(skip: set[str] = frozenset()) -> tuple[dict[str, int], bool]:
    """Opens the keyboards not in `skip`: ({path: file descriptor}, whether any device was
    refused for lack of permission)."""
    found, denied = {}, False
    for path in sorted(glob.glob("/dev/input/event*")):
        if path in skip:
            continue
        try:
            fd = os.open(path, os.O_RDONLY | os.O_NONBLOCK)
        except PermissionError:
            denied = True
            continue
        except OSError:
            continue
        if is_keyboard(fd) and device_name(fd) != VIRTUAL_NAME:
            found[path] = fd
        else:
            os.close(fd)
    return found, denied


def read_keys(fd: int) -> list[tuple[int, bool]]:
    """The key presses and releases waiting on a device, as (key code, is down). Auto-repeat
    is left out. Raises OSError when the device has been unplugged."""
    try:
        data = os.read(fd, EVENT.size * 64)
    except BlockingIOError:
        return []
    events = []
    for offset in range(0, len(data) - EVENT.size + 1, EVENT.size):
        _sec, _usec, kind, code, value = EVENT.unpack_from(data, offset)
        if kind == EV_KEY and value in (0, 1):
            events.append((code, value == 1))
    return events


class VirtualKeyboard:
    """A keyboard that exists only in software. Its key presses reach whichever app is in
    front, on X11 and on Wayland alike."""

    KEYS = (keys.KEY_LEFTCTRL, keys.KEY_V, KEY_LEFTSHIFT, keys.KEY_ENTER)

    def __init__(self, path: str = UINPUT):
        self._fd = os.open(path, os.O_WRONLY | os.O_NONBLOCK)
        try:
            fcntl.ioctl(self._fd, _UI_SET_EVBIT, EV_KEY)
            for code in self.KEYS:
                fcntl.ioctl(self._fd, _UI_SET_KEYBIT, code)
            fcntl.ioctl(self._fd, _UI_DEV_SETUP, _SETUP.pack(0x06, 0x1, 0x1, 1, VIRTUAL_NAME.encode(), 0))
            fcntl.ioctl(self._fd, _UI_DEV_CREATE)
        except OSError:
            os.close(self._fd)
            raise
        self.created = time.monotonic()   # the desktop needs a moment to notice a new keyboard

    def _emit(self, kind: int, code: int, value: int) -> None:
        os.write(self._fd, EVENT.pack(0, 0, kind, code, value))

    def press(self, *codes: int) -> None:
        """Presses the keys in order and releases them in reverse: press(Ctrl, V) is Ctrl+V."""
        wait = 0.4 - (time.monotonic() - self.created)
        if wait > 0:
            time.sleep(wait)
        for code in codes:
            self._emit(EV_KEY, code, 1)
            self._emit(EV_SYN, 0, 0)
        for code in reversed(codes):
            self._emit(EV_KEY, code, 0)
            self._emit(EV_SYN, 0, 0)

    def close(self) -> None:
        try:
            fcntl.ioctl(self._fd, _UI_DEV_DESTROY)
        finally:
            os.close(self._fd)
