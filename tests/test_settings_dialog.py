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
