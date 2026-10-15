# Installable Local Dictation App Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Turn the single-script `dictate.py` into a Poetry-managed, tray-resident Windows app with a settings window and a hotkey (default Ctrl+Win) that is swallowed so other apps never see it.

**Architecture:** One PySide6 tray app. A ctypes `WH_KEYBOARD_LL` hook (own thread) feeds a pure-Python `ShortcutMatcher`; matched events go through a queue to a dispatcher thread, then to a Qt-free `Controller` state machine that drives audio → faster-whisper → optional Ollama → clipboard paste. Qt signals only bridge controller callbacks to the tray/UI.

**Tech Stack:** Python 3.11, Poetry 2.x, PySide6, faster-whisper, sounddevice, numpy, pynput (Ctrl+V only), pyperclip, pytest.

**Spec:** `docs/superpowers/specs/2026-10-15-installable-dictation-app-design.md`

## Global Constraints

- Python `>=3.11,<3.14` (existing venv is 3.11.9). Windows only.
- Local-only: no network access except `http://localhost:11434` (Ollama) and the one-time Whisper model download by faster-whisper.
- Package layout: `src/local_dictation/`, tests in `tests/`, entry point `local-dictation = local_dictation.app:main`.
- Config file: `%APPDATA%\LocalDictation\config.json`. Defaults: record shortcut `ctrl+win`, stop mode `release`, model `base.en`, device `cpu`.
- Existing pipeline behavior is preserved: Whisper `beam_size=1, vad_filter=True`, `int8` on cpu / `float32` on cuda, cleanup prompt text, clipboard-paste-then-restore, trailing space after pasted text.
- Any change to architecture or behavior updates the matching file in `docs/` in the same commit.
- Commit messages end with the trailer `Co-Authored-By: Claude Sonnet 5.5 <noreply@anthropic.com>` (pass it as a second `-m`).
- Hook callbacks must never block (Windows silently unhooks slow low-level hooks).

## Deviations from the spec (decided while planning; recorded in `docs/decisions.md`)

- `Controller` is Qt-free (plain callbacks); a small `Bridge(QObject)` in `app.py` turns them into Qt signals. Same behavior, testable without Qt.
- Hook events go through a queue to a dispatcher thread (`dispatch.py`) so the hook callback returns immediately.
- Microphone stream opens on key press and closes on release (mic only active while held; device changes handled).
- Shortcut capture in the settings window uses the hook itself (capture mode), because Qt cannot reliably see the Win key.
- Shortcut keys are side-agnostic (`ctrl`, not `ctrl_r`). The old default Right Ctrl is dropped.

## Review Focus

1. **Win/Ctrl still physically held when paste fires** (release is detected on the first key up) → sending Ctrl+V would become Win+V (clipboard history). Paste waits for modifiers to be released (timeout 1.5 s). Pinned in Task 6.
2. **Slow work inside the hook callback** → Windows removes the hook silently, shortcut "just stops working". Callback only enqueues. Pinned in Task 3b (`EventDispatcher` order + survives handler exception).
3. **Corrupt, empty, wrong-typed or unsafe `config.json`** → app must start with defaults, never crash. Pinned in Task 2.
4. **Key-down passed through but key-up swallowed (or vice versa)** → stuck Ctrl/Win. Matcher swallows an up only if it swallowed the matching down; auto-repeat of a passed key stays passed. Pinned in Task 3.
5. **Backend failures leave the app wedged**: no microphone, Ollama down/empty reply, empty or too-short audio, transcription exception → notification and back to `idle`, next press works. Pinned in Tasks 5 and 7.

Known limitations (documented, not tested): elevated (admin) windows ignore input from a non-elevated process; non-text clipboard content (images, files) is not restored after a paste.

---

## File Structure

```
pyproject.toml, poetry.toml, poetry.lock
CLAUDE.md
docs/{purpose,architecture,decisions,manual-test-checklist}.md
src/local_dictation/
  __init__.py  __main__.py  app.py
  config.py        # Config dataclass, validate(), ConfigStore
  shortcut.py      # key names, Shortcut, ShortcutMatcher, ShortcutCapture (pure)
  dispatch.py      # EventDispatcher (pure)
  keystate.py      # is_held(name) via GetAsyncKeyState
  hotkey.py        # WindowsHotkeyListener (WH_KEYBOARD_LL)
  audio.py         # Recorder
  transcribe.py    # Transcriber
  cleanup.py       # ollama_cleanup
  paste.py         # Paster
  controller.py    # Controller, State
  startup.py       # start-with-Windows (HKCU Run)
  ui/{__init__,tray,settings}.py
tests/ conftest.py + one test file per module
```

---

### Task 1: Poetry scaffold and knowledge base

**Files:**
- Create: `pyproject.toml`, `poetry.toml`, `src/local_dictation/__init__.py`, `src/local_dictation/__main__.py`, `tests/conftest.py`, `tests/test_smoke.py`
- Create: `CLAUDE.md`, `docs/purpose.md`, `docs/architecture.md`, `docs/decisions.md`, `docs/manual-test-checklist.md`
- Modify: `.gitignore`

**Interfaces:**
- Produces: importable package `local_dictation` with `__version__ = "0.1.0"`; `poetry run pytest` works; `__main__` imports `local_dictation.app.main` (created in Task 8, so `__main__` is only exercised then).

- [ ] **Step 1: Write `pyproject.toml`**

```toml
[project]
name = "local-dictation"
version = "0.1.0"
description = "Offline push-to-talk dictation for Windows (local Whisper), a local alternative to Wispr Flow"
readme = "README.md"
requires-python = ">=3.11,<3.14"
dependencies = [
    "faster-whisper>=1.2",
    "sounddevice>=0.5",
    "numpy>=2.0",
    "pynput>=1.8",
    "pyperclip>=1.11",
    "PySide6>=6.7",
]

[project.scripts]
local-dictation = "local_dictation.app:main"

[tool.poetry]
packages = [{ include = "local_dictation", from = "src" }]

[tool.poetry.group.dev.dependencies]
pytest = ">=8.0"

[tool.pytest.ini_options]
testpaths = ["tests"]

[build-system]
requires = ["poetry-core>=2.0"]
build-backend = "poetry.core.masonry.api"
```

- [ ] **Step 2: Write `poetry.toml`**

```toml
[virtualenvs]
in-project = true
```

- [ ] **Step 3: Write package files**

`src/local_dictation/__init__.py`:
```python
__version__ = "0.1.0"
```

`src/local_dictation/__main__.py`:
```python
from .app import main

raise SystemExit(main())
```

`tests/conftest.py`:
```python
import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
```

`tests/test_smoke.py`:
```python
import local_dictation


def test_package_has_version():
    assert local_dictation.__version__ == "0.1.0"
```

- [ ] **Step 4: Extend `.gitignore`**

Replace the file with:
```
.venv/
__pycache__/
*.pyc
*.wav
dist/
build/
*.egg-info/
.pytest_cache/
```

- [ ] **Step 5: Install and run the smoke test**

Run: `poetry install` then `poetry run pytest -v`
Expected: install succeeds (PySide6 is a large download); `test_package_has_version PASSED`.
If `poetry install` complains about the existing pip-created `.venv`, run `Remove-Item -Recurse -Force .venv` and `poetry install` again (the venv is disposable).
Also run `poetry run python -c "import PySide6, faster_whisper, sounddevice, pynput, pyperclip; print('ok')"` → `ok`. This closes the spec's open item about wheel availability.

- [ ] **Step 6: Write the knowledge base**

`CLAUDE.md`:
```markdown
# Local Dictation — notes for AI sessions

Offline, Windows-only push-to-talk dictation (a local alternative to Wispr Flow). Hold a shortcut (default Ctrl+Win), speak, release; the transcription is pasted into whatever control has keyboard focus. Nothing leaves the machine.

## Where to look
- `docs/purpose.md` — why this exists, target behavior, non-goals
- `docs/architecture.md` — module map and data flow (keep current)
- `docs/decisions.md` — why things are the way they are
- `docs/manual-test-checklist.md` — OS-level checks that unit tests cannot cover
- `docs/superpowers/specs/` and `docs/superpowers/plans/` — design specs and implementation plans

## Commands
- Install: `poetry install`
- Tests: `poetry run pytest`
- Run (with console): `poetry run local-dictation`
- Run (no console): `.venv\Scripts\pythonw.exe -m local_dictation`
- Logs: `%APPDATA%\LocalDictation\dictation.log`; config: `%APPDATA%\LocalDictation\config.json`

## Rules
- Local only: no network except `http://localhost:11434` (Ollama) and the one-time model download.
- The keyboard hook callback must never block; it only enqueues events.
- Pure logic (shortcut matching, controller, config) stays free of OS/Qt imports so it is unit-testable.
- Any change to architecture or behavior updates the relevant file in `docs/` in the same commit.
```

`docs/purpose.md`:
```markdown
# Purpose

A fully local, Windows push-to-talk dictation tool, in the spirit of Wispr Flow but using local models (faster-whisper for speech-to-text, optional Ollama model for punctuation/filler cleanup) instead of an online service.

## Target behavior
1. User holds the record shortcut (default **Ctrl+Win**). The shortcut is swallowed: no application (VS Code, Notepad, GitHub Copilot chat, ...) sees it and the Start menu does not open.
2. Audio is captured only while the shortcut is held.
3. On release (default stop mode) the audio is transcribed, optionally cleaned up, and pasted into the control that currently has keyboard focus.
4. Alternative stop mode "combo": release ends recording, a second configurable shortcut triggers the paste.
5. A tray icon shows state (loading, idle, recording, transcribing, ready, pasting); a small settings window changes the shortcut, stop mode, model, device, language, cleanup model and start-with-Windows.

## Non-goals (for now)
Installer (planned; layout must not block it), macOS/Linux, streaming/partial transcription, per-app formatting, custom vocabulary, on-screen recording overlay.

## Origin
Started as a single script, `dictate.py` (faster-whisper + sounddevice + pynput + pyperclip, optional Ollama cleanup, launched by `run.bat`). Its hotkey leaked into the focused app (seen in VS Code), which motivated the rework.
```

`docs/architecture.md`:
```markdown
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
```

`docs/decisions.md`:
```markdown
# Decisions

- **PySide6 (Qt) for UI** — one event loop for tray + settings + capture widget; pystray+Tkinter means two GUI loops. Cost: ~100 MB install.
- **Own `WH_KEYBOARD_LL` hook (ctypes), not pynput/keyboard** — the original bug was that pynput only observes keys. We need to swallow keys, handle the Win-key/Start menu quirk (inject unassigned VK 0xE8 so Windows does not open Start), and ignore our own injected events. pynput is still used to send Ctrl+V.
- **Hook callback only enqueues** — Windows removes slow low-level hooks without notice.
- **Controller is Qt-free** — callbacks instead of signals so it is unit-testable with fakes; `Bridge` in `app.py` adapts to Qt.
- **Mic opens on press** — mic is only active while the shortcut is held; handles device changes. Trade-off: tiny start latency; if the first word clips, revisit (keep stream open).
- **Clipboard paste** — works in every app incl. Electron/VS Code chat boxes; clipboard text is restored afterwards. Non-text clipboard content is not restored (limitation).
- **Paste waits for modifiers to be released** — otherwise held Win turns Ctrl+V into Win+V.
- **Shortcut capture via the hook** — Qt cannot reliably see the Win key.
- **Side-agnostic keys** (`ctrl` matches either Ctrl) — simpler UI; the old Right-Ctrl default is gone.
- **Poetry with in-project `.venv`** (`poetry.toml`) — editors find the interpreter; reuses the repo-local venv convention.
- **Known limitation** — elevated (admin) windows do not receive/trigger input from a non-elevated process.
```

`docs/manual-test-checklist.md`:
```markdown
# Manual test checklist (needs a real desktop session)

Run after any change to `hotkey.py`, `paste.py`, `audio.py` or `app.py`.

