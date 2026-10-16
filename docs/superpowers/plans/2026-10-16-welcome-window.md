# First-run Welcome Window Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Show a welcome window on first launch that teaches the hold-to-talk gesture, lets the user change the shortcut, and shows when the speech model is ready; reopenable from the tray.

**Architecture:** A new non-modal `WelcomeWindow` (PySide6) in `ui/welcome.py`, styled by a small `ui/theme.py`. Pure logic (`keycaps`) lives in `shortcut.py`; persistence is one new config flag. `app.py` wires it: first-run check, shortcut save via a testable helper, and model status from the existing `Bridge.model_status` signal.

**Tech Stack:** Python 3.11+, PySide6, pytest (Qt tests run offscreen via `tests/conftest.py`).

**Spec:** `docs/superpowers/specs/2026-10-16-welcome-window-design.md`

## Global Constraints

- Local only: no network except `http://localhost:11434` (Ollama) and the one-time model download.
- The keyboard hook callback must never block; it only enqueues events. This plan does not touch `hotkey.py`.
- Pure logic (shortcut matching, controller, config) stays free of OS/Qt imports so it is unit-testable.
- Any change to architecture or behavior updates the relevant file in `docs/` in the same commit.
- Branch: `feature/welcome-window` (from `develop`). Commit messages end with `Co-Authored-By: Claude Sonnet 5.5 <noreply@anthropic.com>`.
- Run tests with `poetry run pytest`.

## Review Focus

1. A config file written by an older version has no `welcome_shown` key: it must load as `False` (the user sees the window once) and not be treated as invalid. Pinned in Task 2.
2. Saving the Settings dialog rebuilds a `Config` from its fields: it must not reset `welcome_shown` to `False` (that would re-show the window after every settings save). Pinned in Task 2.
3. Opening the window when the model already failed to load: it must show the error state immediately, not "loading". Pinned in Task 3.
4. Changing the shortcut to something invalid (for example a bare letter): nothing is saved, the old shortcut stays, and the window shows the message. Pinned in Task 5.
5. Closing the window while a shortcut capture is in progress must cancel the capture, or the global hook stays in capture mode and swallows keys. Pinned in Task 3.
6. Empty or odd shortcut text (empty string, `vk5d`) must not crash the keycap row. Pinned in Task 1.

## File Structure

| File | Change | Responsibility |
|---|---|---|
| `src/local_dictation/shortcut.py` | modify | add pure `keycaps()` |
| `src/local_dictation/config.py` | modify | add `welcome_shown` field |
| `src/local_dictation/ui/settings.py` | modify | `to_config` keeps fields the dialog does not edit |
| `src/local_dictation/ui/theme.py` | create | colour tokens, `is_dark`, `stylesheet` |
| `src/local_dictation/ui/welcome.py` | create | `KeycapRow`, `WelcomeWindow` |
| `src/local_dictation/ui/tray.py` | modify | "How to use…" action, `welcome_requested`, `model_status` attribute |
| `src/local_dictation/app.py` | modify | `apply_shortcut_change`, welcome wiring, first-run check |
| `tests/test_shortcut.py`, `tests/test_config.py`, `tests/test_settings_dialog.py`, `tests/test_app_startup.py` | modify | new tests |
| `tests/test_theme.py`, `tests/test_welcome.py`, `tests/test_tray.py` | create | new tests |
| `docs/*`, `README.md` | modify | Task 6 |

---

### Task 1: `keycaps` helper

**Files:**
- Modify: `src/local_dictation/shortcut.py` (add after `Shortcut`)
- Test: `tests/test_shortcut.py`

**Interfaces:**
- Produces: `keycaps(text: str) -> list[str]`: display labels in modifier-first order; `[]` for empty or unparsable text.

- [ ] **Step 1: Write the failing tests** (append to `tests/test_shortcut.py`; add `keycaps` to its imports from `local_dictation.shortcut`)

