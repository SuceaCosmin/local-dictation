# Ollama discovery and guided setup — design

Date: 2026-10-16. Status: draft, awaiting approval.

## Why

Text cleanup (filler removal, punctuation) works only if a local Ollama answers at the hardcoded `http://localhost:11434`. On any other machine that is likely wrong: Ollama may be on another port (`OLLAMA_HOST`), installed but not running, or not installed at all. Today the user gets one hint ("Ollama is not running at localhost:11434") and no path forward.

Goal: on a machine we know nothing about, cleanup can be made to work from inside the app, with no config editing and no terminal.

## Goals

1. **Discover** a running Ollama on this machine, wherever it listens, and use that address automatically.
2. **Tell apart** three situations and say which one applies: running, installed-but-not-running, not installed.
3. **Guide setup** end to end: install Ollama, start it, pull a small recommended cleanup model, select it.
4. **Every step can fail safely**: each failure shows what went wrong, offers **Retry**, and offers a **manual** route (a link or an exact command to copy).
5. The same setup is available in **Settings** and in the **first-run welcome window**.

## Non-goals

- Backends other than Ollama (LM Studio, llama.cpp server, OpenAI-style APIs). Possible later; not now.
- Remote Ollama hosts. Discovery and any manual address are loopback only (`127.0.0.1`, `localhost`, `::1`).
- Choosing a model by hardware, updating or uninstalling Ollama, managing several models.
- Fixing the 30 s cold-load timeout (separate roadmap item).
- Non-Windows platforms.

## Anti-goals (would be a failure even if it works)

- Any network access the user did not trigger with a click that says what will be downloaded. Nothing downloads in the background or at startup.
- Discovery or setup blocking the UI thread, the keyboard hook, or a dictation in progress.
- Dictation getting worse when Ollama is absent: raw text is still pasted, as today.
- Running a downloaded installer without verifying it first.

## Behaviour

### Status and discovery (`ollama_setup.py`, pure logic with injected probes)

`detect()` returns one of: `RUNNING(base_url)`, `INSTALLED` (not running), `MISSING`.

Candidates are probed in this order, stopping at the first that answers:

1. The saved address from config (`ollama_url`), if any.
2. `OLLAMA_HOST` from the process environment, then from the user's registry environment (`HKCU\Environment`), because the app may have started before the variable was set. Normalise the formats Ollama accepts (`host:port`, `:port`, bare host, `http://...`; `0.0.0.0` becomes `127.0.0.1`; default port 11434).
3. `127.0.0.1:11434`.
4. Ports where an `ollama` process is listening (found from `tasklist` plus `netstat -ano`).
5. A bounded scan of 11430–11450 as a last resort (my call; builder may adjust).

A candidate counts as Ollama only if `GET /api/version` returns JSON with a `version` field. A random web server on that port must not match. Probes run concurrently with a ~0.3 s timeout, so the whole of `detect()` finishes in about a second. Loopback addresses only; a non-loopback `OLLAMA_HOST` is ignored.

If nothing answers, "installed" means any of: `ollama.exe` in `%LOCALAPPDATA%\Programs\Ollama`, `ollama` on `PATH`, or an Ollama uninstall entry in the registry. Otherwise `MISSING`.

When discovery finds a working address that differs from the saved one, it is saved to `ollama_url`. If a saved address stops answering, discovery runs again; this also happens once when a cleanup request fails with a connection error, so a changed port heals itself. This runs on the worker thread, never on the hook thread.

### Guided setup (`SetupFlow`, pure state machine; steps run on a worker thread)

Steps, each skipped if already satisfied:

| Step | Action | On failure |
|---|---|---|
| Detect | `detect()` | n/a (always yields a status) |
| Install | Download `OllamaSetup.exe` from ollama.com to a temp folder, verify it, run it silently, wait, re-detect | **Retry**; **Do it manually** opens `https://ollama.com/download` and shows the steps |
| Start | Launch the installed Ollama in the background; poll `detect()` for up to ~20 s | **Retry**; message says how to start it by hand |
| Model | `POST /api/pull` for the recommended model, stream progress | **Retry** (Ollama resumes partial pulls); **Do it manually** shows `ollama pull <model>` with a Copy button |
| Finish | Re-run `detect()`, confirm the model is listed, select it as `cleanup_model`, save | **Retry** |

Details:

