# Local Dictation

Offline push-to-talk dictation for Windows, similar to Wispr Flow. Speech is transcribed on your own machine with [faster-whisper](https://github.com/SYSTRAN/faster-whisper); nothing is sent to an online service.

Hold **Ctrl+Win**, speak, release: the text is pasted into whatever control has keyboard focus (Notepad, VS Code, GitHub Copilot chat, ...).

## Install

Download `LocalDictation-<version>-Setup.exe` and run it. It installs for your user only (no administrator rights) and adds **Local Dictation** to the Start menu. The default Whisper model (`base.en`) is included, so it works offline from the first launch.

What to expect, because the installer is not code-signed:
- Windows SmartScreen shows "Unknown publisher": click **More info → Run anyway**.
- The app installs a global keyboard hook (that is how Ctrl+Win is detected), so antivirus may flag or quarantine it. If so, add an exclusion for the install folder (`%LOCALAPPDATA%\Programs\Local Dictation`).
- Turn on **Start with Windows** in the app's Settings; the installer does not do it.
- Uninstall from Windows Settings → Apps; it asks whether to delete your settings and logs.

A tray icon shows the state; right-click it for **Settings…**, **Restart hotkey** and **Quit**.

## Run from source

Requires Python 3.11+ and [Poetry](https://python-poetry.org/).

```
poetry install
poetry run local-dictation                      # with a console, for debugging
.venv\Scripts\pythonw.exe -m local_dictation    # no console window
```

The Whisper model downloads on first launch when running from source.

## Build the installer

Needs [Inno Setup 6](https://jrsoftware.org/isinfo.php) (`winget install --id JRSoftware.InnoSetup -e`). Then:

```
poetry install
pwsh packaging\build.ps1
```

This freezes the app with PyInstaller, checks the frozen exe with `--self-test`, and writes `dist\LocalDictation-<version>-Setup.exe`.

## Settings

Shortcut (press-to-record), when to paste (on release, or with a separate shortcut), Whisper model, device (cpu/cuda), language, optional Ollama cleanup model (e.g. `qwen2.5:1.5b`), and start with Windows. Stored in `%APPDATA%\LocalDictation\config.json`; logs in `dictation.log` next to it.

## Development

```
poetry run pytest
```

See `CLAUDE.md` and `docs/` for architecture, decisions and the manual test checklist.

## Limitations

- Windows only. Elevated (administrator) windows do not receive input from a non-elevated process, so dictation does not work into them unless the app is also elevated.
- Only text on the clipboard is restored after pasting.

## Performance

On an i7-6700HQ (CPU, int8), a ~5 s utterance transcribes in about 1.6 s with `base.en` and 4.9 s with `small.en`.
