"""Paths, defaults and access to the API key."""
from __future__ import annotations

import contextlib
import logging
import os
import sys
from logging.handlers import RotatingFileHandler
from pathlib import Path

APP_NAME = "Susurros"
KEYRING_SERVICE = "Susurros"
KEYRING_USER = "anthropic_api_key"

DEFAULTS: dict[str, str] = {
    "language": "es",          # "" = automatic detection
    "model": "large-v3-turbo",
    "llm_enabled": "1",
    "auto_paste": "1",
    "live_typing": "0",        # type as you speak instead of when you finish
    "trailing_space": "1",
    "sounds": "1",
    "sound_set": "bubble",    # sound set (see sounds.SETS)
    "mic_device": "",          # "" = system default microphone
    "hotkey_vk": "20",         # (earlier versions) a single key; see hotkey_keys
    "hotkey_keys": "",         # comma-separated virtual keys of the hotkey: "20", "18,49"…
    "hotkey_name": "Caps Lock",
    "ui_language": "",         # "" = follow Windows | es | en
    "theme": "system",         # system | light | dark
    "hud_always": "1",         # indicator also visible when idle
    "hud_collapsed": "0",      # collapsed against the edge
    "hud_position": "bottom",  # bottom | top | left | right
    "keep_raw": "0",           # also store the uncleaned transcription
}

# Display names are English source strings; the interface translates them (see i18n.py).
HUD_POSITIONS = [("bottom", "Bottom"), ("top", "Top"), ("left", "Left"), ("right", "Right")]
LANGUAGES = [("es", "Spanish"), ("en", "English"), ("", "Detect automatically")]
UI_LANGUAGES = [("", "Same as Windows"), ("es", "Español"), ("en", "English")]

if sys.platform == "darwin":
    # macOS reports Caps Lock when its light changes, not when the key goes down and up, so it
    # cannot be held or double-tapped. Right Command is free: on its own it does nothing.
    DEFAULTS.update(hotkey_vk="92", hotkey_name="Right Command")
    UI_LANGUAGES[0] = ("", "Same as macOS")

log = logging.getLogger("susurros")


def data_dir() -> Path:
    override = os.environ.get("SUSURROS_DATA_DIR")
    if override:
        base = Path(override)
    elif sys.platform == "win32":
        base = Path(os.environ.get("APPDATA", Path.home())) / APP_NAME
    elif sys.platform == "darwin":
        base = Path.home() / "Library" / "Application Support" / APP_NAME
    else:
        base = Path(os.environ.get("XDG_DATA_HOME", Path.home() / ".local/share")) / "susurros"
    base.mkdir(parents=True, exist_ok=True)
    return base


def setup_logging() -> None:
    """Logs to a file. Under pythonw there is no console, so we also
    redirect stdout/stderr so that no library fails when writing."""
    path = data_dir() / "susurros.log"
    # delay=True and no manual deletion: a second instance must not clash with the open file.
    handler = RotatingFileHandler(path, maxBytes=1_000_000, backupCount=1, encoding="utf-8", delay=True)
    handler.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(name)s: %(message)s"))
    logging.basicConfig(level=logging.INFO, handlers=[handler])
    if sys.stdout is None or sys.stderr is None:
        # Separate from the rotating log, so that rotation does not trip over this open file.
        stream = open(data_dir() / "output.log", "w", encoding="utf-8", buffering=1)  # noqa: SIM115
        sys.stdout = sys.stdout or stream
        sys.stderr = sys.stderr or stream


def get_api_key(allow_env: bool = False) -> str:
    """The key saved from Settings. The ANTHROPIC_API_KEY variable only counts if asked for
    (`susurros-cli`): the app must not send text to Anthropic unless a key has been entered in it."""
    try:
        import keyring
        key = keyring.get_password(KEYRING_SERVICE, KEYRING_USER)
        if key:
            return key
    except Exception:  # no credential backend available
        log.info("Credential store not available")
    return os.environ.get("ANTHROPIC_API_KEY", "") if allow_env else ""


def set_api_key(key: str) -> None:
    import keyring
    if key:
        keyring.set_password(KEYRING_SERVICE, KEYRING_USER, key)
    else:
        with contextlib.suppress(keyring.errors.PasswordDeleteError):
            keyring.delete_password(KEYRING_SERVICE, KEYRING_USER)
