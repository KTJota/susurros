"""The dictation key: Caps Lock by default, or any key or combination (Alt + 1, Ctrl + Windows…).

`TapMachine` is the pure logic (hold / double tap) and can be tested without a
keyboard. `KeyFilter` decides, key by key, what is the shortcut and what must be
swallowed; it is pure logic too. `HotkeyListener` installs a low-level keyboard hook
on Windows, swallows the chosen key so it does not do its normal job, and forwards
the events to the Qt thread through signals.
"""
from __future__ import annotations

import logging
import sys
import threading
import time
from collections.abc import Callable

from PySide6.QtCore import QObject, Signal

log = logging.getLogger("susurros.hotkey")

HOLD_MS = 300        # from here on a press counts as a "hold"
DOUBLE_TAP_MS = 400  # window for the second tap


class TapMachine:
    """States:
    idle     -> press: starts recording (pressed)
    pressed  -> late release: finishes and transcribes · early release: tap_wait
    tap_wait -> second press in time: hands-free (locked)
                the window runs out: discarded (it was a stray tap)
    locked   -> double tap: finishes and transcribes
    """

    def __init__(self, *, on_start: Callable[[], bool | None], on_stop: Callable[[], None],
                 on_cancel: Callable[[], None], on_lock: Callable[[], None],
                 set_timer: Callable[[int], None], cancel_timer: Callable[[], None],
                 hold_ms: int = HOLD_MS, double_ms: int = DOUBLE_TAP_MS):
        self.state = "idle"
        self._on_start, self._on_stop = on_start, on_stop
        self._on_cancel, self._on_lock = on_cancel, on_lock
        self._set_timer, self._cancel_timer = set_timer, cancel_timer
        self.hold_s, self.double_s = hold_ms / 1000, double_ms / 1000
        self.double_ms = double_ms
        self._t_down = 0.0
        self._last_locked_down: float | None = None

    @property
    def active(self) -> bool:
        return self.state != "idle"

    def down(self, t: float) -> None:
        if self.state == "idle":
            if self._on_start() is False:
                return   # could not start (model loading, no microphone): stay idle
            self.state, self._t_down = "pressed", t
        elif self.state == "tap_wait":
            self._cancel_timer()
            self.state, self._last_locked_down = "locked", None
            self._on_lock()
        elif self.state == "locked":
            last = self._last_locked_down
            if last is not None and t - last <= self.double_s:
                self.state = "idle"
                self._on_stop()
            else:
                self._last_locked_down = t

    def up(self, t: float) -> None:
        if self.state != "pressed":
            return
        if t - self._t_down >= self.hold_s:
            self.state = "idle"
            self._on_stop()
        else:
            self.state = "tap_wait"
            self._set_timer(self.double_ms)

    def timeout(self) -> None:
        if self.state == "tap_wait":
            self.state = "idle"
            self._on_cancel()

    def cancel(self) -> None:
        """Escape, or any external abort."""
        if self.state != "idle":
            self._cancel_timer()
            self.state = "idle"
            self._on_cancel()

    def force_stop(self) -> None:
        """Finishes as if the user had ended the dictation (time limit)."""
        if self.state != "idle":
            self._cancel_timer()
            self.state = "idle"
            self._on_stop()


VK_CAPITAL, VK_ESCAPE, VK_SHIFT = 0x14, 0x1B, 0x10
VK_CONTROL, VK_ALT, VK_WIN = 0x11, 0x12, 0x5B
VK_MASK = 0xE8   # unassigned key: stops Alt or Windows from opening the menu on release
MAX_COMBO = 3

# In a combination modifiers count for both sides: "Ctrl" is the left or the right one.
_MOD_GROUPS = {VK_CONTROL: (0x11, 0xA2, 0xA3), VK_ALT: (0x12, 0xA4, 0xA5),
               VK_SHIFT: (0x10, 0xA0, 0xA1), VK_WIN: (0x5B, 0x5C)}
_CANONICAL = {vk: canon for canon, group in _MOD_GROUPS.items() for vk in group}
_MOD_ORDER = (VK_CONTROL, VK_ALT, VK_SHIFT, VK_WIN)
_KEY_NAMES = {
    0x14: "Caps Lock", 0x90: "Num Lock", 0x91: "Scroll Lock", 0x13: "Pause", 0x2D: "Insert",
    0x2C: "Print Screen", 0x5D: "Menu", 0x20: "Space", 0x09: "Tab",
    0x11: "Ctrl", 0x12: "Alt", 0x10: "Shift", 0x5B: "Win",
    0xA2: "Left Ctrl", 0xA3: "Right Ctrl", 0xA4: "Left Alt", 0xA5: "Right Alt",
    0xA0: "Left Shift", 0xA1: "Right Shift", 0x5C: "Right Win",
}


