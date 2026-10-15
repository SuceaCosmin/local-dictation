import json

import pytest

from local_dictation.config import Config, ConfigStore


def test_defaults_are_valid():
    assert Config().validate() == []
    assert Config().record_shortcut == "ctrl+win"
    assert Config().stop_mode == "release"


def test_from_dict_ignores_unknown_and_wrong_types():
    cfg = Config.from_dict({"model": "small.en", "device": 5, "bogus": 1, "start_with_windows": "yes"})
    assert cfg.model == "small.en"
    assert cfg.device == "cpu"
    assert cfg.start_with_windows is False


@pytest.mark.parametrize("payload", ["", "not json", "[1, 2]", "null", "{"])
def test_store_survives_corrupt_file(tmp_path, payload):
    path = tmp_path / "config.json"
    path.write_text(payload, encoding="utf-8")
    assert ConfigStore(path).config == Config()


def test_store_missing_file_gives_defaults(tmp_path):
    assert ConfigStore(tmp_path / "nope" / "config.json").config == Config()


def test_store_falls_back_to_defaults_when_loaded_config_invalid(tmp_path):
    path = tmp_path / "config.json"
    path.write_text(json.dumps({"record_shortcut": "a"}), encoding="utf-8")  # plain letter: unsafe
    assert ConfigStore(path).config == Config()


def test_update_saves_and_reloads(tmp_path):
    path = tmp_path / "sub" / "config.json"
    store = ConfigStore(path)
    store.update(Config(model="small.en", record_shortcut="ctrl+alt+space"))
    reloaded = ConfigStore(path).config
    assert reloaded.model == "small.en"
    assert reloaded.record_shortcut == "ctrl+alt+space"


def test_update_rejects_invalid(tmp_path):
    store = ConfigStore(tmp_path / "config.json")
    with pytest.raises(ValueError):
        store.update(Config(record_shortcut="a"))
    assert store.config == Config()


@pytest.mark.parametrize("cfg, fragment", [
    (Config(record_shortcut=""), "Record shortcut"),
    (Config(record_shortcut="a"), "Record shortcut"),
    (Config(record_shortcut="ctrl+a+b"), "Record shortcut"),
    (Config(stop_mode="nope"), "Stop mode"),
    (Config(device="tpu"), "Device"),
    (Config(model="  "), "Model"),
    (Config(stop_mode="combo", paste_shortcut="ctrl+win"), "differ"),
    (Config(stop_mode="combo", paste_shortcut="x"), "Paste shortcut"),
])
def test_validate_reports_problems(cfg, fragment):
    assert any(fragment in e for e in cfg.validate())


def test_paste_shortcut_ignored_unless_combo_mode():
    assert Config(stop_mode="release", paste_shortcut="x").validate() == []


def test_bindings():
    assert set(Config().bindings()) == {"record"}
    combo = Config(stop_mode="combo").bindings()
    assert set(combo) == {"record", "paste"}
    assert combo["record"].format() == "ctrl+win"