```python
def test_keycaps_modifiers_use_canonical_order():
    assert keycaps("win+ctrl") == ["Ctrl", "Win"]
    assert keycaps("ctrl+shift+space") == ["Ctrl", "Shift", "Space"]


def test_keycaps_function_and_letter_keys():
    assert keycaps("f9") == ["F9"]
    assert keycaps("ctrl+alt+a") == ["Ctrl", "Alt", "A"]


def test_keycaps_empty_and_unknown_do_not_crash():
    assert keycaps("") == []
    assert keycaps("  ") == []
    assert keycaps("ctrl+vk5d") == ["Ctrl", "Vk5d"]
```

- [ ] **Step 2: Run to verify failure**

Run: `poetry run pytest tests/test_shortcut.py -k keycaps -v`
Expected: FAIL (ImportError: cannot import name `keycaps`).

- [ ] **Step 3: Implement** (in `shortcut.py`, below the `Shortcut` class)

```python
def keycaps(text: str) -> list[str]:
    """Display labels for a shortcut string, modifiers first ("ctrl+win" -> ["Ctrl", "Win"])."""
    try:
        names = Shortcut.parse(text).format().split("+")
    except ValueError:
        return []
    return [n.upper() if n.startswith("f") and n[1:].isdigit() else n.title() for n in names]
```

- [ ] **Step 4: Run to verify pass**

Run: `poetry run pytest tests/test_shortcut.py -v`
Expected: all PASS.

- [ ] **Step 5: Commit**

```bash
git add src/local_dictation/shortcut.py tests/test_shortcut.py
git commit -m "Add keycaps() display helper for shortcuts

Co-Authored-By: Claude Sonnet 5.5 <noreply@anthropic.com>"
```

---

### Task 2: `welcome_shown` config flag

**Files:**
- Modify: `src/local_dictation/config.py` (`Config`), `src/local_dictation/ui/settings.py` (`SettingsDialog`)
- Test: `tests/test_config.py`, `tests/test_settings_dialog.py`

**Interfaces:**
- Produces: `Config.welcome_shown: bool = False`. `SettingsDialog.to_config()` preserves it.

- [ ] **Step 1: Write the failing tests**

Append to `tests/test_config.py` (it already imports `Config`, `ConfigStore`; add `import json` if absent):

```python
def test_welcome_shown_defaults_false_and_roundtrips(tmp_path):
    store = ConfigStore(tmp_path / "config.json")
    assert store.config.welcome_shown is False
    store.update(Config(welcome_shown=True))
    assert ConfigStore(tmp_path / "config.json").config.welcome_shown is True


def test_config_file_from_older_version_is_still_valid(tmp_path):
    path = tmp_path / "config.json"
    path.write_text(json.dumps({"record_shortcut": "f9", "model": "small.en"}), encoding="utf-8")
    cfg = ConfigStore(path).config
    assert cfg.record_shortcut == "f9" and cfg.model == "small.en"
    assert cfg.welcome_shown is False
```

Append to `tests/test_settings_dialog.py`:

```python
def test_saving_settings_keeps_welcome_shown(qapp):
    cfg = Config(welcome_shown=True)
    assert SettingsDialog(cfg, FakeListener()).to_config().welcome_shown is True
```

- [ ] **Step 2: Run to verify failure**

Run: `poetry run pytest tests/test_config.py tests/test_settings_dialog.py -v`
Expected: the three new tests FAIL (`welcome_shown` unknown / TypeError).

- [ ] **Step 3: Implement**

In `config.py` add as the last field of `Config`:

```python
    welcome_shown: bool = False
```

In `ui/settings.py`: change the import line `from PySide6.QtCore import QTimer, Signal` area to also have `from dataclasses import replace` (stdlib import at the top, before the PySide6 imports). In `SettingsDialog.__init__`, first line after `super().__init__(parent)` add `self._config = config`. Replace the body of `to_config` so it starts from the stored config:

```python
    def to_config(self) -> Config:
        return replace(
            self._config,
            record_shortcut=self.record_edit.value(),
            stop_mode=self.stop_mode_combo.currentData(),
            paste_shortcut=self.paste_edit.value(),
            model=self.model_combo.currentText().strip(),
            device=self.device_combo.currentText(),
            language=self.language_edit.text().strip(),
            cleanup_model=self.cleanup_edit.text().strip(),
            start_with_windows=self.startup_check.isChecked(),
        )
```

- [ ] **Step 4: Run to verify pass**

Run: `poetry run pytest tests/test_config.py tests/test_settings_dialog.py -v`
Expected: all PASS (including the existing round-trip test).

- [ ] **Step 5: Commit**

```bash
git add src/local_dictation/config.py src/local_dictation/ui/settings.py tests/test_config.py tests/test_settings_dialog.py
git commit -m "Add welcome_shown config flag; Settings keeps fields it does not edit

Co-Authored-By: Claude Sonnet 5.5 <noreply@anthropic.com>"
```

---

### Task 3: Theme and `WelcomeWindow`

**Files:**
- Create: `src/local_dictation/ui/theme.py`, `src/local_dictation/ui/welcome.py`
- Test: `tests/test_theme.py`, `tests/test_welcome.py`

**Interfaces:**
- Consumes: `keycaps(text) -> list[str]` (Task 1); `ShortcutEdit(listener, value)` from `ui/settings.py` with `.changed` signal, `.set_value()`, `.cancel()`, `.begin()`.
- Produces:
  - `theme.is_dark(palette: QPalette) -> bool`
  - `theme.stylesheet(dark: bool) -> str`
  - `WelcomeWindow(record_shortcut: str, listener, status: str = "loading", parent=None)` with:
    - signal `shortcut_changed(str)`
    - `set_status(status: str)`, where status is `"loading"`, `"ready"`, or `"error: <detail>"` (any other string is treated as an error)
    - `set_shortcut(value: str)`: updates the field and keycaps and clears any message
    - `show_error(message: str)`
    - attributes used by tests: `status_label`, `progress`, `error_label`, `keycap_row.keys()`, `shortcut_edit`

- [ ] **Step 1: Write the failing tests**

`tests/test_theme.py`:

```python
from PySide6.QtGui import QColor, QPalette

from local_dictation.ui import theme


def test_is_dark_follows_window_colour():
    dark, light = QPalette(), QPalette()
    dark.setColor(QPalette.Window, QColor("#202020"))
    light.setColor(QPalette.Window, QColor("#f5f5f5"))
    assert theme.is_dark(dark) is True
    assert theme.is_dark(light) is False


def test_stylesheet_differs_between_modes_and_styles_keycaps():
    assert theme.stylesheet(True) != theme.stylesheet(False)
    assert "keycap" in theme.stylesheet(False)
```

`tests/test_welcome.py`:

```python
import pytest
from PySide6.QtWidgets import QApplication

from local_dictation.shortcut import Shortcut
from local_dictation.ui.welcome import WelcomeWindow


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


def test_shows_keycaps_for_the_shortcut(qapp):
    win = WelcomeWindow("ctrl+win", FakeListener())
    assert win.keycap_row.keys() == ["Ctrl", "Win"]


def test_status_loading_ready_and_back(qapp):
    win = WelcomeWindow("ctrl+win", FakeListener())
    assert not win.progress.isHidden()
    assert "Preparing" in win.status_label.text()
    win.set_status("ready")
    assert win.progress.isHidden()
    assert "Ready" in win.status_label.text()
    win.set_status("loading")
    assert not win.progress.isHidden()


def test_opening_when_model_already_failed_shows_error(qapp):
    win = WelcomeWindow("ctrl+win", FakeListener(), status="error: out of memory")
    assert win.progress.isHidden()
    assert "out of memory" in win.status_label.text()
    assert "error: " not in win.status_label.text()


def test_unknown_status_is_shown_as_error(qapp):
    win = WelcomeWindow("ctrl+win", FakeListener(), status="boom")
    assert "boom" in win.status_label.text()
    assert win.progress.isHidden()


def test_capturing_a_new_shortcut_emits_signal(qapp):
    listener = FakeListener()
    win = WelcomeWindow("ctrl+win", listener)
    seen = []
    win.shortcut_changed.connect(seen.append)
    win.shortcut_edit.begin()
    listener.on_done(Shortcut.parse("ctrl+alt+space"))
    qapp.processEvents()
    assert seen == ["ctrl+alt+space"]


def test_set_shortcut_updates_keycaps_and_clears_error(qapp):
    win = WelcomeWindow("ctrl+win", FakeListener())
    win.show_error("nope")
    assert win.error_label.text() == "nope"
    win.set_shortcut("f9")
    assert win.keycap_row.keys() == ["F9"]
    assert win.shortcut_edit.value() == "f9"
    assert win.error_label.text() == ""


def test_empty_shortcut_does_not_crash(qapp):
    win = WelcomeWindow("", FakeListener())
    assert win.keycap_row.keys() == []


def test_closing_during_capture_cancels_it(qapp):
    listener = FakeListener()
    win = WelcomeWindow("ctrl+win", listener)
    win.shortcut_edit.begin()
    win.close()
    assert listener.cancelled is True


def test_closing_without_capture_does_not_cancel(qapp):
    listener = FakeListener()
    WelcomeWindow("ctrl+win", listener).close()
    assert listener.cancelled is False
```

- [ ] **Step 2: Run to verify failure**

Run: `poetry run pytest tests/test_theme.py tests/test_welcome.py -v`
Expected: FAIL (ModuleNotFoundError: `local_dictation.ui.theme` / `welcome`).

- [ ] **Step 3: Implement `ui/theme.py`**

```python
"""Colour tokens and the shared stylesheet; light or dark follows the system palette."""
from __future__ import annotations

from PySide6.QtGui import QPalette

LIGHT = {"bg": "#ffffff", "text": "#111827", "muted": "#6b7280", "keycap_bg": "#f3f4f6",
         "keycap_border": "#d1d5db", "accent": "#2563eb", "ok": "#15803d", "error": "#b91c1c"}
DARK = {"bg": "#1f2937", "text": "#f3f4f6", "muted": "#9ca3af", "keycap_bg": "#374151",
        "keycap_border": "#4b5563", "accent": "#60a5fa", "ok": "#4ade80", "error": "#f87171"}


def is_dark(palette: QPalette) -> bool:
    return palette.color(QPalette.Window).lightness() < 128


def stylesheet(dark: bool) -> str:
    c = DARK if dark else LIGHT
    return f"""
QWidget {{ background: {c['bg']}; color: {c['text']}; font-size: 10pt; }}
QLabel#headline {{ font-size: 18pt; font-weight: 600; }}
QLabel#howto, QLabel#hint {{ color: {c['muted']}; }}
QLabel#keycap {{ background: {c['keycap_bg']}; border: 1px solid {c['keycap_border']};
    border-bottom-width: 3px; border-radius: 6px; padding: 8px 16px;
    font-size: 14pt; font-weight: 600; }}
QLabel#plus {{ color: {c['muted']}; font-size: 14pt; }}
QLabel#status[state="ready"] {{ color: {c['ok']}; font-weight: 600; }}
QLabel#status[state="error"], QLabel#error {{ color: {c['error']}; }}
QProgressBar {{ border: none; background: {c['keycap_bg']}; height: 6px; border-radius: 3px; }}
QProgressBar::chunk {{ background: {c['accent']}; border-radius: 3px; }}
QPushButton {{ padding: 6px 16px; }}
QPushButton#primary {{ background: {c['accent']}; color: #ffffff; border: none;
    border-radius: 6px; padding: 8px 24px; font-weight: 600; }}
"""
```

- [ ] **Step 4: Implement `ui/welcome.py`**