def _known_name(vk: int) -> str | None:
    """English name of a key that needs no keyboard layout to be named, or None."""
    if vk in _KEY_NAMES:
        return _KEY_NAMES[vk]
    if 0x70 <= vk <= 0x87:
        return f"F{vk - 0x6F}"
    if 0x30 <= vk <= 0x39 or 0x41 <= vk <= 0x5A:
        return chr(vk)
    if 0x60 <= vk <= 0x69:
        return f"Num {vk - 0x60}"
    return None


def combo_name(keys: list[int], translate: Callable[[str], str] = str, fallback: str = "") -> str:
    """Display name of a stored shortcut in the current interface language. `translate` maps the
    English key names ("Caps Lock", "Shift"); letters, digits and F-keys are the same everywhere.
    A key only the keyboard layout can name (e.g. "º") makes it return `fallback`, the name
    Windows gave when the shortcut was chosen."""
    names = [_known_name(vk) for vk in keys]
    if not keys or any(name is None for name in names):
        return fallback or " + ".join(key_name(vk) for vk in keys)
    return " + ".join(name if len(name) <= 1 else translate(name) for name in names)


def canonical(vk: int) -> int:
    return _CANONICAL.get(vk, vk)


def is_modifier(vk: int) -> bool:
    return vk in _CANONICAL


def key_name(vk: int, scan: int = 0, extended: bool = False) -> str:
    """Readable name of a key, in the keyboard's language when Windows knows it."""
    if vk in _KEY_NAMES:
        return _KEY_NAMES[vk]
    if 0x70 <= vk <= 0x87:
        return f"F{vk - 0x6F}"
    if 0x30 <= vk <= 0x39 or 0x41 <= vk <= 0x5A:
        return chr(vk)                       # digits and letters: their own character
    if 0x60 <= vk <= 0x69:
        return f"Num {vk - 0x60}"
    if sys.platform == "win32" and scan:
        import ctypes
        buf = ctypes.create_unicode_buffer(64)
        if ctypes.windll.user32.GetKeyNameTextW((scan << 16) | (int(extended) << 24), buf, 64):
            return buf.value.capitalize() if len(buf.value) > 1 else buf.value.upper()
    return f"Key {vk}"


def normalize_combo(captured: list[tuple[int, int, bool]]) -> tuple[list[int], str]:
    """From the keys pressed while choosing a shortcut, (codes to store, display name).
    A single key is stored as is ("Right Ctrl" can be chosen); in a combination
    the modifiers are generalised and go first: "Ctrl + Alt + 1".
    """
    if len(captured) == 1:
        vk, scan, extended = captured[0]
        return [vk], key_name(vk, scan, extended)
    names: dict[int, str] = {}
    for vk, scan, extended in captured:
        key = canonical(vk)
        names.setdefault(key, key_name(key, 0 if is_modifier(vk) else scan, extended))
    ordered = [m for m in _MOD_ORDER if m in names] + [k for k in names if not is_modifier(k)]
    if len(ordered) == 1:   # both Ctrl keys at once, for example: that is a single key
        return ordered, names[ordered[0]]
    return ordered, " + ".join(names[k] for k in ordered)


def parse_keys(text: str, fallback: int = VK_CAPITAL) -> list[int]:
    try:
        keys = [int(part) for part in text.split(",") if part.strip()]
    except ValueError:
        keys = []
    return keys[:MAX_COMBO] or [fallback]