- **Consent:** the Install and Model steps start only after a button whose label states the download ("Download and install Ollama (~1.5 GB)", "Download cleanup model (~0.5 GB)"). The sizes are approximations to confirm at build time.
- **Recommended model:** `qwen3.5:0.8b`, the model confirmed to work. One constant, easy to change.
- **Verifying the installer:** check the Authenticode signature (for example `Get-AuthenticodeSignature`) and that the signer is Ollama. Delete the file on failure. The exact signer string and the silent-install switch (`/SILENT`, expected since the installer is Inno Setup based) must be confirmed against the real installer before relying on them. The install is per-user, so no admin prompt is expected; if Windows asks for elevation, that is shown to the user as normal.
- **Progress:** download and pull show a progress bar with percentage, and a **Cancel** button. Cancel leaves no half-installed state (temp file removed).
- **Cancel or close mid-flow:** closing the window while a step runs cancels that step. Setup never continues invisibly.
- A step that fails does not discard the progress of earlier steps. Retry resumes from the failed step.

### UI

One reusable widget, `OllamaSetupPanel`, shows: a one-line status ("Cleanup is ready: qwen3.5:0.8b" / "Ollama is installed but not running" / "Ollama is not installed"), the next action button, a progress bar when busy, and error text with Retry and the manual route.

- **Settings:** replaces the current `cleanup_hint` label under the cleanup model picker. When setup finishes, the picker is refilled and the new model is selected (still only saved when the user presses Save, as with every Settings field). A **Detect again** button re-runs discovery. A small "Advanced" field shows the current address and allows overriding it (loopback only, validated); empty means auto.
- **Welcome window:** a new optional section, "Optional: clean up your text (removes um/uh, fixes punctuation)", containing the same panel. It never blocks "Got it" and the window stays usable while setup runs. When the user already has a working Ollama with a model, the section shows the ready state and nothing else. On first run, setup is not started automatically.
- Both places must not run setup at the same time; the second one shows the current progress instead (single shared flow object owned by `app.py`).

## Changes to existing code

- `config.py`: new `ollama_url: str = ""` (empty = auto-discover); validated as a loopback http URL when non-empty.
- `cleanup.py`: `ollama_cleanup` and `list_models` take a base URL instead of the module constants. `app.py` passes the controller a closure that resolves the address (saved, or discovered) and does the one-time rediscovery on connection failure. The `CleanupError` contract with the controller is unchanged.
- `ui/settings.py`, `ui/welcome.py`, `app.py`: host the panel. Settings keeps its injectable `list_models` for tests.
- New `ollama_setup.py`: detection, installer download and verification, process launch, pull streaming, and `SetupFlow`. OS and network calls sit behind small injected functions so the logic is unit-tested without Ollama installed. Qt stays out of it, per the project rule.
- Docs, in the same commit as the change: `CLAUDE.md` network rule (add: "Ollama installer from ollama.com and the cleanup model, only after an explicit click"), `docs/decisions.md`, `docs/architecture.md`, `docs/manual-test-checklist.md`, `README.md`, `docs/roadmap.md`.

## Testing

- **Unit (no Ollama needed):** `OLLAMA_HOST` normalisation (all formats, `0.0.0.0`, non-loopback rejected); probe order and early stop; a non-Ollama server on the port is rejected; installed-vs-missing detection; `SetupFlow` step order, skipping satisfied steps, failure then retry resuming at the failed step, cancel; NDJSON pull-progress parsing; config validation of `ollama_url`; cleanup rediscovery on connection error (and only once).
- **Panel/dialog tests** with injected flow and models, in the style of `tests/test_settings_dialog.py`; no test may touch a real Ollama or the network.
- **Manual (added to the checklist):** clean Windows VM with no Ollama (full install + pull); Ollama installed but stopped; Ollama on a non-default port via `OLLAMA_HOST`; network unplugged during install and during pull (Retry and manual route work); cancel mid-download; run setup from the welcome window and from Settings.

## Left to the builder

- Exact probe timeouts and the fallback scan range.
- How to read process listening ports (`netstat` parsing versus another Windows API) as long as it needs no new heavy dependency.
- Exact wording of messages and the layout of the panel.
- Confirming the installer URL, signer name, silent switch and approximate sizes (see "Verifying the installer").

## Calls I made (not yet confirmed with you)

- Loopback only, no remote hosts.
- Ollama only; other backends deferred.
- Advanced address override in Settings only, not in the welcome window.
- Setup never starts by itself on first run; the user clicks.
- Port detection through the running `ollama` process, with a small range scan as a fallback.
- Rediscovery once on a connection failure during cleanup.
