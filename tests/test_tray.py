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