class KeyFilter:
    """Receives every keyboard event and says whether to swallow it. No Windows dependencies:
    `pressed(vk)` asks whether a key is down and the other arguments are callbacks."""

    def __init__(self, *, pressed: Callable[[int], bool], on_down: Callable[[], None],
                 on_up: Callable[[], None], on_escape: Callable[[], None],
                 on_captured: Callable[[list], None], mask: Callable[[], None]):
        self._pressed, self._mask = pressed, mask
        self._on_down, self._on_up = on_down, on_up
        self._on_escape, self._on_captured = on_escape, on_captured
        self.keys: tuple[int, ...] = (VK_CAPITAL,)
        self.enabled = True
        self.capture_escape = False
        self.capturing = False
        self._captured: dict[int, tuple[int, bool]] = {}
        self._active = False               # the shortcut is held right now
        self._swallowed: set[int] = set()  # keys whose press we swallowed: their release too

    @property
    def combo(self) -> bool:
        return len(self.keys) > 1

    def set_keys(self, keys: list[int]) -> None:
        self.keys = tuple(keys)
        self._active = False

    def set_enabled(self, enabled: bool) -> None:
        self.enabled = enabled
        self._active = False   # a key released while paused leaves no dangling state

    def begin_capture(self) -> None:
        self._captured = {}
        self.capturing = True

    def cancel_capture(self) -> None:
        self.capturing = False
        self._captured = {}

    def _mod_down(self, canon: int) -> bool:
        return any(self._pressed(vk) for vk in _MOD_GROUPS[canon])

    def _others_down(self, key: int) -> bool:
        return all(self._mod_down(k) if is_modifier(k) else self._pressed(k)
                   for k in self.keys if k != key)

    def _foreign_modifier(self) -> bool:
        """A modifier outside the shortcut is down: Ctrl + Alt + 1 is not Alt + 1."""
        return any(self._mod_down(m) for m in _MOD_ORDER if m not in self.keys)

    def process(self, vk: int, scan: int, extended: bool, is_down: bool, is_up: bool) -> bool:
        release = is_up and vk in self._swallowed
        if release:
            self._swallowed.discard(vk)

        if self.capturing:
            # Keys are recorded as they go down; when the first one is released, that is the shortcut.
            if is_down:
                if vk not in self._captured and len(self._captured) < MAX_COMBO:
                    self._captured[vk] = (scan, extended)
                self._swallowed.add(vk)
                return True
            if is_up and self._captured:
                captured = [(k, s, e) for k, (s, e) in self._captured.items()]
                self.cancel_capture()
                self._on_captured(captured)
            return release

        key = canonical(vk) if self.combo else vk
        if self.enabled and key in self.keys:
            # The shortcut is only observed, never swallowed: Windows and the focused app get
            # every press as usual (Caps Lock still toggles capitals, even mid-dictation).
            if is_down:
                self._key_down(vk, key)
            elif is_up and self._active:
                self._active = False
                self._on_up()
        elif vk == VK_ESCAPE and is_down and (self.capture_escape or vk in self._swallowed):
            # Esc is the one key taken over, and only while a dictation is running: it cancels
            # the dictation and must not also close a dialog in the app. Auto-repeat included.
            if vk not in self._swallowed:
                self._swallowed.add(vk)
                self._on_escape()
            return True
        return release

    def _key_down(self, vk: int, key: int) -> None:
        if self._active:
            return                           # auto-repeat while held
        if self.combo and (not self._others_down(key) or self._foreign_modifier()):
            return
        self._active = True
        self._on_down()
        if self.combo and (VK_ALT in self.keys or VK_WIN in self.keys):
            self._mask()                     # otherwise releasing Alt or Win would open a menu


