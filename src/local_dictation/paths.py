"""Locations that differ between a source run and a frozen (installed) build. Pure: no OS/Qt imports."""
from __future__ import annotations

import sys
from pathlib import Path


REQUIRED_MODEL_FILES = ("config.json", "model.bin", "tokenizer.json")


def is_frozen() -> bool:
    return bool(getattr(sys, "frozen", False))


def app_dir() -> Path:
    return Path(sys.executable).parent


def data_dir() -> Path:
    """Where PyInstaller puts bundled data (the _internal folder beside the exe in v6); the exe folder otherwise."""
    return Path(getattr(sys, "_MEIPASS", app_dir()))


def bundled_model_path(name: str) -> Path | None:
    """Folder of the Whisper model shipped inside the installer, or None to use the normal download."""
    if not is_frozen():
        return None
    if not name or name in (".", "..") or any(sep in name for sep in ("/", "\\", ":")):
        return None
    folder = data_dir() / "models" / name
    # A partial copy must not count: without tokenizer.json faster-whisper silently goes online.
    complete = all((folder / f).is_file() for f in REQUIRED_MODEL_FILES)
    return folder if complete else None
