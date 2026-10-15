# Windows Installer Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Ship `LocalDictation-<version>-Setup.exe`: a per-user installer that installs the app with the `base.en` Whisper model bundled, so it runs offline from first launch with no Python, Poetry or terminal.

**Architecture:** PyInstaller freezes the app (one-folder, windowed) into `build/pyinstaller/dist/LocalDictation/`, with the model copied to `models/base.en/` beside the exe. Inno Setup wraps that folder into a per-user installer. Three small Qt-free code changes make the app frozen-aware: `startup.launch_command()`, a new `paths.py`, and a bundled-model lookup in `transcribe.py`. A `--self-test <outfile>` flag lets the build verify a frozen exe without a UI.

**Tech Stack:** Python 3.11, Poetry 2.x, PyInstaller, Inno Setup 6 (`ISCC.exe`), PowerShell 7, pytest.

**Spec:** `docs/superpowers/specs/2026-10-15-installer-design.md`

## Global Constraints

- Windows only; Python `>=3.11,<3.14`; work happens on branch `feature/installer` (gitflow-like: `main` = tagged releases, `develop` = integration, `feature/*` branch from `develop`).
- Local only: no network except `http://localhost:11434` (Ollama) and model downloads. The build machine downloads `base.en` once into `packaging/model-cache/`; the installed app must not need the network for the default model.
- Freezer: PyInstaller **one-folder**, windowed (no console). Installer: Inno Setup 6, `PrivilegesRequired=lowest`, install dir `%LOCALAPPDATA%\Programs\Local Dictation`.
- Bundle `base.en` only; other models still download on demand.
- **The app owns the `HKCU\Software\Microsoft\Windows\CurrentVersion\Run` value `LocalDictation`.** The installer has no startup task; the uninstaller only removes the value if it points into the install dir.
- Single-instance mutex name stays `Local\LocalDictationSingleton`; the installer's `AppMutex` must match it exactly.
- No code signing, no auto-update, no CI release workflow, no per-machine install.
- Pure logic (config, shortcut, controller, `paths.py`) stays free of OS/Qt imports; the keyboard hook callback must never block.
- Any change to architecture or behavior updates the relevant file in `docs/` in the same commit.
- Commit messages end with the trailer `Co-Authored-By: Claude Sonnet 5.5 <noreply@anthropic.com>` (pass it as a second `-m`).
- Version of the first installer is `0.2.0` (set in Task 6).

## Review Focus

1. **Model name that escapes the models folder** (`..\..\x`, an absolute path, a name with a separator in `config.json`) must never resolve to a path outside `<app dir>\models`. Pinned in Task 1.
2. **A half-copied or empty `models\base.en` folder** (no `model.bin`) must fall back to the normal download, not crash the load. Pinned in Task 1.
3. **Install path with spaces** (`Local Dictation`) must produce a correctly quoted Run value. Pinned in Task 2.
4. **Frozen exe is missing a dependency's data file** (e.g. the Silero VAD onnx, PortAudio DLL) → breaks only at the first dictation, after install. The self-test exercises the model load, VAD transcription and all heavy imports so the build fails instead. Pinned in Tasks 3 and 4.
5. **Upgrade or uninstall while the app is running** (hook installed, files locked) → Inno must detect the mutex and ask the user to close the app, never leave a half-replaced install. Verified in Task 5 and by the manual pass in Task 7.

---

## File Structure

| File | Responsibility |
|---|---|
| `src/local_dictation/paths.py` (new) | Pure: `is_frozen()`, `app_dir()`, `bundled_model_path(name)` |
| `src/local_dictation/startup.py` (modify) | `launch_command()` returns the installed exe when frozen |
| `src/local_dictation/transcribe.py` (modify) | `_model_source(name)` prefers the bundled model |
| `src/local_dictation/selftest.py` (new) | `run(out_path, factory)`: import check + model load + VAD transcribe, writes `OK`/`FAIL` |
| `src/local_dictation/app.py` (modify) | `main()` dispatches `--self-test <outfile>` before any UI |
| `packaging/entry.py` (new) | PyInstaller entry script |
| `packaging/local-dictation.spec` (new) | PyInstaller spec: collects heavy deps, copies the model |
| `packaging/build.ps1` (new) | Version → model fetch → PyInstaller → self-test → Inno |
| `packaging/installer.iss` (new) | Inno Setup script |
| `tests/test_paths.py` (new), `tests/test_startup.py`, `tests/test_transcribe.py`, `tests/test_selftest.py` (new) | Unit tests |