class HotkeyListener(QObject):
    keyDown = Signal(float)
    keyUp = Signal(float)
    escapePressed = Signal()
    keysCaptured = Signal(object)   # list of (vk, scan code, extended key)
    stateChanged = Signal()         # the listener got installed, or is waiting for a permission (macOS)
    needs_permission = ""           # macOS only: the privacy permission still missing, if any

    def __init__(self, parent: QObject | None = None):
        super().__init__(parent)
        self.filter = KeyFilter(
            pressed=lambda _vk: False, mask=lambda: None,
            on_down=lambda: self.keyDown.emit(time.monotonic()),
            on_up=lambda: self.keyUp.emit(time.monotonic()),
            on_escape=self.escapePressed.emit, on_captured=self.keysCaptured.emit)
        self._thread: threading.Thread | None = None
        self._thread_id = 0
        self.installed = False
        self.failed = False      # installing the hook was attempted and Windows refused it

    def describe(self, keys: list[int], name: str) -> str:
        """Display name to store for a shortcut just chosen. Windows already named it."""
        return name

    def start(self) -> None:
        if sys.platform != "win32" or self._thread:
            return
        self._thread = threading.Thread(target=self._run, name="hotkey-hook", daemon=True)
        self._thread.start()

    def stop(self) -> None:
        if self._thread and self._thread_id:
            import ctypes
            ctypes.windll.user32.PostThreadMessageW(self._thread_id, 0x0012, 0, 0)  # WM_QUIT
            self._thread.join(timeout=1)
        self._thread = None

    def _run(self) -> None:
        import ctypes
        import os
        from ctypes import wintypes

        user32 = ctypes.WinDLL("user32", use_last_error=True)
        kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)

        WH_KEYBOARD_LL = 13
        WM_KEYDOWN, WM_KEYUP, WM_SYSKEYDOWN, WM_SYSKEYUP = 0x100, 0x101, 0x104, 0x105
        LLKHF_EXTENDED, LLKHF_INJECTED = 0x01, 0x10
        LRESULT = ctypes.c_ssize_t

        class KBDLLHOOKSTRUCT(ctypes.Structure):
            _fields_ = [("vkCode", wintypes.DWORD), ("scanCode", wintypes.DWORD),
                        ("flags", wintypes.DWORD), ("time", wintypes.DWORD),
                        ("dwExtraInfo", ctypes.c_size_t)]

        HOOKPROC = ctypes.WINFUNCTYPE(LRESULT, ctypes.c_int, wintypes.WPARAM, wintypes.LPARAM)
        user32.SetWindowsHookExW.argtypes = [ctypes.c_int, HOOKPROC, wintypes.HINSTANCE, wintypes.DWORD]
        user32.SetWindowsHookExW.restype = ctypes.c_void_p
        user32.CallNextHookEx.argtypes = [ctypes.c_void_p, ctypes.c_int, wintypes.WPARAM, wintypes.LPARAM]
        user32.CallNextHookEx.restype = LRESULT
        user32.UnhookWindowsHookEx.argtypes = [ctypes.c_void_p]
        user32.GetAsyncKeyState.argtypes = [ctypes.c_int]
        user32.GetAsyncKeyState.restype = ctypes.c_short
        user32.keybd_event.argtypes = [wintypes.BYTE, wintypes.BYTE, wintypes.DWORD, ctypes.c_size_t]

        def mask() -> None:
            user32.keybd_event(VK_MASK, 0, 0, 0)
            user32.keybd_event(VK_MASK, 0, 0x0002, 0)

        self.filter._pressed = lambda vk: bool(user32.GetAsyncKeyState(vk) & 0x8000)
        self.filter._mask = mask
        # For automated tests only: accept synthetic keys.
        accept_injected = os.environ.get("SUSURROS_ACCEPT_INJECTED") == "1"

        def proc(n_code, w_param, l_param):
            if n_code == 0:
                kb = ctypes.cast(l_param, ctypes.POINTER(KBDLLHOOKSTRUCT)).contents
                if (accept_injected or not kb.flags & LLKHF_INJECTED) and self.filter.process(
                        kb.vkCode, kb.scanCode, bool(kb.flags & LLKHF_EXTENDED),
                        w_param in (WM_KEYDOWN, WM_SYSKEYDOWN), w_param in (WM_KEYUP, WM_SYSKEYUP)):
                    return 1
            return user32.CallNextHookEx(None, n_code, w_param, l_param)

        callback = HOOKPROC(proc)  # keep the reference alive for as long as the hook lasts
        self._thread_id = kernel32.GetCurrentThreadId()
        hook = user32.SetWindowsHookExW(WH_KEYBOARD_LL, callback, None, 0)
        self.installed, self.failed = bool(hook), not hook
        log.info("Keyboard hook %s", "installed" if hook else
                 f"not installed (error {ctypes.get_last_error()})")
        if not hook:
            return
        msg = wintypes.MSG()
        while user32.GetMessageW(ctypes.byref(msg), None, 0, 0) > 0:
            pass
        user32.UnhookWindowsHookEx(hook)
        self.installed = False


def create_listener(parent: QObject | None = None) -> HotkeyListener:
    """The keyboard listener for this system: the Windows hook, the macOS event tap or the Linux reader."""
    if sys.platform == "darwin":
        from .mac.hotkey import MacHotkeyListener
        return MacHotkeyListener(parent)
    if sys.platform.startswith("linux"):
        from .linux.hotkey import LinuxHotkeyListener
        return LinuxHotkeyListener(parent)
    return HotkeyListener(parent)
