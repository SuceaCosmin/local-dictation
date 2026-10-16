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
