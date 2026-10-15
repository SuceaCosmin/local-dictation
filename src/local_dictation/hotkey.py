"""Global keyboard hook (WH_KEYBOARD_LL) that can swallow shortcut keys.

The callback runs on the hook thread and must return fast: it only consults the matcher and
enqueues events. A Win-key shortcut injects an unassigned key (VK 0xE8) so Windows does not
open the Start menu when Win is released.
"""
from __future__ import annotations

import ctypes
import logging
import threading
from ctypes import wintypes
from typing import Callable

from .dispatch import EventDispatcher
from .keystate import is_held
from .shortcut import PASS, Shortcut, ShortcutCapture, ShortcutMatcher, vk_to_name

log = logging.getLogger(__name__)

WH_KEYBOARD_LL = 13
HC_ACTION = 0
WM_KEYDOWN, WM_KEYUP, WM_SYSKEYDOWN, WM_SYSKEYUP = 0x0100, 0x0101, 0x0104, 0x0105
WM_QUIT = 0x0012
LLKHF_INJECTED = 0x10
KEYEVENTF_KEYUP = 0x0002
MASK_VK = 0xE8  # unassigned virtual key, same trick AutoHotkey uses

LRESULT = ctypes.c_ssize_t
HOOKPROC = ctypes.WINFUNCTYPE(LRESULT, ctypes.c_int, wintypes.WPARAM, wintypes.LPARAM)


class KBDLLHOOKSTRUCT(ctypes.Structure):
    _fields_ = [
        ("vkCode", wintypes.DWORD),
        ("scanCode", wintypes.DWORD),
        ("flags", wintypes.DWORD),
        ("time", wintypes.DWORD),
        ("dwExtraInfo", ctypes.c_size_t),
    ]


user32 = ctypes.WinDLL("user32", use_last_error=True)
kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
user32.SetWindowsHookExW.argtypes = [ctypes.c_int, HOOKPROC, wintypes.HINSTANCE, wintypes.DWORD]
user32.SetWindowsHookExW.restype = wintypes.HHOOK
user32.CallNextHookEx.argtypes = [wintypes.HHOOK, ctypes.c_int, wintypes.WPARAM, wintypes.LPARAM]
user32.CallNextHookEx.restype = LRESULT
user32.UnhookWindowsHookEx.argtypes = [wintypes.HHOOK]
user32.GetMessageW.argtypes = [ctypes.POINTER(wintypes.MSG), wintypes.HWND, wintypes.UINT, wintypes.UINT]
user32.PostThreadMessageW.argtypes = [wintypes.DWORD, wintypes.UINT, wintypes.WPARAM, wintypes.LPARAM]
user32.keybd_event.argtypes = [wintypes.BYTE, wintypes.BYTE, wintypes.DWORD, ctypes.c_size_t]
kernel32.GetModuleHandleW.argtypes = [wintypes.LPCWSTR]
kernel32.GetModuleHandleW.restype = wintypes.HMODULE


def _inject_mask() -> None:
    user32.keybd_event(MASK_VK, 0, 0, 0)
    user32.keybd_event(MASK_VK, 0, KEYEVENTF_KEYUP, 0)


class WindowsHotkeyListener:
    def __init__(self):
        self._matcher = ShortcutMatcher()
        self._dispatcher = EventDispatcher()
        self._capture: ShortcutCapture | None = None
        self._on_update: Callable[[str], None] | None = None
        self._on_done: Callable[[Shortcut | None], None] | None = None
        self._thread: threading.Thread | None = None
        self._thread_id: int | None = None
        self._hook = None
        self._proc = None
        self._ready = threading.Event()
        self._error: Exception | None = None

    # -- public API -------------------------------------------------------
    def set_handler(self, handler: Callable[[str, str], None]) -> None:
        self._dispatcher.set_handler(handler)

    def set_bindings(self, bindings: dict) -> None:
        self._matcher.set_bindings(bindings)

    def start(self) -> None:
        self._error = None
        self._ready.clear()
        self._matcher.reset()
        self._dispatcher.start()
        self._thread = threading.Thread(target=self._run, name="keyboard-hook", daemon=True)
        self._thread.start()
        if not self._ready.wait(5) or self._error is not None:
            self._dispatcher.stop()
            raise RuntimeError(f"Could not install keyboard hook: {self._error}")

    def stop(self) -> None:
        if self._thread is not None and self._thread_id is not None:
            user32.PostThreadMessageW(self._thread_id, WM_QUIT, 0, 0)
            self._thread.join(2)
        self._thread = None
        self._dispatcher.stop()

    def begin_capture(self, on_update, on_done) -> None:
        self._on_update, self._on_done = on_update, on_done
        self._capture = ShortcutCapture()

    def cancel_capture(self) -> None:
        self._capture = None

    # -- hook thread ------------------------------------------------------
    def _run(self) -> None:
        self._thread_id = kernel32.GetCurrentThreadId()
        self._proc = HOOKPROC(self._hook_proc)  # keep a reference or it gets garbage collected
        self._hook = user32.SetWindowsHookExW(WH_KEYBOARD_LL, self._proc,
                                              kernel32.GetModuleHandleW(None), 0)
        if not self._hook:
            self._error = ctypes.WinError(ctypes.get_last_error())
            self._ready.set()
            return
        self._ready.set()
        msg = wintypes.MSG()
        while user32.GetMessageW(ctypes.byref(msg), None, 0, 0) > 0:
            user32.TranslateMessage(ctypes.byref(msg))
            user32.DispatchMessageW(ctypes.byref(msg))
        user32.UnhookWindowsHookEx(self._hook)
        self._hook = None

    def _hook_proc(self, n_code, w_param, l_param):
        if n_code == HC_ACTION:
            try:
                if self._handle(w_param, l_param):
                    return 1
            except Exception:
                log.exception("keyboard hook error")
        return user32.CallNextHookEx(None, n_code, w_param, l_param)

    def _handle(self, w_param, l_param) -> bool:
        kb = ctypes.cast(l_param, ctypes.POINTER(KBDLLHOOKSTRUCT)).contents
        if kb.flags & LLKHF_INJECTED:
            return False
        is_down = w_param in (WM_KEYDOWN, WM_SYSKEYDOWN)
        name = vk_to_name(kb.vkCode)

        capture = self._capture
        if capture is not None:
            step = capture.on_key(name, is_down)
            if step.done is not None or step.cancelled:
                self._capture = None
            if is_down and self._on_update:
                self._on_update(capture.preview())
            if (step.done is not None or step.cancelled) and self._on_done:
                self._on_done(step.done)
            return step.swallow

        for binding, kind in self._matcher.prune(is_held, keep=name):
            self._dispatcher.submit(binding, kind)
        decision = self._matcher.on_key(name, is_down)
        for binding, kind in decision.events:
            self._dispatcher.submit(binding, kind)
        if decision.inject_mask:
            _inject_mask()
        return decision.swallow
