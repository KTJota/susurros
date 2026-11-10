## ⬇️ [Download Susurros-0.3.0-macos-arm64.dmg](https://github.com/KTJota/susurros/releases/download/v0.3.0-macos/Susurros-0.3.0-macos-arm64.dmg)

Voice dictation for macOS 14 or later on Apple Silicon (M1 and newer). Transcription runs on your own Mac, on its GPU.

This first macOS build has been checked automatically (tests, a real transcription and a start of the packaged app on a Mac in the cloud), but not yet by a person on a real keyboard and microphone. Please report what does not work.

## Install

1. Download the disk image with the link above, open it and drag Susurros to Applications.
2. The app is not signed with an Apple developer certificate, so macOS will not open it the first time. Open it once, close the warning, then go to System Settings › Privacy & Security and press **Open Anyway**. Or, from Terminal:

   ```sh
   xattr -dr com.apple.quarantine /Applications/Susurros.app
   ```

3. Allow the two permissions it asks for: **Microphone**, and **Accessibility** (System Settings › Privacy & Security › Accessibility), which is what lets it see the shortcut and type the text into other apps. If the app still says a permission is missing after you allow it, quit it from the menu bar icon and open it again.

The speech model, about 1.6 GB, is downloaded the first time the app opens.

After updating to a newer build, macOS asks for the Accessibility permission again: remove Susurros from that list and add it back.

## Use

Hold the **right Command** key, speak and release. Press it twice in a row to dictate hands-free, and twice again to finish. The shortcut can be changed in Settings to another key or a combination.

Differences from the Windows version: Caps Lock cannot be the dictation key (macOS does not report when it is held and released), and Esc cancels a dictation but also reaches the app in front.

The Windows and Linux versions are published as separate releases.