---

### Task 1: `paths.py` (frozen detection and bundled-model lookup)

**Files:**
- Create: `src/local_dictation/paths.py`
- Test: `tests/test_paths.py`

**Interfaces:**
- Produces:
  - `is_frozen() -> bool` — `getattr(sys, "frozen", False)`.
  - `app_dir() -> Path` — `Path(sys.executable).parent` (meaningful when frozen).
  - `bundled_model_path(name: str) -> Path | None` — `app_dir()/"models"/name` only if frozen, `name` is a plain single path component, and `model.bin` exists inside; else `None`.

- [ ] **Step 1: Write the failing tests**

Create `tests/test_paths.py`:

```python
import sys

import pytest

from local_dictation import paths


def _frozen(monkeypatch, exe_dir):
    monkeypatch.setattr(sys, "frozen", True, raising=False)
    monkeypatch.setattr(sys, "executable", str(exe_dir / "LocalDictation.exe"))


def _make_model(exe_dir, name="base.en", with_bin=True):
    model = exe_dir / "models" / name
    model.mkdir(parents=True)
    (model / "config.json").write_text("{}")
    if with_bin:
        (model / "model.bin").write_bytes(b"x")
    return model


def test_not_frozen_by_default(monkeypatch):
    monkeypatch.delattr(sys, "frozen", raising=False)
    assert paths.is_frozen() is False
    assert paths.bundled_model_path("base.en") is None


def test_app_dir_is_exe_folder_when_frozen(monkeypatch, tmp_path):
    _frozen(monkeypatch, tmp_path)
    assert paths.is_frozen() is True
    assert paths.app_dir() == tmp_path


def test_bundled_model_found(monkeypatch, tmp_path):
    _frozen(monkeypatch, tmp_path)
    model = _make_model(tmp_path)
    assert paths.bundled_model_path("base.en") == model


def test_unbundled_model_name_returns_none(monkeypatch, tmp_path):
    _frozen(monkeypatch, tmp_path)
    _make_model(tmp_path)
    assert paths.bundled_model_path("small.en") is None


def test_model_folder_without_model_bin_is_ignored(monkeypatch, tmp_path):
    _frozen(monkeypatch, tmp_path)
    _make_model(tmp_path, with_bin=False)
    assert paths.bundled_model_path("base.en") is None


@pytest.mark.parametrize("name", ["..", "..\\base.en", "../base.en", "C:\\models\\base.en",
                                  "sub\\base.en", "sub/base.en", "", "."])
def test_name_cannot_escape_models_folder(monkeypatch, tmp_path, name):
    _frozen(monkeypatch, tmp_path)
    _make_model(tmp_path)
    (tmp_path / "model.bin").write_bytes(b"x")  # a decoy one level up
    assert paths.bundled_model_path(name) is None
```

- [ ] **Step 2: Run to verify failure**

Run: `poetry run pytest tests/test_paths.py -v`
Expected: FAIL — `ImportError: cannot import name 'paths'`.

- [ ] **Step 3: Implement**

Create `src/local_dictation/paths.py`:

```python
"""Locations that differ between a source run and a frozen (installed) build. Pure: no OS/Qt imports."""
from __future__ import annotations

import sys
from pathlib import Path


def is_frozen() -> bool:
    return bool(getattr(sys, "frozen", False))


def app_dir() -> Path:
    return Path(sys.executable).parent


def bundled_model_path(name: str) -> Path | None:
    """Folder of the Whisper model shipped inside the installer, or None to use the normal download."""
    if not is_frozen():
        return None
    if not name or name in (".", "..") or any(sep in name for sep in ("/", "\\", ":")):
        return None
    folder = app_dir() / "models" / name
    return folder if (folder / "model.bin").is_file() else None
```

- [ ] **Step 4: Run to verify pass**

Run: `poetry run pytest tests/test_paths.py -v`
Expected: all PASS.

- [ ] **Step 5: Commit**

```bash
git add src/local_dictation/paths.py tests/test_paths.py
git commit -m "Add paths module: frozen detection and bundled-model lookup" -m "Co-Authored-By: Claude Sonnet 5.5 <noreply@anthropic.com>"
```

---

### Task 2: Frozen-aware `launch_command()`

**Files:**
- Modify: `src/local_dictation/startup.py:12-15`
- Test: `tests/test_startup.py`

