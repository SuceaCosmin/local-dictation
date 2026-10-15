# Local Dictation — notes for AI sessions

Offline, Windows-only push-to-talk dictation (a local alternative to Wispr Flow). Hold a shortcut (default Ctrl+Win), speak, release; the transcription is pasted into whatever control has keyboard focus. Nothing leaves the machine.

## Where to look
- `docs/purpose.md` — why this exists, target behavior, non-goals
- `docs/architecture.md` — module map and data flow (keep current)
- `docs/decisions.md` — why things are the way they are
- `docs/manual-test-checklist.md` — OS-level checks that unit tests cannot cover
- `docs/superpowers/specs/` and `docs/superpowers/plans/` — design specs and implementation plans

## Commands
- Install: `poetry install`
- Tests: `poetry run pytest`
- Run (with console): `poetry run local-dictation`
- Run (no console): `.venv\Scripts\pythonw.exe -m local_dictation`
- Logs: `%APPDATA%\LocalDictation\dictation.log`; config: `%APPDATA%\LocalDictation\config.json`

## Rules
- Local only: no network except `http://localhost:11434` (Ollama) and the one-time model download.
- The keyboard hook callback must never block; it only enqueues events.
- Pure logic (shortcut matching, controller, config) stays free of OS/Qt imports so it is unit-testable.
- Any change to architecture or behavior updates the relevant file in `docs/` in the same commit.