```python
"""First-run welcome window: how to dictate, change the shortcut, model status."""
from __future__ import annotations

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (QHBoxLayout, QLabel, QProgressBar, QPushButton, QVBoxLayout,
                               QWidget)

from ..shortcut import keycaps
from . import theme
from .settings import ShortcutEdit

_ERROR_HINT = "Open Settings to choose another model, or use tray → Restart hotkey."


class KeycapRow(QWidget):
    """Keys drawn as keycaps with "+" between them."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self._layout = QHBoxLayout(self)
        self._layout.setAlignment(Qt.AlignCenter)
        self._keys: list[str] = []

    def keys(self) -> list[str]:
        return list(self._keys)

    def set_keys(self, keys: list[str]) -> None:
        self._keys = list(keys)
        while self._layout.count():
            self._layout.takeAt(0).widget().deleteLater()
        for i, key in enumerate(keys):
            if i:
                plus = QLabel("+")
                plus.setObjectName("plus")
                self._layout.addWidget(plus)
            cap = QLabel(key)
            cap.setObjectName("keycap")
            self._layout.addWidget(cap)


class WelcomeWindow(QWidget):
    shortcut_changed = Signal(str)

    def __init__(self, record_shortcut: str, listener, status: str = "loading", parent=None):
        super().__init__(parent)
        self.setWindowTitle("Welcome to Local Dictation")
        self.setFixedWidth(480)
        self.setStyleSheet(theme.stylesheet(theme.is_dark(self.palette())))

        headline = QLabel("Dictate anywhere. Fully offline.")
        headline.setObjectName("headline")
        self.keycap_row = KeycapRow()
        howto = QLabel("Hold, speak, release. Your words are pasted where your cursor is.")
        howto.setObjectName("howto")
        howto.setWordWrap(True)
        howto.setAlignment(Qt.AlignCenter)
        hint = QLabel("Hold to talk shortcut")
        hint.setObjectName("hint")
        self.shortcut_edit = ShortcutEdit(listener, record_shortcut)
        self.shortcut_edit.changed.connect(self.shortcut_changed)
        self.error_label = QLabel()
        self.error_label.setObjectName("error")
        self.error_label.setWordWrap(True)
        self.progress = QProgressBar()
        self.progress.setRange(0, 0)
        self.progress.setTextVisible(False)
        self.status_label = QLabel()
        self.status_label.setObjectName("status")
        self.status_label.setWordWrap(True)
        done = QPushButton("Got it")
        done.setObjectName("primary")
        done.clicked.connect(self.close)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(32, 28, 32, 24)
        layout.setSpacing(14)
        layout.addWidget(headline)
        layout.addWidget(self.keycap_row)
        layout.addWidget(howto)
        layout.addSpacing(6)
        layout.addWidget(hint)
        layout.addWidget(self.shortcut_edit)
        layout.addWidget(self.error_label)
        layout.addSpacing(6)
        layout.addWidget(self.progress)
        layout.addWidget(self.status_label)
        layout.addSpacing(6)
        layout.addWidget(done, alignment=Qt.AlignRight)

        self.set_shortcut(record_shortcut)
        self.set_status(status)

    def set_shortcut(self, value: str) -> None:
        self.shortcut_edit.set_value(value)
        self.keycap_row.set_keys(keycaps(value))
        self.error_label.setText("")

    def show_error(self, message: str) -> None:
        self.error_label.setText(message)

    def set_status(self, status: str) -> None:
        if status == "loading":
            state, text = "loading", "Preparing the speech model…"
        elif status == "ready":
            state, text = "ready", "Ready. Try it now."
        else:
            detail = status[len("error: "):] if status.startswith("error: ") else status
            state = "error"
            text = f"The speech model could not be loaded: {detail}\n{_ERROR_HINT}"
        self.progress.setVisible(state == "loading")
        self.status_label.setText(text)
        self.status_label.setProperty("state", state)
        self.status_label.style().unpolish(self.status_label)
        self.status_label.style().polish(self.status_label)

    def closeEvent(self, event) -> None:
        self.shortcut_edit.cancel()  # never leave the global hook in capture mode
        super().closeEvent(event)
```