**Interfaces:**
- Consumes: `paths.is_frozen() -> bool` (Task 1).
- Produces: `launch_command() -> str` — frozen: `"<sys.executable>"` quoted, no `-m`; source: unchanged (`"<pythonw.exe>" -m local_dictation`).

- [ ] **Step 1: Write the failing tests**

Append to `tests/test_startup.py` (add `import sys` to the imports at the top):

```python
def test_command_when_frozen_is_the_installed_exe_quoted(monkeypatch):
    exe = r"C:\Users\Some One\AppData\Local\Programs\Local Dictation\LocalDictation.exe"
    monkeypatch.setattr(sys, "frozen", True, raising=False)
    monkeypatch.setattr(sys, "executable", exe)
    assert startup.launch_command() == f'"{exe}"'


def test_command_from_source_is_unchanged_when_not_frozen(monkeypatch):
    monkeypatch.delattr(sys, "frozen", raising=False)
    assert startup.launch_command().lower().endswith("-m local_dictation")
```

- [ ] **Step 2: Run to verify failure**

Run: `poetry run pytest tests/test_startup.py -v`
Expected: `test_command_when_frozen_is_the_installed_exe_quoted` FAILS (returns the pythonw form).

- [ ] **Step 3: Implement**

In `src/local_dictation/startup.py` add `from . import paths` after the `from pathlib import Path` import, and replace `launch_command`:

```python
def launch_command() -> str:
    exe = Path(sys.executable)
    if paths.is_frozen():
        return f'"{exe}"'
    pythonw = exe.with_name("pythonw.exe")
    return f'"{pythonw if pythonw.exists() else exe}" -m local_dictation'
```

- [ ] **Step 4: Run to verify pass**

Run: `poetry run pytest tests/test_startup.py -v`
Expected: all PASS (the existing `test_command_uses_pythonw_and_module` still passes).

- [ ] **Step 5: Commit**

```bash
git add src/local_dictation/startup.py tests/test_startup.py
git commit -m "Make launch_command frozen-aware for installed builds" -m "Co-Authored-By: Claude Sonnet 5.5 <noreply@anthropic.com>"
```

---

### Task 3: Bundled-model lookup and `--self-test`

**Files:**
- Modify: `src/local_dictation/transcribe.py:13-15`, `src/local_dictation/app.py` (`main()`)
- Create: `src/local_dictation/selftest.py`
- Test: `tests/test_transcribe.py`, `tests/test_selftest.py`

**Interfaces:**
- Consumes: `paths.bundled_model_path(name) -> Path | None` (Task 1).
- Produces:
  - `transcribe._model_source(name: str) -> str` — bundled folder path as `str`, else `name`.
  - `transcribe._default_factory(name, device)` — unchanged signature; passes `_model_source(name)` to `WhisperModel`.
  - `selftest.run(out_path: Path, factory=_default_factory) -> int` — writes `OK source=<str>` and returns 0, or `FAIL <ExceptionType>: <msg>` and returns 1.
  - `app.main()` handles `LocalDictation.exe --self-test <outfile>` before logging, mutex or Qt.

- [ ] **Step 1: Write the failing tests**

Append to `tests/test_transcribe.py`:

```python
from local_dictation import transcribe as transcribe_module


def test_model_source_prefers_bundled_folder(monkeypatch, tmp_path):
    monkeypatch.setattr(transcribe_module.paths, "bundled_model_path", lambda name: tmp_path / name)
    assert transcribe_module._model_source("base.en") == str(tmp_path / "base.en")


def test_model_source_falls_back_to_name(monkeypatch):
    monkeypatch.setattr(transcribe_module.paths, "bundled_model_path", lambda name: None)
    assert transcribe_module._model_source("small.en") == "small.en"


def test_default_factory_loads_from_the_resolved_source(monkeypatch):
    seen = {}

    class FakeWhisper:
        def __init__(self, source, **kwargs):
            seen["source"], seen["kwargs"] = source, kwargs

    monkeypatch.setattr("faster_whisper.WhisperModel", FakeWhisper)
    monkeypatch.setattr(transcribe_module, "_model_source", lambda name: "C:\\bundled\\base.en")
    transcribe_module._default_factory("base.en", "cpu")
    assert seen["source"] == "C:\\bundled\\base.en"
    assert seen["kwargs"]["compute_type"] == "int8"
```

Create `tests/test_selftest.py`:

```python
from types import SimpleNamespace

from local_dictation import selftest


class FakeModel:
    def transcribe(self, audio, beam_size=None, vad_filter=None):
        assert vad_filter is True
        return iter([SimpleNamespace(text="")]), None


def test_ok_writes_file_and_returns_zero(tmp_path):
    out = tmp_path / "result.txt"
    assert selftest.run(out, factory=lambda name, device: FakeModel()) == 0
    assert out.read_text().startswith("OK source=")


def test_failure_writes_reason_and_returns_one(tmp_path):
    out = tmp_path / "result.txt"

    def factory(name, device):
        raise FileNotFoundError("model.bin")

    assert selftest.run(out, factory=factory) == 1
    assert out.read_text().startswith("FAIL FileNotFoundError: model.bin")
```

- [ ] **Step 2: Run to verify failure**

Run: `poetry run pytest tests/test_transcribe.py tests/test_selftest.py -v`
Expected: FAIL — `AttributeError: ... has no attribute 'paths'` / `ImportError: cannot import name 'selftest'`.

- [ ] **Step 3: Implement**

In `src/local_dictation/transcribe.py` add `from . import paths` after `from typing import Callable`, and replace `_default_factory`:

```python
def _model_source(name: str) -> str:
    bundled = paths.bundled_model_path(name)
    return str(bundled) if bundled else name


def _default_factory(name: str, device: str):
    from faster_whisper import WhisperModel
    compute = "int8" if device == "cpu" else "float32"
    return WhisperModel(_model_source(name), device=device, compute_type=compute,
                        cpu_threads=os.cpu_count() or 4)
```

Create `src/local_dictation/selftest.py`:

```python
"""Build verification: `LocalDictation.exe --self-test <outfile>` proves a frozen build is complete."""
from __future__ import annotations

from pathlib import Path

import numpy as np

from .transcribe import _default_factory, _model_source


def run(out_path: Path, factory=_default_factory) -> int:
    try:
        # Every heavy dependency must import inside the frozen build.
        import ctranslate2  # noqa: F401
        import faster_whisper  # noqa: F401
        import onnxruntime  # noqa: F401
        import pynput.keyboard  # noqa: F401
        import pyperclip  # noqa: F401
        import sounddevice  # noqa: F401
        from PySide6 import QtWidgets  # noqa: F401

        from . import hotkey  # noqa: F401  (ctypes hook module)

        model = factory("base.en", "cpu")
        # Silence still runs the VAD (onnxruntime + the Silero asset) and the decoder.
        segments, _ = model.transcribe(np.zeros(32000, dtype="float32"), beam_size=1, vad_filter=True)
        "".join(s.text for s in segments)
        result, code = f"OK source={_model_source('base.en')}", 0
    except Exception as e:  # report every failure; the build reads this file
        result, code = f"FAIL {type(e).__name__}: {e}", 1
    Path(out_path).write_text(result, encoding="utf-8")
    return code
```

In `src/local_dictation/app.py`, add `from pathlib import Path` to the stdlib imports and, as the first lines of `main()`:

```python
def main() -> int:
    if len(sys.argv) == 3 and sys.argv[1] == "--self-test":
        from .selftest import run
        return run(Path(sys.argv[2]))
    setup_logging()
```

(keep the rest of `main()` unchanged).

- [ ] **Step 4: Run to verify pass**

Run: `poetry run pytest -q`
Expected: the full suite PASSES. Also run the self-test from source once: `poetry run python -m local_dictation --self-test %TEMP%\st.txt` then read the file; expected `OK source=base.en` (not frozen, so not bundled; needs the cached model, which exists on this machine).

- [ ] **Step 5: Commit**

```bash
git add src/local_dictation/transcribe.py src/local_dictation/selftest.py src/local_dictation/app.py tests/test_transcribe.py tests/test_selftest.py
git commit -m "Load the bundled Whisper model when frozen; add --self-test" -m "Co-Authored-By: Claude Sonnet 5.5 <noreply@anthropic.com>"
```

---

### Task 4: PyInstaller build (the spike, then `build.ps1` stages 1–3)

This is the riskiest task: expect to iterate on the spec. The self-test names the first missing module or data file; add it to the spec and rebuild until `OK` is reported.

**Files:**
- Modify: `pyproject.toml` (dev dependency), `.gitignore`
- Create: `packaging/entry.py`, `packaging/local-dictation.spec`, `packaging/build.ps1`

