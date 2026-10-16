# Ollama discovery and guided setup Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Cleanup finds Ollama wherever it listens on this machine, and a guided Install → Start → Pull-model flow (with Retry and manual routes) is available in Settings and in the welcome window.

**Architecture:** Three small modules with a strict split: `ollama_discovery.py` (pure detection, all I/O injected), `ollama_flow.py` (pure `SetupFlow`, derives its position from `detect()` on every run so Retry resumes naturally), `ollama_actions.py` (the only module doing real I/O: registry, `tasklist`/`netstat`, download, installer, launch, pull). `ui/ollama_panel.py` holds one shared `SetupRunner` (worker thread + Qt signals, owned by `app.py`) and the `OllamaSetupPanel` view used by both windows.

**Tech Stack:** Python 3.x, PySide6, pytest, stdlib only (`urllib`, `subprocess`, `winreg`, `concurrent.futures`). No new dependencies.

**Spec:** `docs/superpowers/specs/2026-10-16-ollama-discovery-and-setup-design.md`. The spec names one `ollama_setup.py`; this plan splits it into the three modules above so the pure logic stays free of I/O (project rule).

## Global Constraints

- Local only: loopback addresses only (`127.0.0.1`, `localhost`, `::1`); a non-loopback `OLLAMA_HOST` is ignored.
- Network only after an explicit click whose label states the download; nothing downloads at startup or in the background.
- The keyboard hook callback must never block; discovery and setup run on worker threads only.
- Pure logic stays free of OS/Qt imports (unit-testable without Ollama or a network).
- A candidate counts as Ollama only if `GET /api/version` returns JSON containing `version`.
- Recommended model constant: `qwen3.5:0.8b`. Probe timeout ~0.3 s; start-wait ~20 s; fallback scan ports 11430–11450.
- Any behaviour or architecture change updates `docs/` in the same commit.
- Branching: `feature/ollama-setup` from `develop`. Commit messages end with `Co-Authored-By: Claude Sonnet 5.5 <noreply@anthropic.com>`.

## Review Focus

1. A non-Ollama web server answers on 11434 (or on an `OLLAMA_HOST` port): must be rejected, not saved as the address.
2. `OLLAMA_HOST` in odd forms (`:11500`, `0.0.0.0:11500`, `http://localhost:11500/`, `[::1]:11500`, garbage, a remote host): normalised or ignored, never a crash.
3. Ollama down for a long session: cleanup must not run a ~1 s rediscovery before every paste (rediscovery is rate-limited).
4. Network drops mid-download or mid-pull, or the user cancels: temp installer removed, no half-installed state, Retry works.
5. Hand-edited config with a bad `ollama_url` (remote host, junk): falls back to defaults like other invalid values, never crashes startup.

---

### Task 1: Branch and `ollama_url` config field

**Files:**
- Modify: `src/local_dictation/config.py`
- Test: `tests/test_config.py`

**Interfaces:**
- Produces: `Config.ollama_url: str = ""` (empty = auto-discover); `validate()` reports an error when non-empty and not an `http://` URL whose host is loopback. Task 2, 3, 8, 9 rely on this field.

- [ ] **Step 1:** `git switch develop && git switch -c feature/ollama-setup`.
- [ ] **Step 2: Write failing tests** in `tests/test_config.py`: `test_ollama_url_defaults_to_empty`; `test_ollama_url_accepts_loopback_http` (parametrize `http://127.0.0.1:11500`, `http://localhost:11434`, `http://[::1]:11500`); `test_ollama_url_rejects_remote_and_junk` (parametrize `http://example.com:11434`, `ftp://127.0.0.1`, `not a url`; assert `validate()` non-empty); `test_invalid_ollama_url_in_file_falls_back_to_defaults` (write JSON with a remote URL, `ConfigStore(path)` → `invalid is True` and `config.ollama_url == ""`).
- [ ] **Step 3:** Run `poetry run pytest tests/test_config.py -v`; expect the new tests FAIL.
- [ ] **Step 4:** Add the field and validation (use `urllib.parse.urlsplit`; hostname in `{"127.0.0.1","localhost","::1"}`).
- [ ] **Step 5:** Run `poetry run pytest tests/test_config.py -v`; expect PASS.
- [ ] **Step 6:** Commit `feat(config): add ollama_url setting`.

### Task 2: `cleanup.py` takes a base URL and distinguishes "unreachable"

**Files:**
- Modify: `src/local_dictation/cleanup.py`
- Test: `tests/test_cleanup.py`

