"""Shortcut model, matching state machine and capture helper. Pure Python: no OS calls."""
from __future__ import annotations

import threading
from dataclasses import dataclass
from typing import Callable

MODIFIER_ORDER = ("ctrl", "alt", "shift", "win")

_MODIFIER_VKS = {
    0x10: "shift", 0xA0: "shift", 0xA1: "shift",
    0x11: "ctrl", 0xA2: "ctrl", 0xA3: "ctrl",
    0x12: "alt", 0xA4: "alt", 0xA5: "alt",
    0x5B: "win", 0x5C: "win",
}
_SPECIAL_VKS = {0x20: "space", 0x0D: "enter", 0x09: "tab", 0x1B: "esc", 0x08: "backspace"}
_SIDE_VKS = {  # specific (left/right) keys used for GetAsyncKeyState
    "shift": (0xA0, 0xA1), "ctrl": (0xA2, 0xA3), "alt": (0xA4, 0xA5), "win": (0x5B, 0x5C),
}


def vk_to_name(vk: int) -> str:
    if vk in _MODIFIER_VKS:
        return _MODIFIER_VKS[vk]
    if 0x70 <= vk <= 0x87:
        return f"f{vk - 0x6F}"
    if 0x30 <= vk <= 0x39 or 0x41 <= vk <= 0x5A:
        return chr(vk).lower()
    if vk in _SPECIAL_VKS:
        return _SPECIAL_VKS[vk]
    return f"vk{vk:02x}"


def name_to_vks(name: str) -> tuple[int, ...]:
    if name in _SIDE_VKS:
        return _SIDE_VKS[name]
    if name.startswith("f") and name[1:].isdigit():
        return (0x6F + int(name[1:]),)
    for vk, special in _SPECIAL_VKS.items():
        if special == name:
            return (vk,)
    if len(name) == 1 and name.isalnum():
        return (ord(name.upper()),)
    if name.startswith("vk"):
        return (int(name[2:], 16),)
    return ()


@dataclass(frozen=True)
class Shortcut:
    keys: frozenset

    @classmethod
    def parse(cls, text: str) -> "Shortcut":
        parts = [p.strip().lower() for p in text.split("+") if p.strip()]
        if not parts:
            raise ValueError("empty shortcut")
        return cls(frozenset(parts))

    def format(self) -> str:
        modifiers = [m for m in MODIFIER_ORDER if m in self.keys]
        others = sorted(k for k in self.keys if k not in MODIFIER_ORDER)
        return "+".join(modifiers + others)

    def is_safe(self) -> bool:
        """True if the shortcut cannot hijack normal typing."""
        others = [k for k in self.keys if k not in MODIFIER_ORDER]
        if len(others) > 1:
            return False
        if len(others) < len(self.keys):  # contains a modifier
            return True
        return len(others) == 1 and others[0][0] == "f" and others[0][1:].isdigit()
