"""Locations that differ between a source run and a frozen (installed) build. Pure: no OS/Qt imports."""
from __future__ import annotations

import sys
from pathlib import Path


def is_frozen() -> bool:
    return bool(getattr(sys, "frozen", False))


def app_dir() -> Path:
    return Path(sys.executable).parent


def bundled_model_path(name: str) -> Path | None:
    """Folder of the Whisper model shipped inside the installer, or None to use the normal download."""
    if not is_frozen():
        return None
    if not name or name in (".", "..") or any(sep in name for sep in ("/", "\\", ":")):
        return None
    folder = app_dir() / "models" / name
    return folder if (folder / "model.bin").is_file() else None