1. Start: `poetry run local-dictation`. Tray icon appears; "loading" then "ready" notification.
2. Notepad: click into it, hold Ctrl+Win, say a sentence, release → text appears at the caret. Start menu did **not** open.
3. VS Code editor: same; no VS Code command palette/shortcut fires.
4. VS Code GitHub Copilot chat input: click into the box, hold, speak, release → text pasted there.
5. Press Win first, then Ctrl (reverse order) → still records, Start menu does not open.
6. Hold, press nothing else, release after < 0.3 s → nothing pasted, no error.
7. Clipboard: copy "abc", dictate, then paste manually → "abc" is back.
8. Settings → change shortcut with the capture widget (try Ctrl+Alt+Space and F9) → new shortcut works, old one no longer does.
9. Settings → stop mode "separate shortcut": release ends recording, text waits (tray "ready"); paste shortcut pastes it.
10. Unplug/disable the microphone → press shortcut → tray notification, app keeps working after re-enabling.
11. Stop Ollama, set a cleanup model → dictation still pastes the raw text.
12. Start with Windows on → reboot/login → app is running.
13. Start a second copy → it exits immediately.
14. Tray → Restart hotkey → shortcut still works.
```

- [ ] **Step 7: Commit**

```bash
git add pyproject.toml poetry.toml poetry.lock .gitignore src tests CLAUDE.md docs
git commit -m "Scaffold Poetry project and knowledge base" -m "Co-Authored-By: Claude Sonnet 5.5 <noreply@anthropic.com>"
```

---

### Task 2: Config

**Files:**
- Create: `src/local_dictation/config.py`
- Test: `tests/test_config.py`

**Interfaces:**
- Consumes: `Shortcut.parse/format/is_safe`, `Shortcut.keys` from Task 3 (see note below).
- Produces:
  - `Config` dataclass with fields `record_shortcut: str`, `stop_mode: str`, `paste_shortcut: str`, `model: str`, `device: str`, `language: str`, `cleanup_model: str`, `start_with_windows: bool`; methods `Config.from_dict(data) -> Config`, `validate() -> list[str]`, `bindings() -> dict[str, Shortcut]`.
  - `ConfigStore(path: Path | None = None)` with attributes `.path`, `.config`; methods `update(cfg) -> None` (raises `ValueError` on invalid), `default_config_path() -> Path`.

**Note:** `config.py` imports `shortcut.py`. Do **Task 3a first** (the pure `Shortcut` class), then this task. Implementers: execute 3a → 2 → 3b+.

(Task 3 is split in the order below so Config can be built on `Shortcut`.)

- [ ] **Step 1: Write the failing tests**

```python
import json

import pytest

from local_dictation.config import Config, ConfigStore


def test_defaults_are_valid():
    assert Config().validate() == []
    assert Config().record_shortcut == "ctrl+win"
    assert Config().stop_mode == "release"


def test_from_dict_ignores_unknown_and_wrong_types():
    cfg = Config.from_dict({"model": "small.en", "device": 5, "bogus": 1, "start_with_windows": "yes"})
    assert cfg.model == "small.en"
    assert cfg.device == "cpu"
    assert cfg.start_with_windows is False


@pytest.mark.parametrize("payload", ["", "not json", "[1, 2]", "null", "{"])
def test_store_survives_corrupt_file(tmp_path, payload):
    path = tmp_path / "config.json"
    path.write_text(payload, encoding="utf-8")
    assert ConfigStore(path).config == Config()


def test_store_missing_file_gives_defaults(tmp_path):
    assert ConfigStore(tmp_path / "nope" / "config.json").config == Config()


def test_store_falls_back_to_defaults_when_loaded_config_invalid(tmp_path):
    path = tmp_path / "config.json"
    path.write_text(json.dumps({"record_shortcut": "a"}), encoding="utf-8")  # plain letter: unsafe
    assert ConfigStore(path).config == Config()


def test_update_saves_and_reloads(tmp_path):
    path = tmp_path / "sub" / "config.json"
    store = ConfigStore(path)
    store.update(Config(model="small.en", record_shortcut="ctrl+alt+space"))
    reloaded = ConfigStore(path).config
    assert reloaded.model == "small.en"
    assert reloaded.record_shortcut == "ctrl+alt+space"


def test_update_rejects_invalid(tmp_path):
    store = ConfigStore(tmp_path / "config.json")
    with pytest.raises(ValueError):
        store.update(Config(record_shortcut="a"))
    assert store.config == Config()


@pytest.mark.parametrize("cfg, fragment", [
    (Config(record_shortcut=""), "Record shortcut"),
    (Config(record_shortcut="a"), "Record shortcut"),
    (Config(record_shortcut="ctrl+a+b"), "Record shortcut"),
    (Config(stop_mode="nope"), "Stop mode"),
    (Config(device="tpu"), "Device"),
    (Config(model="  "), "Model"),
    (Config(stop_mode="combo", paste_shortcut="ctrl+win"), "differ"),
    (Config(stop_mode="combo", paste_shortcut="x"), "Paste shortcut"),
])
def test_validate_reports_problems(cfg, fragment):
    assert any(fragment in e for e in cfg.validate())


def test_paste_shortcut_ignored_unless_combo_mode():
    assert Config(stop_mode="release", paste_shortcut="x").validate() == []


def test_bindings():
    assert set(Config().bindings()) == {"record"}
    combo = Config(stop_mode="combo").bindings()
    assert set(combo) == {"record", "paste"}
    assert combo["record"].format() == "ctrl+win"
```

- [ ] **Step 2: Run to verify failure**

Run: `poetry run pytest tests/test_config.py -v`
Expected: FAIL (`ModuleNotFoundError: local_dictation.config`).

- [ ] **Step 3: Implement `config.py`**

```python
"""Application settings: validated dataclass plus a JSON store in %APPDATA%."""
from __future__ import annotations

import json
import logging
import os
import tempfile
from dataclasses import asdict, dataclass, fields
from pathlib import Path

from .shortcut import Shortcut

log = logging.getLogger(__name__)

STOP_MODES = ("release", "combo")
DEVICES = ("cpu", "cuda")


def default_config_path() -> Path:
    base = os.environ.get("APPDATA") or str(Path.home() / "AppData" / "Roaming")
    return Path(base) / "LocalDictation" / "config.json"


def _check_shortcut(text: str, label: str, errors: list[str]) -> Shortcut | None:
    try:
        shortcut = Shortcut.parse(text)
    except ValueError:
        errors.append(f"{label} is empty.")
        return None
    if not shortcut.is_safe():
        errors.append(f"{label} must include Ctrl, Alt, Shift or Win (or be a function key) "
                      "and at most one other key.")
        return None
    return shortcut


@dataclass
class Config:
    record_shortcut: str = "ctrl+win"
    stop_mode: str = "release"
    paste_shortcut: str = "ctrl+win+space"
    model: str = "base.en"
    device: str = "cpu"
    language: str = ""
    cleanup_model: str = ""
    start_with_windows: bool = False

    @classmethod
    def from_dict(cls, data) -> "Config":
        cfg = cls()
        if not isinstance(data, dict):
            return cfg
        for f in fields(cls):
            value = data.get(f.name)
            if type(value) is type(getattr(cfg, f.name)):
                setattr(cfg, f.name, value)
        return cfg

    def validate(self) -> list[str]:
        errors: list[str] = []
        record = _check_shortcut(self.record_shortcut, "Record shortcut", errors)
        if self.stop_mode not in STOP_MODES:
            errors.append("Stop mode must be 'release' or 'combo'.")
        if self.device not in DEVICES:
            errors.append("Device must be 'cpu' or 'cuda'.")
        if not self.model.strip():
            errors.append("Model must not be empty.")
        if self.stop_mode == "combo":
            paste = _check_shortcut(self.paste_shortcut, "Paste shortcut", errors)
            if record and paste and record.keys == paste.keys:
                errors.append("Record and paste shortcuts must differ.")
        return errors

    def bindings(self) -> dict[str, Shortcut]:
        result = {"record": Shortcut.parse(self.record_shortcut)}
        if self.stop_mode == "combo":
            result["paste"] = Shortcut.parse(self.paste_shortcut)
        return result


class ConfigStore:
    def __init__(self, path: Path | None = None):
        self.path = path or default_config_path()
        self.config = self._load()

    def _load(self) -> Config:
        try:
            data = json.loads(self.path.read_text(encoding="utf-8"))
        except FileNotFoundError:
            return Config()
        except (OSError, ValueError) as e:
            log.warning("Could not read %s (%s); using defaults", self.path, e)
            return Config()
        cfg = Config.from_dict(data)
        errors = cfg.validate()
        if errors:
            log.warning("Invalid config (%s); using defaults", "; ".join(errors))
            return Config()
        return cfg

    def update(self, cfg: Config) -> None:
        errors = cfg.validate()
        if errors:
            raise ValueError("; ".join(errors))
        self.path.parent.mkdir(parents=True, exist_ok=True)
        fd, tmp = tempfile.mkstemp(dir=self.path.parent, suffix=".tmp")
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            json.dump(asdict(cfg), f, indent=2)
        os.replace(tmp, self.path)
        self.config = cfg
```

- [ ] **Step 4: Run to verify pass**

Run: `poetry run pytest tests/test_config.py -v`
Expected: all PASS.

- [ ] **Step 5: Commit**

```bash
git add src/local_dictation/config.py tests/test_config.py
git commit -m "Add validated config with JSON store" -m "Co-Authored-By: Claude Sonnet 5.5 <noreply@anthropic.com>"
```

---

### Task 3a: Shortcut value type and key names (do before Task 2)

**Files:**
- Create: `src/local_dictation/shortcut.py`
- Test: `tests/test_shortcut.py`

**Interfaces:**
- Produces:
  - `MODIFIER_ORDER = ("ctrl", "alt", "shift", "win")`
  - `vk_to_name(vk: int) -> str`, `name_to_vks(name: str) -> tuple[int, ...]`
  - `Shortcut` (frozen dataclass, field `keys: frozenset[str]`): `Shortcut.parse(text) -> Shortcut` (raises `ValueError` if empty), `.format() -> str`, `.is_safe() -> bool`.

- [ ] **Step 1: Write the failing tests**

```python
import pytest

from local_dictation.shortcut import Shortcut, name_to_vks, vk_to_name


@pytest.mark.parametrize("vk, name", [
    (0xA2, "ctrl"), (0xA3, "ctrl"), (0x11, "ctrl"),
    (0x5B, "win"), (0x5C, "win"),
    (0xA4, "alt"), (0xA0, "shift"),
    (0x78, "f9"), (0x70, "f1"), (0x41, "a"), (0x31, "1"),
    (0x20, "space"), (0x0D, "enter"), (0x1B, "esc"),
    (0xFE, "vkfe"),
])
def test_vk_to_name(vk, name):
    assert vk_to_name(vk) == name


@pytest.mark.parametrize("name", ["ctrl", "win", "alt", "shift", "f9", "a", "7", "space", "esc", "vkfe"])
def test_name_to_vks_roundtrip(name):
    vks = name_to_vks(name)
    assert vks and all(vk_to_name(vk) == name for vk in vks)


def test_parse_and_format_normalize_order_and_case():
    assert Shortcut.parse("Win + Ctrl").format() == "ctrl+win"
    assert Shortcut.parse("space+ctrl+win").format() == "ctrl+win+space"


def test_parse_empty_raises():
    with pytest.raises(ValueError):
        Shortcut.parse(" + ")


@pytest.mark.parametrize("text, safe", [
    ("ctrl+win", True), ("ctrl+alt+space", True), ("f9", True), ("win", True),
    ("a", False), ("space", False), ("ctrl+a+b", False), ("esc", False),
])
def test_is_safe(text, safe):
    assert Shortcut.parse(text).is_safe() is safe
```

- [ ] **Step 2: Run to verify failure**

Run: `poetry run pytest tests/test_shortcut.py -v`
Expected: FAIL (`ModuleNotFoundError`).

- [ ] **Step 3: Implement the first half of `shortcut.py`**

```python
"""Shortcut model, matching state machine and capture helper. Pure Python: no OS calls."""
from __future__ import annotations

import threading
from dataclasses import dataclass
from typing import Callable

MODIFIER_ORDER = ("ctrl", "alt", "shift", "win")

_MODIFIER_VKS = {
    0x10: "shift", 0xA0: "shift", 0xA1: "shift",
    0x11: "ctrl", 0xA2: "ctrl", 0xA3: "ctrl",
    0x12: "alt", 0xA4: "alt", 0xA5: "alt",
    0x5B: "win", 0x5C: "win",
}
_SPECIAL_VKS = {0x20: "space", 0x0D: "enter", 0x09: "tab", 0x1B: "esc", 0x08: "backspace"}
_SIDE_VKS = {  # specific (left/right) keys used for GetAsyncKeyState
    "shift": (0xA0, 0xA1), "ctrl": (0xA2, 0xA3), "alt": (0xA4, 0xA5), "win": (0x5B, 0x5C),
}


def vk_to_name(vk: int) -> str:
    if vk in _MODIFIER_VKS:
        return _MODIFIER_VKS[vk]
    if 0x70 <= vk <= 0x87:
        return f"f{vk - 0x6F}"
    if 0x30 <= vk <= 0x39 or 0x41 <= vk <= 0x5A:
        return chr(vk).lower()
    if vk in _SPECIAL_VKS:
        return _SPECIAL_VKS[vk]
    return f"vk{vk:02x}"


def name_to_vks(name: str) -> tuple[int, ...]:
    if name in _SIDE_VKS:
        return _SIDE_VKS[name]
    if name.startswith("f") and name[1:].isdigit():
        return (0x6F + int(name[1:]),)
    for vk, special in _SPECIAL_VKS.items():
        if special == name:
            return (vk,)
    if len(name) == 1 and name.isalnum():
        return (ord(name.upper()),)
    if name.startswith("vk"):
        return (int(name[2:], 16),)
    return ()


