"""macOS services: privacy permissions, sounds, the active app, floating windows and start at login."""
from __future__ import annotations

import logging
import plistlib
import sys
from pathlib import Path

log = logging.getLogger("susurros.mac")

BUNDLE_ID = "io.github.ktjota.susurros"


# -- privacy permissions -----------------------------------------------------
def accessibility_granted(prompt: bool = False) -> bool:
    """Accessibility is what lets the app type the dictation into other apps and see the
    shortcut. With `prompt`, macOS shows its own dialog pointing to System Settings."""
    import ApplicationServices as services
    if services.AXIsProcessTrusted():
        return True
    if prompt:
        services.AXIsProcessTrustedWithOptions({services.kAXTrustedCheckOptionPrompt: True})
    return False


def request_input_monitoring() -> None:
    """Asks for Input Monitoring, in case macOS wants it on top of Accessibility."""
    import Quartz
    request = getattr(Quartz, "CGRequestListenEventAccess", None)
    if request:
        request()


def request_microphone() -> None:
    """Shows the microphone permission dialog at startup instead of on the first dictation,
    which would otherwise be recorded as silence while the dialog is on screen."""
    try:
        import AVFoundation as av
        if av.AVCaptureDevice.authorizationStatusForMediaType_(av.AVMediaTypeAudio) == 0:  # not asked yet
            av.AVCaptureDevice.requestAccessForMediaType_completionHandler_(
                av.AVMediaTypeAudio, lambda _granted: None)
    except Exception:
        log.warning("Could not ask for the microphone permission", exc_info=True)


# -- sounds --------------------------------------------------------------------
_sounds: dict[str, object] = {}


def play_sound(path: str) -> None:
    from AppKit import NSSound
    sound = _sounds.get(path)
    if sound is None:
        sound = NSSound.alloc().initWithContentsOfFile_byReference_(path, True)
        if sound is None:
            raise OSError(f"macOS could not load {path}")
        _sounds[path] = sound
    if sound.isPlaying():
        sound.stop()
    sound.play()


# -- active app ----------------------------------------------------------------
def frontmost_app() -> str:
    """Name of the app in front, e.g. "Safari"."""
    try:
        from AppKit import NSWorkspace
        app = NSWorkspace.sharedWorkspace().frontmostApplication()
        return str(app.localizedName() or "") if app else ""
    except Exception:
        log.warning("Could not read the active app", exc_info=True)
        return ""


# -- floating windows ----------------------------------------------------------
def float_window(widget) -> None:
    """Makes a Qt window behave like a system overlay: visible on every desktop and over
    full-screen apps, still there when another app is active, and clickable without taking
    the keyboard away from the app being dictated into."""
    from PySide6.QtGui import QGuiApplication
    if QGuiApplication.platformName() != "cocoa":
        return   # e.g. the off-screen platform of the tests: there is no native window
    try:
        import AppKit
        import objc
        view = objc.objc_object(c_void_p=int(widget.winId()))
        window = view.window()
        if window is None:
            return
        window.setCollectionBehavior_(
            AppKit.NSWindowCollectionBehaviorCanJoinAllSpaces
            | AppKit.NSWindowCollectionBehaviorStationary
            | AppKit.NSWindowCollectionBehaviorFullScreenAuxiliary
            | AppKit.NSWindowCollectionBehaviorIgnoresCycle)
        window.setLevel_(AppKit.NSStatusWindowLevel)
        window.setHidesOnDeactivate_(False)
        window.setHasShadow_(False)   # the shadow would not follow the animated shape
        if window.isKindOfClass_(AppKit.NSPanel):
            window.setStyleMask_(window.styleMask() | AppKit.NSWindowStyleMaskNonactivatingPanel)
    except Exception:
        log.warning("Could not adjust a floating window", exc_info=True)


# -- start at login ------------------------------------------------------------
def _agent_path() -> Path:
    return Path.home() / "Library" / "LaunchAgents" / f"{BUNDLE_ID}.plist"


def _program() -> list[str]:
    if getattr(sys, "frozen", False):          # the packaged app: its own executable
        return [sys.executable, "--hidden"]
    return [sys.executable, "-m", "susurros", "--hidden"]


def _agent() -> dict:
    return {"Label": BUNDLE_ID, "ProgramArguments": _program(), "RunAtLoad": True,
            "ProcessType": "Interactive"}


def autostart_enabled() -> bool:
    path = _agent_path()
    if not path.exists():
        return False
    try:
        current = plistlib.loads(path.read_bytes())
    except Exception:
        current = {}
    if current.get("ProgramArguments") != _program():
        set_autostart(True)   # it pointed to another copy of the app: fixed silently
    return True


def set_autostart(enabled: bool) -> None:
    """A launch agent in the user's Library: macOS runs it at login, no admin rights needed."""
    path = _agent_path()
    if enabled:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(plistlib.dumps(_agent()))
    else:
        path.unlink(missing_ok=True)