- [ ] **Step 5: Run to verify pass**

Run: `poetry run pytest tests/test_theme.py tests/test_welcome.py -v`
Expected: all PASS. (`progress.isHidden()` is used because the window is never shown in tests.) If `setVisible(True)` on a child of a hidden window makes `isHidden()` still report False, that is the expected "not explicitly hidden" state.

- [ ] **Step 6: Commit**

```bash
git add src/local_dictation/ui/theme.py src/local_dictation/ui/welcome.py tests/test_theme.py tests/test_welcome.py
git commit -m "Add WelcomeWindow and shared theme

Co-Authored-By: Claude Sonnet 5.5 <noreply@anthropic.com>"
```

---

### Task 4: Tray menu item and model status attribute

**Files:**
- Modify: `src/local_dictation/ui/tray.py`
- Test: `tests/test_tray.py` (create)

**Interfaces:**
- Produces: `TrayIcon.welcome_requested` signal; menu action "How to use…" first in the menu; `TrayIcon.model_status: str` (`"loading"` initially; set by `set_model_status` to `"loading"`, `"ready"`, or the raw `status` string such as `"error: …"`).

- [ ] **Step 1: Write the failing tests** (`tests/test_tray.py`)

```python
import pytest
from PySide6.QtWidgets import QApplication

from local_dictation.ui.tray import TrayIcon


@pytest.fixture(scope="module")
def qapp():
    return QApplication.instance() or QApplication([])


def test_menu_has_how_to_use_first_and_it_emits(qapp):
    tray = TrayIcon()
    actions = tray._menu.actions()
    assert [a.text() for a in actions] == ["How to use…", "Settings…", "Restart hotkey", "Quit"]
    seen = []
    tray.welcome_requested.connect(lambda: seen.append(True))
    actions[0].trigger()
    assert seen == [True]


def test_model_status_is_remembered(qapp):
    tray = TrayIcon()
    assert tray.model_status == "loading"
    tray.set_model_status("ready")
    assert tray.model_status == "ready"
    tray.set_model_status("error: boom")
    assert tray.model_status == "error: boom"
    tray.set_model_status("loading")
    assert tray.model_status == "loading"
```

- [ ] **Step 2: Run to verify failure**

Run: `poetry run pytest tests/test_tray.py -v`
Expected: FAIL (menu texts differ / no `model_status`).

- [ ] **Step 3: Implement** in `ui/tray.py`

Add the signal next to the others: `welcome_requested = Signal()`. Change the menu tuple to start with `("How to use…", self.welcome_requested),`. In `__init__`, before `self.set_state("loading")`, add `self.model_status = "loading"`. At the top of `set_model_status`, add `self.model_status = status`.

- [ ] **Step 4: Run to verify pass**

Run: `poetry run pytest tests/test_tray.py -v`
Expected: PASS. If the offscreen platform cannot create `QSystemTrayIcon`, stop and report; do not skip the test silently.

- [ ] **Step 5: Commit**

```bash
git add src/local_dictation/ui/tray.py tests/test_tray.py
git commit -m "Tray: How to use… action; remember model status

Co-Authored-By: Claude Sonnet 5.5 <noreply@anthropic.com>"
```

---

### Task 5: Wire into the app

**Files:**
- Modify: `src/local_dictation/app.py`
- Test: `tests/test_app_startup.py`

**Interfaces:**
- Consumes: `WelcomeWindow` (Task 3), `TrayIcon.welcome_requested` / `.model_status` (Task 4), `Config.welcome_shown` (Task 2).
- Produces: `apply_shortcut_change(store, value: str, apply_runtime) -> list[str]`: returns error messages; on success the config is saved and `apply_runtime(new, previous)` has been called; on any error nothing is saved and `apply_runtime` is not called.

