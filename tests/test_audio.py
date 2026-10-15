import numpy as np

from local_dictation.audio import SAMPLE_RATE, Recorder


class FakeStream:
    def __init__(self, **kwargs):
        self.callback = kwargs["callback"]
        self.kwargs = kwargs
        self.started = self.stopped = self.closed = False

    def start(self): self.started = True
    def stop(self): self.stopped = True
    def close(self): self.closed = True


def test_records_between_start_and_stop():
    streams = []

    def factory(**kwargs):
        streams.append(FakeStream(**kwargs))
        return streams[-1]

    rec = Recorder(factory)
    rec.start()
    assert streams[0].started and streams[0].kwargs["samplerate"] == SAMPLE_RATE
    streams[0].callback(np.ones((100, 1), dtype="float32"), 100, None, None)
    streams[0].callback(np.ones((50, 1), dtype="float32") * 2, 50, None, None)
    audio = rec.stop()
    assert audio.shape == (150,) and audio.dtype == np.float32
    assert streams[0].stopped and streams[0].closed


def test_stop_without_audio_returns_empty():
    rec = Recorder(lambda **kw: FakeStream(**kw))
    rec.start()
    assert rec.stop().shape == (0,)


def test_stop_without_start_is_safe():
    assert Recorder(lambda **kw: FakeStream(**kw)).stop().shape == (0,)


def test_start_failure_propagates_and_next_start_works():
    calls = {"n": 0}

    def factory(**kw):
        calls["n"] += 1
        if calls["n"] == 1:
            raise OSError("no microphone")
        return FakeStream(**kw)

    rec = Recorder(factory)
    try:
        rec.start()
        assert False, "expected OSError"
    except OSError:
        pass
    rec.start()
    assert rec.stop().shape == (0,)
