Voice dictation for Ubuntu and Debian. Your voice is turned into text on your own computer.

This first Linux version has been checked automatically on Ubuntu (tests, a real virtual keyboard read back through the kernel, and a start of the installed app), but not yet by a person at a real desktop. Please report what does not work.

## Install

Open a terminal, paste this line and press Enter:

```sh
curl -fsSL https://raw.githubusercontent.com/KTJota/susurros/main/scripts/install-linux.sh | bash
```

It asks for your password once: to install a few system packages, and to add your user to the `input` group, which is what lets Susurros notice the dictation key and press Ctrl+V for you on both X11 and Wayland. **Log out and back in** afterwards, then open Susurros from the applications menu.

If the computer has an NVIDIA card, the installer adds the GPU libraries; otherwise dictation runs on the CPU, which is slower. The speech model, about 1.6 GB, is downloaded the first time the app opens.

Prefer to look before you run? Download the archive below, extract it and run `bash scripts/install-linux.sh` from its folder.

## Use

Hold Caps Lock, speak and release. Press it twice in a row to dictate hands-free, and twice again to finish. The shortcut can be changed in Settings.

## Good to know

- The text is pasted with Ctrl+V. In a terminal, where paste is Ctrl+Shift+V, copy the dictation from the history instead.
- Esc cancels a dictation but also reaches the app in front.
- On GNOME, the tray icon needs the AppIndicator extension (Ubuntu has it; Debian does not by default). Without it, open Susurros again from the applications menu to bring its window back.
- Being in the `input` group lets programs you run read the keyboard directly. That is how Susurros works without being tied to X11; remove yourself from the group if you uninstall it.

The Windows and macOS versions are published as separate releases.