**Interfaces:**
- Produces: `DEFAULT_OLLAMA_URL = "http://127.0.0.1:11434"`; `class OllamaUnreachable(CleanupError)`; `ollama_cleanup(text: str, model: str, base_url: str = DEFAULT_OLLAMA_URL) -> str`; `list_models(timeout: float = 1.5, base_url: str = DEFAULT_OLLAMA_URL) -> list[OllamaModel] | None`. Remove the two module URL constants.
- `OllamaUnreachable` is raised for `ConnectionError` and for `URLError` whose `reason` is not a timeout; timeouts and bad replies stay plain `CleanupError`.

- [ ] **Step 1: Write failing tests:** `test_cleanup_posts_to_given_base_url` (assert `opener.request.full_url == "http://127.0.0.1:11500/api/generate"`); `test_list_models_uses_given_base_url`; `test_refused_connection_raises_unreachable` (URLError("refused") → `OllamaUnreachable`); `test_timeout_is_not_unreachable` (`TimeoutError` → `CleanupError` and `not isinstance(e, OllamaUnreachable)`). Update the existing URL assertion to the new default.
- [ ] **Step 2:** Run `poetry run pytest tests/test_cleanup.py -v`; expect FAIL.
- [ ] **Step 3:** Implement as specified in Interfaces.
- [ ] **Step 4:** Run `poetry run pytest tests/test_cleanup.py tests/test_controller.py -v`; expect PASS.
- [ ] **Step 5:** Commit `refactor(cleanup): configurable Ollama address`.

### Task 3: Pure discovery (`ollama_discovery.py`)

**Files:**
- Create: `src/local_dictation/ollama_discovery.py`
- Test: `tests/test_ollama_discovery.py`

**Interfaces:**
- Produces:
  - `class Status(Enum): RUNNING, INSTALLED, MISSING`
  - `@dataclass(frozen=True) class Detection: status: Status; base_url: str | None`
  - `parse_ollama_host(value: str) -> str | None` returns `http://127.0.0.1:PORT` (or the loopback host given, normalised) or `None` for empty, junk or non-loopback; `0.0.0.0` and `::` map to `127.0.0.1`; missing port → 11434; trailing slash/path stripped.
  - `is_ollama(base_url: str, *, timeout: float = 0.3) -> bool` (`GET {base_url}/api/version`, JSON with `version`; any exception → False).
  - `detect(*, saved_url: str, env: Mapping[str, str], registry_host: Callable[[], str | None], process_ports: Callable[[], list[int]], installed: Callable[[], bool], probe: Callable[[str], bool] = is_ollama) -> Detection`. Candidate order: saved URL, `env["OLLAMA_HOST"]`, `registry_host()`, `127.0.0.1:11434`, each of `process_ports()`, ports 11430–11450; de-duplicate; probe all concurrently (`ThreadPoolExecutor`) but return the **earliest candidate in that order** that answered. No answer → `INSTALLED` if `installed()` else `MISSING`.

- [ ] **Step 1: Write failing tests:** `test_parse_ollama_host` parametrized over the forms in Review Focus 2 with exact expected outputs (`":11500"`→`http://127.0.0.1:11500`, `"0.0.0.0:11500"`→same host mapped, `"[::1]:11500"`→`http://[::1]:11500`, `"localhost"`→`http://localhost:11434`, `"example.com:11434"`→None, `""`→None, `"::::"`→None); `test_detect_prefers_saved_url_over_env_over_default` (fake probe that answers several); `test_detect_uses_process_port_when_default_is_closed`; `test_detect_falls_back_to_range_scan`; `test_detect_rejects_non_ollama_listener` (probe False everywhere → not RUNNING); `test_detect_installed_vs_missing`; `test_detect_ignores_remote_ollama_host`; `test_is_ollama_requires_version_field` (monkeypatch `urllib.request.urlopen` with the `FakeResponse` helper pattern from `tests/test_cleanup.py`: `{"version":"0.5"}` True, `{"foo":1}` False, `b"<html>"` False, raising → False).
- [ ] **Step 2:** Run `poetry run pytest tests/test_ollama_discovery.py -v`; expect FAIL (module missing).
- [ ] **Step 3:** Implement per Interfaces.
- [ ] **Step 4:** Run the same command; expect PASS.
- [ ] **Step 5:** Commit `feat: pure Ollama discovery`.

### Task 4: Real-I/O discovery adapters (`ollama_actions.py`, part 1)

