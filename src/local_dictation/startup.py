"""Start with Windows via the per-user Run registry key."""
from __future__ import annotations

import sys
import winreg
from pathlib import Path

from . import paths

RUN_KEY = r"Software\Microsoft\Windows\CurrentVersion\Run"
VALUE_NAME = "LocalDictation"


def launch_command() -> str:
    exe = Path(sys.executable)
    if paths.is_frozen():
        return f'"{exe}"'
    pythonw = exe.with_name("pythonw.exe")
    return f'"{pythonw if pythonw.exists() else exe}" -m local_dictation'


def is_enabled(key_path: str = RUN_KEY) -> bool:
    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, key_path) as key:
            winreg.QueryValueEx(key, VALUE_NAME)
            return True
    except OSError:
        return False


def set_enabled(enabled: bool, key_path: str = RUN_KEY) -> None:
    if enabled:
        with winreg.CreateKey(winreg.HKEY_CURRENT_USER, key_path) as key:
            winreg.SetValueEx(key, VALUE_NAME, 0, winreg.REG_SZ, launch_command())
        return
    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, key_path, 0, winreg.KEY_SET_VALUE) as key:
            winreg.DeleteValue(key, VALUE_NAME)
    except OSError:
        pass
