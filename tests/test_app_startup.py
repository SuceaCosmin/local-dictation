from local_dictation.app import apply_shortcut_change, apply_startup
from local_dictation.config import ConfigStore


def test_apply_startup_swallows_oserror_and_notifies_once():
    calls = []

    def boom(enabled):
        raise OSError("denied")

    assert apply_startup(True, lambda t, m: calls.append((t, m)), set_enabled=boom) is False
    assert len(calls) == 1
    assert calls[0][0] == "Start with Windows failed"


def test_apply_startup_success_does_not_notify():
    calls, seen = [], []
    assert apply_startup(True, lambda t, m: calls.append((t, m)), set_enabled=seen.append) is True
    assert seen == [True]
    assert calls == []


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
