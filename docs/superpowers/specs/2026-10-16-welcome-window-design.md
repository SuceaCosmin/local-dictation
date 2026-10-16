# First-run welcome window — design

Sub-project 1 of the UX review. Later sub-projects (separate specs): recording/status overlay, Settings redesign, visual identity (app/tray/installer icon).

## Problem
After install a new user sees no window: a grey tray dot appears (often hidden in the overflow area) and one 4-second toast says "Ready. Hold your shortcut and speak." Nothing explains the hold-to-talk gesture, and nothing shows that the speech model is still loading.

## Goal
On first launch the user sees a welcome window that (1) teaches the hold-to-talk gesture, (2) lets them change the shortcut on the spot, and (3) shows when the speech model is ready. It can be reopened from the tray.

Assumptions (confirmed in discussion): audience is people who install the Setup.exe without reading docs; PySide6 only; local-only rules unchanged. Out of scope: practice/try-it box, tray-location and start-with-Windows tips, real download percentages.

## Behaviour
- New `ui/welcome.py`: `WelcomeWindow`, a non-modal `QWidget`, fixed width about 480 px, normal title bar. One instance at a time (reopening raises the existing window).
- Content, top to bottom:
  1. Headline "Dictate anywhere. Fully offline."
  2. Keycap row built from the current record shortcut (for example `Ctrl` + `Win`) and the line "Hold, speak, release. Your words are pasted where your cursor is."
  3. Shortcut row reusing `ShortcutEdit` (including its capture-through-the-hook behaviour and cancel on close).
  4. Model status row: loading = indeterminate progress bar and "Preparing the speech model…"; ready = green "Ready. Try it now."; error = the error text in red plus "Open Settings to choose another model, or use tray → Restart hotkey."
  5. Practice box (added after the first review): a text box that takes focus when the window opens. Dictation is pasted into the focused control, so the user clicks in, holds the shortcut, speaks, and sees the text appear. The placeholder names the current shortcut and follows shortcut changes.
  6. "Got it" button that closes the window.
- Shown automatically on first launch once the tray exists; raised above other windows. Tray menu gets "How to use…" (above "Settings…") which reopens it.
- New config field `welcome_shown: bool = False`. Set to true and saved when the window first opens (not on dismiss), so a crash never causes repeat nagging. Old config files without the key load as `False`; existing users therefore see the window once after upgrading, which is accepted.
- Changing the shortcut in the window saves it through the same path as Settings (`store.update` then `apply_runtime`), so the hook rebinds immediately. A validation failure shows the message inline in the window and keeps the old shortcut.

## Model status
- Driven by the existing `Bridge.model_status` signal ("loading", "ready", "error: …"). `TrayIcon.model_status` keeps the latest status string (the tray already receives the signal on the UI thread), and `app.py` passes it to the window when opening, so a window opened later renders the correct state immediately.
- The bundled `base.en` loads in seconds, so an indeterminate bar is honest. No percentage is shown for on-demand model downloads (no progress hook exists today).
- Tray icon and tooltip are unchanged; the window complements them.

## Structure
- `ui/theme.py`: colour tokens and one stylesheet function, choosing light or dark from the system palette. Used by the welcome window first; the Settings redesign reuses it.
- `shortcut.py` (pure): `keycaps(text) -> list[str]`, for example `"ctrl+win"` gives `["Ctrl", "Win"]`, `"ctrl+shift+space"` gives `["Ctrl", "Shift", "Space"]`. Unknown keys are capitalized (first letter only); modifier order follows `MODIFIER_ORDER`.
- `config.py`: add `welcome_shown`. `from_dict` already ignores missing keys and type-mismatched values.
- `ui/tray.py`: new `welcome_requested` signal and menu action.
- `app.py`: create/raise the window, first-run check, `apply_shortcut_change` helper (validate, save, apply; returns errors), wiring. The window takes the listener and config as constructor arguments like `SettingsDialog`, and emits a `shortcut_changed(str)` signal; `app.py` does the saving.
- The keyboard hook callback is untouched. No new threads.

## Testing
- Unit: `keycaps` (modifiers order, single key, function key, unknown key); `Config` round-trip with `welcome_shown`, and loading a file without it.
- Qt (offscreen, same fake-listener style as `test_settings_dialog.py`): status transitions loading → ready and loading → error; opening when status is already ready; shortcut change emits the signal and updates the keycaps; closing cancels an in-progress capture; tray menu contains and emits "How to use…".
- Manual (`docs/manual-test-checklist.md`): first run with no config file; reopen from the tray; change the shortcut from the window and dictate with the new one; light and dark Windows themes; close during capture.

## Docs updated in the same change
`architecture.md` (new modules, data flow note), `purpose.md` (target behaviour item for the welcome window), `manual-test-checklist.md`, `roadmap.md` (this item done, remaining UX sub-projects listed), README tray paragraph.

## Not doing
Multi-step wizard, download percentage, tray-location tips, start-with-Windows prompt, a persisted "don't show again" checkbox.
