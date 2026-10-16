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
            if not others:  # modifiers only: a lone modifier would be swallowed everywhere
                return len(self.keys) > 1
            if self.keys - set(others) == {"shift"}:  # shift+letter hijacks typing
                return others[0][0] == "f" and others[0][1:].isdigit()
            return True
        return len(others) == 1 and others[0][0] == "f" and others[0][1:].isdigit()


def keycaps(text: str) -> list[str]:
    """Display labels for a shortcut string, modifiers first ("ctrl+win" -> ["Ctrl", "Win"])."""
    try:
        names = Shortcut.parse(text).format().split("+")
    except ValueError:
        return []
    return [n.upper() if n.startswith("f") and n[1:].isdigit() else n.capitalize() for n in names]


@dataclass(frozen=True)
class Decision:
    swallow: bool = False
    events: tuple = ()
    inject_mask: bool = False


PASS = Decision()


class ShortcutMatcher:
    """Decides, per key event, whether to swallow it and which shortcut events to emit.

    Invariant: a key-up is swallowed only if the matching key-down was swallowed, so the OS
    never sees an unbalanced down/up pair (no stuck modifiers).
    """

    def __init__(self, bindings: dict | None = None):
        self._bindings = dict(bindings or {})
        self._down: set = set()
        self._swallowed: set = set()
        self._active: set = set()
        self._lock = threading.RLock()

    def set_bindings(self, bindings: dict) -> None:
        with self._lock:
            self._bindings = dict(bindings)
            self._active.clear()

    def reset(self) -> None:
        with self._lock:
            self._down.clear()
            self._swallowed.clear()
            self._active.clear()

    def on_key(self, name: str, is_down: bool) -> Decision:
        with self._lock:
            return self._on_down(name) if is_down else self._on_up(name)

    def _on_down(self, name: str) -> Decision:
        first = name not in self._down
        self._down.add(name)
        if name in self._swallowed:
            return Decision(swallow=True)
        if not first:
            return PASS
        events, mask = [], False
        candidate = frozenset(self._down)
        for binding, shortcut in self._bindings.items():
            if shortcut.keys == candidate and binding not in self._active:
                self._active.add(binding)
                events.append((binding, "pressed"))
                mask = mask or "win" in shortcut.keys
        if events or self._active:
            self._swallowed.add(name)
            return Decision(True, tuple(events), mask)
        return PASS

    def _on_up(self, name: str) -> Decision:
        self._down.discard(name)
        events = []
        for binding in list(self._active):
            shortcut = self._bindings.get(binding)
            if shortcut is None or name in shortcut.keys:
                self._active.discard(binding)
                events.append((binding, "released"))
        swallow = name in self._swallowed
        self._swallowed.discard(name)
        return Decision(swallow, tuple(events))

    def prune(self, is_held: Callable[[str], bool], keep: str | None = None) -> tuple:
        """Forget passed-through keys the OS says are up (a missed key-up).

        Swallowed keys are skipped: the OS never saw them go down, so it cannot confirm them.
        """
        with self._lock:
            events: list = []
            for name in list(self._down):
                if name == keep or name in self._swallowed:
                    continue
                if not is_held(name):
                    events.extend(self._on_up(name).events)
            return tuple(events)


@dataclass(frozen=True)
class CaptureStep:
    swallow: bool
    done: Shortcut | None = None
    cancelled: bool = False


class ShortcutCapture:
    """Records the largest set of keys held together; finishes when all are released."""

    def __init__(self):
        self._down: set = set()
        self._peak: set = set()
        self._seen: set = set()

    def preview(self) -> str:
        return Shortcut(frozenset(self._peak)).format() if self._peak else ""

    def on_key(self, name: str, is_down: bool) -> CaptureStep:
        if is_down:
            if not self._seen and name == "esc":
                return CaptureStep(True, cancelled=True)
            self._seen.add(name)
            self._down.add(name)
            self._peak.add(name)
            return CaptureStep(True)
        if name not in self._seen:
            return CaptureStep(False)
        self._down.discard(name)
        if not self._down and self._peak:
            return CaptureStep(True, done=Shortcut(frozenset(self._peak)))
        return CaptureStep(True)