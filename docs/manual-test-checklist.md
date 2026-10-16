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

## Welcome window (run after any change to `ui/welcome.py`, `ui/tray.py` or the first-run block in `app.py`)
21. First run: start with no config file (point `APPDATA` at an empty folder) → the welcome window appears with the right keycaps; the progress bar becomes "Ready. Try it now.". Start again → it does not reappear.
22. Tray → How to use… reopens it (no second window if already open). Change the shortcut there and dictate with the new one; try an invalid one (a single letter) → message shown, old shortcut still works.
23. Close the window while "Press the keys…" is showing → afterwards normal typing still works (capture was cancelled).
24. Windows light and dark app mode: the window is readable in both.
25. Open the window with a broken model name in config → red error text, no progress bar.
26. Welcome window → Change… (capture running), then open Settings from the tray → the welcome capture is cancelled, and the Settings shortcut capture works normally.
27. Put a deliberately broken `config.json` (trailing comma) in place and start the app → the file is left untouched (the welcome window shows, defaults are used).
28. Welcome window → click in the practice box, hold the shortcut, speak, release → the text appears in the box. Change the shortcut in the window → the placeholder shows the new keys.
29. Settings: Whisper model, Device, Language and Cleanup model cannot be typed into. With Ollama running, the cleanup list shows Off plus your installed models with sizes; pick one, save, dictate with filler words ("um, so I think we should, uh, meet tomorrow") → fillers are removed.
30. Stop Ollama, dictate with a cleanup model set → raw text is pasted and one "Cleanup skipped" notification appears (not one per dictation). Open Settings with Ollama stopped → hint "Ollama is not running…" and the saved model is still shown.
31. With a cleanup model set, dictate → the tray icon turns purple with tooltip "Cleaning up text…" while Ollama works, then amber while pasting. Without a cleanup model it never turns purple.
