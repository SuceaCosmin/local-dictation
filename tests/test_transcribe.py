import threading
import time
from types import SimpleNamespace

import numpy as np
import pytest

from local_dictation.transcribe import Transcriber


class FakeModel:
    def __init__(self):
        self.calls = []

    def transcribe(self, audio, language=None, beam_size=None, vad_filter=None):
        self.calls.append((language, beam_size, vad_filter))
        return iter([SimpleNamespace(text=" hello "), SimpleNamespace(text="world ")]), None


def test_transcribe_joins_segments_and_maps_empty_language_to_none():
    model = FakeModel()
    statuses = []
    t = Transcriber(lambda name, device: model, on_status=statuses.append)
    t.configure("base.en", "cpu")
    assert t.transcribe(np.zeros(16000, dtype="float32"), "") == "hello world"
    assert model.calls == [(None, 1, True)]
    assert statuses == ["loading", "ready"]


def test_language_is_passed_through():
    model = FakeModel()
    t = Transcriber(lambda n, d: model)
    t.configure("base", "cpu")
    t.transcribe(np.zeros(10, dtype="float32"), "ro")
    assert model.calls[0][0] == "ro"


def test_load_failure_is_reported_not_raised_at_configure():
    def factory(name, device):
        raise ValueError("bad model")

    statuses = []
    t = Transcriber(factory, on_status=statuses.append)
    t.configure("nope", "cpu")
    with pytest.raises(RuntimeError, match="bad model"):
        t.transcribe(np.zeros(10, dtype="float32"), "")
    assert statuses[-1].startswith("error")


def test_transcribe_waits_for_loading_and_times_out():
    gate = threading.Event()
    t = Transcriber(lambda n, d: (gate.wait(5), FakeModel())[1])
    t.configure("base.en", "cpu")
    with pytest.raises(RuntimeError, match="still loading"):
        t.transcribe(np.zeros(10, dtype="float32"), "", timeout=0.05)
    gate.set()
    time.sleep(0.2)
    assert t.transcribe(np.zeros(10, dtype="float32"), "") == "hello world"


def test_reconfigure_discards_stale_load():
    first_gate = threading.Event()
    old, new = FakeModel(), FakeModel()

    def factory(name, device):
        if name == "old":
            first_gate.wait(5)
            return old
        return new

    t = Transcriber(factory)
    t.configure("old", "cpu")
    t.configure("new", "cpu")
    first_gate.set()
    time.sleep(0.2)
    t.transcribe(np.zeros(10, dtype="float32"), "")
    assert new.calls and not old.calls


def test_transcribe_before_configure_raises():
    with pytest.raises(RuntimeError):
        Transcriber(lambda n, d: FakeModel()).transcribe(np.zeros(10, dtype="float32"), "", timeout=0.01)
