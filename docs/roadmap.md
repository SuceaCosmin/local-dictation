# Roadmap

Status as of v0.2.0 (installer shipped; v0.1.0 was run-from-source with Poetry).

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
