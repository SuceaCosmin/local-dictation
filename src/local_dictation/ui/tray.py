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
    "cleaning": "#8b5cf6",
    "pasting": "#f59e0b",
    "ready": "#3b82f6",
}
STATE_TEXT = {
    "loading": "Loading speech model…",
    "idle": "Idle",
    "recording": "Recording…",
    "transcribing": "Transcribing…",
    "cleaning": "Cleaning up text…",
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
    welcome_requested = Signal()
    settings_requested = Signal()
    restart_requested = Signal()
    quit_requested = Signal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self._tray = QSystemTrayIcon(make_icon(STATE_COLORS["loading"]))
        self._menu = QMenu()
        for text, signal in (("How to use…", self.welcome_requested),
                             ("Settings…", self.settings_requested),
                             ("Restart hotkey", self.restart_requested),
                             ("Quit", self.quit_requested)):
            action = QAction(text, self._menu)
            action.triggered.connect(signal.emit)
            self._menu.addAction(action)
        self._tray.setContextMenu(self._menu)
        self._tray.activated.connect(self._on_activated)
        self._model_ready = False
        self.model_status = "loading"
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
        self.model_status = status
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