**Interfaces:**
- Consumes: `--self-test <outfile>` (Task 3).
- Produces: `packaging/build.ps1 [-SkipInstaller]` — writes `build/pyinstaller/dist/LocalDictation/LocalDictation.exe` plus `models/base.en/`; `-SkipInstaller` stops after the frozen self-test. Reads `$version` from `pyproject.toml`.

- [ ] **Step 1: Add PyInstaller and ignore rules**

Run: `poetry add --group dev pyinstaller`
Append to `.gitignore`: `packaging/model-cache/`

- [ ] **Step 2: Create the entry script**

`packaging/entry.py`:

```python
from local_dictation.app import main

raise SystemExit(main())
```

- [ ] **Step 3: Create the spec**

`packaging/local-dictation.spec` (PyInstaller specs are Python; `SPECPATH` is provided by PyInstaller):

```python
# -*- mode: python -*-
from pathlib import Path

from PyInstaller.utils.hooks import collect_all

root = Path(SPECPATH).parent
datas, binaries, hiddenimports = [], [], []
for pkg in ("faster_whisper", "ctranslate2", "onnxruntime", "sounddevice", "_sounddevice_data",
            "av", "tokenizers"):
    d, b, h = collect_all(pkg)
    datas += d
    binaries += b
    hiddenimports += h
hiddenimports += ["pynput.keyboard._win32", "pynput.mouse._win32"]

# The Whisper model fetched by build.ps1 ships beside the exe as models/base.en.
datas += [(str(root / "packaging" / "model-cache" / "base.en"), "models/base.en")]

a = Analysis(
    [str(root / "packaging" / "entry.py")],
    pathex=[str(root / "src")],
    binaries=binaries,
    datas=datas,
    hiddenimports=hiddenimports,
)
pyz = PYZ(a.pure)
exe = EXE(pyz, a.scripts, [], exclude_binaries=True, name="LocalDictation",
          console=False, upx=False)
coll = COLLECT(exe, a.binaries, a.datas, name="LocalDictation", upx=False)
```

- [ ] **Step 4: Create `build.ps1` (stages 1–3; the Inno stage is added in Task 5)**

`packaging/build.ps1`:

```powershell
param([switch]$SkipInstaller)
$ErrorActionPreference = "Stop"
$root = Split-Path $PSScriptRoot -Parent
Set-Location $root

# 1. Version from pyproject.toml
$version = (Select-String -Path "pyproject.toml" -Pattern '^version = "(.+)"').Matches[0].Groups[1].Value
Write-Host "Building Local Dictation $version"

# 2. Bundled model (cached between builds)
$model = Join-Path $root "packaging\model-cache\base.en"
if (-not (Test-Path (Join-Path $model "model.bin"))) {
    Write-Host "Fetching base.en model..."
    poetry run python -c "from faster_whisper.utils import download_model; download_model('base.en', output_dir=r'$model')"
    if ($LASTEXITCODE -ne 0) { throw "model download failed" }
}

# 3. Freeze, then prove the frozen exe is complete
$out = Join-Path $root "build\pyinstaller"
poetry run pyinstaller packaging\local-dictation.spec --noconfirm --distpath "$out\dist" --workpath "$out\work"
if ($LASTEXITCODE -ne 0) { throw "PyInstaller failed" }
$exe = Join-Path $out "dist\LocalDictation\LocalDictation.exe"
$result = Join-Path $out "selftest.txt"
Remove-Item $result -ErrorAction SilentlyContinue
Start-Process $exe -ArgumentList "--self-test", "`"$result`"" -Wait
$text = if (Test-Path $result) { Get-Content $result -Raw } else { "no result file (frozen exe crashed)" }
if (-not $text.StartsWith("OK")) { throw "frozen self-test failed: $text" }
if ($text -notmatch "models") { throw "frozen build is not using the bundled model: $text" }
Write-Host "Frozen self-test: $text"
$size = (Get-ChildItem "$out\dist\LocalDictation" -Recurse | Measure-Object Length -Sum).Sum / 1MB
Write-Host ("Frozen folder size: {0:N0} MB" -f $size)

