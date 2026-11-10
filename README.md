# susurros

Voice dictation for Windows. Hold the dictation key (Caps Lock by default, or any key or key combination such as Alt + 1 or Ctrl + Win), speak and release: the text, already cleaned of filler words and repetitions, is typed wherever your cursor is and saved to a local history.

- **Hold the key**: records while it is held down.
- **Double tap**: hands-free, until the next double tap.
- **Single short tap**: the key does its normal job (Caps Lock still toggles capitals).
- **Esc** cancels a dictation in progress.

The key can be changed in Settings. There is also a mode that types on the fly while you speak, a floating indicator you can reposition by dragging (and that tucks away against the screen edge), light and dark themes, several sounds to choose from, and an Insights page with your pace and what the cleanup changes. The interface is available in English and Spanish.

Transcription is local (faster-whisper `large-v3-turbo`, on the GPU if CUDA is available). Cleanup uses local rules and, if you add an Anthropic API key in Settings, a pass with Claude Haiku that only receives the text. The history, the dictionary and the settings live in a SQLite database in `%APPDATA%\Susurros`.

## Install

You need [uv](https://docs.astral.sh/uv/) (`winget install astral-sh.uv`). Then, from the project folder:

```powershell
powershell -ExecutionPolicy Bypass -File scripts\install.ps1
```

It creates the environment in `%LOCALAPPDATA%\Susurros` and the shortcuts. Run it again after changing the code.

## Development

```sh
uv sync
uv run pytest
```
