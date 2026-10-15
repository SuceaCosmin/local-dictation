"""Paste text into the focused control via the clipboard, then restore the clipboard."""
from __future__ import annotations

import logging
import time

import pyperclip
from pynput import keyboard

from .shortcut import MODIFIER_ORDER

log = logging.getLogger(__name__)

MODIFIER_WAIT_SECONDS = 1.5
POLL_SECONDS = 0.02


class Paster:
    def __init__(self, clipboard=None, keyboard_factory=None, is_held=None,
                 sleep=time.sleep, clock=time.monotonic):
        self._clipboard = clipboard or pyperclip
        self._keyboard_factory = keyboard_factory or keyboard.Controller
        if is_held is None:
            from .keystate import is_held as is_held  # imported lazily: Windows-only
        self._is_held = is_held
        self._sleep = sleep
        self._clock = clock

    def _wait_for_modifiers_up(self) -> None:
        # Release is detected on the first key up; if Win/Ctrl is still down, our Ctrl+V
        # would become Win+V (clipboard history) or similar.
        deadline = self._clock() + MODIFIER_WAIT_SECONDS
        while any(self._is_held(m) for m in MODIFIER_ORDER) and self._clock() < deadline:
            self._sleep(POLL_SECONDS)

    def paste(self, text: str) -> None:
        self._wait_for_modifiers_up()
        try:
            previous = self._clipboard.paste()
        except Exception:
            previous = None
        self._clipboard.copy(text)
        self._sleep(0.05)
        kb = self._keyboard_factory()
        with kb.pressed(keyboard.Key.ctrl):
            kb.press("v")
            kb.release("v")
        self._sleep(0.3)
        if previous is not None:
            self._clipboard.copy(previous)
