# susurros

Voice dictation for Windows and macOS. Hold the dictation key, speak and release: the text, already cleaned of filler words and repetitions, is typed wherever your cursor is and saved to a local history.

- **Hold the key**: records while it is held down.
- **Double tap**: hands-free, until the next double tap.
- **Single short tap**: the key does its normal job (on Windows, Caps Lock still toggles capitals).
- **Esc** cancels a dictation in progress.

The key is Caps Lock on Windows and the right Command key on macOS. It can be changed in Settings to any key or combination, such as Alt + 1 or Ctrl + Win. There is also a mode that types on the fly while you speak, a floating indicator you can reposition by dragging (and that tucks away against the screen edge), light and dark themes, several sounds to choose from, and an Insights page with your pace and what the cleanup changes. The interface is available in English and Spanish.

Transcription is local, with the Whisper `large-v3-turbo` model. Cleanup uses local rules and, if you add an Anthropic API key in Settings, a pass with Claude Haiku that only receives the text. The history, the dictionary and the settings live in a SQLite database on your computer.

| | Windows | macOS |
|---|---|---|
| Requirements | Windows 10 or 11 | macOS 14 or later, Apple Silicon |
| Speech engine | faster-whisper, on the GPU with CUDA or on the CPU | mlx-whisper on the GPU; faster-whisper on the CPU as a fallback |
| Default key | Caps Lock | Right Command |
| Data folder | `%APPDATA%\Susurros` | `~/Library/Application Support/Susurros` |

## Install on Windows

You need [uv](https://docs.astral.sh/uv/) (`winget install astral-sh.uv`). Download the Windows release (or clone the repository) and, from its folder:

```powershell
powershell -ExecutionPolicy Bypass -File scripts\install.ps1
```

It creates the environment in `%LOCALAPPDATA%\Susurros` and the shortcuts. Run it again after changing the code.

## Install on macOS

Download the disk image from the macOS release, open it and drag Susurros to Applications.

The app is not signed with an Apple developer certificate, so macOS refuses to open it the first time: open it once, then go to System Settings › Privacy & Security and press **Open Anyway**. It then asks for two permissions: **Microphone**, and **Accessibility**, which lets it see the shortcut and type into other apps. After installing a newer build, remove Susurros from the Accessibility list and add it back.

What differs from Windows: Caps Lock cannot be the dictation key (macOS does not report when it is held and released), and Esc cancels a dictation but also reaches the app in front.

## Development

```sh
uv sync
uv run pytest
```

The Windows-specific code (keyboard hook, text injection, sounds, start with Windows) lives in the modules at the top of `src/susurros`; the macOS counterparts are in `src/susurros/mac` and are only imported on a Mac.

To build the macOS app on an Apple Silicon Mac: `sh packaging/macos/build.sh`.

## Releasing

Each version is published as two GitHub releases, one per system.

1. Set the version in `pyproject.toml`, run `uv lock` and push.
2. Run the **Build** workflow on GitHub (`gh workflow run build.yml`). It runs the tests on Windows and macOS, builds the Windows zip and the macOS disk image, and checks that the packaged Mac app starts and transcribes.
3. Publish both releases from that run: `sh scripts/publish-release.sh RUN_ID`.
