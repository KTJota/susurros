"""macOS counterparts of the Windows-specific parts: keyboard listener, text injection,
permissions, sounds, start at login and the Apple Silicon speech engine.

Nothing here is imported on Windows. Only `keys` is free of macOS dependencies (so it can be
tested anywhere); the other modules need PyObjC and must be imported on macOS only.
"""
