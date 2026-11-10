<div align="center">

<img src="docs/images/logo.png" width="96" alt="Susurros logo">

# Susurros

**Talk instead of typing.** Hold a key, speak, and your words appear wherever your cursor is.

Free, open source, and your voice never leaves your computer.

[![Download for Windows](https://img.shields.io/badge/Download-Windows-0078D4?style=for-the-badge&logo=windows11&logoColor=white)](#-install-on-windows)
[![Download for macOS](https://img.shields.io/badge/Download-macOS-000000?style=for-the-badge&logo=apple&logoColor=white)](#-install-on-macos)
[![Install on Linux](https://img.shields.io/badge/Install-Linux-E95420?style=for-the-badge&logo=ubuntu&logoColor=white)](#-install-on-linux)

<img src="docs/images/history.png" width="760" alt="The Susurros window, showing a history of dictations">

</div>

## ✨ How it works

| 1. Hold the key | 2. Speak | 3. Let go |
|:---:|:---:|:---:|
| <img src="docs/images/pill-idle.png" width="120" alt="Indicator at rest"> | <img src="docs/images/pill-recording.png" width="120" alt="Indicator while recording"> | 📝 |
| **Caps Lock** on Windows and Linux<br>**Right Command** on a Mac | Say it the way you would say it out loud | The text is typed for you, in any app |

That is all there is to it. It works in your email, your browser, your chat apps, your code editor: anywhere you can type.

## 💡 What makes it nice

- 🧹 **It tidies up what you say.** "Um", "uh", repeated words and false starts are removed, so the text reads the way you meant it.
- 🙌 **Hands-free mode.** Tap the key twice and keep talking for as long as you like. Tap twice again to finish.
- 🔒 **Private.** Your voice is turned into text on your own computer. No audio is saved or uploaded.
- 📚 **It remembers.** Every dictation is kept in a history you can search and copy from with one click.
- 📖 **It learns your words.** Add names, brands or jargon to the dictionary and they are spelled right.
- ⚡ **Live typing.** Optionally, the text appears while you are still speaking.
- 🎨 **Yours to adjust.** Pick the key, the sounds, a light or dark look, and where the little indicator sits on screen.
- 🌍 **English and Spanish** interface. Dictation works in many languages.

<div align="center">
<img src="docs/images/insights-light.png" width="49%" alt="The Insights page, in the light theme">
<img src="docs/images/settings.png" width="49%" alt="The Settings page, in the dark theme">
</div>

## 🪟 Install on Windows

1. **[Download Susurros for Windows](https://github.com/KTJota/susurros/releases/download/v0.3.0-windows/Susurros-Setup-0.3.0.exe)** and open the file.
2. Windows will say it does not recognise the app. Click **More info**, then **Run anyway**. You only do this once.
3. Click through the installer. Susurros opens when it finishes.

The first time it opens, it downloads the speech model, so give it a few minutes.

> Works on Windows 10 and 11. It is fastest with an NVIDIA graphics card, and works without one too.

<details>
<summary>Windows blocks the installer and there is no "Run anyway"?</summary>

<br>

Some computers have *Smart App Control* turned on, which blocks apps that are not signed with a paid certificate. Install it this way instead: open the **Start** menu, type **PowerShell**, press Enter, paste this line and press Enter again.

```powershell
irm https://raw.githubusercontent.com/KTJota/susurros/main/scripts/get.ps1 | iex
```

</details>

## 🍎 Install on macOS

1. **[Download Susurros for Mac](https://github.com/KTJota/susurros/releases/download/v0.3.0-macos/Susurros-0.3.0-macos-arm64.dmg)**, open the file and drag **Susurros** into **Applications**.
2. Open Susurros. macOS will say it cannot check the app. Close that message, open **System Settings › Privacy & Security**, scroll down and click **Open Anyway**. You only do this once.
3. Say yes to the two permissions it asks for: **Microphone** (to hear you) and **Accessibility** (to type the text for you).

> For Macs with Apple Silicon (M1 or newer) and macOS 14 or later. The Mac version is new: if something does not work, [tell us](https://github.com/KTJota/susurros/issues).

## 🐧 Install on Linux

1. Open a terminal.
2. Paste this line and press Enter. It asks for your password once.

   ```sh
   curl -fsSL https://raw.githubusercontent.com/KTJota/susurros/main/scripts/install-linux.sh | bash
   ```

3. **Log out and back in**, then open **Susurros** from your applications menu.

> For Ubuntu and Debian, on X11 or Wayland. The Linux version is new: if something does not work, [tell us](https://github.com/KTJota/susurros/issues). The text is pasted with Ctrl+V, so in a terminal copy it from the history instead.

## ⌨️ Using it

| You do | Susurros does |
|---|---|
| **Hold** the key and speak | Records while you hold; types the text when you let go |
| **Tap twice** quickly | Starts hands-free dictation; tap twice again to finish |
| Press **Esc** | Cancels the dictation |
| Click a dictation in the history | Copies it |

<div align="center">
<img src="docs/images/pill-recording.png" width="120" alt="Indicator while recording">&nbsp;&nbsp;&nbsp;
<img src="docs/images/pill-locked.png" width="120" alt="Indicator in hands-free mode">
<br><sub>The small indicator shows when Susurros is listening. Drag it to any edge of the screen.</sub>
</div>

## ❓ Questions

**Is it really free?**
Yes. There is no account, no subscription and no limit.

**Does it need the internet?**
Only to download the speech model the first time. After that, dictation works offline.

**Where does my voice go?**
Nowhere. The audio is turned into text on your computer and then discarded. Your history is a file on your computer that only you can see.

**What is the "Claude" option in Settings?**
An optional extra polish for your text. If you add your own Anthropic API key, the already transcribed *text* (never the audio) is sent to Claude to fix punctuation and wording. Without a key, nothing is sent anywhere.

**Why does my Mac warn me about the app?**
Apple charges developers a yearly fee to remove that warning, and this is a free project. The app is open source, so anyone can check what it does.

**Why does Windows warn me about the installer?**
For the same reason: removing that warning requires a paid certificate. Click **More info** and then **Run anyway**.

**Why does the Linux installer ask for my password?**
To install a few system packages and to add you to the `input` group, which lets Susurros notice the dictation key and paste for you on both X11 and Wayland.

**Can I use Caps Lock on a Mac?**
No: macOS does not tell apps when Caps Lock is held and released. Any other key or combination works; choose yours in Settings.

## 🛠️ For developers

<details>
<summary>Build it yourself, run the tests, publish a release</summary>

<br>

Susurros is written in Python with PySide6. Speech recognition is Whisper `large-v3-turbo`: [faster-whisper](https://github.com/SYSTRAN/faster-whisper) on Windows and Linux (CUDA or CPU) and [mlx-whisper](https://github.com/ml-explore/mlx-examples/tree/main/whisper) on Apple Silicon.

```sh
uv sync
uv run pytest
```

The Windows-specific code (keyboard hook, text injection, sounds, start with Windows) lives in the modules at the top of `src/susurros`. The macOS counterparts are in `src/susurros/mac` and the Linux ones in `src/susurros/linux`; each is only imported on its own system.

**Install from a clone:** `powershell -ExecutionPolicy Bypass -File scripts\install.ps1` on Windows, `bash scripts/install-linux.sh` on Linux.

**Build the Windows setup program** (needs Inno Setup 6): `powershell -ExecutionPolicy Bypass -File packaging\windows\build.ps1`

**Build the Mac app** on an Apple Silicon Mac: `sh packaging/macos/build.sh`

**Data folder:** `%APPDATA%\Susurros` on Windows, `~/Library/Application Support/Susurros` on macOS, `~/.local/share/susurros` on Linux.

**Publishing a version.** Each version is three GitHub releases, one per system.

1. Set the version in `pyproject.toml`, in the download links above and in `packaging/release-notes`, run `uv lock` and push.
2. Run the **Build** workflow with releases on: `gh workflow run build.yml -f release=true`. It runs the tests on the three systems, builds the Windows setup program, the Mac disk image and the Linux archive, checks that each packaged app starts, and attaches everything to three draft releases.
3. Look at the drafts, then publish them: `sh scripts/publish-release.sh VERSION`.

</details>

## 📄 License

[MIT](LICENSE). Use it, change it, share it.
