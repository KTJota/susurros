"""Start with the system: the user's Run key on Windows, a launch agent on macOS."""
from __future__ import annotations

import contextlib
import sys
from pathlib import Path

_RUN_KEY = r"Software\Microsoft\Windows\CurrentVersion\Run"
_NAME = "Susurros"


def _command() -> str:
    # pythonw and not susurros.exe: Windows may block the unsigned launcher.
    pythonw = Path(sys.prefix) / "Scripts" / "pythonw.exe"
    return f'"{pythonw}" -m susurros --hidden'


def is_enabled() -> bool:
    if sys.platform == "darwin":
        from .mac import system
        return system.autostart_enabled()
    if sys.platform != "win32":
        return False
    import winreg
    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, _RUN_KEY) as key:
            value, _kind = winreg.QueryValueEx(key, _NAME)
    except FileNotFoundError:
        return False
    if value != _command():
        # It pointed to another install (or to the old launcher): fixed silently.
        set_enabled(True)
    return True


def set_enabled(enabled: bool) -> None:
    if sys.platform == "darwin":
        from .mac import system
        system.set_autostart(enabled)
        return
    if sys.platform != "win32":
        return
    import winreg
    with winreg.OpenKey(winreg.HKEY_CURRENT_USER, _RUN_KEY, 0, winreg.KEY_SET_VALUE) as key:
        if enabled:
            winreg.SetValueEx(key, _NAME, 0, winreg.REG_SZ, _command())
        else:
            with contextlib.suppress(FileNotFoundError):
                winreg.DeleteValue(key, _NAME)