if ($SkipInstaller) { return }
# 4. Installer stage is added in Task 5.
```

- [ ] **Step 5: Build and iterate until the self-test passes**

Run: `pwsh packaging\build.ps1 -SkipInstaller`
Expected on success: `Frozen self-test: OK source=...\models\base.en` and a folder size line. On `FAIL ...` or "no result file": read the error (for a crash, run the exe once from a console: `build\pyinstaller\dist\LocalDictation\LocalDictation.exe --self-test x.txt`, or temporarily set `console=True` in the spec to see the traceback), add the missing package to the `collect_all` list or `hiddenimports`, rebuild. Record the final folder size.

- [ ] **Step 6: Human check of the frozen exe (needs a desktop session)**

Run `build\pyinstaller\dist\LocalDictation\LocalDictation.exe`. Walk `docs/manual-test-checklist.md` items 1–9 against it, in particular 2–5 (Win key / Start menu suppression, still an unverified assumption). Stop and report to the user if the hook, paste or tray behave differently from the source run. Quit the app from the tray afterwards.

- [ ] **Step 7: Commit**

```bash
git add pyproject.toml poetry.lock .gitignore packaging/entry.py packaging/local-dictation.spec packaging/build.ps1
git commit -m "Add PyInstaller build with bundled model and frozen self-test" -m "Co-Authored-By: Claude Sonnet 5.5 <noreply@anthropic.com>"
```

---

### Task 5: Inno Setup installer

Prerequisite: Inno Setup 6 on the build machine (not installed here yet): `winget install --id JRSoftware.InnoSetup -e`.

**Files:**
- Create: `packaging/installer.iss`
- Modify: `packaging/build.ps1` (stage 4)

**Interfaces:**
- Consumes: the frozen folder `build/pyinstaller/dist/LocalDictation/` (Task 4); mutex name `Local\LocalDictationSingleton` (`app.py`).
- Produces: `dist/LocalDictation-<version>-Setup.exe`; `ISCC` receives `/DAppVersion=<version>`.

- [ ] **Step 1: Create `packaging/installer.iss`**

```ini
; Version is passed in by build.ps1: ISCC /DAppVersion=0.2.0 installer.iss
#ifndef AppVersion
  #error AppVersion must be defined (run packaging\build.ps1)
#endif

