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
