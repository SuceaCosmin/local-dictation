"""Settings dialog and the shortcut-capture widget."""
from __future__ import annotations

from dataclasses import replace

from PySide6.QtCore import QTimer, Signal
from PySide6.QtWidgets import (QCheckBox, QComboBox, QDialog, QDialogButtonBox, QFormLayout,
                               QHBoxLayout, QLabel, QLineEdit, QPushButton, QWidget)

from ..cleanup import list_models as list_installed_models
from ..config import Config
from ..shortcut import Shortcut

CAPTURE_TIMEOUT_MS = 10_000
WHISPER_MODELS = ["tiny.en", "base.en", "small.en", "medium.en",
                  "tiny", "base", "small", "medium", "large-v3"]
# (label, Whisper language code); "" lets Whisper detect the language
LANGUAGES = [("Auto-detect", ""), ("English", "en"), ("Romanian", "ro"), ("German", "de"),
             ("French", "fr"), ("Spanish", "es"), ("Italian", "it"), ("Portuguese", "pt"),
             ("Dutch", "nl"), ("Polish", "pl"), ("Russian", "ru"), ("Ukrainian", "uk"),
             ("Turkish", "tr"), ("Japanese", "ja"), ("Chinese", "zh"), ("Korean", "ko"),
             ("Arabic", "ar"), ("Hindi", "hi")]


class ShortcutEdit(QWidget):
    """Read-only field plus a Change button; capture runs through the global keyboard hook."""

    changed = Signal(str)
    _preview = Signal(str)
    _finished = Signal(object)

    def __init__(self, listener, value: str, parent=None):
        super().__init__(parent)
        self._listener = listener
        self._value = value
        self._capturing = False
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
        self._capturing = True
        self._button.setEnabled(False)
        self._field.setText("Press the keys… (Esc cancels)")
        self._timer.start()
        # callbacks arrive on the hook thread; the signals marshal them to the UI thread
        self._listener.begin_capture(self._preview.emit, self._finished.emit)

    def _on_preview(self, text: str) -> None:
        self._field.setText(text or "Press the keys… (Esc cancels)")

    def _on_finished(self, shortcut: Shortcut | None) -> None:
        if not self._capturing:  # late queued result after cancel/timeout
            return
        self._capturing = False
        self._timer.stop()
        self._button.setEnabled(True)
        if shortcut is not None:
            self._value = shortcut.format()
            self.changed.emit(self._value)
        self._field.setText(self._value)

    def cancel(self) -> None:
        """Abort an in-progress capture started by this edit (no-op otherwise)."""
        if not self._capturing:
            return
        self._listener.cancel_capture()
        self._on_finished(None)

    def _on_timeout(self) -> None:
        self.cancel()


class SettingsDialog(QDialog):
    def __init__(self, config: Config, listener, parent=None, *, list_models=None):
        super().__init__(parent)
        self._config = config
        self.setWindowTitle("Local Dictation — Settings")
        self.setMinimumWidth(460)

        self.record_edit = ShortcutEdit(listener, config.record_shortcut)
        self.stop_mode_combo = QComboBox()
        self.stop_mode_combo.addItem("Paste when I release the keys", "release")
        self.stop_mode_combo.addItem("Paste with a separate shortcut", "combo")
        self.stop_mode_combo.setCurrentIndex(self.stop_mode_combo.findData(config.stop_mode))
        self.paste_edit = ShortcutEdit(listener, config.paste_shortcut)
        self.model_combo = QComboBox()
        self.model_combo.addItems(WHISPER_MODELS)
        if config.model not in WHISPER_MODELS:  # hand-edited config: keep it selectable, not lost
            self.model_combo.addItem(config.model)
        self.model_combo.setCurrentText(config.model)
        self.device_combo = QComboBox()
        self.device_combo.addItems(["cpu", "cuda"])
        self.device_combo.setCurrentText(config.device)
        self.language_combo = QComboBox()
        for label, code in LANGUAGES:
            self.language_combo.addItem(label, code)
        if self.language_combo.findData(config.language) < 0:  # code outside the list: keep it
            self.language_combo.addItem(config.language, config.language)
        self.language_combo.setCurrentIndex(self.language_combo.findData(config.language))
        self.cleanup_combo = QComboBox()
        self.cleanup_hint = QLabel()
        self.cleanup_hint.setWordWrap(True)
        self.cleanup_hint.setStyleSheet("color: #6b7280;")
        self._fill_cleanup(config.cleanup_model, (list_models or list_installed_models)())
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
        form.addRow("Language", self.language_combo)
        form.addRow("Cleanup model", self.cleanup_combo)
        form.addRow("", self.cleanup_hint)
        form.addRow("", self.startup_check)
        form.addRow(self.error_label)
        buttons = QDialogButtonBox(QDialogButtonBox.Save | QDialogButtonBox.Cancel)
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        form.addRow(buttons)
        self.setLayout(form)

        self.stop_mode_combo.currentIndexChanged.connect(self._sync_enabled)
        self._sync_enabled()

    def _fill_cleanup(self, current: str, models) -> None:
        """Off + the models Ollama has installed; the saved choice always stays selectable."""
        self.cleanup_combo.addItem("Off", "")
        installed = {m.name for m in models or []}
        for m in models or []:
            self.cleanup_combo.addItem(f"{m.name} · {m.size}", m.name)
        if current and current not in installed:
            self.cleanup_combo.addItem(f"{current} (not installed)", current)
        self.cleanup_combo.setCurrentIndex(self.cleanup_combo.findData(current))
        if models is None:
            self.cleanup_hint.setText("Ollama is not running at localhost:11434. Start it, then "
                                      "reopen Settings to choose a cleanup model.")
        elif not models:
            self.cleanup_hint.setText("Ollama has no models installed. Run: ollama pull <model>")
        self.cleanup_hint.setVisible(bool(self.cleanup_hint.text()))

    def _sync_enabled(self) -> None:
        self.paste_edit.setEnabled(self.stop_mode_combo.currentData() == "combo")

    def to_config(self) -> Config:
        return replace(
            self._config,
            record_shortcut=self.record_edit.value(),
            stop_mode=self.stop_mode_combo.currentData(),
            paste_shortcut=self.paste_edit.value(),
            model=self.model_combo.currentText().strip(),
            device=self.device_combo.currentText(),
            language=self.language_combo.currentData(),
            cleanup_model=self.cleanup_combo.currentData(),
            start_with_windows=self.startup_check.isChecked(),
        )

    def done(self, result: int) -> None:
        # covers accept, reject and window close: never leave the global hook in capture mode
        self.record_edit.cancel()
        self.paste_edit.cancel()
        super().done(result)

    def accept(self) -> None:
        errors = self.to_config().validate()
        if errors:
            self.error_label.setText("\n".join(errors))
            return
        super().accept()