@dataclass(frozen=True)
class Shortcut:
    keys: frozenset

    @classmethod
    def parse(cls, text: str) -> "Shortcut":
        parts = [p.strip().lower() for p in text.split("+") if p.strip()]
        if not parts:
            raise ValueError("empty shortcut")
        return cls(frozenset(parts))

    def format(self) -> str:
        modifiers = [m for m in MODIFIER_ORDER if m in self.keys]
        others = sorted(k for k in self.keys if k not in MODIFIER_ORDER)
        return "+".join(modifiers + others)

    def is_safe(self) -> bool:
        """True if the shortcut cannot hijack normal typing."""
        others = [k for k in self.keys if k not in MODIFIER_ORDER]
        if len(others) > 1:
            return False
        if len(others) < len(self.keys):  # contains a modifier
            return True
        return len(others) == 1 and others[0][0] == "f" and others[0][1:].isdigit()
```

- [ ] **Step 4: Run to verify pass**

Run: `poetry run pytest tests/test_shortcut.py -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add src/local_dictation/shortcut.py tests/test_shortcut.py
git commit -m "Add Shortcut value type and key names" -m "Co-Authored-By: Claude Sonnet 5.5 <noreply@anthropic.com>"
```

---

### Task 3b: ShortcutMatcher, ShortcutCapture and EventDispatcher

**Files:**
- Modify: `src/local_dictation/shortcut.py` (append)
- Create: `src/local_dictation/dispatch.py`
- Test: `tests/test_matcher.py`, `tests/test_dispatch.py`

**Interfaces:**
- Consumes: `Shortcut`, `MODIFIER_ORDER` (3a).
- Produces:
  - `Decision(swallow: bool = False, events: tuple[tuple[str, str], ...] = (), inject_mask: bool = False)`; constant `PASS = Decision()`.
  - `ShortcutMatcher(bindings: dict[str, Shortcut] | None = None)`: `.set_bindings(bindings)`, `.on_key(name: str, is_down: bool) -> Decision` (events are `(binding_name, "pressed" | "released")`), `.prune(is_held: Callable[[str], bool], keep: str | None = None) -> tuple[tuple[str, str], ...]`, `.reset()`.
  - `CaptureStep(swallow: bool, done: Shortcut | None = None, cancelled: bool = False)`; `ShortcutCapture()` with `.on_key(name, is_down) -> CaptureStep` and `.preview() -> str`.
  - `EventDispatcher()`: `.set_handler(fn(binding, kind))`, `.start()`, `.stop()` (drains queue then joins), `.submit(binding, kind)`.

- [ ] **Step 1: Write the failing matcher tests** (`tests/test_matcher.py`)

```python
from local_dictation.shortcut import Shortcut, ShortcutCapture, ShortcutMatcher

REC = {"record": Shortcut.parse("ctrl+win")}


def make(bindings=REC):
    return ShortcutMatcher(dict(bindings))


def test_ctrl_then_win_swallows_win_and_masks_start_menu():
    m = make()
    assert m.on_key("ctrl", True).swallow is False
    d = m.on_key("win", True)
    assert d.swallow is True
    assert d.events == (("record", "pressed"),)
    assert d.inject_mask is True
    d = m.on_key("ctrl", False)               # ctrl-down was passed, so ctrl-up must pass
    assert d.swallow is False
    assert d.events == (("record", "released"),)
    assert m.on_key("win", False).swallow is True   # win-down was swallowed


def test_win_then_ctrl_swallows_ctrl():
    m = make()
    assert m.on_key("win", True).swallow is False
    d = m.on_key("ctrl", True)
    assert d.swallow is True and d.events == (("record", "pressed"),) and d.inject_mask is True
    d = m.on_key("ctrl", False)
    assert d.swallow is True and d.events == (("record", "released"),)
    assert m.on_key("win", False).swallow is False


def test_other_keys_pass_when_idle_and_are_swallowed_while_active():
    m = make()
    assert m.on_key("a", True).swallow is False
    assert m.on_key("a", False).swallow is False
    m.on_key("ctrl", True)
    m.on_key("win", True)
    assert m.on_key("b", True).swallow is True
    assert m.on_key("b", False).swallow is True


def test_auto_repeat_of_passed_key_never_leaves_stuck_key():
    m = make()
    m.on_key("ctrl", True)
    m.on_key("win", True)
    assert m.on_key("ctrl", True).swallow is False     # auto-repeat of a passed key stays passed
    assert m.on_key("ctrl", False).swallow is False    # so its key-up must pass too


def test_auto_repeat_of_swallowed_key_is_swallowed_without_new_event():
    m = make()
    m.on_key("ctrl", True)
    m.on_key("win", True)
    d = m.on_key("win", True)
    assert d.swallow is True and d.events == ()


def test_pressing_again_after_release_triggers_again():
    m = make()
    m.on_key("ctrl", True); m.on_key("win", True)
    m.on_key("ctrl", False)
    d = m.on_key("ctrl", True)
    assert d.events == (("record", "pressed"),)


def test_second_binding_while_first_active():
    m = make({"record": Shortcut.parse("ctrl+win"), "paste": Shortcut.parse("ctrl+win+space")})
    m.on_key("ctrl", True); m.on_key("win", True)
    d = m.on_key("space", True)
    assert d.swallow is True and d.events == (("paste", "pressed"),)


def test_function_key_binding():
    m = make({"record": Shortcut.parse("f9")})
    d = m.on_key("f9", True)
    assert d.swallow is True and d.events == (("record", "pressed"),) and d.inject_mask is False
    d = m.on_key("f9", False)
    assert d.swallow is True and d.events == (("record", "released"),)


def test_set_bindings_replaces_and_clears_active():
    m = make()
    m.on_key("ctrl", True); m.on_key("win", True)
    m.set_bindings({"record": Shortcut.parse("f9")})
    m.on_key("ctrl", False); m.on_key("win", False)    # held keys would otherwise block the f9 match
    assert m.on_key("f9", True).events == (("record", "pressed"),)


def test_prune_releases_when_passed_key_missed_its_key_up():
    m = make()
    m.on_key("ctrl", True); m.on_key("win", True)
    events = m.prune(lambda name: False)          # OS says nothing is held
    assert events == (("record", "released"),)


def test_prune_never_drops_swallowed_keys_or_keep():
    m = make()
    m.on_key("win", True)                         # passed
    assert m.prune(lambda name: False, keep="win") == ()
    m.on_key("ctrl", True)                        # swallowed, binding active
    # swallowed keys are invisible to the OS, so "not held" must not count against them
    assert m.prune(lambda name: name == "win") == ()


def test_capture_collects_peak_set_and_finishes_when_all_released():
    c = ShortcutCapture()
    assert c.on_key("ctrl", True).swallow is True
    assert c.on_key("win", True).swallow is True
    assert c.preview() == "ctrl+win"
    assert c.on_key("ctrl", False).done is None
    step = c.on_key("win", False)
    assert step.swallow is True and step.done == Shortcut.parse("ctrl+win")


def test_capture_esc_first_cancels():
    step = ShortcutCapture().on_key("esc", True)
    assert step.cancelled is True


def test_capture_passes_key_up_of_unseen_key():
    assert ShortcutCapture().on_key("shift", False).swallow is False
```

- [ ] **Step 2: Write the failing dispatcher tests** (`tests/test_dispatch.py`)

```python
from local_dictation.dispatch import EventDispatcher


def test_events_delivered_in_order_on_other_thread():
    import threading
    seen, threads = [], set()
    d = EventDispatcher()
    d.set_handler(lambda b, k: (seen.append((b, k)), threads.add(threading.current_thread())))
    d.start()
    for i in range(50):
        d.submit("record", "pressed" if i % 2 == 0 else "released")
    d.stop()
    assert seen == [("record", "pressed" if i % 2 == 0 else "released") for i in range(50)]
    assert threading.current_thread() not in threads


def test_handler_exception_does_not_kill_dispatcher():
    seen = []

    def handler(binding, kind):
        if kind == "boom":
            raise RuntimeError("x")
        seen.append(kind)

    d = EventDispatcher()
    d.set_handler(handler)
    d.start()
    d.submit("record", "boom")
    d.submit("record", "ok")
    d.stop()
    assert seen == ["ok"]


def test_submit_without_handler_is_harmless():
    d = EventDispatcher()
    d.start()
    d.submit("record", "pressed")
    d.stop()
```

- [ ] **Step 3: Run to verify failure**

Run: `poetry run pytest tests/test_matcher.py tests/test_dispatch.py -v`
Expected: FAIL (import errors).

- [ ] **Step 4: Append to `shortcut.py`**

```python
@dataclass(frozen=True)
class Decision:
    swallow: bool = False
    events: tuple = ()
    inject_mask: bool = False


PASS = Decision()


class ShortcutMatcher:
    """Decides, per key event, whether to swallow it and which shortcut events to emit.

    Invariant: a key-up is swallowed only if the matching key-down was swallowed, so the OS
    never sees an unbalanced down/up pair (no stuck modifiers).
    """

    def __init__(self, bindings: dict | None = None):
        self._bindings = dict(bindings or {})
        self._down: set = set()
        self._swallowed: set = set()
        self._active: set = set()
        self._lock = threading.RLock()

    def set_bindings(self, bindings: dict) -> None:
        with self._lock:
            self._bindings = dict(bindings)
            self._active.clear()

    def reset(self) -> None:
        with self._lock:
            self._down.clear()
            self._swallowed.clear()
            self._active.clear()

    def on_key(self, name: str, is_down: bool) -> Decision:
        with self._lock:
            return self._on_down(name) if is_down else self._on_up(name)

    def _on_down(self, name: str) -> Decision:
        first = name not in self._down
        self._down.add(name)
        if name in self._swallowed:
            return Decision(swallow=True)
        if not first:
            return PASS
        events, mask = [], False
        candidate = frozenset(self._down)
        for binding, shortcut in self._bindings.items():
            if shortcut.keys == candidate and binding not in self._active:
                self._active.add(binding)
                events.append((binding, "pressed"))
                mask = mask or "win" in shortcut.keys
        if events or self._active:
            self._swallowed.add(name)
            return Decision(True, tuple(events), mask)
        return PASS

    def _on_up(self, name: str) -> Decision:
        self._down.discard(name)
        events = []
        for binding in list(self._active):
            shortcut = self._bindings.get(binding)
            if shortcut is None or name in shortcut.keys:
                self._active.discard(binding)
                events.append((binding, "released"))
        swallow = name in self._swallowed
        self._swallowed.discard(name)
        return Decision(swallow, tuple(events))

    def prune(self, is_held: Callable[[str], bool], keep: str | None = None) -> tuple:
        """Forget passed-through keys the OS says are up (a missed key-up).

        Swallowed keys are skipped: the OS never saw them go down, so it cannot confirm them.
        """
        with self._lock:
            events: list = []
            for name in list(self._down):
                if name == keep or name in self._swallowed:
                    continue
                if not is_held(name):
                    events.extend(self._on_up(name).events)
            return tuple(events)


@dataclass(frozen=True)
class CaptureStep:
    swallow: bool
    done: Shortcut | None = None
    cancelled: bool = False


class ShortcutCapture:
    """Records the largest set of keys held together; finishes when all are released."""

    def __init__(self):
        self._down: set = set()
        self._peak: set = set()
        self._seen: set = set()

    def preview(self) -> str:
        return Shortcut(frozenset(self._peak)).format() if self._peak else ""

    def on_key(self, name: str, is_down: bool) -> CaptureStep:
        if is_down:
            if not self._seen and name == "esc":
                return CaptureStep(True, cancelled=True)
            self._seen.add(name)
            self._down.add(name)
            self._peak.add(name)
            return CaptureStep(True)
        if name not in self._seen:
            return CaptureStep(False)
        self._down.discard(name)
        if not self._down and self._peak:
            return CaptureStep(True, done=Shortcut(frozenset(self._peak)))
        return CaptureStep(True)
```

- [ ] **Step 5: Implement `dispatch.py`**

```python
"""Queue + thread between the keyboard hook and the controller, so the hook only enqueues."""
from __future__ import annotations

import logging
import queue
import threading
from typing import Callable

log = logging.getLogger(__name__)


class EventDispatcher:
    def __init__(self):
        self._queue: queue.Queue = queue.Queue()
        self._handler: Callable[[str, str], None] | None = None
        self._thread: threading.Thread | None = None

    def set_handler(self, handler: Callable[[str, str], None]) -> None:
        self._handler = handler

    def start(self) -> None:
        self._thread = threading.Thread(target=self._loop, name="hotkey-dispatch", daemon=True)
        self._thread.start()

    def stop(self) -> None:
        if self._thread is not None:
            self._queue.put(None)
            self._thread.join()
            self._thread = None

    def submit(self, binding: str, kind: str) -> None:
        self._queue.put((binding, kind))

    def _loop(self) -> None:
        while True:
            item = self._queue.get()
            if item is None:
                return
            handler = self._handler
            if handler is None:
                continue
            try:
                handler(*item)
            except Exception:
                log.exception("hotkey handler failed for %s", item)