**Files:**
- Create: `src/local_dictation/ollama_actions.py`
- Test: `tests/test_ollama_actions.py`

**Interfaces:**
- Produces: `registry_ollama_host() -> str | None` (reads `OLLAMA_HOST` from `HKCU\Environment`, `None` if absent); `parse_listening_ports(netstat_output: str, pids: set[int]) -> list[int]` (pure parser for `netstat -ano -p tcp`, LISTENING rows on loopback/any address for those PIDs); `parse_tasklist_pids(tasklist_csv: str) -> set[int]` (pure, for `tasklist /FI "IMAGENAME eq ollama*" /FO CSV /NH`, includes `ollama app.exe`/`ollama.exe`); `ollama_process_ports() -> list[int]` (runs both commands with `CREATE_NO_WINDOW`, 3 s timeout, returns `[]` on any failure); `ollama_installed() -> bool` (`%LOCALAPPDATA%\Programs\Ollama\ollama.exe` exists, or `shutil.which("ollama")`, or an Ollama entry under `HKCU`/`HKLM` `...\Uninstall`); `real_detect(saved_url: str) -> Detection` (wires all of the above into `detect`, using `os.environ`).

- [ ] **Step 1: Write failing tests** for the two pure parsers using realistic captured text (include IPv4 and `[::]` rows, a non-listening row, another PID, a header line, and empty input) and for `ollama_installed` with monkeypatched `Path.exists`/`shutil.which`/registry helper (each of the three sources alone → True; none → False).
- [ ] **Step 2:** Run `poetry run pytest tests/test_ollama_actions.py -v`; expect FAIL.
- [ ] **Step 3:** Implement. Keep registry access in tiny helper functions so tests can patch them; wrap `winreg` use in `try/except OSError`.
- [ ] **Step 4:** Run the same command; expect PASS. Then run `poetry run python -c "from local_dictation.ollama_actions import real_detect; print(real_detect(''))"` on this machine and record the printed `Detection` in the commit message body.
- [ ] **Step 5:** Commit `feat: Windows adapters for Ollama discovery`.

### Task 5: Endpoint resolver with rate-limited rediscovery, wired into cleanup

**Files:**
- Create: `src/local_dictation/ollama_endpoint.py`
- Modify: `src/local_dictation/app.py:111-119` (cleanup wiring)
- Test: `tests/test_ollama_endpoint.py`

**Interfaces:**
- Consumes: `Detection`, `Status`, `OllamaUnreachable`, `ollama_cleanup`, `DEFAULT_OLLAMA_URL`.
- Produces: `class EndpointResolver(*, get_url: Callable[[], str], set_url: Callable[[str], None], discover: Callable[[], Detection], clock: Callable[[], float] = time.monotonic, min_interval: float = 60.0)` with `url() -> str` (saved URL or `DEFAULT_OLLAMA_URL`) and `rediscover() -> str | None` (returns a **new** working URL, saves it via `set_url`; returns `None` if nothing new or if called again within `min_interval` of the previous attempt). `make_cleanup(resolver, cleanup=ollama_cleanup) -> Callable[[str, str], str]`: calls `cleanup(text, model, base_url=resolver.url())`; on `OllamaUnreachable` calls `resolver.rediscover()` once and, if it returned a URL, retries once with it; otherwise re-raises.

- [ ] **Step 1: Write failing tests** with fakes: `test_rediscovery_heals_changed_port` (first call unreachable, discover returns RUNNING on new port → second call succeeds, `set_url` called with new URL); `test_rediscovery_rate_limited` (two failures 10 s apart → `discover` called once; after `min_interval` → again); `test_timeout_does_not_trigger_rediscovery`; `test_same_url_found_is_not_a_retry` (discover returns the url already in use → re-raise original error); `test_unreachable_when_nothing_found_reraises`.
- [ ] **Step 2:** Run `poetry run pytest tests/test_ollama_endpoint.py -v`; expect FAIL.
- [ ] **Step 3:** Implement. In `app.py`, build the resolver with `store` (`set_url` does `store.update(replace(store.config, ollama_url=url))`, skipped when `store.invalid`, swallowing `OSError` with `log.exception`) and `real_detect`, and pass `make_cleanup(resolver)` as `cleanup=`.
- [ ] **Step 4:** Run `poetry run pytest -q`; expect all PASS.
- [ ] **Step 5:** Commit `feat: cleanup finds Ollama again after a port change`.

