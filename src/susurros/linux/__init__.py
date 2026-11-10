"""Linux counterparts of the Windows-specific parts (Ubuntu and Debian): keyboard listener,
pasting, sounds and start at login. Only imported on Linux.

Keys are read from the kernel's input devices and the paste shortcut is sent through a
virtual keyboard, because that works the same on X11 and on Wayland, where apps are not
allowed to watch or press keys in other apps. Both need the user to be in the `input`
group, which scripts/install-linux.sh sets up.
"""