```

- [ ] **Step 6: Run to verify pass**

Run: `poetry run pytest tests/test_matcher.py tests/test_dispatch.py tests/test_shortcut.py -v`
Expected: all PASS.

- [ ] **Step 7: Commit**

```bash
git add src/local_dictation/shortcut.py src/local_dictation/dispatch.py tests/test_matcher.py tests/test_dispatch.py
git commit -m "Add shortcut matcher, capture and event dispatcher" -m "Co-Authored-By: Claude Sonnet 5.5 <noreply@anthropic.com>"
```

---

### Task 4: Windows keyboard hook

**Files:**
- Create: `src/local_dictation/keystate.py`, `src/local_dictation/hotkey.py`
- Test: `tests/test_hotkey_import.py` (import-level only; behavior is covered by the manual checklist)

**Interfaces:**
- Consumes: `ShortcutMatcher`, `ShortcutCapture`, `Shortcut`, `vk_to_name`, `name_to_vks` (Task 3); `EventDispatcher` (Task 3b).
- Produces:
  - `keystate.is_held(name: str) -> bool`
  - `WindowsHotkeyListener()` with: `.set_handler(fn(binding: str, kind: str))`, `.set_bindings(dict[str, Shortcut])`, `.start() -> None` (raises `RuntimeError` if the hook cannot be installed), `.stop() -> None`, `.begin_capture(on_update: Callable[[str], None], on_done: Callable[[Shortcut | None], None]) -> None`, `.cancel_capture() -> None`. Handler and capture callbacks are invoked on non-Qt threads.

- [ ] **Step 1: Write the import test**

```python
def test_modules_import_and_listener_constructs():
    from local_dictation.hotkey import WindowsHotkeyListener
    from local_dictation.keystate import is_held

    listener = WindowsHotkeyListener()
    assert callable(listener.start) and callable(listener.begin_capture)
    assert isinstance(is_held("ctrl"), bool)
```

- [ ] **Step 2: Run to verify failure**

Run: `poetry run pytest tests/test_hotkey_import.py -v`
Expected: FAIL (`ModuleNotFoundError`).

- [ ] **Step 3: Implement `keystate.py`**

```python
"""Physical key state via GetAsyncKeyState (note: keys swallowed by our hook read as up)."""
import ctypes

from .shortcut import name_to_vks

_user32 = ctypes.WinDLL("user32", use_last_error=True)
_user32.GetAsyncKeyState.argtypes = [ctypes.c_int]
_user32.GetAsyncKeyState.restype = ctypes.c_short


def is_held(name: str) -> bool:
    return any(_user32.GetAsyncKeyState(vk) & 0x8000 for vk in name_to_vks(name))
```

- [ ] **Step 4: Implement `hotkey.py`**

```python
"""Global keyboard hook (WH_KEYBOARD_LL) that can swallow shortcut keys.

The callback runs on the hook thread and must return fast: it only consults the matcher and
enqueues events. A Win-key shortcut injects an unassigned key (VK 0xE8) so Windows does not
open the Start menu when Win is released.
"""
from __future__ import annotations

import ctypes
import logging
import threading
from ctypes import wintypes
from typing import Callable

from .dispatch import EventDispatcher
from .keystate import is_held
from .shortcut import PASS, Shortcut, ShortcutCapture, ShortcutMatcher, vk_to_name

log = logging.getLogger(__name__)

WH_KEYBOARD_LL = 13
HC_ACTION = 0
WM_KEYDOWN, WM_KEYUP, WM_SYSKEYDOWN, WM_SYSKEYUP = 0x0100, 0x0101, 0x0104, 0x0105
WM_QUIT = 0x0012
LLKHF_INJECTED = 0x10
KEYEVENTF_KEYUP = 0x0002
MASK_VK = 0xE8  # unassigned virtual key, same trick AutoHotkey uses

LRESULT = ctypes.c_ssize_t
HOOKPROC = ctypes.WINFUNCTYPE(LRESULT, ctypes.c_int, wintypes.WPARAM, wintypes.LPARAM)


class KBDLLHOOKSTRUCT(ctypes.Structure):
    _fields_ = [
        ("vkCode", wintypes.DWORD),
        ("scanCode", wintypes.DWORD),
        ("flags", wintypes.DWORD),
        ("time", wintypes.DWORD),
        ("dwExtraInfo", ctypes.c_size_t),
    ]


user32 = ctypes.WinDLL("user32", use_last_error=True)
kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
user32.SetWindowsHookExW.argtypes = [ctypes.c_int, HOOKPROC, wintypes.HINSTANCE, wintypes.DWORD]
user32.SetWindowsHookExW.restype = wintypes.HHOOK
user32.CallNextHookEx.argtypes = [wintypes.HHOOK, ctypes.c_int, wintypes.WPARAM, wintypes.LPARAM]
user32.CallNextHookEx.restype = LRESULT
user32.UnhookWindowsHookEx.argtypes = [wintypes.HHOOK]
user32.GetMessageW.argtypes = [ctypes.POINTER(wintypes.MSG), wintypes.HWND, wintypes.UINT, wintypes.UINT]
user32.PostThreadMessageW.argtypes = [wintypes.DWORD, wintypes.UINT, wintypes.WPARAM, wintypes.LPARAM]
user32.keybd_event.argtypes = [wintypes.BYTE, wintypes.BYTE, wintypes.DWORD, ctypes.c_size_t]
kernel32.GetModuleHandleW.argtypes = [wintypes.LPCWSTR]
kernel32.GetModuleHandleW.restype = wintypes.HMODULE


def _inject_mask() -> None:
    user32.keybd_event(MASK_VK, 0, 0, 0)
    user32.keybd_event(MASK_VK, 0, KEYEVENTF_KEYUP, 0)


class WindowsHotkeyListener:
    def __init__(self):
        self._matcher = ShortcutMatcher()
        self._dispatcher = EventDispatcher()
        self._capture: ShortcutCapture | None = None
        self._on_update: Callable[[str], None] | None = None
        self._on_done: Callable[[Shortcut | None], None] | None = None
        self._thread: threading.Thread | None = None
        self._thread_id: int | None = None
        self._hook = None
        self._proc = None
        self._ready = threading.Event()
        self._error: Exception | None = None

    # -- public API -------------------------------------------------------
    def set_handler(self, handler: Callable[[str, str], None]) -> None:
        self._dispatcher.set_handler(handler)

    def set_bindings(self, bindings: dict) -> None:
        self._matcher.set_bindings(bindings)

    def start(self) -> None:
        self._error = None
        self._ready.clear()
        self._matcher.reset()
        self._dispatcher.start()
        self._thread = threading.Thread(target=self._run, name="keyboard-hook", daemon=True)
        self._thread.start()
        if not self._ready.wait(5) or self._error is not None:
            self._dispatcher.stop()
            raise RuntimeError(f"Could not install keyboard hook: {self._error}")

    def stop(self) -> None:
        if self._thread is not None and self._thread_id is not None:
            user32.PostThreadMessageW(self._thread_id, WM_QUIT, 0, 0)
            self._thread.join(2)
        self._thread = None
        self._dispatcher.stop()

    def begin_capture(self, on_update, on_done) -> None:
        self._on_update, self._on_done = on_update, on_done
        self._capture = ShortcutCapture()

    def cancel_capture(self) -> None:
        self._capture = None

    # -- hook thread ------------------------------------------------------
    def _run(self) -> None:
        self._thread_id = kernel32.GetCurrentThreadId()
        self._proc = HOOKPROC(self._hook_proc)  # keep a reference or it gets garbage collected
        self._hook = user32.SetWindowsHookExW(WH_KEYBOARD_LL, self._proc,
                                              kernel32.GetModuleHandleW(None), 0)
        if not self._hook:
            self._error = ctypes.WinError(ctypes.get_last_error())
            self._ready.set()
            return
        self._ready.set()
        msg = wintypes.MSG()
        while user32.GetMessageW(ctypes.byref(msg), None, 0, 0) > 0:
            user32.TranslateMessage(ctypes.byref(msg))
            user32.DispatchMessageW(ctypes.byref(msg))
        user32.UnhookWindowsHookEx(self._hook)
        self._hook = None

    def _hook_proc(self, n_code, w_param, l_param):
        if n_code == HC_ACTION:
            try:
                if self._handle(w_param, l_param):
                    return 1
            except Exception:
                log.exception("keyboard hook error")
        return user32.CallNextHookEx(None, n_code, w_param, l_param)

    def _handle(self, w_param, l_param) -> bool:
        kb = ctypes.cast(l_param, ctypes.POINTER(KBDLLHOOKSTRUCT)).contents
        if kb.flags & LLKHF_INJECTED:
            return False
        is_down = w_param in (WM_KEYDOWN, WM_SYSKEYDOWN)
        name = vk_to_name(kb.vkCode)

        capture = self._capture
        if capture is not None:
            step = capture.on_key(name, is_down)
            if step.done is not None or step.cancelled:
                self._capture = None
            if is_down and self._on_update:
                self._on_update(capture.preview())
            if (step.done is not None or step.cancelled) and self._on_done:
                self._on_done(step.done)
            return step.swallow

        for binding, kind in self._matcher.prune(is_held, keep=name):
            self._dispatcher.submit(binding, kind)
        decision = self._matcher.on_key(name, is_down)
        for binding, kind in decision.events:
            self._dispatcher.submit(binding, kind)
        if decision.inject_mask:
            _inject_mask()
        return decision.swallow
```

- [ ] **Step 5: Run to verify pass**

Run: `poetry run pytest tests/test_hotkey_import.py -v`
Expected: PASS.

- [ ] **Step 6: Smoke-test the real hook by hand**

Run (from the repo root):
```
poetry run python -c "import time; from local_dictation.hotkey import WindowsHotkeyListener; from local_dictation.config import Config; l = WindowsHotkeyListener(); l.set_bindings(Config().bindings()); l.set_handler(lambda b, k: print(b, k, flush=True)); l.start(); print('hold Ctrl+Win in Notepad for 20s'); time.sleep(20); l.stop()"
```
Expected: `record pressed` on press and `record released` on release; the Start menu does not open; Notepad shows no side effects; try Win-then-Ctrl order too. If the Start menu still opens, change `MASK_VK` (try `0xFF` or tap Left Shift `0xA0`) — this is the spec's open item; record the working value in `docs/decisions.md`.

- [ ] **Step 7: Commit**

```bash
git add src/local_dictation/keystate.py src/local_dictation/hotkey.py tests/test_hotkey_import.py docs/decisions.md
git commit -m "Add low-level keyboard hook with key swallowing" -m "Co-Authored-By: Claude Sonnet 5.5 <noreply@anthropic.com>"
```

---

### Task 5: Audio, transcription and cleanup

**Files:**
- Create: `src/local_dictation/audio.py`, `src/local_dictation/transcribe.py`, `src/local_dictation/cleanup.py`
- Test: `tests/test_audio.py`, `tests/test_transcribe.py`, `tests/test_cleanup.py`

**Interfaces:**
- Produces:
  - `SAMPLE_RATE = 16000` (in `audio.py`); `Recorder(stream_factory=None)` with `.start() -> None` (raises on mic errors), `.stop() -> numpy.ndarray` (float32, mono; empty array if nothing recorded).
  - `Transcriber(model_factory=None, on_status: Callable[[str], None] | None = None)`: `.configure(model_name: str, device: str) -> None` (loads in background; status strings `"loading"`, `"ready"`, `"error: <msg>"`), `.transcribe(audio, language: str, timeout: float = 600) -> str` (language `""` = auto; raises `RuntimeError` if the model failed or is still loading after `timeout`).
  - `ollama_cleanup(text: str, model: str) -> str` (never raises; returns `text` on any failure or empty reply).

- [ ] **Step 1: Write the failing tests**

`tests/test_audio.py`:
```python
import numpy as np

from local_dictation.audio import SAMPLE_RATE, Recorder


class FakeStream:
    def __init__(self, **kwargs):
        self.callback = kwargs["callback"]
        self.kwargs = kwargs
        self.started = self.stopped = self.closed = False

    def start(self): self.started = True
    def stop(self): self.stopped = True
    def close(self): self.closed = True


