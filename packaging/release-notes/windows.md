Voice dictation for Windows 10 and 11. Your voice is turned into text on your own computer.

## Install

Open PowerShell, paste this line and press Enter:

```powershell
irm https://raw.githubusercontent.com/KTJota/susurros/main/scripts/get.ps1 | iex
```

It downloads what Susurros needs and adds it to the Start menu and the desktop. The first time takes a few minutes, because it includes the speech model. Run the same line again to update.

Prefer to do it by hand? Install [uv](https://docs.astral.sh/uv/) (`winget install astral-sh.uv`), extract the zip below and double-click `scripts\install.cmd`.

## Use

Hold Caps Lock, speak and release. Press it twice in a row to dictate hands-free, and twice again to finish. The shortcut can be changed in Settings.

Looking for the Mac version? It is published as a separate release.
