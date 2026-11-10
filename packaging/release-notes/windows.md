Voice dictation for Windows 10 and 11. Transcription runs on your own computer, on the GPU if it has an NVIDIA card with CUDA and on the CPU otherwise.

## Install

1. Install [uv](https://docs.astral.sh/uv/): `winget install astral-sh.uv`
2. Download the zip below and extract it.
3. Double-click `scripts\install.cmd`, or run this from the extracted folder:

   ```powershell
   powershell -ExecutionPolicy Bypass -File scripts\install.ps1
   ```

It downloads what it needs into `%LOCALAPPDATA%\Susurros` and adds Susurros to the Start menu and the desktop. The speech model, about 1.6 GB, is downloaded the first time the app opens.

If Windows refuses to run the downloaded script, right-click the zip before extracting it, choose Properties and tick Unblock.

## Use

Hold Caps Lock, speak and release. Press it twice in a row to dictate hands-free, and twice again to finish. The shortcut can be changed in Settings.

Looking for the Mac version? It is published as a separate release.