def test_records_between_start_and_stop():
    streams = []

    def factory(**kwargs):
        streams.append(FakeStream(**kwargs))
        return streams[-1]

    rec = Recorder(factory)
    rec.start()
    assert streams[0].started and streams[0].kwargs["samplerate"] == SAMPLE_RATE
    streams[0].callback(np.ones((100, 1), dtype="float32"), 100, None, None)
    streams[0].callback(np.ones((50, 1), dtype="float32") * 2, 50, None, None)
    audio = rec.stop()
    assert audio.shape == (150,) and audio.dtype == np.float32
    assert streams[0].stopped and streams[0].closed


def test_stop_without_audio_returns_empty():
    rec = Recorder(lambda **kw: FakeStream(**kw))
    rec.start()
    assert rec.stop().shape == (0,)


def test_stop_without_start_is_safe():
    assert Recorder(lambda **kw: FakeStream(**kw)).stop().shape == (0,)


def test_start_failure_propagates_and_next_start_works():
    calls = {"n": 0}

    def factory(**kw):
        calls["n"] += 1
        if calls["n"] == 1:
            raise OSError("no microphone")
        return FakeStream(**kw)

    rec = Recorder(factory)
    try:
        rec.start()
        assert False, "expected OSError"
    except OSError:
        pass
    rec.start()
    assert rec.stop().shape == (0,)
```

`tests/test_transcribe.py`:
```python
import threading
import time
from types import SimpleNamespace

import numpy as np
import pytest

from local_dictation.transcribe import Transcriber


class FakeModel:
    def __init__(self):
        self.calls = []

    def transcribe(self, audio, language=None, beam_size=None, vad_filter=None):
        self.calls.append((language, beam_size, vad_filter))
        return iter([SimpleNamespace(text=" hello "), SimpleNamespace(text="world ")]), None


def test_transcribe_joins_segments_and_maps_empty_language_to_none():
    model = FakeModel()
    statuses = []
    t = Transcriber(lambda name, device: model, on_status=statuses.append)
    t.configure("base.en", "cpu")
    assert t.transcribe(np.zeros(16000, dtype="float32"), "") == "hello world"
    assert model.calls == [(None, 1, True)]
    assert statuses == ["loading", "ready"]


def test_language_is_passed_through():
    model = FakeModel()
    t = Transcriber(lambda n, d: model)
    t.configure("base", "cpu")
    t.transcribe(np.zeros(10, dtype="float32"), "ro")
    assert model.calls[0][0] == "ro"


def test_load_failure_is_reported_not_raised_at_configure():
    def factory(name, device):
        raise ValueError("bad model")

    statuses = []
    t = Transcriber(factory, on_status=statuses.append)
    t.configure("nope", "cpu")
    with pytest.raises(RuntimeError, match="bad model"):
        t.transcribe(np.zeros(10, dtype="float32"), "")
    assert statuses[-1].startswith("error")


def test_transcribe_waits_for_loading_and_times_out():
    gate = threading.Event()
    t = Transcriber(lambda n, d: (gate.wait(5), FakeModel())[1])
    t.configure("base.en", "cpu")
    with pytest.raises(RuntimeError, match="still loading"):
        t.transcribe(np.zeros(10, dtype="float32"), "", timeout=0.05)
    gate.set()
    time.sleep(0.2)
    assert t.transcribe(np.zeros(10, dtype="float32"), "") == "hello world"


def test_reconfigure_discards_stale_load():
    first_gate = threading.Event()
    old, new = FakeModel(), FakeModel()

    def factory(name, device):
        if name == "old":
            first_gate.wait(5)
            return old
        return new

    t = Transcriber(factory)
    t.configure("old", "cpu")
    t.configure("new", "cpu")
    first_gate.set()
    time.sleep(0.2)
    t.transcribe(np.zeros(10, dtype="float32"), "")
    assert new.calls and not old.calls


def test_transcribe_before_configure_raises():
    with pytest.raises(RuntimeError):
        Transcriber(lambda n, d: FakeModel()).transcribe(np.zeros(10, dtype="float32"), "", timeout=0.01)
```

`tests/test_cleanup.py`:
```python
import io
import json
import urllib.error

from local_dictation import cleanup


class FakeResponse(io.BytesIO):
    def __enter__(self): return self
    def __exit__(self, *a): return False


def fake_urlopen(payload):
    def _open(req, timeout=None):
        _open.request = req
        return FakeResponse(json.dumps(payload).encode())
    return _open


def test_returns_cleaned_text_and_posts_expected_body(monkeypatch):
    opener = fake_urlopen({"response": " Hello, world. "})
    monkeypatch.setattr(cleanup.urllib.request, "urlopen", opener)
    assert cleanup.ollama_cleanup("um hello world", "qwen2.5:1.5b") == "Hello, world."
    body = json.loads(opener.request.data)
    assert body["model"] == "qwen2.5:1.5b" and body["stream"] is False
    assert "um hello world" in body["prompt"]
    assert opener.request.full_url == "http://localhost:11434/api/generate"


def test_empty_reply_falls_back_to_raw_text(monkeypatch):
    monkeypatch.setattr(cleanup.urllib.request, "urlopen", fake_urlopen({"response": "  "}))
    assert cleanup.ollama_cleanup("raw", "m") == "raw"


def test_connection_error_falls_back(monkeypatch):
    def boom(req, timeout=None):
        raise urllib.error.URLError("refused")
    monkeypatch.setattr(cleanup.urllib.request, "urlopen", boom)
    assert cleanup.ollama_cleanup("raw", "m") == "raw"


def test_malformed_json_falls_back(monkeypatch):
    monkeypatch.setattr(cleanup.urllib.request, "urlopen",
                        lambda req, timeout=None: FakeResponse(b"not json"))
    assert cleanup.ollama_cleanup("raw", "m") == "raw"
```

- [ ] **Step 2: Run to verify failure**

Run: `poetry run pytest tests/test_audio.py tests/test_transcribe.py tests/test_cleanup.py -v`
Expected: FAIL (import errors).

- [ ] **Step 3: Implement `audio.py`**

```python
"""Microphone capture: the stream exists only between start() and stop()."""
from __future__ import annotations

import numpy as np

SAMPLE_RATE = 16000


def _default_stream_factory(**kwargs):
    import sounddevice as sd
    return sd.InputStream(**kwargs)


class Recorder:
    def __init__(self, stream_factory=None):
        self._factory = stream_factory or _default_stream_factory
        self._stream = None
        self._chunks: list = []

    def start(self) -> None:
        self._chunks = []
        stream = self._factory(samplerate=SAMPLE_RATE, channels=1, dtype="float32",
                               callback=self._on_audio)
        stream.start()
        self._stream = stream

    def _on_audio(self, indata, frames, time_info, status) -> None:
        self._chunks.append(indata.copy())

    def stop(self) -> np.ndarray:
        stream, self._stream = self._stream, None
        if stream is not None:
            stream.stop()
            stream.close()
        chunks, self._chunks = self._chunks, []
        if not chunks:
            return np.zeros(0, dtype=np.float32)
        return np.concatenate(chunks).flatten().astype(np.float32)
```

- [ ] **Step 4: Implement `transcribe.py`**

```python
"""faster-whisper wrapper: loads in the background, can be reloaded when settings change."""
from __future__ import annotations

import logging
import os
import threading
from typing import Callable

log = logging.getLogger(__name__)


def _default_factory(name: str, device: str):
    from faster_whisper import WhisperModel
    compute = "int8" if device == "cpu" else "float32"
    return WhisperModel(name, device=device, compute_type=compute, cpu_threads=os.cpu_count() or 4)


class Transcriber:
    def __init__(self, model_factory=None, on_status: Callable[[str], None] | None = None):
        self._factory = model_factory or _default_factory
        self._on_status = on_status or (lambda status: None)
        self._lock = threading.Lock()
        self._ready = threading.Event()
        self._generation = 0
        self._model = None
        self._error: Exception | None = None

    def configure(self, model_name: str, device: str) -> None:
        with self._lock:
            self._generation += 1
            generation = self._generation
            self._ready.clear()
            self._model, self._error = None, None
        self._on_status("loading")
        threading.Thread(target=self._load, args=(generation, model_name, device),
                         name="whisper-loader", daemon=True).start()

    def _load(self, generation: int, model_name: str, device: str) -> None:
        model, error = None, None
        try:
            model = self._factory(model_name, device)
        except Exception as e:
            log.exception("Whisper model failed to load")
            error = e
        with self._lock:
            if generation != self._generation:
                return  # superseded by a newer configure()
            self._model, self._error = model, error
            # report before unblocking transcribe() so callers observe a consistent order
            self._on_status("ready" if error is None else f"error: {error}")
            self._ready.set()

    def transcribe(self, audio, language: str, timeout: float = 600) -> str:
        if not self._ready.wait(timeout):
            raise RuntimeError("The Whisper model is still loading; try again in a moment.")
        with self._lock:
            model, error = self._model, self._error
        if error is not None or model is None:
            raise RuntimeError(f"Whisper model failed to load: {error}")
        segments, _ = model.transcribe(audio, language=language or None, beam_size=1, vad_filter=True)
        return " ".join(s.text.strip() for s in segments).strip()
```

- [ ] **Step 5: Implement `cleanup.py`**

```python
"""Optional text polish through a local Ollama model."""
from __future__ import annotations

import json
import logging
import urllib.request

log = logging.getLogger(__name__)

OLLAMA_URL = "http://localhost:11434/api/generate"

CLEANUP_PROMPT = """Clean up this dictated text. Fix punctuation and capitalization, \
remove filler words (um, uh, like, you know) and false starts. Keep the meaning and \
wording otherwise unchanged. Output ONLY the cleaned text, nothing else.

Text: {text}"""