- [ ] **Step 1: Write the failing tests** (append to `tests/test_app_startup.py`; add `from local_dictation.app import apply_shortcut_change` and `from local_dictation.config import ConfigStore`)

```python
def test_apply_shortcut_change_saves_and_applies(tmp_path):
    store = ConfigStore(tmp_path / "config.json")
    calls = []
    errors = apply_shortcut_change(store, "ctrl+alt+space", lambda new, prev: calls.append((new, prev)))
    assert errors == []
    assert store.config.record_shortcut == "ctrl+alt+space"
    assert ConfigStore(tmp_path / "config.json").config.record_shortcut == "ctrl+alt+space"
    assert calls[0][0].record_shortcut == "ctrl+alt+space"
    assert calls[0][1].record_shortcut == "ctrl+win"


def test_apply_shortcut_change_rejects_unsafe_shortcut(tmp_path):
    store = ConfigStore(tmp_path / "config.json")
    calls = []
    errors = apply_shortcut_change(store, "a", lambda new, prev: calls.append(1))
    assert errors != []
    assert store.config.record_shortcut == "ctrl+win"
    assert calls == []
    assert not (tmp_path / "config.json").exists()


def test_apply_shortcut_change_reports_save_failure(tmp_path):
    store = ConfigStore(tmp_path / "config.json")

    def boom(cfg):
        raise OSError("disk full")

    store.update = boom
    calls = []
    errors = apply_shortcut_change(store, "f9", lambda new, prev: calls.append(1))
    assert errors and "disk full" in errors[0]
    assert store.config.record_shortcut == "ctrl+win"
    assert calls == []
```

- [ ] **Step 2: Run to verify failure**

Run: `poetry run pytest tests/test_app_startup.py -v`
Expected: FAIL (ImportError `apply_shortcut_change`).

- [ ] **Step 3: Implement in `app.py`**

Add `from dataclasses import replace` to the stdlib imports and `from .ui.welcome import WelcomeWindow` next to the other `.ui` imports. Below `apply_startup` add:

```python
def apply_shortcut_change(store, value: str, apply_runtime) -> list[str]:
    """Save a new record shortcut; returns error messages (nothing is saved or applied then)."""
    previous = store.config
    new = replace(previous, record_shortcut=value)
    errors = new.validate()
    if errors:
        return errors
    try:
        store.update(new)
    except OSError as e:
        log.exception("could not save the new shortcut")
        return [f"Could not save the shortcut: {e}"]
    apply_runtime(new, previous)
    return []
```

In `main()`, after the existing `dialog_open = False` / `open_settings` block and before `quit_app`, add:

```python
    welcome: WelcomeWindow | None = None

    def on_welcome_shortcut(value: str) -> None:
        errors = apply_shortcut_change(store, value, apply_runtime)
        welcome.set_shortcut(store.config.record_shortcut)  # also clears any old message
        if errors:
            welcome.show_error("\n".join(errors))

    def open_welcome() -> None:
        nonlocal welcome
        if welcome is None:
            welcome = WelcomeWindow(store.config.record_shortcut, listener, tray.model_status)
            welcome.shortcut_changed.connect(on_welcome_shortcut)
            bridge.model_status.connect(welcome.set_status)
        else:
            welcome.set_shortcut(store.config.record_shortcut)
            welcome.set_status(tray.model_status)
        welcome.show()
        welcome.raise_()
        welcome.activateWindow()
```

Connect the tray signal with the others: `tray.welcome_requested.connect(open_welcome)`. Just before `log.info("Local Dictation started ...")`, add the first-run block:

```python
    if not store.config.welcome_shown:
        try:
            store.update(replace(store.config, welcome_shown=True))
        except OSError:
            log.exception("could not record that the welcome window was shown")
        open_welcome()
```

- [ ] **Step 4: Run to verify pass, then the full suite**

Run: `poetry run pytest -v`
Expected: all PASS.

- [ ] **Step 5: Smoke run** (needs a desktop session; use a throwaway config)

