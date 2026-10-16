"""Dictation flow as a small state machine. No Qt, no OS calls: everything is injected."""
from __future__ import annotations

import logging
import threading
from enum import Enum

from .audio import SAMPLE_RATE

log = logging.getLogger(__name__)

MIN_SECONDS = 0.3


class State(str, Enum):
    IDLE = "idle"
    RECORDING = "recording"
    TRANSCRIBING = "transcribing"
    READY = "ready"        # combo mode: text waits for the paste shortcut
    CLEANING = "cleaning"  # waiting for the Ollama cleanup model, which can take many seconds
    PASTING = "pasting"


def _run_in_thread(fn) -> None:
    threading.Thread(target=fn, name="dictation-worker", daemon=True).start()


class Controller:
    def __init__(self, *, get_config, recorder, transcriber, cleanup, paster,
                 notify, on_state, run_async=None):
        self._get_config = get_config
        self._recorder = recorder
        self._transcriber = transcriber
        self._cleanup = cleanup
        self._paster = paster
        self._notify = notify
        self._on_state = on_state
        self._run_async = run_async or _run_in_thread
        self._lock = threading.RLock()
        self._state = State.IDLE
        self._pending_text: str | None = None
        self._paste_requested = False
        self._cleanup_warned = False  # one notification per run of cleanup failures

    @property
    def state(self) -> State:
        return self._state

    def _set(self, state: State) -> None:
        self._state = state
        self._on_state(state.value)

    def handle_hotkey(self, binding: str, kind: str) -> None:
        if binding == "record" and kind == "pressed":
            self._start_recording()
        elif binding == "record" and kind == "released":
            self._stop_recording()
        elif binding == "paste" and kind == "pressed":
            self._request_paste()

    # -- recording --------------------------------------------------------
    def _start_recording(self) -> None:
        with self._lock:
            if self._state not in (State.IDLE, State.READY):
                return
            self._pending_text = None
            try:
                self._recorder.start()
            except Exception as e:
                log.exception("microphone error")
                self._notify("Microphone error", str(e))
                self._set(State.IDLE)
                return
            self._set(State.RECORDING)

    def _stop_recording(self) -> None:
        with self._lock:
            if self._state is not State.RECORDING:
                return
            try:
                audio = self._recorder.stop()
            except Exception as e:
                log.exception("microphone error")
                self._notify("Microphone error", str(e))
                self._set(State.IDLE)
                return
            if len(audio) / SAMPLE_RATE < MIN_SECONDS:
                self._set(State.IDLE)
                return
            self._paste_requested = False
            config = self._get_config()
            self._set(State.TRANSCRIBING)
        self._run_async(lambda: self._transcribe(audio, config))

    # -- worker -----------------------------------------------------------
    def _transcribe(self, audio, config) -> None:
        try:
            text = self._transcriber.transcribe(audio, config.language)
        except Exception as e:
            log.exception("transcription failed")
            self._notify("Transcription failed", str(e))
            self._set(State.IDLE)
            return
        if not text:
            self._notify("Local Dictation", "No speech detected.")
            self._set(State.IDLE)
            return
        with self._lock:
            if config.stop_mode == "combo" and not self._paste_requested:
                self._pending_text = text
                self._set(State.READY)
                return
        self._finish(text, config)

    def _finish(self, text: str, config) -> None:
        self._set(State.CLEANING if config.cleanup_model else State.PASTING)
        try:
            if config.cleanup_model:
                text = self._cleaned(text, config.cleanup_model)
                self._set(State.PASTING)
            self._paster.paste(text + " ")
        except Exception as e:
            log.exception("paste failed")
            self._notify("Paste failed", str(e))
        self._set(State.IDLE)

    def _cleaned(self, text: str, model: str) -> str:
        """Polish the text; on any failure paste the raw text and say so once."""
        try:
            result = self._cleanup(text, model)
        except Exception as e:
            log.warning("cleanup skipped: %s", e)
            if not self._cleanup_warned:
                self._cleanup_warned = True
                self._notify("Cleanup skipped", f"{e} Pasting the text without cleanup.")
            return text
        self._cleanup_warned = False
        return result

    # -- combo mode -------------------------------------------------------
    def _request_paste(self) -> None:
        config = self._get_config()
        if config.stop_mode != "combo":
            return
        with self._lock:
            if self._state is State.TRANSCRIBING:
                self._paste_requested = True
                return
            if self._state is not State.READY or not self._pending_text:
                return
            text, self._pending_text = self._pending_text, None
            self._set(State.CLEANING if config.cleanup_model else State.PASTING)
        self._run_async(lambda: self._finish(text, config))
