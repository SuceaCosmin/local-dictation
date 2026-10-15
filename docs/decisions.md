# Decisions

- **PySide6 (Qt) for UI** — one event loop for tray + settings + capture widget; pystray+Tkinter means two GUI loops. Cost: ~100 MB install.
- **Own `WH_KEYBOARD_LL` hook (ctypes), not pynput/keyboard** — the original bug was that pynput only observes keys. We need to swallow keys, handle the Win-key/Start menu quirk (inject unassigned VK 0xE8 so Windows does not open Start), and ignore our own injected events. pynput is still used to send Ctrl+V.
- **Hook callback only enqueues** — Windows removes slow low-level hooks without notice.
- **Controller is Qt-free** — callbacks instead of signals so it is unit-testable with fakes; `Bridge` in `app.py` adapts to Qt.
- **Mic opens on press** — mic is only active while the shortcut is held; handles device changes. Trade-off: tiny start latency; if the first word clips, revisit (keep stream open).
- **Clipboard paste** — works in every app incl. Electron/VS Code chat boxes; clipboard text is restored afterwards. Non-text clipboard content is not restored (limitation).
- **Paste waits for modifiers to be released** — otherwise held Win turns Ctrl+V into Win+V.
- **Shortcut capture via the hook** — Qt cannot reliably see the Win key.
- **Side-agnostic keys** (`ctrl` matches either Ctrl) — simpler UI; the old Right-Ctrl default is gone.
- **Poetry with in-project `.venv`** (`poetry.toml`) — editors find the interpreter; reuses the repo-local venv convention.
- **Known limitation** — elevated (admin) windows do not receive/trigger input from a non-elevated process.

## Unverified assumptions (need a human at the keyboard)
- Start-menu suppression via the unassigned virtual key 0xE8 (injected with `keybd_event` when a Win shortcut activates) is unverified on a real desktop. Fallbacks to try: 0xFF or tapping Left Shift (0xA0). Items 2-5 of `docs/manual-test-checklist.md` verify it.
- The hook is never re-installed if Windows silently times it out; Tray > Restart hotkey is the recovery.
