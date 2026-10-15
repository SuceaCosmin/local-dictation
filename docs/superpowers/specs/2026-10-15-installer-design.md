# Windows installer — design

Status: approved in conversation, pending written-spec review. Branch: `feature/installer` (from `develop`).

## Goal

A Windows user double-clicks `LocalDictation-<version>-Setup.exe` and gets Local Dictation: Start menu entry, no Python, Poetry or terminal, works offline from the first launch.

**Success:** on a clean Windows machine without Python, a user can install, pass `docs/manual-test-checklist.md` items 1–9 on the installed build, turn on "Start with Windows" in the app, and uninstall without leftovers.

## Decisions (made while brainstorming)

| Topic | Decision | Reason |
|---|---|---|
| Audience | Me plus a few trusted people | Unsigned build is acceptable; no signing, no CI release automation now |
| Freezer | PyInstaller, **one-folder**, windowed | Fast start (no per-launch unpacking), fewer antivirus false positives than one-file |
| Installer | Inno Setup 6, per-user | No admin rights, built-in upgrade/uninstall, mutex-aware |
| Whisper model | **Bundle `base.en`** in the installer | Works offline from first launch; removes the silent first-run download failure mode |
| Other models | Still downloaded on demand | Only the default is bundled |
| Start with Windows | **The app owns the Run key** | One source of truth; installer has no startup task |
| Uninstall data | Ask whether to delete `%APPDATA%\LocalDictation`; default keep | Protects config and logs |
| Version | First installer is 0.2.0 | Bumped in `pyproject.toml` at the end |

Not in scope: code signing, auto-update, per-machine install, GitHub Actions release workflow, the "also deferred" robustness items in `docs/roadmap.md`.

## Components

### 1. Build pipeline (`packaging/`)

- `packaging/build.ps1` — single entry point:
  1. Read the version from `pyproject.toml`.
  2. Ensure `packaging/model-cache/base.en/` exists; if not, fetch it with faster-whisper's own downloader so the files match what the app loads today.
  3. Run PyInstaller with `packaging/local-dictation.spec` (windowed, one-folder, entry `local_dictation.app:main`). The spec collects data files and binaries for faster-whisper, CTranslate2, onnxruntime, PySide6 and sounddevice (PortAudio), and copies the model to `models/base.en/` in PyInstaller's data folder (`_internal`, next to the exe).
  4. Run the Inno compiler on `packaging/installer.iss`, passing the version; output `dist/LocalDictation-<version>-Setup.exe`.
- `dist/`, `build/` are already git-ignored; add `packaging/model-cache/`.
- PyInstaller is a Poetry dev dependency. Inno Setup 6 must be installed on the build machine (documented, not automated).

### 2. App code changes (Qt-free, unit-testable)

- `startup.launch_command()`: when `sys.frozen` is set, return the quoted `sys.executable` with no `-m`. Source runs keep `"<pythonw.exe>" -m local_dictation`.
- A small helper (a new `src/local_dictation/paths.py`) returns the app directory for frozen builds (`Path(sys.executable).parent`) and exposes the bundled-models directory. No OS or Qt imports beyond `sys`/`pathlib`.
- `transcribe._default_factory`: if frozen and `<app dir>/models/<name>` exists, load from that path; otherwise fall back to the model name (downloads as today).
- Nothing else changes: the single-instance mutex (`Local\LocalDictationSingleton`), config and log paths in `%APPDATA%\LocalDictation` already work in a frozen build.

### 3. Installer behavior (`packaging/installer.iss`)

- `PrivilegesRequired=lowest`; install dir `%LOCALAPPDATA%\Programs\Local Dictation`.
- Start menu shortcut only. No desktop icon, no startup task.
- Finish page: optional "Launch Local Dictation".
- `AppMutex=Local\LocalDictationSingleton`: Inno detects a running instance and asks the user to close it. A fixed `AppId` GUID makes a newer Setup upgrade in place.
- Uninstall: remove program files and the `HKCU\...\Run\LocalDictation` value; prompt to delete `%APPDATA%\LocalDictation` (default keep).

## Risks to front-load

1. The PyInstaller spec for faster-whisper / CTranslate2 / onnxruntime will likely need iteration. First plan task: a spike that gets a frozen exe transcribing a sample.
2. The `WH_KEYBOARD_LL` ctypes hook and pynput paste in a frozen build. Verify early on the frozen exe, including the Win-key / Start-menu suppression (still an unverified assumption, see `docs/decisions.md`).
3. Antivirus may flag the frozen exe because it installs a global keyboard hook. Accepted for the audience; documented in the README.

## Testing

- **Unit:** `launch_command()` frozen and source branches (patch `sys.frozen`, `sys.executable`); bundled-model lookup with path present and absent; existing suite stays green.
- **Build:** `build.ps1` runs cleanly and produces the Setup.exe; record its size in the docs.
- **Manual (user, clean VM or account without Python):** install; checklist items 1–9 on the installed build; toggle "Start with Windows" and confirm the Run value targets the installed exe; install over a running instance; uninstall, confirm no leftovers, and exercise both keep and delete data choices. Add these as an "installed build" section in `docs/manual-test-checklist.md`.

## Documentation (same commits as the code)

- `docs/architecture.md`: packaging layer and bundled-model lookup.
- `docs/decisions.md`: one-folder, bundled model, app owns the Run key, unsigned, Inno Setup.
- `docs/manual-test-checklist.md`: installed-build section.
- `docs/roadmap.md`: mark the installer done; move signing and CI to deferred.
- `README.md`: install instructions and a "what to expect" note (SmartScreen "Run anyway", antivirus exclusion, elevated windows limitation).

## Branching

Gitflow-like: `main` (releases, tagged), `develop` (integration), `feature/*` branched from `develop` and merged back. This work lives on `feature/installer`.