def ollama_cleanup(text: str, model: str) -> str:
    body = json.dumps({"model": model, "prompt": CLEANUP_PROMPT.format(text=text),
                       "stream": False, "options": {"temperature": 0}}).encode()
    request = urllib.request.Request(OLLAMA_URL, data=body,
                                     headers={"Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(request, timeout=30) as response:
            return json.loads(response.read())["response"].strip() or text
    except Exception as e:
        log.warning("cleanup skipped: %s", e)
        return text
```

- [ ] **Step 6: Run to verify pass**

Run: `poetry run pytest tests/test_audio.py tests/test_transcribe.py tests/test_cleanup.py -v`
Expected: all PASS.

- [ ] **Step 7: Commit**

```bash
git add src/local_dictation/audio.py src/local_dictation/transcribe.py src/local_dictation/cleanup.py tests
git commit -m "Port audio, transcription and cleanup into the package" -m "Co-Authored-By: Claude Sonnet 5.5 <noreply@anthropic.com>"
```

---

### Task 6: Paste

**Files:**
- Create: `src/local_dictation/paste.py`
- Test: `tests/test_paste.py`

**Interfaces:**
- Consumes: `MODIFIER_ORDER` (3a), `keystate.is_held` (Task 4, default only).
- Produces: `Paster(clipboard=None, keyboard_factory=None, is_held=None, sleep=time.sleep, clock=time.monotonic)` with `.paste(text: str) -> None`. Waits (max 1.5 s) until Ctrl/Alt/Shift/Win are physically up, sets the clipboard, sends Ctrl+V, then restores the previous clipboard text.

- [ ] **Step 1: Write the failing tests**

```python
from local_dictation.paste import Paster


class FakeClipboard:
    def __init__(self, content="old", fail_read=False):
        self.content, self.fail_read, self.log = content, fail_read, []

    def paste(self):
        if self.fail_read:
            raise RuntimeError("clipboard unavailable")
        return self.content

    def copy(self, text):
        self.content = text
        self.log.append(("copy", text))


class FakeKeyboard:
    def __init__(self, log):
        self.log = log

    def pressed(self, key):
        outer = self

        class Ctx:
            def __enter__(self_inner): outer.log.append(("down", key)); return self_inner
            def __exit__(self_inner, *a): outer.log.append(("up", key)); return False
        return Ctx()

    def press(self, key): self.log.append(("press", key))
    def release(self, key): self.log.append(("release", key))


def make(clipboard, held=None, log=None):
    log = log if log is not None else []
    sleeps = []
    clock = {"t": 0.0}

    def sleep(seconds):
        sleeps.append(seconds)
        clock["t"] += seconds
        if held is not None and len(sleeps) == 1 and held.get("auto_release"):
            held.pop("ctrl", None); held.pop("win", None)

    paster = Paster(clipboard=clipboard,
                    keyboard_factory=lambda: FakeKeyboard(log),
                    is_held=lambda name: bool((held or {}).get(name)),
                    sleep=sleep, clock=lambda: clock["t"])
    return paster, log, sleeps


def test_sets_clipboard_sends_ctrl_v_and_restores_previous():
    clip = FakeClipboard("old")
    paster, log, _ = make(clip)
    paster.paste("hello ")
    assert clip.log == [("copy", "hello "), ("copy", "old")]
    assert [e[0] for e in log] == ["down", "press", "release", "up"]
    assert log[1][1] == "v"


def test_waits_for_modifiers_to_be_released_before_pasting():
    clip = FakeClipboard()
    held = {"ctrl": True, "win": True, "auto_release": True}
    paster, log, sleeps = make(clip, held)
    paster.paste("x")
    assert sleeps[0] == 0.02            # polled once while keys were held
    assert ("copy", "x") in clip.log


def test_gives_up_waiting_after_timeout_but_still_pastes():
    clip = FakeClipboard()
    paster, log, sleeps = make(clip, {"win": True})
    paster.paste("x")
    assert sum(s for s in sleeps if s == 0.02) >= 1.4   # polled until the 1.5 s deadline
    assert ("copy", "x") in clip.log and any(e[0] == "press" for e in log)


def test_unreadable_clipboard_does_not_block_paste_or_restore():
    clip = FakeClipboard(fail_read=True)
    paster, log, _ = make(clip)
    paster.paste("x")
    assert clip.log == [("copy", "x")]
```

- [ ] **Step 2: Run to verify failure**

Run: `poetry run pytest tests/test_paste.py -v`
Expected: FAIL (`ModuleNotFoundError`).

- [ ] **Step 3: Implement `paste.py`**

```python
"""Paste text into the focused control via the clipboard, then restore the clipboard."""
from __future__ import annotations

import logging
import time

import pyperclip
from pynput import keyboard

from .shortcut import MODIFIER_ORDER

log = logging.getLogger(__name__)

MODIFIER_WAIT_SECONDS = 1.5
POLL_SECONDS = 0.02


class Paster:
    def __init__(self, clipboard=None, keyboard_factory=None, is_held=None,
                 sleep=time.sleep, clock=time.monotonic):
        self._clipboard = clipboard or pyperclip
        self._keyboard_factory = keyboard_factory or keyboard.Controller
        if is_held is None:
            from .keystate import is_held as is_held  # imported lazily: Windows-only
        self._is_held = is_held
        self._sleep = sleep
        self._clock = clock

    def _wait_for_modifiers_up(self) -> None:
        # Release is detected on the first key up; if Win/Ctrl is still down, our Ctrl+V
        # would become Win+V (clipboard history) or similar.
        deadline = self._clock() + MODIFIER_WAIT_SECONDS
        while any(self._is_held(m) for m in MODIFIER_ORDER) and self._clock() < deadline:
            self._sleep(POLL_SECONDS)

    def paste(self, text: str) -> None:
        self._wait_for_modifiers_up()
        try:
            previous = self._clipboard.paste()
        except Exception:
            previous = None
        self._clipboard.copy(text)
        self._sleep(0.05)
        kb = self._keyboard_factory()
        with kb.pressed(keyboard.Key.ctrl):
            kb.press("v")
            kb.release("v")
        self._sleep(0.3)
        if previous is not None:
            self._clipboard.copy(previous)
```

- [ ] **Step 4: Run to verify pass**

Run: `poetry run pytest tests/test_paste.py -v`
Expected: all PASS.

- [ ] **Step 5: Commit**

```bash
git add src/local_dictation/paste.py tests/test_paste.py
git commit -m "Add paste with modifier-release wait" -m "Co-Authored-By: Claude Sonnet 5.5 <noreply@anthropic.com>"
```

---

### Task 7: Controller state machine

**Files:**
- Create: `src/local_dictation/controller.py`
- Test: `tests/test_controller.py`

**Interfaces:**
- Consumes: `Config` fields (Task 2) via `get_config() -> Config`; `Recorder.start/stop` (5); `Transcriber.transcribe(audio, language)` (5); `ollama_cleanup(text, model)` (5); `Paster.paste(text)` (6); `SAMPLE_RATE` (5).
- Produces:
  - `State` (str Enum): `IDLE="idle"`, `RECORDING="recording"`, `TRANSCRIBING="transcribing"`, `READY="ready"`, `PASTING="pasting"`.
  - `Controller(*, get_config, recorder, transcriber, cleanup, paster, notify, on_state, run_async=None)`; `notify(title: str, message: str)`; `on_state(state_value: str)`; `run_async(fn)` defaults to a daemon thread. Method `handle_hotkey(binding: str, kind: str)` where binding ∈ {`"record"`, `"paste"`} and kind ∈ {`"pressed"`, `"released"`}. Property `.state -> State`.

- [ ] **Step 1: Write the failing tests**

```python
import numpy as np

from local_dictation.config import Config
from local_dictation.controller import Controller, State

ONE_SECOND = np.zeros(16000, dtype="float32")


class FakeRecorder:
    def __init__(self, audio=ONE_SECOND, start_error=None):
        self.audio, self.start_error, self.started = audio, start_error, 0

    def start(self):
        if self.start_error:
            raise self.start_error
        self.started += 1

    def stop(self):
        return self.audio


class FakeTranscriber:
    def __init__(self, text="hello world", error=None):
        self.text, self.error, self.calls = text, error, []

    def transcribe(self, audio, language):
        self.calls.append(language)
        if self.error:
            raise self.error
        return self.text


class FakePaster:
    def __init__(self, error=None):
        self.pasted, self.error = [], error

    def paste(self, text):
        if self.error:
            raise self.error
        self.pasted.append(text)


def build(config=None, recorder=None, transcriber=None, paster=None, cleanup=None, deferred=False):
    config = config or Config()
    jobs = []
    states, notes = [], []
    c = Controller(
        get_config=lambda: config,
        recorder=recorder or FakeRecorder(),
        transcriber=transcriber or FakeTranscriber(),
        cleanup=cleanup or (lambda text, model: f"[{model}] {text}"),
        paster=paster or FakePaster(),
        notify=lambda title, msg: notes.append((title, msg)),
        on_state=states.append,
        run_async=(jobs.append if deferred else (lambda fn: fn())),
    )
    return c, states, notes, jobs


def test_release_mode_full_flow_pastes_with_trailing_space():
    paster = FakePaster()
    c, states, notes, _ = build(paster=paster)
    c.handle_hotkey("record", "pressed")
    assert c.state is State.RECORDING
    c.handle_hotkey("record", "released")
    assert paster.pasted == ["hello world "]
    assert c.state is State.IDLE
    assert states == ["recording", "transcribing", "pasting", "idle"]
    assert notes == []


def test_cleanup_used_only_when_model_configured():
    paster = FakePaster()
    c, *_ = build(Config(cleanup_model="qwen"), paster=paster)
    c.handle_hotkey("record", "pressed"); c.handle_hotkey("record", "released")
    assert paster.pasted == ["[qwen] hello world "]


def test_language_passed_to_transcriber():
    t = FakeTranscriber()
    c, *_ = build(Config(language="ro"), transcriber=t)
    c.handle_hotkey("record", "pressed"); c.handle_hotkey("record", "released")
    assert t.calls == ["ro"]


def test_too_short_recording_is_ignored_silently():
    paster = FakePaster()
    c, states, notes, _ = build(recorder=FakeRecorder(np.zeros(1000, dtype="float32")), paster=paster)
    c.handle_hotkey("record", "pressed"); c.handle_hotkey("record", "released")
    assert paster.pasted == [] and notes == [] and c.state is State.IDLE


def test_empty_audio_is_ignored_silently():
    c, _, notes, _ = build(recorder=FakeRecorder(np.zeros(0, dtype="float32")))
    c.handle_hotkey("record", "pressed"); c.handle_hotkey("record", "released")
    assert notes == [] and c.state is State.IDLE


def test_no_speech_notifies_and_returns_to_idle():
    paster = FakePaster()
    c, _, notes, _ = build(transcriber=FakeTranscriber(text=""), paster=paster)
    c.handle_hotkey("record", "pressed"); c.handle_hotkey("record", "released")
    assert paster.pasted == [] and c.state is State.IDLE
    assert notes and "speech" in notes[0][1].lower()


def test_microphone_error_notifies_and_next_press_works():
    recorder = FakeRecorder(start_error=OSError("no mic"))
    c, _, notes, _ = build(recorder=recorder)
    c.handle_hotkey("record", "pressed")
    assert c.state is State.IDLE and "no mic" in notes[0][1]
    recorder.start_error = None
    c.handle_hotkey("record", "pressed")
    assert c.state is State.RECORDING


def test_transcription_error_notifies_and_returns_to_idle():
    c, _, notes, _ = build(transcriber=FakeTranscriber(error=RuntimeError("model broke")))
    c.handle_hotkey("record", "pressed"); c.handle_hotkey("record", "released")
    assert c.state is State.IDLE and "model broke" in notes[0][1]


def test_paste_error_notifies_and_returns_to_idle():
    c, _, notes, _ = build(paster=FakePaster(error=RuntimeError("clipboard locked")))
    c.handle_hotkey("record", "pressed"); c.handle_hotkey("record", "released")
    assert c.state is State.IDLE and "clipboard locked" in notes[0][1]


def test_recorder_stop_error_returns_to_idle():
    class BadStop(FakeRecorder):
        def stop(self): raise RuntimeError("stream died")
    c, _, notes, _ = build(recorder=BadStop())
    c.handle_hotkey("record", "pressed"); c.handle_hotkey("record", "released")
    assert c.state is State.IDLE and notes


def test_press_while_busy_is_ignored():
    c, _, _, jobs = build(deferred=True)
    c.handle_hotkey("record", "pressed"); c.handle_hotkey("record", "released")
    assert c.state is State.TRANSCRIBING
    c.handle_hotkey("record", "pressed")
    assert c.state is State.TRANSCRIBING
    assert len(jobs) == 1


def test_release_without_press_is_ignored():
    c, states, *_ = build()
    c.handle_hotkey("record", "released")
    assert states == [] and c.state is State.IDLE


def test_paste_shortcut_ignored_in_release_mode():
    paster = FakePaster()
    c, *_ = build(paster=paster)
    c.handle_hotkey("paste", "pressed")
    assert paster.pasted == []


def test_combo_mode_waits_for_paste_shortcut():
    paster = FakePaster()
    c, states, *_ = build(Config(stop_mode="combo"), paster=paster)
    c.handle_hotkey("record", "pressed"); c.handle_hotkey("record", "released")
    assert paster.pasted == [] and c.state is State.READY
    c.handle_hotkey("paste", "pressed")
    assert paster.pasted == ["hello world "] and c.state is State.IDLE


def test_combo_mode_paste_requested_during_transcription():
    paster = FakePaster()
    c, _, _, jobs = build(Config(stop_mode="combo"), paster=paster, deferred=True)
    c.handle_hotkey("record", "pressed"); c.handle_hotkey("record", "released")
    c.handle_hotkey("paste", "pressed")           # still transcribing
    assert paster.pasted == []
    jobs.pop(0)()                                 # transcription finishes
    assert paster.pasted == ["hello world "] and c.state is State.IDLE


def test_combo_mode_new_recording_replaces_pending_text():
    paster = FakePaster()
    t = FakeTranscriber()
    c, *_ = build(Config(stop_mode="combo"), paster=paster, transcriber=t)
    c.handle_hotkey("record", "pressed"); c.handle_hotkey("record", "released")
    t.text = "second"
    c.handle_hotkey("record", "pressed"); c.handle_hotkey("record", "released")
    c.handle_hotkey("paste", "pressed")
    assert paster.pasted == ["second "]


def test_combo_paste_with_nothing_pending_is_ignored():
    paster = FakePaster()
    c, *_ = build(Config(stop_mode="combo"), paster=paster)
    c.handle_hotkey("paste", "pressed")
    assert paster.pasted == [] and c.state is State.IDLE
```

- [ ] **Step 2: Run to verify failure**

Run: `poetry run pytest tests/test_controller.py -v`
Expected: FAIL (`ModuleNotFoundError`).

- [ ] **Step 3: Implement `controller.py`**

```python
"""Dictation flow as a small state machine. No Qt, no OS calls: everything is injected."""
from __future__ import annotations

import logging
import threading
from enum import Enum

from .audio import SAMPLE_RATE

log = logging.getLogger(__name__)

MIN_SECONDS = 0.3


class State(str, Enum):
    IDLE = "idle"
    RECORDING = "recording"
    TRANSCRIBING = "transcribing"
    READY = "ready"        # combo mode: text waits for the paste shortcut
    PASTING = "pasting"


def _run_in_thread(fn) -> None:
    threading.Thread(target=fn, name="dictation-worker", daemon=True).start()


class Controller:
    def __init__(self, *, get_config, recorder, transcriber, cleanup, paster,
                 notify, on_state, run_async=None):
        self._get_config = get_config
        self._recorder = recorder
        self._transcriber = transcriber
        self._cleanup = cleanup
        self._paster = paster
        self._notify = notify
        self._on_state = on_state
        self._run_async = run_async or _run_in_thread
        self._lock = threading.RLock()
        self._state = State.IDLE
        self._pending_text: str | None = None
        self._paste_requested = False

    @property
    def state(self) -> State:
        return self._state

    def _set(self, state: State) -> None:
        self._state = state
        self._on_state(state.value)

    def handle_hotkey(self, binding: str, kind: str) -> None:
        if binding == "record" and kind == "pressed":
            self._start_recording()
        elif binding == "record" and kind == "released":
            self._stop_recording()
        elif binding == "paste" and kind == "pressed":
            self._request_paste()

    # -- recording --------------------------------------------------------
    def _start_recording(self) -> None:
        with self._lock:
            if self._state not in (State.IDLE, State.READY):
                return
            self._pending_text = None
            try:
                self._recorder.start()
            except Exception as e:
                log.exception("microphone error")
                self._notify("Microphone error", str(e))
                self._set(State.IDLE)
                return
            self._set(State.RECORDING)

    def _stop_recording(self) -> None:
        with self._lock:
            if self._state is not State.RECORDING:
                return
            try:
                audio = self._recorder.stop()
            except Exception as e:
                log.exception("microphone error")
                self._notify("Microphone error", str(e))
                self._set(State.IDLE)
                return
            if len(audio) / SAMPLE_RATE < MIN_SECONDS:
                self._set(State.IDLE)
                return
            self._paste_requested = False
            config = self._get_config()
            self._set(State.TRANSCRIBING)
        self._run_async(lambda: self._transcribe(audio, config))

    # -- worker -----------------------------------------------------------
    def _transcribe(self, audio, config) -> None:
        try:
            text = self._transcriber.transcribe(audio, config.language)
        except Exception as e:
            log.exception("transcription failed")
            self._notify("Transcription failed", str(e))
            self._set(State.IDLE)
            return
        if not text:
            self._notify("Local Dictation", "No speech detected.")
            self._set(State.IDLE)
            return
        with self._lock:
            if config.stop_mode == "combo" and not self._paste_requested:
                self._pending_text = text
                self._set(State.READY)
                return
        self._finish(text, config)

    def _finish(self, text: str, config) -> None:
        self._set(State.PASTING)
        try:
            if config.cleanup_model:
                text = self._cleanup(text, config.cleanup_model)
            self._paster.paste(text + " ")
        except Exception as e:
            log.exception("paste failed")
            self._notify("Paste failed", str(e))
        self._set(State.IDLE)

    # -- combo mode -------------------------------------------------------
    def _request_paste(self) -> None:
        config = self._get_config()
        if config.stop_mode != "combo":
            return
        with self._lock:
            if self._state is State.TRANSCRIBING:
                self._paste_requested = True
                return
            if self._state is not State.READY or not self._pending_text:
                return
            text, self._pending_text = self._pending_text, None
            self._set(State.PASTING)
        self._run_async(lambda: self._finish(text, config))
```

- [ ] **Step 4: Run to verify pass**

Run: `poetry run pytest tests/test_controller.py -v`
Expected: all PASS. If `test_release_mode_full_flow...` shows an extra `"pasting"` state, that is correct behavior: `_finish` sets `PASTING` once, so the expected list is exactly `["recording", "transcribing", "pasting", "idle"]`; fix the code, not the test, if the order differs.

- [ ] **Step 5: Commit**

```bash
git add src/local_dictation/controller.py tests/test_controller.py
git commit -m "Add dictation controller state machine" -m "Co-Authored-By: Claude Sonnet 5.5 <noreply@anthropic.com>"
```

---

### Task 8: UI, startup registration and app wiring

**Files:**
- Create: `src/local_dictation/startup.py`, `src/local_dictation/ui/__init__.py`, `src/local_dictation/ui/tray.py`, `src/local_dictation/ui/settings.py`, `src/local_dictation/app.py`
- Test: `tests/test_startup.py`, `tests/test_settings_dialog.py`

**Interfaces:**
- Consumes: everything above. `WindowsHotkeyListener.begin_capture/cancel_capture` (4), `Config` (2), `Controller` (7).
- Produces:
  - `startup.set_enabled(enabled: bool, key_path: str = RUN_KEY) -> None`, `startup.is_enabled(key_path: str = RUN_KEY) -> bool`, `RUN_KEY`.
  - `SettingsDialog(config: Config, listener, parent=None)`: `.to_config() -> Config`; `accept()` refuses to close while `to_config().validate()` has errors.
  - `TrayIcon(QObject)`: signals `settings_requested`, `restart_requested`, `quit_requested`; methods `set_state(str)`, `set_model_status(str)`, `notify(title, message)`.
  - `app.main() -> int`.

- [ ] **Step 1: Write the failing tests**

`tests/test_startup.py`:
```python
import winreg

from local_dictation import startup

TEST_KEY = r"Software\LocalDictationTest\Run"


def teardown_function(_):
    for sub in (TEST_KEY, r"Software\LocalDictationTest"):
        try:
            winreg.DeleteKey(winreg.HKEY_CURRENT_USER, sub)
        except OSError:
            pass


def test_enable_disable_roundtrip():
    assert startup.is_enabled(TEST_KEY) is False
    startup.set_enabled(True, TEST_KEY)
    assert startup.is_enabled(TEST_KEY) is True
    startup.set_enabled(False, TEST_KEY)
    assert startup.is_enabled(TEST_KEY) is False


def test_disable_when_not_enabled_is_harmless():
    startup.set_enabled(False, TEST_KEY)


def test_command_uses_pythonw_and_module():
    cmd = startup.launch_command()
    assert cmd.lower().endswith("-m local_dictation")
    assert "pythonw" in cmd.lower()
```

`tests/test_settings_dialog.py`:
```python
import pytest
from PySide6.QtWidgets import QApplication

from local_dictation.config import Config
from local_dictation.shortcut import Shortcut
from local_dictation.ui.settings import SettingsDialog


@pytest.fixture(scope="module")
def qapp():
    return QApplication.instance() or QApplication([])


class FakeListener:
    def __init__(self):
        self.on_update = self.on_done = None
        self.cancelled = False

    def begin_capture(self, on_update, on_done):
        self.on_update, self.on_done = on_update, on_done

    def cancel_capture(self):
        self.cancelled = True


def test_roundtrip_of_all_fields(qapp):
    cfg = Config(record_shortcut="ctrl+alt+space", stop_mode="combo", paste_shortcut="f9",
                 model="small.en", device="cuda", language="ro", cleanup_model="qwen",
                 start_with_windows=True)
    assert SettingsDialog(cfg, FakeListener()).to_config() == cfg


def test_paste_shortcut_only_enabled_in_combo_mode(qapp):
    dlg = SettingsDialog(Config(), FakeListener())
    assert dlg.paste_edit.isEnabled() is False
    dlg.stop_mode_combo.setCurrentIndex(dlg.stop_mode_combo.findData("combo"))
    assert dlg.paste_edit.isEnabled() is True


def test_shortcut_capture_updates_value(qapp):
    listener = FakeListener()
    dlg = SettingsDialog(Config(), listener)
    dlg.record_edit.begin()
    listener.on_update("ctrl")
    listener.on_done(Shortcut.parse("ctrl+alt+space"))
    qapp.processEvents()
    assert dlg.record_edit.value() == "ctrl+alt+space"


def test_cancelled_capture_keeps_old_value(qapp):
    listener = FakeListener()
    dlg = SettingsDialog(Config(), listener)
    dlg.record_edit.begin()
    listener.on_done(None)
    qapp.processEvents()
    assert dlg.record_edit.value() == "ctrl+win"


def test_invalid_config_blocks_accept(qapp):
    dlg = SettingsDialog(Config(), FakeListener())
    dlg.record_edit.set_value("a")
    dlg.accept()
    assert dlg.result() == 0
    assert dlg.error_label.text() != ""
```

- [ ] **Step 2: Run to verify failure**

Run: `poetry run pytest tests/test_startup.py tests/test_settings_dialog.py -v`
Expected: FAIL (import errors).

- [ ] **Step 3: Implement `startup.py`**

```python
"""Start with Windows via the per-user Run registry key."""
from __future__ import annotations

import sys
import winreg
from pathlib import Path

RUN_KEY = r"Software\Microsoft\Windows\CurrentVersion\Run"
VALUE_NAME = "LocalDictation"


def launch_command() -> str:
    exe = Path(sys.executable)
    pythonw = exe.with_name("pythonw.exe")
    return f'"{pythonw if pythonw.exists() else exe}" -m local_dictation'


def is_enabled(key_path: str = RUN_KEY) -> bool:
    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, key_path) as key:
            winreg.QueryValueEx(key, VALUE_NAME)
            return True
    except OSError:
        return False


def set_enabled(enabled: bool, key_path: str = RUN_KEY) -> None:
    if enabled:
        with winreg.CreateKey(winreg.HKEY_CURRENT_USER, key_path) as key:
            winreg.SetValueEx(key, VALUE_NAME, 0, winreg.REG_SZ, launch_command())
        return
    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, key_path, 0, winreg.KEY_SET_VALUE) as key:
            winreg.DeleteValue(key, VALUE_NAME)
    except OSError:
        pass
