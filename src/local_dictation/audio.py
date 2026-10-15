"""Microphone capture: the stream exists only between start() and stop()."""
from __future__ import annotations

import numpy as np

SAMPLE_RATE = 16000


def _default_stream_factory(**kwargs):
    import sounddevice as sd
    return sd.InputStream(**kwargs)


class Recorder:
    def __init__(self, stream_factory=None):
        self._factory = stream_factory or _default_stream_factory
        self._stream = None
        self._chunks: list = []

    def start(self) -> None:
        self._chunks = []
        stream = self._factory(samplerate=SAMPLE_RATE, channels=1, dtype="float32",
                               callback=self._on_audio)
        stream.start()
        self._stream = stream

    def _on_audio(self, indata, frames, time_info, status) -> None:
        self._chunks.append(indata.copy())

    def stop(self) -> np.ndarray:
        stream, self._stream = self._stream, None
        if stream is not None:
            stream.stop()
            stream.close()
        chunks, self._chunks = self._chunks, []
        if not chunks:
            return np.zeros(0, dtype=np.float32)
        return np.concatenate(chunks).flatten().astype(np.float32)