### Task 6: Install, start and pull actions (`ollama_actions.py`, part 2)

**Files:**
- Modify: `src/local_dictation/ollama_actions.py`
- Test: `tests/test_ollama_actions.py`

**Interfaces:**
- Produces: `class SetupError(Exception)`; constants `INSTALLER_URL = "https://ollama.com/download/OllamaSetup.exe"`, `DOWNLOAD_PAGE = "https://ollama.com/download"`, `RECOMMENDED_MODEL = "qwen3.5:0.8b"`; `parse_pull_line(line: bytes) -> tuple[str, float | None]` (status text and fraction 0–1 from `completed`/`total`, `None` when absent; raises `SetupError` when the line has an `error` field); `download_installer(dest_dir: Path, progress: Callable[[float], None], cancelled: Callable[[], bool], urlopen=urllib.request.urlopen) -> Path` (chunked, deletes the partial file on error or cancel, raises `SetupError`); `verify_installer(path: Path, run=subprocess.run) -> None` (PowerShell `Get-AuthenticodeSignature`; requires status `Valid` and a subject containing `Ollama`; raises `SetupError` and deletes the file otherwise); `run_installer(path: Path, cancelled: Callable[[], bool], run=subprocess.run) -> None` (silent switch `/SILENT`); `launch_ollama() -> None` (starts `ollama app.exe` from the install dir, else `ollama serve`, detached, no window); `pull_model(base_url: str, model: str, progress: Callable[[float], None], cancelled: Callable[[], bool], urlopen=urllib.request.urlopen) -> None` (`POST /api/pull`, `stream: true`, NDJSON); `has_model(base_url: str, model: str) -> bool` (via `list_models`).
- **Verify before trusting:** confirm the real installer's signer name and that `/SILENT` is accepted; fix the constants if they differ and note the result in `docs/decisions.md` (Task 11).

- [ ] **Step 1: Write failing tests:** `parse_pull_line` (progress line, status-only line, error line raises); `download_installer` with a fake `urlopen` — writes the file and reports increasing progress, cancel mid-way deletes the partial file, an exception raises `SetupError` and leaves no file; `verify_installer` with a fake `run` returning "Valid|CN=Ollama Inc." passes, "NotSigned" / a different subject raises and deletes the file; `pull_model` with a fake streaming response reports progress and raises `SetupError` on an error line and on cancel; `has_model` true/false.
- [ ] **Step 2:** Run `poetry run pytest tests/test_ollama_actions.py -v`; expect FAIL.
- [ ] **Step 3:** Implement. Every real network/process call takes the injected callable so tests never touch the network. Use `tempfile.mkdtemp` for the caller-supplied `dest_dir`.
- [ ] **Step 4:** Run the same command; expect PASS.
- [ ] **Step 5:** Commit `feat: Ollama install, start and model-pull actions`.

### Task 7: `SetupFlow` state machine (`ollama_flow.py`)

**Files:**
- Create: `src/local_dictation/ollama_flow.py`
- Test: `tests/test_ollama_flow.py`

**Interfaces:**
- Consumes: `Detection`, `Status`, `SetupError`, `RECOMMENDED_MODEL`, `DOWNLOAD_PAGE`.
- Produces:
  - `class StepId(Enum): INSTALL, START, MODEL`
  - `@dataclass(frozen=True) class StepFailure: step: StepId; message: str; manual_url: str | None; manual_command: str | None`
  - `@dataclass(frozen=True) class Done: base_url: str; model: str`
  - `@dataclass(frozen=True) class NeedsConsent: step: StepId; label: str`
  - `Outcome = Done | NeedsConsent | StepFailure`
  - `class Actions(Protocol)`: `detect() -> Detection`, `install(progress, cancelled) -> None`, `start() -> None`, `has_model(base_url, model) -> bool`, `pull(base_url, model, progress, cancelled) -> None`, each raising `SetupError` on failure.
  - `class SetupFlow(actions: Actions, model: str = RECOMMENDED_MODEL)` with `advance(approved: frozenset[StepId], on_progress: Callable[[str, float | None], None], cancelled: Callable[[], bool]) -> Outcome`.
