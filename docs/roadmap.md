# Roadmap

Status as of v0.1.0 (first release: run from source with Poetry).

## Next: installer

**Goal:** a normal Windows user installs Local Dictation with a double-click and starts it from the Start menu or at sign-in, with no Python, Poetry or terminal.

**Status:** not started. Needs its own brainstorm → spec → plan cycle (superpowers workflow) before any code.

### Likely approach (to be confirmed in the spec)
1. **Freeze the app** with PyInstaller (windowed build, no console) from the existing `local-dictation` entry point `local_dictation.app:main`.
2. **Wrap it in an installer** (Inno Setup is the leading candidate): per-user install without admin rights, Start menu shortcut, optional "start with Windows", clean uninstall.
3. **Publish** the installer as an asset on the GitHub release, versioned from `pyproject.toml`. Consider a GitHub Actions workflow to build it on tag push.

### Things the installer work must handle (known from the code)
- **`startup.launch_command()`** builds `"<pythonw.exe>" -m local_dictation` from `sys.executable` (`src/local_dictation/startup.py`). In a frozen build `sys.executable` is the app itself and `-m` is wrong. Make it frozen-aware (`sys.frozen`) and return the installed exe path. The installer and the in-app "Start with Windows" checkbox must not fight over the same `HKCU\...\Run` value (`LocalDictation`); pick one owner.
- **Heavy dependencies** (faster-whisper / CTranslate2 / onnxruntime / PySide6 / PortAudio via sounddevice) need explicit PyInstaller collection of their data files and binaries. Expect a large build; measure it before choosing one-file vs one-folder (one-folder starts faster and is easier for an installer).
- **Whisper model:** currently downloaded on first launch (the app's only non-localhost network use). Decide: keep the first-run download, or bundle a default model. The tray already shows "loading", but first-run needs clearer feedback (see "Also deferred").
- **Antivirus / SmartScreen:** an unsigned executable that installs a global keyboard hook is likely to be flagged. Decide on code signing, and document what users should expect.
- **Keyboard hook in a frozen app:** re-verify `docs/manual-test-checklist.md` against the installed build, including the Start-menu suppression (still an unverified assumption, see `docs/decisions.md`).
- **Single instance, logs and config** already live in `%APPDATA%\LocalDictation` and a named mutex, so they are installer-friendly. Uninstall should offer to keep or remove that folder.
- **Upgrades:** installing over a running instance (the mutex and the hook) needs the installer to close the app first.
- **Elevated windows:** the known limitation (admin windows ignore input from a non-elevated process) stays; document it in the installer's readme/notes.

### Done when
A clean Windows machine with no Python can install, run the checklist items 1–9, start with Windows, and uninstall without leftovers.

## Also deferred (small, from the v0.1.0 reviews)
None of these blocks use; pick them up opportunistically.
- Tray shows no error state after a model load failure (only a one-time notification); same for a hook that fails to start.
- A dictation pressed while the model is still loading (first-run download) waits silently in "transcribing" for up to 10 minutes; fail fast with a "model still loading" message instead.
- No `sys.excepthook` / Qt slot exception logging, so tracebacks are lost under `pythonw`.
- Hook robustness: capture started while the shortcut is held, `start()` called twice, stale thread state after a failed start, hook not re-installed if Windows times it out (recovery today: tray > Restart hotkey).
- `ShortcutMatcher.set_bindings` drops an active binding without emitting a release (only reachable by saving settings while holding the record shortcut).
- `Paster` has no `try/finally`, so a failure between setting the clipboard and restoring it leaves the dictated text on the clipboard.
- Controller worker bodies have no `try/finally` back to `idle` (only matters if a notify/state callback itself raises).
- Hand-test combo mode (separate paste shortcut) and start-with-Windows; both are covered by unit tests only.
