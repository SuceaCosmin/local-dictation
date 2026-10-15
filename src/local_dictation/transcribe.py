"""faster-whisper wrapper: loads in the background, can be reloaded when settings change."""
from __future__ import annotations

import logging
import os
import threading
from typing import Callable

log = logging.getLogger(__name__)


def _default_factory(name: str, device: str):
    from faster_whisper import WhisperModel
    compute = "int8" if device == "cpu" else "float32"
    return WhisperModel(name, device=device, compute_type=compute, cpu_threads=os.cpu_count() or 4)


class Transcriber:
    def __init__(self, model_factory=None, on_status: Callable[[str], None] | None = None):
        self._factory = model_factory or _default_factory
        self._on_status = on_status or (lambda status: None)
        self._lock = threading.Lock()
        self._ready = threading.Event()
        self._generation = 0
        self._model = None
        self._error: Exception | None = None

    def configure(self, model_name: str, device: str) -> None:
        with self._lock:
            self._generation += 1
            generation = self._generation
            self._ready.clear()
            self._model, self._error = None, None
        self._on_status("loading")
        threading.Thread(target=self._load, args=(generation, model_name, device),
                         name="whisper-loader", daemon=True).start()

    def _load(self, generation: int, model_name: str, device: str) -> None:
        model, error = None, None
        try:
            model = self._factory(model_name, device)
        except Exception as e:
            log.exception("Whisper model failed to load")
            error = e
        with self._lock:
            if generation != self._generation:
                return  # superseded by a newer configure()
            self._model, self._error = model, error
            # report before unblocking transcribe() so callers observe a consistent order
            self._on_status("ready" if error is None else f"error: {error}")
            self._ready.set()

    def transcribe(self, audio, language: str, timeout: float = 600) -> str:
        if not self._ready.wait(timeout):
            raise RuntimeError("The Whisper model is still loading; try again in a moment.")
        with self._lock:
            model, error = self._model, self._error
        if error is not None or model is None:
            raise RuntimeError(f"Whisper model failed to load: {error}")
        segments, _ = model.transcribe(audio, language=language or None, beam_size=1, vad_filter=True)
        return " ".join(s.text.strip() for s in segments).strip()
