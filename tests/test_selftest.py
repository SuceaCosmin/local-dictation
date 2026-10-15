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
