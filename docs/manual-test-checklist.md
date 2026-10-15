# Manual test checklist (needs a real desktop session)

Run after any change to `hotkey.py`, `paste.py`, `audio.py` or `app.py`.

1. Start: `poetry run local-dictation`. Tray icon appears; "loading" then "ready" notification.
2. Notepad: click into it, hold Ctrl+Win, say a sentence, release → text appears at the caret. Start menu did **not** open.
3. VS Code editor: same; no VS Code command palette/shortcut fires.
4. VS Code GitHub Copilot chat input: click into the box, hold, speak, release → text pasted there.
5. Press Win first, then Ctrl (reverse order) → still records, Start menu does not open.
6. Hold, press nothing else, release after < 0.3 s → nothing pasted, no error.
7. Clipboard: copy "abc", dictate, then paste manually → "abc" is back.
8. Settings → change shortcut with the capture widget (try Ctrl+Alt+Space and F9) → new shortcut works, old one no longer does.
9. Settings → stop mode "separate shortcut": release ends recording, text waits (tray "ready"); paste shortcut (default Ctrl+Shift+Space; it must not contain or be contained in the record shortcut) pastes it.
10. Unplug/disable the microphone → press shortcut → tray notification, app keeps working after re-enabling.
11. Stop Ollama, set a cleanup model → dictation still pastes the raw text.
12. Start with Windows on → reboot/login → app is running.
13. Start a second copy → it exits immediately.
14. Tray → Restart hotkey → shortcut still works.

## Installed build (run after any change to `packaging/` or before sharing an installer)
On a machine or user account without Python:
15. Run `LocalDictation-<version>-Setup.exe` (SmartScreen: More info → Run anyway). No admin prompt. Start menu has "Local Dictation".
16. Launch it from the Start menu: tray icon, "loading" then "ready" with **no network connection** (the model is bundled). Items 2–9 pass.
17. Settings → Start with Windows on → the `HKCU\...\Run\LocalDictation` value points at the installed exe (quoted); log out and in → app runs.
18. Run the installer again while the app is running → it asks to close the app, then upgrades in place; settings are kept.
19. Uninstall (Settings → Apps): the app is closed first; install folder and the Run value are gone; the prompt about settings and logs works for both Yes (folder deleted) and No (folder kept).
20. Automated variant of 15/19 (use a dummy `%APPDATA%\LocalDictation`, never real settings): `Setup.exe /VERYSILENT /CURRENTUSER /DIR=...` then `unins000.exe /VERYSILENT /SUPPRESSMSGBOXES`; without `/SUPPRESSMSGBOXES` the "delete settings?" dialog still appears and waits.
