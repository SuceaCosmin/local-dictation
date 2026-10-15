"""Physical key state via GetAsyncKeyState (note: keys swallowed by our hook read as up)."""
import ctypes

from .shortcut import name_to_vks

_user32 = ctypes.WinDLL("user32", use_last_error=True)
_user32.GetAsyncKeyState.argtypes = [ctypes.c_int]
_user32.GetAsyncKeyState.restype = ctypes.c_short


def is_held(name: str) -> bool:
    return any(_user32.GetAsyncKeyState(vk) & 0x8000 for vk in name_to_vks(name))
