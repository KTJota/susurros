## ⬇️ [Download Susurros-Setup-0.3.0.exe](https://github.com/KTJota/susurros/releases/download/v0.3.0-windows/Susurros-Setup-0.3.0.exe)

Voice dictation for Windows 10 and 11. Your voice is turned into text on your own computer.

## Install

1. Download **Susurros-Setup-0.3.0.exe** with the link above and open it.
2. Windows will say it does not recognise the app, because it is not signed with a paid certificate. Click **More info**, then **Run anyway**.
3. Follow the two steps of the installer. Susurros opens when it finishes.

The download is large because it includes the libraries that make dictation fast on NVIDIA graphics cards. The speech model, about 1.6 GB, is downloaded the first time the app opens.

### If Windows blocks the installer completely

Some computers have *Smart App Control* turned on, which blocks every app without a certificate and offers no way around it. Use the script installer instead: open PowerShell, paste this line and press Enter.

```powershell
irm https://raw.githubusercontent.com/KTJota/susurros/main/scripts/get.ps1 | iex
```

## Use

Hold Caps Lock, speak and release. Press it twice in a row to dictate hands-free, and twice again to finish. The shortcut can be changed in Settings.

The macOS and Linux versions are published as separate releases.