[Setup]
AppId={{8F3B6C1E-4D27-4A55-9B0E-5C2A7D1F6E93}
AppName=Local Dictation
AppVersion={#AppVersion}
AppPublisher=Local Dictation
DefaultDirName={localappdata}\Programs\Local Dictation
DefaultGroupName=Local Dictation
DisableProgramGroupPage=yes
PrivilegesRequired=lowest
AppMutex=Local\LocalDictationSingleton
OutputDir=..\dist
OutputBaseFilename=LocalDictation-{#AppVersion}-Setup
Compression=lzma2
SolidCompression=yes
ArchitecturesInstallIn64BitMode=x64compatible
WizardStyle=modern
UninstallDisplayName=Local Dictation

[Files]
Source: "..\build\pyinstaller\dist\LocalDictation\*"; DestDir: "{app}"; Flags: recursesubdirs ignoreversion

[Icons]
Name: "{autoprograms}\Local Dictation"; Filename: "{app}\LocalDictation.exe"

[Run]
Filename: "{app}\LocalDictation.exe"; Description: "Launch Local Dictation"; Flags: nowait postinstall skipifsilent

[Code]
const
  RunKey = 'Software\Microsoft\Windows\CurrentVersion\Run';
  RunValue = 'LocalDictation';

procedure CurUninstallStepChanged(CurUninstallStep: TUninstallStep);
var
  Command: String;
  DataDir: String;
begin
  if CurUninstallStep <> usUninstall then exit;

  { The app owns this value; remove it only if it points into this install. }
  if RegQueryStringValue(HKCU, RunKey, RunValue, Command) then
    if Pos(Lowercase(ExpandConstant('{app}')), Lowercase(Command)) > 0 then
      RegDeleteValue(HKCU, RunKey, RunValue);

  DataDir := ExpandConstant('{userappdata}\LocalDictation');
  if DirExists(DataDir) then
    if SuppressibleMsgBox('Also delete your settings and logs?' + #13#10 + DataDir,
                          mbConfirmation, MB_YESNO or MB_DEFBUTTON2, IDNO) = IDYES then
      DelTree(DataDir, True, True, True);
end;
```

- [ ] **Step 2: Add stage 4 to `build.ps1`**

Replace the final two lines (`if ($SkipInstaller) { return }` and the stage-4 comment) with:

```powershell
if ($SkipInstaller) { return }

# 4. Installer
$iscc = @(
    (Get-Command ISCC.exe -ErrorAction SilentlyContinue).Source,
    "$env:LOCALAPPDATA\Programs\Inno Setup 6\ISCC.exe",
    "${env:ProgramFiles(x86)}\Inno Setup 6\ISCC.exe",
    "$env:ProgramFiles\Inno Setup 6\ISCC.exe"
) | Where-Object { $_ -and (Test-Path $_) } | Select-Object -First 1
if (-not $iscc) { throw "Inno Setup 6 not found. Install it: winget install --id JRSoftware.InnoSetup -e" }
& $iscc "/DAppVersion=$version" "packaging\installer.iss"
if ($LASTEXITCODE -ne 0) { throw "Inno Setup failed" }
$setup = Join-Path $root "dist\LocalDictation-$version-Setup.exe"
Write-Host ("Installer: {0} ({1:N0} MB)" -f $setup, ((Get-Item $setup).Length / 1MB))
```

- [ ] **Step 3: Build the installer**

Run: `pwsh packaging\build.ps1`
Expected: ends with `Installer: ...\dist\LocalDictation-0.1.0-Setup.exe (NNN MB)` (the version becomes 0.2.0 in Task 6). Record the size.

- [ ] **Step 4: Automated install / self-test / uninstall smoke test**

Run these in PowerShell (a throwaway directory; uses silent flags so nothing prompts):

```powershell
$setup = (Get-ChildItem dist\LocalDictation-*-Setup.exe | Select-Object -First 1).FullName
$dir = "C:\tmp\ld-install-test"
Start-Process $setup -ArgumentList "/VERYSILENT","/CURRENTUSER","/DIR=`"$dir`"","/LOG=C:\tmp\ld-install.log" -Wait
Test-Path "$dir\LocalDictation.exe"                      # expect True
Test-Path "$dir\models\base.en\model.bin"                # expect True
Start-Process "$dir\LocalDictation.exe" -ArgumentList "--self-test","C:\tmp\ld-st.txt" -Wait
Get-Content C:\tmp\ld-st.txt                             # expect: OK source=C:\tmp\ld-install-test\models\base.en
Start-Process "$dir\unins000.exe" -ArgumentList "/VERYSILENT","/SUPPRESSMSGBOXES" -Wait   # /VERYSILENT alone still shows the "delete settings?" dialog and waits
Test-Path $dir                                           # expect False
Test-Path "$env:APPDATA\LocalDictation"                  # expect unchanged (silent uninstall keeps data)
```

If `$dir` still exists after uninstall, check `C:\tmp\ld-install.log` and fix the script.

- [ ] **Step 5: Commit**

```bash
git add packaging/installer.iss packaging/build.ps1
git commit -m "Add Inno Setup per-user installer" -m "Co-Authored-By: Claude Sonnet 5.5 <noreply@anthropic.com>"
```

---

### Task 6: Docs, README and version 0.2.0

**Files:**
- Modify: `docs/architecture.md`, `docs/decisions.md`, `docs/manual-test-checklist.md`, `docs/roadmap.md`, `README.md`, `CLAUDE.md`, `pyproject.toml`, `src/local_dictation/__init__.py`, `tests/test_smoke.py`

- [ ] **Step 1: Bump the version (test first)**

In `tests/test_smoke.py` change the asserted version to `"0.2.0"`, run `poetry run pytest tests/test_smoke.py` (expect FAIL), then set `version = "0.2.0"` in `pyproject.toml` and `__version__ = "0.2.0"` in `src/local_dictation/__init__.py`. Re-run (expect PASS).

- [ ] **Step 2: `docs/architecture.md`**

Add these rows to the module table (after `startup.py`):

```
| `paths.py` | Pure: `is_frozen()`, `app_dir()`, `bundled_model_path(name)` (model shipped in the installer) |
| `selftest.py` | `--self-test <outfile>`: imports every heavy dependency, loads the model, runs VAD transcription; used by the build to verify a frozen exe |
```

Append a section:

```
## Packaging (`packaging/`)
`build.ps1` → reads the version from `pyproject.toml` → fetches `base.en` into `packaging/model-cache/` → PyInstaller (`local-dictation.spec`, one-folder, windowed) → runs the frozen exe with `--self-test` → Inno Setup (`installer.iss`) → `dist/LocalDictation-<version>-Setup.exe`. The model sits beside the exe in `models/base.en/`; `transcribe._model_source` prefers it when frozen. Per-user install under `%LOCALAPPDATA%\Programs\Local Dictation`; the installer's `AppMutex` is the app's single-instance mutex.
```

- [ ] **Step 3: `docs/decisions.md`**

Add these bullets above "Unverified assumptions":

```
- **PyInstaller one-folder, not one-file** — no per-launch unpacking of a large tree, faster start, fewer antivirus false positives. Cost: a folder instead of a single exe (the installer hides this).
- **Inno Setup, per-user** — no admin rights, built-in upgrade and uninstall, detects a running instance through the app's mutex.
- **`base.en` bundled in the installer** — works offline from the first launch and removes the silent first-run download failure. Cost: a larger installer. Other models still download on demand.
- **The app owns the HKCU Run value** — the in-app checkbox is the only switch; the installer has no startup task. `apply_startup` rewrites the value on every start, so a moved or upgraded install self-heals. The uninstaller removes the value only if it points into the install folder.
- **Unsigned installer** — the audience is the author and a few trusted people. Expect a SmartScreen "Unknown publisher" prompt and possible antivirus flags (the app installs a global keyboard hook). Signing can be added later as a build step.
```

- [ ] **Step 4: `docs/manual-test-checklist.md`**

Append:

```

## Installed build (run after any change to `packaging/` or before sharing an installer)
On a machine or user account without Python:
15. Run `LocalDictation-<version>-Setup.exe` (SmartScreen: More info → Run anyway). No admin prompt. Start menu has "Local Dictation".
16. Launch it from the Start menu: tray icon, "loading" then "ready" with **no network connection** (the model is bundled). Items 2–9 pass.
17. Settings → Start with Windows on → the `HKCU\...\Run\LocalDictation` value points at the installed exe (quoted); log out and in → app runs.
18. Run the installer again while the app is running → it asks to close the app, then upgrades in place; settings are kept.
19. Uninstall (Settings → Apps): the app is closed first; install folder and the Run value are gone; the prompt about settings and logs works for both Yes (folder deleted) and No (folder kept).
```

- [ ] **Step 5: `docs/roadmap.md`, `README.md`, `CLAUDE.md`**

- `docs/roadmap.md`: change the header to `Status as of v0.2.0 (installer shipped).`, replace the "Next: installer" section with a short "Done: installer (v0.2.0)" note linking the spec and listing the leftovers: code signing and SmartScreen, a GitHub Actions workflow that builds the installer on tag push, and an installer icon. Keep the "Also deferred" section.
- `README.md`: replace "Install and run" with an **Install** section (download `LocalDictation-<version>-Setup.exe`, run it, expect the SmartScreen "More info → Run anyway" prompt and add an antivirus exclusion if the exe is quarantined, start it from the Start menu, the model is included so no download is needed) followed by a **Run from source** subsection holding the existing Poetry instructions. Add a **Build the installer** note: Inno Setup 6 (`winget install --id JRSoftware.InnoSetup -e`), then `pwsh packaging\build.ps1`.
- `CLAUDE.md`: add `- Build installer: pwsh packaging\build.ps1 (needs Inno Setup 6)` to the Commands list, and add `- Branching: gitflow-like. main = tagged releases, develop = integration, feature/* branch from develop.` to the Rules list.

- [ ] **Step 6: Full verification and commit**

Run: `poetry run pytest -q` (expect all PASS), then `pwsh packaging\build.ps1` (expect `LocalDictation-0.2.0-Setup.exe`).

```bash
git add docs README.md CLAUDE.md pyproject.toml src/local_dictation/__init__.py tests/test_smoke.py
git commit -m "Document the installer and bump to 0.2.0" -m "Co-Authored-By: Claude Sonnet 5.5 <noreply@anthropic.com>"
```

---

### Task 7: Clean-machine verification and integration

**Files:** none (manual verification; fixes go back to the owning task).

- [ ] **Step 1: Human clean-machine pass.** Copy `dist\LocalDictation-0.2.0-Setup.exe` to a machine or VM without Python (or a fresh Windows user account) and run checklist items 1–9 and 15–19. Report any failure; fix it in the task that owns it and rebuild.
- [ ] **Step 2: Record sizes.** Add the installer size and installed-folder size to the `docs/roadmap.md` installer note; commit `Record installer size`.
- [ ] **Step 3: Integrate (ask the user first).** Merge `feature/installer` into `develop` with `--no-ff`. Merging `develop` into `main` and tagging `v0.2.0` happens only when the user says so. Pushing anything to `origin` also needs the user's go-ahead.
