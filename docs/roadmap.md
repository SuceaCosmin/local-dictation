# Roadmap

Status as of v0.3.0 (welcome window, select-only Settings, working Ollama cleanup; v0.2.0 shipped the installer, v0.1.0 was run-from-source with Poetry).

## In progress: Ollama discovery and guided setup (resume here)
Status (2026-10-16): design and plan are written and committed on `feature/ollama-setup`; **no code has been written yet**. Both documents were drafted for review and the owner has not explicitly approved them yet.
- Spec: `docs/superpowers/specs/2026-10-16-ollama-discovery-and-setup-design.md`; plan (11 tasks, test-first): `docs/superpowers/plans/2026-10-16-ollama-discovery-and-setup.md`.
- Why: cleanup is hardcoded to `localhost:11434`. The feature finds Ollama on any local port and offers install, start and model pull (with Retry and manual routes) in Settings and in the welcome window.
- **Next steps:** (1) owner reviews the spec and plan and confirms or changes the "calls I made" list at the end of the spec; (2) choose the execution method, subagent-driven (recommended) or native; (3) start at Task 1 of the plan.
- Open item for Task 6: confirm the real Ollama installer's signer name, silent-install switch and download sizes before relying on them.

## Done: v0.3.0 UX update (UX review, part 1)
Spec: `docs/superpowers/specs/2026-10-16-welcome-window-design.md`; plan: `docs/superpowers/plans/2026-10-16-welcome-window.md`. Opens on first launch and from tray > How to use…; shows the keycaps, lets the user change the shortcut, shows model status and has a practice box to try dictation.
- **Settings are select-only** (Whisper model, device, language, cleanup model); the cleanup model is picked from the models installed in Ollama.
- **Ollama cleanup fixed**: requests send `think: false` (thinking models used to time out silently), failures show one tray notification, and the tray shows a purple "Cleaning up text…" state while the model works. See `docs/decisions.md`.
- Known gap: a cold load of a large cleanup model (for example `qwen3.5:4b` on a laptop CPU) can exceed the 30 s timeout; small models such as `qwen3.5:0.8b` work.

### Next UX review sub-projects (each needs its own spec)
- **Recording/status overlay**: small floating pill showing recording / transcribing / cleaning up / done (the controller already has the `cleaning` state). Reverses the old "no overlay" non-goal in `docs/purpose.md`.
- **Settings redesign**: grouped and themed (reuse `ui/theme.py`), plain-language Whisper model names (selection is already select-only).
- **Visual identity**: app/tray/installer icon and a shared look across windows.

## Done: installer (v0.2.0)
`packaging/build.ps1` builds `dist/LocalDictation-<version>-Setup.exe` (about 216 MB, `base.en` bundled, per-user, unsigned). Design: `docs/superpowers/specs/2026-10-15-installer-design.md`; plan: `docs/superpowers/plans/2026-10-15-windows-installer.md`. Tried by the author on the development machine (install, reinstall); the clean-machine pass (`docs/manual-test-checklist.md` items 15-19) has not been done. Released as v0.2.0 with the installer attached to the GitHub release.

### Deferred installer work
- **Code signing** and the SmartScreen / antivirus story, if the audience grows beyond trusted people.
- **GitHub Actions** workflow that builds the installer on tag push and attaches it to the release.
- **Installer and exe icon** (the tray icon is drawn at runtime; the exe has the default icon).
- **Clean-machine check** (Visual C++ runtime, SmartScreen) if the app is shared beyond the author.
- **Small installer nits**: the model cache `.cache` metadata is bundled; the build self-test does not create a `QApplication`; the build script breaks on a repo path containing a single quote; models downloaded on demand are not removed on uninstall.
- **Upgrade-over-running-instance** and **uninstall** are covered by checklist items 18-19, not by automation.

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