```

Note: `test_command_uses_pythonw_and_module` requires `pythonw.exe` to exist next to the interpreter (true for the Poetry venv on Windows).

- [ ] **Step 4: Implement `ui/__init__.py` (empty file) and `ui/settings.py`**

```python
"""Settings dialog and the shortcut-capture widget."""
from __future__ import annotations

from PySide6.QtCore import QTimer, Signal
from PySide6.QtWidgets import (QCheckBox, QComboBox, QDialog, QDialogButtonBox, QFormLayout,
                               QHBoxLayout, QLabel, QLineEdit, QPushButton, QWidget)

from ..config import Config
from ..shortcut import Shortcut

CAPTURE_TIMEOUT_MS = 10_000
WHISPER_MODELS = ["tiny.en", "base.en", "small.en", "medium.en",
                  "tiny", "base", "small", "medium", "large-v3"]


class ShortcutEdit(QWidget):
    """Read-only field plus a Change button; capture runs through the global keyboard hook."""

    changed = Signal(str)
    _preview = Signal(str)
    _finished = Signal(object)

    def __init__(self, listener, value: str, parent=None):
        super().__init__(parent)
        self._listener = listener
        self._value = value
        self._field = QLineEdit(value)
        self._field.setReadOnly(True)
        self._button = QPushButton("Change…")
        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(self._field, 1)
        layout.addWidget(self._button)
        self._timer = QTimer(self)
        self._timer.setSingleShot(True)
        self._timer.setInterval(CAPTURE_TIMEOUT_MS)
        self._timer.timeout.connect(self._on_timeout)
        self._button.clicked.connect(self.begin)
        self._preview.connect(self._on_preview)
        self._finished.connect(self._on_finished)

    def value(self) -> str:
        return self._value

    def set_value(self, value: str) -> None:
        self._value = value
        self._field.setText(value)

    def begin(self) -> None:
        self._button.setEnabled(False)
        self._field.setText("Press the keys… (Esc cancels)")
        self._timer.start()
        # callbacks arrive on the hook thread; the signals marshal them to the UI thread
        self._listener.begin_capture(self._preview.emit, self._finished.emit)

    def _on_preview(self, text: str) -> None:
        self._field.setText(text or "Press the keys… (Esc cancels)")

    def _on_finished(self, shortcut: Shortcut | None) -> None:
        self._timer.stop()
        self._button.setEnabled(True)
        if shortcut is not None:
            self._value = shortcut.format()
            self.changed.emit(self._value)
        self._field.setText(self._value)

    def _on_timeout(self) -> None:
        self._listener.cancel_capture()
        self._on_finished(None)


