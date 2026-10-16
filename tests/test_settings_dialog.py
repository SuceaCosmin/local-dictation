import pytest
from PySide6.QtWidgets import QApplication

from local_dictation.cleanup import OllamaModel
from local_dictation.config import Config
from local_dictation.shortcut import Shortcut
from local_dictation.ui import settings as settings_module
from local_dictation.ui.settings import SettingsDialog


@pytest.fixture(scope="module")
def qapp():
    return QApplication.instance() or QApplication([])


class FakeListener:
    def __init__(self):
        self.on_update = self.on_done = None
        self.cancelled = False
        self.cancel_calls = 0

    def begin_capture(self, on_update, on_done):
        self.on_update, self.on_done = on_update, on_done

    def cancel_capture(self):
        self.cancelled = True
        self.cancel_calls += 1


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


def test_reject_during_capture_cancels_capture(qapp):
    listener = FakeListener()
    dlg = SettingsDialog(Config(), listener)
    dlg.record_edit.begin()
    dlg.reject()
    assert listener.cancelled is True


def test_accept_during_capture_cancels_capture(qapp):
    listener = FakeListener()
    dlg = SettingsDialog(Config(), listener)
    dlg.record_edit.begin()
    dlg.accept()
    assert dlg.result() == 1
    assert listener.cancelled is True


def test_closing_without_capture_does_not_cancel(qapp):
    listener = FakeListener()
    dlg = SettingsDialog(Config(), listener)
    dlg.reject()
    assert listener.cancel_calls == 0


def test_late_done_after_cancel_is_ignored(qapp):
    listener = FakeListener()
    dlg = SettingsDialog(Config(), listener)
    dlg.record_edit.begin()
    dlg.reject()
    listener.on_done(Shortcut.parse("ctrl+alt+space"))
    qapp.processEvents()
    assert dlg.record_edit.value() == "ctrl+win"


def test_saving_settings_keeps_welcome_shown(qapp):
    cfg = Config(welcome_shown=True)
    assert SettingsDialog(cfg, FakeListener()).to_config().welcome_shown is True


@pytest.fixture(autouse=True)
def no_real_ollama(monkeypatch):
    """Settings must never talk to the developer's real Ollama during tests."""
    monkeypatch.setattr(settings_module, "list_installed_models", lambda: None)


MODELS = [OllamaModel("qwen3.5:0.8b", "1.2 GB"), OllamaModel("gemma4:26b", "15.8 GB")]


def _items(combo):
    return [(combo.itemText(i), combo.itemData(i)) for i in range(combo.count())]


def test_comboboxes_are_select_only(qapp):
    dlg = SettingsDialog(Config(), FakeListener())
    for combo in (dlg.model_combo, dlg.device_combo, dlg.language_combo, dlg.cleanup_combo,
                  dlg.stop_mode_combo):
        assert combo.isEditable() is False


def test_whisper_model_not_in_the_list_is_kept_selectable(qapp):
    dlg = SettingsDialog(Config(model="my-custom-model"), FakeListener())
    assert dlg.model_combo.currentText() == "my-custom-model"
    assert dlg.to_config().model == "my-custom-model"


def test_language_is_a_select_with_auto_detect_first(qapp):
    dlg = SettingsDialog(Config(), FakeListener())
    assert _items(dlg.language_combo)[0] == ("Auto-detect", "")
    assert ("Romanian", "ro") in _items(dlg.language_combo)
    assert dlg.to_config().language == ""


def test_language_code_outside_the_list_is_kept(qapp):
    dlg = SettingsDialog(Config(language="sv"), FakeListener())
    assert dlg.language_combo.currentData() == "sv"
    assert dlg.to_config().language == "sv"


def test_cleanup_lists_off_and_installed_models(qapp):
    dlg = SettingsDialog(Config(), FakeListener(), list_models=lambda: MODELS)
    assert _items(dlg.cleanup_combo) == [("Off", ""), ("qwen3.5:0.8b · 1.2 GB", "qwen3.5:0.8b"),
                                         ("gemma4:26b · 15.8 GB", "gemma4:26b")]
    assert dlg.cleanup_combo.currentData() == ""
    assert dlg.cleanup_hint.isHidden()


def test_cleanup_selection_roundtrips(qapp):
    cfg = Config(cleanup_model="gemma4:26b")
    dlg = SettingsDialog(cfg, FakeListener(), list_models=lambda: MODELS)
    assert dlg.cleanup_combo.currentData() == "gemma4:26b"
    assert dlg.to_config().cleanup_model == "gemma4:26b"


def test_saved_cleanup_model_that_is_not_installed_stays_visible(qapp):
    dlg = SettingsDialog(Config(cleanup_model="llama3:8b"), FakeListener(), list_models=lambda: MODELS)
    assert dlg.cleanup_combo.currentText() == "llama3:8b (not installed)"
    assert dlg.to_config().cleanup_model == "llama3:8b"


def test_ollama_unreachable_shows_hint_and_keeps_current_value(qapp):
    dlg = SettingsDialog(Config(cleanup_model="qwen3.5:0.8b"), FakeListener(), list_models=lambda: None)
    assert not dlg.cleanup_hint.isHidden()
    assert "not running" in dlg.cleanup_hint.text()
    assert dlg.to_config().cleanup_model == "qwen3.5:0.8b"
    assert _items(dlg.cleanup_combo)[0] == ("Off", "")


def test_ollama_with_no_models_says_how_to_get_one(qapp):
    dlg = SettingsDialog(Config(), FakeListener(), list_models=lambda: [])
    assert "ollama pull" in dlg.cleanup_hint.text()
    assert dlg.to_config().cleanup_model == ""
