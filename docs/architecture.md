# Architecture

One long-running tray app (PySide6, single Qt event loop). See the design spec in `docs/superpowers/specs/` for rationale.

## Modules (`src/local_dictation/`)
| Module | Responsibility |
|---|---|
| `shortcut.py` | Pure: key names, `Shortcut`, `ShortcutMatcher` (swallow/event decisions), `ShortcutCapture` |
| `dispatch.py` | Pure: `EventDispatcher` — queue + thread so the hook callback only enqueues |
| `keystate.py` | `is_held(name)` via `GetAsyncKeyState` |
| `hotkey.py` | `WindowsHotkeyListener`: `WH_KEYBOARD_LL` hook thread, swallowing, Win-key Start-menu mask, capture mode |
| `audio.py` | `Recorder`: mic stream opened on press, closed on release |
| `transcribe.py` | `Transcriber`: faster-whisper loaded in background, reloadable |
| `cleanup.py` | `ollama_cleanup`: optional polish via local Ollama, falls back to raw text |
| `paste.py` | `Paster`: wait for modifiers up, clipboard set, Ctrl+V, restore clipboard |
| `config.py` | `Config` (validated), `ConfigStore` (JSON in `%APPDATA%`) |
| `controller.py` | `Controller` state machine: idle → recording → transcribing → (ready) → pasting → idle |
| `startup.py` | Start with Windows (HKCU Run key) |
| `ui/tray.py`, `ui/settings.py` | Tray icon + menu; settings dialog with shortcut capture widget |
| `app.py` | Wiring, logging, single-instance mutex, `main()` |

## Data flow
hook thread → `ShortcutMatcher` → `EventDispatcher` queue → dispatcher thread → `Controller.handle_hotkey(binding, kind)` → recorder / worker thread (transcribe → cleanup → paste) → callbacks → `Bridge` Qt signals → tray.

## Threads
Qt main thread (UI) · hook thread (message loop, must stay fast) · dispatcher thread (runs controller handlers, may block briefly) · worker threads (transcription/paste) · model-loader thread.
