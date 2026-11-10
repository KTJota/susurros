"""Writes the text into the focused application (clipboard + Ctrl+V)."""
from __future__ import annotations

import logging
import os
import sys

from PySide6.QtCore import QMimeData, QTimer
from PySide6.QtGui import QGuiApplication

log = logging.getLogger("susurros.injector")
IS_WINDOWS = sys.platform == "win32"


def foreground_app() -> str:
    """Executable name of the active window, e.g. "Code" or "chrome"."""
    if not IS_WINDOWS:
        return ""
    import ctypes
    from ctypes import wintypes
    user32, kernel32 = ctypes.windll.user32, ctypes.windll.kernel32
    user32.GetForegroundWindow.restype = wintypes.HWND
    kernel32.OpenProcess.restype = wintypes.HANDLE
    hwnd = user32.GetForegroundWindow()
    if not hwnd:
        return ""
    pid = wintypes.DWORD()
    user32.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
    handle = kernel32.OpenProcess(0x1000, False, pid.value)  # PROCESS_QUERY_LIMITED_INFORMATION
    if not handle:
        return ""
    try:
        buf = ctypes.create_unicode_buffer(1024)
        size = wintypes.DWORD(len(buf))
        if kernel32.QueryFullProcessImageNameW(wintypes.HANDLE(handle), 0, buf, ctypes.byref(size)):
            return os.path.splitext(os.path.basename(buf.value))[0]
    finally:
        kernel32.CloseHandle(wintypes.HANDLE(handle))
    return ""


def _send_keys(keys: list[tuple[int, int, int]]) -> None:
    """Sends synthetic keyboard events: tuples of (virtual key, UTF-16 character, flags)."""
    import ctypes
    from ctypes import wintypes

    class KEYBDINPUT(ctypes.Structure):
        _fields_ = [("wVk", wintypes.WORD), ("wScan", wintypes.WORD), ("dwFlags", wintypes.DWORD),
                    ("time", wintypes.DWORD), ("dwExtraInfo", ctypes.c_size_t)]

    class MOUSEINPUT(ctypes.Structure):  # only so the union has the right size
        _fields_ = [("dx", wintypes.LONG), ("dy", wintypes.LONG), ("mouseData", wintypes.DWORD),
                    ("dwFlags", wintypes.DWORD), ("time", wintypes.DWORD),
                    ("dwExtraInfo", ctypes.c_size_t)]

    class _U(ctypes.Union):
        _fields_ = [("ki", KEYBDINPUT), ("mi", MOUSEINPUT)]

    class INPUT(ctypes.Structure):
        _fields_ = [("type", wintypes.DWORD), ("u", _U)]

    events = (INPUT * len(keys))(*(
        INPUT(type=1, u=_U(ki=KEYBDINPUT(wVk=vk, wScan=scan, dwFlags=flags))) for vk, scan, flags in keys))
    sent = ctypes.windll.user32.SendInput(len(keys), events, ctypes.sizeof(INPUT))
    if sent != len(keys):
        log.warning("SendInput only sent %d of %d events", sent, len(keys))


_KEYUP, _UNICODE = 0x0002, 0x0004


def _send_ctrl_v() -> None:
    vk_control, vk_v = 0x11, 0x56
    _send_keys([(vk_control, 0, 0), (vk_v, 0, 0), (vk_v, 0, _KEYUP), (vk_control, 0, _KEYUP)])


def type_text(text: str) -> None:
    """Types `text` into the active window character by character, without using the clipboard.
    This is what on-the-fly dictation uses, since it writes many small pieces."""
    if not IS_WINDOWS or not text:
        return
    units = text.encode("utf-16-le")
    keys = []
    for i in range(0, len(units), 2):
        code = int.from_bytes(units[i:i + 2], "little")
        keys += [(0, code, _UNICODE), (0, code, _UNICODE | _KEYUP)]
    for i in range(0, len(keys), 400):   # in batches, so as not to flood the input queue
        _send_keys(keys[i:i + 400])


def _clone(mime: QMimeData) -> QMimeData:
    """Copy of what is on the clipboard, with images, files and formatting."""
    copy = QMimeData()
    if mime is None:
        return copy
    for fmt in mime.formats():
        copy.setData(fmt, mime.data(fmt))
    if mime.hasImage():
        copy.setImageData(mime.imageData())
    if mime.hasUrls():
        copy.setUrls(mime.urls())
    if mime.hasHtml():
        copy.setHtml(mime.html())
    if mime.hasText():
        copy.setText(mime.text())
    return copy


class _Paster:
    """Pastes through the clipboard and leaves it as it was. Keeps a single copy of the original
    content even if several dictations arrive in a row, so as not to restore an earlier dictation."""

    def __init__(self):
        self._original: QMimeData | None = None
        self._ours = ""
        self._timer = QTimer(singleShot=True, interval=900, timeout=self._restore)

    def paste(self, text: str) -> None:
        clipboard = QGuiApplication.clipboard()
        if self._original is None:
            self._original = _clone(clipboard.mimeData())
        self._ours = text
        clipboard.setText(text)
        QTimer.singleShot(60, _send_ctrl_v)
        self._timer.start()   # restarts the wait if a restore was pending

    def _restore(self) -> None:
        clipboard = QGuiApplication.clipboard()
        original, self._original = self._original, None
        # If the user has copied something else in the meantime, do not overwrite it.
        if original is not None and clipboard.text() == self._ours:
            clipboard.setMimeData(original)


_paster: _Paster | None = None


def paste(text: str) -> None:
    """Pastes `text` into the active window and puts back what was on the clipboard."""
    global _paster
    if not IS_WINDOWS:
        QGuiApplication.clipboard().setText(text)   # outside Windows it stays on the clipboard
        return
    if _paster is None:
        _paster = _Paster()
    _paster.paste(text)