class SettingsDialog(QDialog):
    def __init__(self, config: Config, listener, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Local Dictation — Settings")
        self.setMinimumWidth(460)

        self.record_edit = ShortcutEdit(listener, config.record_shortcut)
        self.stop_mode_combo = QComboBox()
        self.stop_mode_combo.addItem("Paste when I release the keys", "release")
        self.stop_mode_combo.addItem("Paste with a separate shortcut", "combo")
        self.stop_mode_combo.setCurrentIndex(self.stop_mode_combo.findData(config.stop_mode))
        self.paste_edit = ShortcutEdit(listener, config.paste_shortcut)
        self.model_combo = QComboBox()
        self.model_combo.setEditable(True)
        self.model_combo.addItems(WHISPER_MODELS)
        self.model_combo.setCurrentText(config.model)
        self.device_combo = QComboBox()
        self.device_combo.addItems(["cpu", "cuda"])
        self.device_combo.setCurrentText(config.device)
        self.language_edit = QLineEdit(config.language)
        self.language_edit.setPlaceholderText("auto-detect (e.g. en, ro, de)")
        self.cleanup_edit = QLineEdit(config.cleanup_model)
        self.cleanup_edit.setPlaceholderText("off (e.g. qwen2.5:1.5b via Ollama)")
        self.startup_check = QCheckBox("Start Local Dictation when I sign in to Windows")
        self.startup_check.setChecked(config.start_with_windows)
        self.error_label = QLabel()
        self.error_label.setStyleSheet("color: #c0392b;")
        self.error_label.setWordWrap(True)

        form = QFormLayout()
        form.addRow("Hold to talk", self.record_edit)
        form.addRow("When to paste", self.stop_mode_combo)
        form.addRow("Paste shortcut", self.paste_edit)
        form.addRow("Whisper model", self.model_combo)
        form.addRow("Device", self.device_combo)
        form.addRow("Language", self.language_edit)
        form.addRow("Cleanup model", self.cleanup_edit)
        form.addRow("", self.startup_check)
        form.addRow(self.error_label)
        buttons = QDialogButtonBox(QDialogButtonBox.Save | QDialogButtonBox.Cancel)
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        form.addRow(buttons)
        self.setLayout(form)

        self.stop_mode_combo.currentIndexChanged.connect(self._sync_enabled)
        self._sync_enabled()

    def _sync_enabled(self) -> None:
        self.paste_edit.setEnabled(self.stop_mode_combo.currentData() == "combo")

    def to_config(self) -> Config:
        return Config(
            record_shortcut=self.record_edit.value(),
            stop_mode=self.stop_mode_combo.currentData(),
            paste_shortcut=self.paste_edit.value(),
            model=self.model_combo.currentText().strip(),
            device=self.device_combo.currentText(),
            language=self.language_edit.text().strip(),
            cleanup_model=self.cleanup_edit.text().strip(),
            start_with_windows=self.startup_check.isChecked(),
        )

    def accept(self) -> None:
        errors = self.to_config().validate()
        if errors:
            self.error_label.setText("\n".join(errors))
            return
        super().accept()
```

- [ ] **Step 5: Implement `ui/tray.py`**

```python
"""Tray icon: colour shows state; menu opens settings, restarts the hotkey, quits."""
from __future__ import annotations

from PySide6.QtCore import QObject, Qt, Signal
from PySide6.QtGui import QAction, QColor, QIcon, QPainter, QPixmap
from PySide6.QtWidgets import QMenu, QSystemTrayIcon

STATE_COLORS = {
    "loading": "#9ca3af",
    "idle": "#6b7280",
    "recording": "#ef4444",
    "transcribing": "#f59e0b",
    "pasting": "#f59e0b",
    "ready": "#3b82f6",
}
STATE_TEXT = {
    "loading": "Loading speech model…",
    "idle": "Idle",
    "recording": "Recording…",
    "transcribing": "Transcribing…",
    "pasting": "Pasting…",
    "ready": "Text ready — press the paste shortcut",
}


def make_icon(color: str) -> QIcon:
    pixmap = QPixmap(64, 64)
    pixmap.fill(Qt.transparent)
    painter = QPainter(pixmap)
    painter.setRenderHint(QPainter.Antialiasing)
    painter.setBrush(QColor(color))
    painter.setPen(QColor("#111827"))
    painter.drawEllipse(6, 6, 52, 52)
    painter.end()
    return QIcon(pixmap)


class TrayIcon(QObject):
    settings_requested = Signal()
    restart_requested = Signal()
    quit_requested = Signal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self._tray = QSystemTrayIcon(make_icon(STATE_COLORS["loading"]))
        self._menu = QMenu()
        for text, signal in (("Settings…", self.settings_requested),
                             ("Restart hotkey", self.restart_requested),
                             ("Quit", self.quit_requested)):
            action = QAction(text, self._menu)
            action.triggered.connect(signal.emit)
            self._menu.addAction(action)
        self._tray.setContextMenu(self._menu)
        self._tray.activated.connect(self._on_activated)
        self._model_ready = False
        self.set_state("loading")
        self._tray.show()

    def _on_activated(self, reason) -> None:
        if reason == QSystemTrayIcon.DoubleClick:
            self.settings_requested.emit()

    def set_state(self, state: str) -> None:
        shown = state if self._model_ready or state != "idle" else "loading"
        self._tray.setIcon(make_icon(STATE_COLORS.get(shown, STATE_COLORS["idle"])))
        self._tray.setToolTip(f"Local Dictation — {STATE_TEXT.get(shown, shown)}")

    def set_model_status(self, status: str) -> None:
        if status == "loading":
            self._model_ready = False
            self.set_state("loading")
        elif status == "ready":
            self._model_ready = True
            self.set_state("idle")
            self.notify("Local Dictation", "Ready. Hold your shortcut and speak.")
        else:
            self._model_ready = False
            self.notify("Speech model problem", status)

    def notify(self, title: str, message: str) -> None:
        self._tray.showMessage(title, message, QSystemTrayIcon.Information, 4000)
```

- [ ] **Step 6: Implement `app.py`**

```python
"""Application wiring: logging, single instance, tray, hotkey, controller."""
from __future__ import annotations

import ctypes
import logging
import logging.handlers
import sys

from PySide6.QtCore import QObject, Signal
from PySide6.QtWidgets import QApplication, QDialog

from . import startup
from .audio import Recorder
from .cleanup import ollama_cleanup
from .config import Config, ConfigStore, default_config_path
from .controller import Controller
from .hotkey import WindowsHotkeyListener
from .paste import Paster
from .transcribe import Transcriber
from .ui.settings import SettingsDialog
from .ui.tray import TrayIcon

log = logging.getLogger("local_dictation")
_mutex_handle = None  # keep the mutex alive for the life of the process


def setup_logging() -> None:
    log_dir = default_config_path().parent
    log_dir.mkdir(parents=True, exist_ok=True)
    handlers: list[logging.Handler] = [
        logging.handlers.RotatingFileHandler(log_dir / "dictation.log", maxBytes=500_000,
                                             backupCount=2, encoding="utf-8")
    ]
    if sys.stderr is not None:
        handlers.append(logging.StreamHandler())
    logging.basicConfig(level=logging.INFO, handlers=handlers,
                        format="%(asctime)s %(levelname)s %(name)s: %(message)s")


def acquire_single_instance() -> bool:
    global _mutex_handle
    kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
    _mutex_handle = kernel32.CreateMutexW(None, False, "Local\\LocalDictationSingleton")
    return ctypes.get_last_error() != 183  # ERROR_ALREADY_EXISTS


class Bridge(QObject):
    """Turns callbacks from worker threads into queued Qt signals."""
    state_changed = Signal(str)
    notified = Signal(str, str)
    model_status = Signal(str)


def main() -> int:
    setup_logging()
    if not acquire_single_instance():
        log.warning("Local Dictation is already running")
        return 1

    qapp = QApplication(sys.argv)
    qapp.setQuitOnLastWindowClosed(False)

    store = ConfigStore()
    bridge = Bridge()
    tray = TrayIcon()
    listener = WindowsHotkeyListener()
    transcriber = Transcriber(on_status=bridge.model_status.emit)
    controller = Controller(
        get_config=lambda: store.config,
        recorder=Recorder(),
        transcriber=transcriber,
        cleanup=ollama_cleanup,
        paster=Paster(),
        notify=bridge.notified.emit,
        on_state=bridge.state_changed.emit,
    )
    bridge.state_changed.connect(tray.set_state)
    bridge.notified.connect(tray.notify)
    bridge.model_status.connect(tray.set_model_status)
    listener.set_handler(controller.handle_hotkey)

    def apply_runtime(new: Config, previous: Config | None) -> None:
        if previous is None or (new.model, new.device) != (previous.model, previous.device):
            transcriber.configure(new.model, new.device)
        listener.set_bindings(new.bindings())
        startup.set_enabled(new.start_with_windows)

    def start_listener() -> None:
        try:
            listener.start()
        except RuntimeError as e:
            log.exception("hotkey failed to start")
            tray.notify("Hotkey error", str(e))

    def restart_listener() -> None:
        listener.stop()
        listener.set_bindings(store.config.bindings())
        start_listener()

    dialog_open = False

    def open_settings() -> None:
        nonlocal dialog_open
        if dialog_open:
            return
        dialog_open = True
        try:
            dialog = SettingsDialog(store.config, listener)
            if dialog.exec() == QDialog.Accepted:
                previous, new = store.config, dialog.to_config()
                store.update(new)
                apply_runtime(new, previous)
        finally:
            dialog_open = False

    def quit_app() -> None:
        listener.stop()
        qapp.quit()

    tray.settings_requested.connect(open_settings)
    tray.restart_requested.connect(restart_listener)
    tray.quit_requested.connect(quit_app)

    apply_runtime(store.config, None)
    start_listener()
    log.info("Local Dictation started (shortcut: %s)", store.config.record_shortcut)
    return qapp.exec()
```

- [ ] **Step 7: Run all automated tests**

Run: `poetry run pytest -v`
Expected: every test PASSES (startup tests write and delete a temporary registry key under `HKCU\Software\LocalDictationTest`).

- [ ] **Step 8: Launch the app for real**

Run: `poetry run local-dictation`
Expected: tray icon appears (grey, "Loading speech model…"), then a "Ready" notification and a grey idle icon. Right-click → Settings… opens the dialog. Quit exits cleanly. If it crashes at startup, read `%APPDATA%\LocalDictation\dictation.log`.

- [ ] **Step 9: Commit**

```bash
git add src/local_dictation/startup.py src/local_dictation/ui src/local_dictation/app.py tests
git commit -m "Add tray UI, settings dialog, startup registration and app wiring" -m "Co-Authored-By: Claude Sonnet 5.5 <noreply@anthropic.com>"
```

---

### Task 9: Retire the old script, final docs, manual verification

**Files:**
- Delete: `dictate.py`, `run.bat`, `requirements.txt`
- Modify: `README.md`, `docs/architecture.md` (only if module names drifted), `docs/decisions.md` (record the working `MASK_VK` from Task 4)

**Interfaces:** none (cleanup and verification).

- [ ] **Step 1: Run the manual checklist**

Work through every item in `docs/manual-test-checklist.md` with the real app running (`poetry run local-dictation`). For any failure, stop and use superpowers:systematic-debugging before changing code; add a regression test where one is possible.

- [ ] **Step 2: Remove the legacy files**

```bash
git rm dictate.py run.bat requirements.txt
```

- [ ] **Step 3: Rewrite `README.md`**

```markdown
# Local Dictation

Offline push-to-talk dictation for Windows, similar to Wispr Flow. Speech is transcribed on your own machine with [faster-whisper](https://github.com/SYSTRAN/faster-whisper); nothing is sent to an online service.

Hold **Ctrl+Win**, speak, release: the text is pasted into whatever control has keyboard focus (Notepad, VS Code, GitHub Copilot chat, ...).

## Install and run

Requires Python 3.11+ and [Poetry](https://python-poetry.org/).

```
poetry install
poetry run local-dictation                      # with a console, for debugging
.venv\Scripts\pythonw.exe -m local_dictation    # no console window
```

The Whisper model downloads on first launch. A tray icon shows the state; right-click it for **Settings…**, **Restart hotkey** and **Quit**.

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
```

- [ ] **Step 4: Verify docs match the code**

Check that every module listed in `docs/architecture.md` exists under `src/local_dictation/` and vice versa; update the doc if not. Record the verified `MASK_VK` value and the Task 4 manual-test outcome in `docs/decisions.md`.

- [ ] **Step 5: Final run and commit**

Run: `poetry run pytest -v` → all PASS. Then:

```bash
git add -A
git commit -m "Retire legacy script, update README and docs" -m "Co-Authored-By: Claude Sonnet 5.5 <noreply@anthropic.com>"
```

---

## Self-Review (done while writing)

- **Spec coverage:** Poetry migration → T1; tray + settings UI (shortcut, stop mode, model, device, language, cleanup, startup) → T8; swallowed Ctrl+Win with Start-menu mask → T3b/T4; release and combo stop modes → T7; paste at focused control → T6/T7; failures surfaced via tray notifications → T7/T8; config in `%APPDATA%` → T2; tests → every task, plus manual checklist → T1/T9; knowledge base (`CLAUDE.md`, `docs/*`) → T1/T9; installer left for later (layout supports it). Open items from the spec: wheel availability → T1 step 5; mask key → T4 step 6.
- **Order dependency:** `config.py` imports `shortcut.py`, so execute **3a → 2 → 3b → 4 → 5 → 6 → 7 → 8 → 9**.
- **Type consistency:** `Decision/PASS`, `ShortcutMatcher.on_key/prune/set_bindings/reset`, `ShortcutCapture.on_key/preview`, `EventDispatcher.set_handler/start/stop/submit`, `WindowsHotkeyListener.set_handler/set_bindings/start/stop/begin_capture/cancel_capture`, `Controller.handle_hotkey`, `Transcriber.configure/transcribe(audio, language)`, `Paster.paste`, `Config.bindings/validate` are used with identical names across tasks.
- **Placeholders:** none; the only conditional step is the empirical `MASK_VK` check, with a concrete fallback.
