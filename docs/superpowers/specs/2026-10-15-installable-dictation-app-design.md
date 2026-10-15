# Installable Local Dictation App — Design

Date: 2026-10-15 · Status: draft, awaiting user review

## 1. Purpose

A fully local, Windows push-to-talk dictation tool in the spirit of Wispr Flow:
hold a shortcut, speak, release, and the transcription is pasted into whatever
control currently has keyboard focus (Notepad, a GitHub Copilot chat box, ...).
No audio or text leaves the machine. The models (faster-whisper, optional
Ollama) already exist locally; this project makes the tool reliable and
installable instead of a batch-launched script.

### Success criteria
- Installs/runs as a Poetry project; launched via a `local-dictation` entry point, no console window needed.
- A tray icon plus a small settings window. The user can change the shortcut and other basics without editing files.
- Default shortcut **Ctrl+Win** (hold to talk) works in VS Code, Notepad and Copilot chat without triggering their own shortcuts or the Start menu.
- Text is pasted at the focused control on release.
- Failures (no mic, model error) are visible to the user, not console-only.

### Non-goals (for now)
Installer/packaging (planned later, layout must not block it), macOS/Linux,
streaming/partial transcription, per-app formatting, custom vocabulary,
on-screen recording overlay.

## 2. Starting point

`dictate.py` (single script: faster-whisper + sounddevice + pynput + pyperclip,
optional Ollama cleanup), `run.bat`, `requirements.txt`. Known bug: the pynput
listener only observes keys, so the hotkey also reaches the focused app (seen
in VS Code). The existing pipeline is kept; the structure around it changes.

## 3. Architecture

One long-running tray application (PySide6 / Qt, single event loop). Modules
under `src/local_dictation/`, communicating via Qt signals:

| Module | Responsibility |
|---|---|
| `hotkey.py` | Low-level keyboard hook (`WH_KEYBOARD_LL` via ctypes) on a dedicated thread. Tracks held keys, matches the configured shortcut, swallows matched keys, emits `pressed`/`released`. Hidden behind a `HotkeyListener` interface so it can be faked in tests. |
| `audio.py` | Mic `InputStream`; buffers audio only between press and release. |
| `transcribe.py` | Loads faster-whisper once in the background; transcribes a buffer on a worker thread. |
| `cleanup.py` | Optional Ollama polish; on any failure returns the raw text. |
| `paste.py` | Save clipboard, set text, send Ctrl+V to the focused control, restore clipboard. |
| `config.py` | Typed settings dataclass, JSON in `%APPDATA%\LocalDictation\config.json`, defaults on missing/corrupt file. |
| `controller.py` | State machine `idle → recording → transcribing → pasting`; only module that knows the flow. |
| `ui/` | Tray icon (state by icon color) and settings window. |

### Data flow
1. Shortcut pressed → hook swallows it → controller starts recording.
2. Shortcut released → recording stops → transcription on a worker thread (UI never blocks).
3. Optional Ollama cleanup.
4. Paste into the control focused at paste time.
5. Back to idle.

### Stop modes (configurable)
- **release** (default): release of the shortcut ends recording and triggers paste.
- **combo**: release only ends recording; the text waits until a second, separate shortcut triggers cleanup + paste.

## 4. Hotkey details
- Shortcut = a set of keys (modifiers and/or one key). Matching is on the full set being held.
- Matched keys are swallowed (hook returns non-zero) so applications never see them.
- Win-key quirk: a lone Win tap opens Start on release. When Win was part of a matched shortcut, inject a harmless dummy key event before Win-up so Windows suppresses Start.
- Injected events (our own Ctrl+V) are ignored by the hook via the `LLKHF_INJECTED` flag, preventing feedback loops.
- If the hook thread dies, the tray shows an error state and offers a restart.
- Known limitation: a low-level hook cannot intercept keys in elevated (admin) windows from a non-elevated process; documented in the knowledge base.

## 5. Settings window
Shortcut (press-to-record capture widget), stop mode (+ second shortcut when combo), Whisper model, device (cpu/cuda), language (auto or code), optional Ollama cleanup model, start with Windows. Changes apply on Save; model changes reload the model in the background.

## 6. Project layout and migration

```
pyproject.toml            # Poetry; entry point local-dictation = local_dictation.app:main
poetry.lock
src/local_dictation/...
tests/
docs/                     # knowledge base (section 8)
CLAUDE.md                 # pointer for AI sessions
```
Migration: `requirements.txt`, `run.bat` and `dictate.py` are removed once the new package reproduces their behavior; logic from `dictate.py` is moved, not rewritten (Whisper settings, cleanup prompt, paste approach). `.gitignore` extended for Poetry/build artifacts. Python version pinned in `pyproject.toml` to what the existing `.venv` uses (verified during planning).

## 7. Testing
- Unit tests (pytest) for `config`, `controller` (with fake hotkey/audio/transcriber/paster), `cleanup` fallback, shortcut matching logic.
- Hotkey hook and paste are thin OS wrappers: covered by a documented manual checklist (VS Code, Notepad, Copilot chat, Start-menu suppression) because they need a real desktop session.
- No tests that download models.

## 8. Knowledge base (for future AI/human sessions)
- `CLAUDE.md`: short entry point — what the project is, how to run tests, where docs live, rules (local-only, no network except localhost Ollama).
- `docs/purpose.md`: why the project exists, target behavior, non-goals.
- `docs/architecture.md`: module map and data flow from section 3, kept current.
- `docs/decisions.md`: short ADR-style log (why PySide6, why own low-level hook, why clipboard paste, Poetry).
- `docs/manual-test-checklist.md`: the hotkey/paste checks from section 7.
- `docs/superpowers/specs/` and `docs/superpowers/plans/`: design specs and implementation plans.
Rule recorded in `CLAUDE.md`: any change to architecture or behavior updates the relevant doc in the same commit.

## 9. Open items for the plan stage
- Confirm Python version and that PySide6 and faster-whisper wheels install under Poetry on this machine.
- Exact dummy-key choice for Start-menu suppression (verify empirically).