Run (PowerShell): `$env:APPDATA = "$env:TEMP\ld-welcome-test"; poetry run local-dictation`
Expected: the welcome window appears with `Ctrl` + `Win` keycaps and a progress bar that turns into "Ready. Try it now."; closing it and starting the app again does not show it; tray → "How to use…" reopens it. Quit from the tray. If no desktop is available, say so in the report instead of claiming this passed.

- [ ] **Step 6: Commit**

```bash
git add src/local_dictation/app.py tests/test_app_startup.py
git commit -m "Wire welcome window: first-run, tray reopen, shortcut change

Co-Authored-By: Claude Sonnet 5.5 <noreply@anthropic.com>"
```

---

### Task 6: Documentation

**Files:**
- Modify: `docs/architecture.md`, `docs/purpose.md`, `docs/manual-test-checklist.md`, `docs/roadmap.md`, `README.md`, `docs/superpowers/specs/2026-10-16-welcome-window-design.md`

- [ ] **Step 1: `docs/architecture.md`**: in the module table add rows after `ui/settings.py`:
  - `ui/welcome.py` | `WelcomeWindow` (first-run/how-to window: keycaps, shortcut change, model status) and `KeycapRow`
  - `ui/theme.py` | colour tokens and shared stylesheet (light/dark from the system palette)

  Update the `ui/tray.py` row to "…menu (How to use, Settings, Restart hotkey, Quit); remembers the last model status", the `shortcut.py` row to mention `keycaps`, and the data-flow sentence to end "…→ `Bridge` Qt signals → tray and welcome window."

- [ ] **Step 2: `docs/purpose.md`**: in Target behavior item 5 add "; a welcome window on first launch (and from the tray) explains the gesture, offers a shortcut change and shows when the speech model is ready."

- [ ] **Step 3: `docs/manual-test-checklist.md`**: add under the main list:

```
21. First run: start with no config file (`$env:APPDATA` pointing at an empty folder) → welcome window appears with the right keycaps; the progress bar becomes "Ready. Try it now.". Start again → it does not reappear.
22. Tray → How to use… reopens it (no second window if already open). Change the shortcut there, dictate with the new one; try an invalid one (a single letter) → message shown, old shortcut still works.
23. Close the window while "Press the keys…" is showing → afterwards normal typing still works (capture was cancelled).
24. Windows light and dark app mode: the window is readable in both.
25. Open the window with a missing/broken model name → red error text, no progress bar.
```

- [ ] **Step 4: `docs/roadmap.md`**: add a section "Done: first-run welcome window (UX review, part 1)" and a "Next UX review sub-projects" list: recording/status overlay (reverses the old non-goal), Settings redesign (reusing `ui/theme.py`), visual identity (app/tray/installer icon).

- [ ] **Step 5: `README.md`**: change the tray sentence to "A tray icon shows the state; right-click it for **How to use…**, **Settings…**, **Restart hotkey** and **Quit**. A welcome window opens on first launch."

- [ ] **Step 6: Spec correction**: in the spec's "Model status" and "Structure" sections, replace the statement that `app.py` keeps the status holder with: the tray keeps the latest status in `TrayIcon.model_status`, and `app.py` passes it to the window when opening.

- [ ] **Step 7: Verify and commit**

Run: `poetry run pytest` → all PASS.

```bash
git add docs README.md
git commit -m "Docs: welcome window

Co-Authored-By: Claude Sonnet 5.5 <noreply@anthropic.com>"
```

---

## Self-review notes
- Spec coverage: window content and behaviour (Task 3, 5), first-run flag (2, 5), tray reopen (4, 5), status handling (3, 4, 5), theme (3), keycaps (1), tests (each task), docs (6). The spec said `app.py` holds the status; the plan puts it on `TrayIcon` (already main-thread, queued) and Task 6 corrects the spec.
- Extra fix beyond the spec: `SettingsDialog.to_config` would otherwise reset `welcome_shown` (Task 2).
- Known limitation: if the config file cannot be written, the window shows on every launch.
