"""Linux services: the paste shortcut, sounds and start at login."""
from __future__ import annotations

import logging
import os
import shutil
import subprocess
import sys
from pathlib import Path

from . import devices, keys

log = logging.getLogger("susurros.linux")
_keyboard: devices.VirtualKeyboard | None = None


# -- pasting ---------------------------------------------------------------------
def prepare_keyboard() -> bool:
    """Creates the virtual keyboard ahead of time: the desktop takes a moment to accept a new
    one. False if /dev/uinput cannot be opened (the user is not in the `input` group yet)."""
    global _keyboard
    if _keyboard is None:
        try:
            _keyboard = devices.VirtualKeyboard()
        except OSError as exc:
            log.warning("Cannot create the virtual keyboard: %s", exc)
            return False
    return True


def send_ctrl_v() -> None:
    if prepare_keyboard():
        _keyboard.press(keys.KEY_LEFTCTRL, keys.KEY_V)


# -- sounds ----------------------------------------------------------------------
def play_sound(path: str) -> None:
    """Through whichever player the desktop has: PulseAudio/PipeWire first, plain ALSA last."""
    for player in ("paplay", "pw-play", "aplay"):
        command = shutil.which(player)
        if command:
            args = [command, "-q", path] if player == "aplay" else [command, path]
            subprocess.Popen(args, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            return
    log.info("No sound player found (paplay, pw-play or aplay)")


# -- start at login --------------------------------------------------------------
def _entry_path() -> Path:
    config = Path(os.environ.get("XDG_CONFIG_HOME") or Path.home() / ".config")
    return config / "autostart" / "susurros.desktop"


def _entry() -> str:
    return ("[Desktop Entry]\nType=Application\nName=Susurros\nComment=Voice dictation\n"
            f"Exec={sys.executable} -m susurros --hidden\nIcon=susurros\nTerminal=false\n")


def autostart_enabled() -> bool:
    path = _entry_path()
    if not path.exists():
        return False
    if path.read_text(encoding="utf-8") != _entry():
        set_autostart(True)   # it pointed to another install: fixed silently
    return True


def set_autostart(enabled: bool) -> None:
    path = _entry_path()
    if enabled:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(_entry(), encoding="utf-8")
    else:
        path.unlink(missing_ok=True)