- Behaviour: each call starts with `actions.detect()` (so Retry resumes where it failed). `MISSING` → if `INSTALL` not approved return `NeedsConsent(INSTALL, "Download and install Ollama (~1.5 GB)")`, else `install`, then re-detect. `INSTALLED` → `start`, then poll `detect()` up to ~20 s (injected `sleep`/`clock` params with defaults). `RUNNING` → if `has_model` is false: not approved → `NeedsConsent(MODEL, "Download cleanup model (~0.5 GB)")`, else `pull`. Finally re-check `has_model` and return `Done`. `SetupError` → `StepFailure` with the manual route: INSTALL → `manual_url=DOWNLOAD_PAGE`; START → message only; MODEL → `manual_command=f"ollama pull {model}"`. Cancel (`cancelled()` true) → `StepFailure` with message "Cancelled".

- [ ] **Step 1: Write failing tests** with a scripted fake `Actions` and fake clock: `test_running_with_model_is_done_without_consent`; `test_missing_asks_consent_then_installs_after_approval`; `test_installed_not_running_starts_and_waits`; `test_start_timeout_is_a_failure_with_message`; `test_running_without_model_needs_consent_then_pulls`; `test_failed_pull_gives_manual_command_and_retry_resumes_at_pull` (second `advance` with the same approvals skips install/start because `detect` says RUNNING, and succeeds); `test_install_failure_offers_download_page`; `test_cancel_returns_cancelled_failure_and_stops`; `test_consent_for_install_does_not_approve_model` (model still asks separately).
- [ ] **Step 2:** Run `poetry run pytest tests/test_ollama_flow.py -v`; expect FAIL.
- [ ] **Step 3:** Implement per the behaviour above.
- [ ] **Step 4:** Run the same command; expect PASS.
- [ ] **Step 5:** Commit `feat: guided Ollama setup flow`.

### Task 8: `SetupRunner` and `OllamaSetupPanel`

**Files:**
- Create: `src/local_dictation/ui/ollama_panel.py`
- Test: `tests/test_ollama_panel.py`

**Interfaces:**
- Consumes: `SetupFlow`, `Outcome` types, `StepId`, `Config.ollama_url`.
- Produces:
  - `@dataclass(frozen=True) class PanelState: kind: str` (`"checking" | "ready" | "needs_consent" | "busy" | "failed"`), `text: str`, `progress: float | None = None`, `consent: StepId | None = None`, `failure: StepFailure | None = None`, `model: str | None = None`.
  - `class SetupRunner(QObject)` with `state_changed = Signal(object)`, `model_ready = Signal(str, str)` (base_url, model), `__init__(self, flow: SetupFlow, parent=None)`, `state -> PanelState`, `refresh()` (runs `advance(frozenset())` on a worker thread to learn the status; never starts a download), `approve(step: StepId)` (adds to the approved set and runs), `retry()`, `cancel()`. At most one worker at a time; a second request while busy is ignored. Worker results reach the UI thread only through signals.
  - `class OllamaSetupPanel(QWidget)`: `__init__(self, runner: SetupRunner, parent=None)`; shows status line, one action button (the consent label, "Retry", or "Detect again"), progress bar when busy, a Cancel button when busy, and on failure the message plus "Do it manually" (opens `manual_url` via `QDesktopServices`, or shows `manual_command` in a read-only field with a Copy button). Object names: `status_label`, `action_button`, `cancel_button`, `progress`, `manual_button`, `command_field`.

- [ ] **Step 1: Write failing tests** (module-scoped `qapp` fixture as in `tests/test_settings_dialog.py`; a `FakeFlow` whose `advance` returns scripted outcomes): panel shows consent label on `NeedsConsent`; clicking the action button calls `approve` and shows busy state with Cancel visible; failure shows message, Retry, and Copy field with `ollama pull qwen3.5:0.8b` for a MODEL failure; `Done` emits `model_ready` and the ready text; two panels on one runner show the same state; a second `approve` while busy is ignored; no test touches a real thread leak (join/`processEvents` helper).
- [ ] **Step 2:** Run `poetry run pytest tests/test_ollama_panel.py -v`; expect FAIL.
- [ ] **Step 3:** Implement; follow `ui/theme.py` tokens for colours (no hard-coded greys beyond what `settings.py` already uses).
- [ ] **Step 4:** Run the same command; expect PASS.
- [ ] **Step 5:** Commit `feat(ui): Ollama setup panel and runner`.

### Task 9: Settings integration and address override

**Files:**
- Modify: `src/local_dictation/ui/settings.py`
- Test: `tests/test_settings_dialog.py`

