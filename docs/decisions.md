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

- **PyInstaller one-folder, not one-file** — no per-launch unpacking of a large tree, faster start, fewer antivirus false positives. Cost: a folder instead of a single exe (the installer hides this).
- **Inno Setup, per-user** — no admin rights, built-in upgrade and uninstall, detects a running instance through the app's mutex.
- **`base.en` bundled in the installer** — works offline from the first launch and removes the silent first-run download failure. Cost: a larger installer (about 216 MB). Other models still download on demand. PyInstaller 6 puts it in `_internal/models/base.en`, which `paths.data_dir()` resolves.
- **The app owns the HKCU Run value** — the in-app checkbox is the only switch; the installer has no startup task. `apply_startup` rewrites the value on every start, so a moved or upgraded install self-heals. The uninstaller removes the value only if it points into the install folder.
- **Unsigned installer** — the audience is the author and a few trusted people. Expect a SmartScreen "Unknown publisher" prompt and possible antivirus flags (the app installs a global keyboard hook). Signing can be added later as a build step.
- **Frozen self-test in the build** — `LocalDictation.exe --self-test <file>` fails the build if a dependency, data file or the bundled model is missing, instead of failing at the first dictation on someone else's machine.

## Unverified assumptions (need a human at the keyboard)
- Start-menu suppression via the unassigned virtual key 0xE8 (injected with `keybd_event` when a Win shortcut activates) is unverified on a real desktop. Fallbacks to try: 0xFF or tapping Left Shift (0xA0). Items 2-5 of `docs/manual-test-checklist.md` verify it.
- The hook is never re-installed if Windows silently times it out; Tray > Restart hotkey is the recovery.

## Welcome window and Ollama cleanup (UX review)
- **`welcome_shown` is set when the window opens, not when it is dismissed** — a crash or force-quit never causes repeat nagging. It is never written when `config.json` was unreadable or invalid (`ConfigStore.invalid`), so a hand-edited file is not replaced with defaults.
- **The tray keeps the last model status (`TrayIcon.model_status`)** — it already receives the signal on the UI thread, and a welcome window opened later reads it to show the right state at once.
- **Practice box needs no special plumbing** — dictation is pasted into whichever control has focus, so a focused text box in the welcome window receives it like any other app.
- **Ollama requests send `"think": false`** — thinking models (qwen3.5, ...) otherwise reason for minutes and always hit the 30 s timeout, so cleanup silently never worked. Cost: none seen; models without thinking ignore the field.
- **Cleanup failures are visible** — `ollama_cleanup` raises, the controller pastes the raw text and shows one "Cleanup skipped" notification per failure streak (reset by the next success). A cold load of a large model can still exceed the 30 s timeout; prefer small cleanup models.
- **Settings are select-only** — model, device, language and cleanup model are chosen from lists. A saved value that is not in the list (hand-edited config, model no longer installed) stays selectable instead of being dropped. The cleanup list is read from Ollama's `/api/tags` when Settings opens (1.5 s timeout); if Ollama is down the user sees a hint instead of an empty list.
