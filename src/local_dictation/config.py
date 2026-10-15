"""Application settings: validated dataclass plus a JSON store in %APPDATA%."""
from __future__ import annotations

import json
import logging
import os
import tempfile
from dataclasses import asdict, dataclass, fields
from pathlib import Path

from .shortcut import Shortcut

log = logging.getLogger(__name__)

STOP_MODES = ("release", "combo")
DEVICES = ("cpu", "cuda")


def default_config_path() -> Path:
    base = os.environ.get("APPDATA") or str(Path.home() / "AppData" / "Roaming")
    return Path(base) / "LocalDictation" / "config.json"


def _check_shortcut(text: str, label: str, errors: list[str]) -> Shortcut | None:
    try:
        shortcut = Shortcut.parse(text)
    except ValueError:
        errors.append(f"{label} is empty.")
        return None
    if not shortcut.is_safe():
        errors.append(f"{label} must include Ctrl, Alt, Shift or Win (or be a function key) "
                      "and at most one other key.")
        return None
    return shortcut


@dataclass
class Config:
    record_shortcut: str = "ctrl+win"
    stop_mode: str = "release"
    paste_shortcut: str = "ctrl+win+space"
    model: str = "base.en"
    device: str = "cpu"
    language: str = ""
    cleanup_model: str = ""
    start_with_windows: bool = False

    @classmethod
    def from_dict(cls, data) -> "Config":
        cfg = cls()
        if not isinstance(data, dict):
            return cfg
        for f in fields(cls):
            value = data.get(f.name)
            if type(value) is type(getattr(cfg, f.name)):
                setattr(cfg, f.name, value)
        return cfg

    def validate(self) -> list[str]:
        errors: list[str] = []
        record = _check_shortcut(self.record_shortcut, "Record shortcut", errors)
        if self.stop_mode not in STOP_MODES:
            errors.append("Stop mode must be 'release' or 'combo'.")
        if self.device not in DEVICES:
            errors.append("Device must be 'cpu' or 'cuda'.")
        if not self.model.strip():
            errors.append("Model must not be empty.")
        if self.stop_mode == "combo":
            paste = _check_shortcut(self.paste_shortcut, "Paste shortcut", errors)
            if record and paste and record.keys == paste.keys:
                errors.append("Record and paste shortcuts must differ.")
        return errors

    def bindings(self) -> dict[str, Shortcut]:
        result = {"record": Shortcut.parse(self.record_shortcut)}
        if self.stop_mode == "combo":
            result["paste"] = Shortcut.parse(self.paste_shortcut)
        return result


class ConfigStore:
    def __init__(self, path: Path | None = None):
        self.path = path or default_config_path()
        self.config = self._load()

    def _load(self) -> Config:
        try:
            data = json.loads(self.path.read_text(encoding="utf-8"))
        except FileNotFoundError:
            return Config()
        except (OSError, ValueError) as e:
            log.warning("Could not read %s (%s); using defaults", self.path, e)
            return Config()
        cfg = Config.from_dict(data)
        errors = cfg.validate()
        if errors:
            log.warning("Invalid config (%s); using defaults", "; ".join(errors))
            return Config()
        return cfg

    def update(self, cfg: Config) -> None:
        errors = cfg.validate()
        if errors:
            raise ValueError("; ".join(errors))
        self.path.parent.mkdir(parents=True, exist_ok=True)
        fd, tmp = tempfile.mkstemp(dir=self.path.parent, suffix=".tmp")
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            json.dump(asdict(cfg), f, indent=2)
        os.replace(tmp, self.path)
        self.config = cfg
