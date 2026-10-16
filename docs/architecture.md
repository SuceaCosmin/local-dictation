# Architecture

One long-running tray app (PySide6, single Qt event loop). See the design spec in `docs/superpowers/specs/` for rationale.

## Modules (`src/local_dictation/`)
| Module | Responsibility |
|---|---|
| `shortcut.py` | Pure: key names, `Shortcut`, `keycaps` (display labels), `ShortcutMatcher` (swallow/event decisions), `ShortcutCapture` |
| `dispatch.py` | Pure: `EventDispatcher` — queue + thread so the hook callback only enqueues |
| `keystate.py` | `is_held(name)` via `GetAsyncKeyState` |
| `hotkey.py` | `WindowsHotkeyListener`: `WH_KEYBOARD_LL` hook thread, swallowing, Win-key Start-menu mask, capture mode |
| `audio.py` | `Recorder`: mic stream opened on press, closed on release |
| `transcribe.py` | `Transcriber`: faster-whisper loaded in background, reloadable |
| `cleanup.py` | `ollama_cleanup` (optional polish via local Ollama; raises `CleanupError` on failure, the controller then pastes the raw text and notifies once) and `list_models` (installed models, for the Settings picker) |
| `paste.py` | `Paster`: wait for modifiers up, clipboard set, Ctrl+V, restore clipboard |
| `config.py` | `Config` (validated), `ConfigStore` (JSON in `%APPDATA%`) |
| `controller.py` | `Controller` state machine: idle → recording → transcribing → (ready) → (cleaning) → pasting → idle |
| `startup.py` | Start with Windows (HKCU Run key) |
| `paths.py` | Pure: `is_frozen()`, `app_dir()`, `data_dir()`, `bundled_model_path(name)` (model shipped in the installer) |
| `selftest.py` | `--self-test <outfile>`: imports every heavy dependency, loads the model, runs VAD transcription; used by the build to verify a frozen exe |
| `ui/tray.py` | `TrayIcon`: state-coloured icon + menu (How to use, Settings, Restart hotkey, Quit); remembers the last model status in `model_status` |
| `ui/settings.py` | `SettingsDialog` (select-only: Whisper model, device, language, cleanup model filled from Ollama) and `ShortcutEdit` (shortcut capture via the hook; cancels capture when the dialog closes) |
| `ui/welcome.py` | `WelcomeWindow` (first-run / how-to window: keycaps, shortcut change, model status, practice box) and `KeycapRow` |
| `ui/theme.py` | Colour tokens and the shared stylesheet (light or dark from the system palette) |
| `app.py` | Wiring, logging, single-instance mutex, `Bridge` (controller callbacks to Qt signals), `main()` |
| `__main__.py` | `python -m local_dictation` entry point (calls `app.main()`) |

## Data flow
hook thread → `ShortcutMatcher` → `EventDispatcher` queue → dispatcher thread → `Controller.handle_hotkey(binding, kind)` → recorder / worker thread (transcribe → cleanup → paste) → callbacks → `Bridge` Qt signals → tray and welcome window.

## Threads
Qt main thread (UI) · hook thread (message loop, must stay fast) · dispatcher thread (runs controller handlers, may block briefly) · worker threads (transcription/paste) · model-loader thread.

## Packaging (`packaging/`)
`build.ps1` → reads the version from `pyproject.toml` → fetches `base.en` into `packaging/model-cache/` → PyInstaller (`local-dictation.spec`, one-folder, windowed) → runs the frozen exe with `--self-test` → Inno Setup (`installer.iss`) → `dist/LocalDictation-<version>-Setup.exe`. The model sits in PyInstaller's data folder (`_internal/models/base.en/`, i.e. `sys._MEIPASS`); `transcribe._model_source` prefers it when frozen. Per-user install under `%LOCALAPPDATA%\Programs\Local Dictation`; the installer's `AppMutex` is the app's single-instance mutex.
