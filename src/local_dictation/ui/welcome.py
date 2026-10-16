"""First-run welcome window: how to dictate, change the shortcut, model status."""
from __future__ import annotations

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (QHBoxLayout, QLabel, QPlainTextEdit, QProgressBar, QPushButton,
                               QVBoxLayout, QWidget)

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
        # dictation is pasted into whichever control has focus, so a focused text box just works
        self.practice_box = QPlainTextEdit()
        self.practice_box.setFixedHeight(84)
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
        layout.addWidget(self.practice_box)
        layout.addSpacing(6)
        layout.addWidget(done, alignment=Qt.AlignRight)

        self.set_shortcut(record_shortcut)
        self.set_status(status)

    def set_shortcut(self, value: str) -> None:
        self.shortcut_edit.set_value(value)
        caps = keycaps(value)
        self.keycap_row.set_keys(caps)
        held = " + ".join(caps) if caps else "your shortcut"
        self.practice_box.setPlaceholderText(
            f"Try it here: click in this box, hold {held}, say something, then release.")
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

    def showEvent(self, event) -> None:
        super().showEvent(event)
        self.practice_box.setFocus()

    def closeEvent(self, event) -> None:
        self.shortcut_edit.cancel()  # never leave the global hook in capture mode
        super().closeEvent(event)
