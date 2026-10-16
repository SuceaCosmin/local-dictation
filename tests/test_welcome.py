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
