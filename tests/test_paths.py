import sys

import pytest

from local_dictation import paths


def _frozen(monkeypatch, exe_dir):
    monkeypatch.setattr(sys, "frozen", True, raising=False)
    monkeypatch.setattr(sys, "executable", str(exe_dir / "LocalDictation.exe"))


def _make_model(exe_dir, name="base.en", with_bin=True):
    model = exe_dir / "models" / name
    model.mkdir(parents=True)
    (model / "config.json").write_text("{}")
    if with_bin:
        (model / "model.bin").write_bytes(b"x")
    return model


def test_not_frozen_by_default(monkeypatch):
    monkeypatch.delattr(sys, "frozen", raising=False)
    assert paths.is_frozen() is False
    assert paths.bundled_model_path("base.en") is None


def test_app_dir_is_exe_folder_when_frozen(monkeypatch, tmp_path):
    _frozen(monkeypatch, tmp_path)
    assert paths.is_frozen() is True
    assert paths.app_dir() == tmp_path


def test_bundled_model_found(monkeypatch, tmp_path):
    _frozen(monkeypatch, tmp_path)
    model = _make_model(tmp_path)
    assert paths.bundled_model_path("base.en") == model


def test_unbundled_model_name_returns_none(monkeypatch, tmp_path):
    _frozen(monkeypatch, tmp_path)
    _make_model(tmp_path)
    assert paths.bundled_model_path("small.en") is None


def test_model_folder_without_model_bin_is_ignored(monkeypatch, tmp_path):
    _frozen(monkeypatch, tmp_path)
    _make_model(tmp_path, with_bin=False)
    assert paths.bundled_model_path("base.en") is None


@pytest.mark.parametrize("name", ["..", "..\\base.en", "../base.en", "C:\\models\\base.en",
                                  "sub\\base.en", "sub/base.en", "", "."])
def test_name_cannot_escape_models_folder(monkeypatch, tmp_path, name):
    _frozen(monkeypatch, tmp_path)
    _make_model(tmp_path)
    (tmp_path / "model.bin").write_bytes(b"x")  # a decoy one level up
    assert paths.bundled_model_path(name) is None


def test_bundled_model_is_found_in_pyinstaller_data_dir(monkeypatch, tmp_path):
    # PyInstaller 6 keeps data files in <exe dir>\_internal (sys._MEIPASS), not beside the exe.
    _frozen(monkeypatch, tmp_path)
    data_dir = tmp_path / "_internal"
    monkeypatch.setattr(sys, "_MEIPASS", str(data_dir), raising=False)
    model = _make_model(data_dir)
    assert paths.bundled_model_path("base.en") == model