**Interfaces:**
- Consumes: `SetupRunner`, `OllamaSetupPanel`, `Config.ollama_url`.
- Produces: `SettingsDialog(config, listener, parent=None, *, list_models=None, setup_runner=None)`. With a runner: the panel replaces `cleanup_hint` in the form; when the runner emits `model_ready(base_url, model)` the combo is refilled via `list_models()` and `model` is selected (saved only on Save). Without a runner: current hint behaviour unchanged (keeps existing tests valid). New "Ollama address" `QLineEdit` (`address_edit`, placeholder "Automatic") in an "Advanced" row; `to_config()` returns it as `ollama_url` (stripped); `accept()` already blocks on `validate()` errors. `list_models` default uses the configured address.

- [ ] **Step 1: Write failing tests:** `test_roundtrip_includes_ollama_url` (extend the roundtrip config); `test_invalid_address_blocks_save` (remote URL → `accept()` leaves dialog open, `error_label` set); `test_model_ready_refills_and_selects_model` (fake runner emits signal; combo has the model selected, config not saved yet); `test_dialog_without_runner_keeps_hint` (existing behaviour).
- [ ] **Step 2:** Run `poetry run pytest tests/test_settings_dialog.py -v`; expect FAIL.
- [ ] **Step 3:** Implement. Make `_fill_cleanup` callable again for the refill.
- [ ] **Step 4:** Run the same command; expect PASS.
- [ ] **Step 5:** Commit `feat(settings): guided Ollama setup and address override`.

### Task 10: Welcome window section and `app.py` wiring

**Files:**
- Modify: `src/local_dictation/ui/welcome.py`, `src/local_dictation/app.py`
- Test: `tests/test_welcome.py`, `tests/test_app_startup.py`

**Interfaces:**
- Consumes: `SetupRunner`, `OllamaSetupPanel`, `real_detect`, `ActionsImpl` (a thin class in `ollama_actions.py` binding the Task 4/6 functions to the `Actions` protocol; add it here, with a test that each method delegates).
- Produces: `WelcomeWindow(..., setup_runner=None)`: when given, adds a section titled "Optional: clean up your text" (one-line explanation: removes um/uh, fixes punctuation) containing the panel; it never disables "Got it". `app.py` creates one `SetupRunner(SetupFlow(ActionsImpl(...)))`, passes it to both `WelcomeWindow` and `SettingsDialog`, calls `runner.refresh()` when either opens (not at startup), and on `model_ready` saves `cleanup_model` and `ollama_url` via a helper `apply_ollama_ready(store, base_url, model)` (mirrors `apply_shortcut_change`: skips when `store.invalid`, returns error list, no crash on `OSError`).

- [ ] **Step 1: Write failing tests:** welcome window with a fake runner shows the section and "Got it" stays enabled during busy; welcome window without a runner is unchanged; `apply_ollama_ready` saves both fields, and does not touch an invalid config store; `ActionsImpl` delegates.
- [ ] **Step 2:** Run `poetry run pytest tests/test_welcome.py tests/test_app_startup.py -v`; expect FAIL.
- [ ] **Step 3:** Implement per Interfaces. First run must not start any download (only `refresh()`).
- [ ] **Step 4:** Run `poetry run pytest -q`; expect all PASS.
- [ ] **Step 5:** Commit `feat: Ollama setup in the welcome window; shared runner`.

### Task 11: Docs and manual verification

**Files:**
- Modify: `CLAUDE.md` (network rule: add "the Ollama installer from ollama.com and the cleanup model, only after an explicit click"), `docs/decisions.md`, `docs/architecture.md` (module table and data flow for the four new modules and the panel), `docs/manual-test-checklist.md`, `README.md`, `docs/roadmap.md`, and the spec's file-layout note (three modules instead of `ollama_setup.py`).

- [ ] **Step 1:** Update each doc. `decisions.md` records: loopback only, process-port detection, rate-limited rediscovery, consent-per-download, and the confirmed installer URL / signer / silent switch from Task 6.
- [ ] **Step 2:** Add checklist items for: clean machine with no Ollama (full install + pull); installed but stopped; `OLLAMA_HOST` on a non-default port; network off during install and during pull (Retry and manual route); Cancel mid-download (no leftover temp file); setup from the welcome window and from Settings; stale saved port heals after Ollama restarts on another port.
- [ ] **Step 3:** Run `poetry run pytest -q`; expect all PASS. Walk the new checklist items on this machine as far as it allows (running and stopped Ollama, a non-default `OLLAMA_HOST`) and report which items could not be tested here.
- [ ] **Step 4:** Commit `docs: Ollama discovery and guided setup`.
