import numpy as np

from local_dictation.config import Config
from local_dictation.controller import Controller, State

ONE_SECOND = np.zeros(16000, dtype="float32")


class FakeRecorder:
    def __init__(self, audio=ONE_SECOND, start_error=None):
        self.audio, self.start_error, self.started = audio, start_error, 0

    def start(self):
        if self.start_error:
            raise self.start_error
        self.started += 1

    def stop(self):
        return self.audio


class FakeTranscriber:
    def __init__(self, text="hello world", error=None):
        self.text, self.error, self.calls = text, error, []

    def transcribe(self, audio, language):
        self.calls.append(language)
        if self.error:
            raise self.error
        return self.text


class FakePaster:
    def __init__(self, error=None):
        self.pasted, self.error = [], error

    def paste(self, text):
        if self.error:
            raise self.error
        self.pasted.append(text)


def build(config=None, recorder=None, transcriber=None, paster=None, cleanup=None, deferred=False):
    config = config or Config()
    jobs = []
    states, notes = [], []
    c = Controller(
        get_config=lambda: config,
        recorder=recorder or FakeRecorder(),
        transcriber=transcriber or FakeTranscriber(),
        cleanup=cleanup or (lambda text, model: f"[{model}] {text}"),
        paster=paster or FakePaster(),
        notify=lambda title, msg: notes.append((title, msg)),
        on_state=states.append,
        run_async=(jobs.append if deferred else (lambda fn: fn())),
    )
    return c, states, notes, jobs


def test_release_mode_full_flow_pastes_with_trailing_space():
    paster = FakePaster()
    c, states, notes, _ = build(paster=paster)
    c.handle_hotkey("record", "pressed")
    assert c.state is State.RECORDING
    c.handle_hotkey("record", "released")
    assert paster.pasted == ["hello world "]
    assert c.state is State.IDLE
    assert states == ["recording", "transcribing", "pasting", "idle"]
    assert notes == []


def test_cleanup_used_only_when_model_configured():
    paster = FakePaster()
    c, *_ = build(Config(cleanup_model="qwen"), paster=paster)
    c.handle_hotkey("record", "pressed"); c.handle_hotkey("record", "released")
    assert paster.pasted == ["[qwen] hello world "]


def test_language_passed_to_transcriber():
    t = FakeTranscriber()
    c, *_ = build(Config(language="ro"), transcriber=t)
    c.handle_hotkey("record", "pressed"); c.handle_hotkey("record", "released")
    assert t.calls == ["ro"]


def test_too_short_recording_is_ignored_silently():
    paster = FakePaster()
    c, states, notes, _ = build(recorder=FakeRecorder(np.zeros(1000, dtype="float32")), paster=paster)
    c.handle_hotkey("record", "pressed"); c.handle_hotkey("record", "released")
    assert paster.pasted == [] and notes == [] and c.state is State.IDLE


def test_empty_audio_is_ignored_silently():
    c, _, notes, _ = build(recorder=FakeRecorder(np.zeros(0, dtype="float32")))
    c.handle_hotkey("record", "pressed"); c.handle_hotkey("record", "released")
    assert notes == [] and c.state is State.IDLE


def test_no_speech_notifies_and_returns_to_idle():
    paster = FakePaster()
    c, _, notes, _ = build(transcriber=FakeTranscriber(text=""), paster=paster)
    c.handle_hotkey("record", "pressed"); c.handle_hotkey("record", "released")
    assert paster.pasted == [] and c.state is State.IDLE
    assert notes and "speech" in notes[0][1].lower()


def test_microphone_error_notifies_and_next_press_works():
    recorder = FakeRecorder(start_error=OSError("no mic"))
    c, _, notes, _ = build(recorder=recorder)
    c.handle_hotkey("record", "pressed")
    assert c.state is State.IDLE and "no mic" in notes[0][1]
    recorder.start_error = None
    c.handle_hotkey("record", "pressed")
    assert c.state is State.RECORDING


def test_transcription_error_notifies_and_returns_to_idle():
    c, _, notes, _ = build(transcriber=FakeTranscriber(error=RuntimeError("model broke")))
    c.handle_hotkey("record", "pressed"); c.handle_hotkey("record", "released")
    assert c.state is State.IDLE and "model broke" in notes[0][1]


def test_paste_error_notifies_and_returns_to_idle():
    c, _, notes, _ = build(paster=FakePaster(error=RuntimeError("clipboard locked")))
    c.handle_hotkey("record", "pressed"); c.handle_hotkey("record", "released")
    assert c.state is State.IDLE and "clipboard locked" in notes[0][1]


def test_recorder_stop_error_returns_to_idle():
    class BadStop(FakeRecorder):
        def stop(self): raise RuntimeError("stream died")
    c, _, notes, _ = build(recorder=BadStop())
    c.handle_hotkey("record", "pressed"); c.handle_hotkey("record", "released")
    assert c.state is State.IDLE and notes


def test_press_while_busy_is_ignored():
    c, _, _, jobs = build(deferred=True)
    c.handle_hotkey("record", "pressed"); c.handle_hotkey("record", "released")
    assert c.state is State.TRANSCRIBING
    c.handle_hotkey("record", "pressed")
    assert c.state is State.TRANSCRIBING
    assert len(jobs) == 1


def test_release_without_press_is_ignored():
    c, states, *_ = build()
    c.handle_hotkey("record", "released")
    assert states == [] and c.state is State.IDLE


def test_paste_shortcut_ignored_in_release_mode():
    paster = FakePaster()
    c, *_ = build(paster=paster)
    c.handle_hotkey("paste", "pressed")
    assert paster.pasted == []


def test_combo_mode_waits_for_paste_shortcut():
    paster = FakePaster()
    c, states, *_ = build(Config(stop_mode="combo"), paster=paster)
    c.handle_hotkey("record", "pressed"); c.handle_hotkey("record", "released")
    assert paster.pasted == [] and c.state is State.READY
    c.handle_hotkey("paste", "pressed")
    assert paster.pasted == ["hello world "] and c.state is State.IDLE


def test_combo_mode_paste_requested_during_transcription():
    paster = FakePaster()
    c, _, _, jobs = build(Config(stop_mode="combo"), paster=paster, deferred=True)
    c.handle_hotkey("record", "pressed"); c.handle_hotkey("record", "released")
    c.handle_hotkey("paste", "pressed")           # still transcribing
    assert paster.pasted == []
    jobs.pop(0)()                                 # transcription finishes
    assert paster.pasted == ["hello world "] and c.state is State.IDLE


def test_combo_mode_new_recording_replaces_pending_text():
    paster = FakePaster()
    t = FakeTranscriber()
    c, *_ = build(Config(stop_mode="combo"), paster=paster, transcriber=t)
    c.handle_hotkey("record", "pressed"); c.handle_hotkey("record", "released")
    t.text = "second"
    c.handle_hotkey("record", "pressed"); c.handle_hotkey("record", "released")
    c.handle_hotkey("paste", "pressed")
    assert paster.pasted == ["second "]


def test_combo_paste_with_nothing_pending_is_ignored():
    paster = FakePaster()
    c, *_ = build(Config(stop_mode="combo"), paster=paster)
    c.handle_hotkey("paste", "pressed")
    assert paster.pasted == [] and c.state is State.IDLE


def _failing_cleanup(text, model):
    raise RuntimeError("Ollama request failed: timed out")


def _dictate(c):
    c.handle_hotkey("record", "pressed")
    c.handle_hotkey("record", "released")


def test_cleanup_failure_pastes_raw_text_and_notifies():
    paster = FakePaster()
    c, _, notes, _ = build(Config(cleanup_model="qwen"), paster=paster, cleanup=_failing_cleanup)
    _dictate(c)
    assert paster.pasted == ["hello world "]
    assert c.state is State.IDLE
    assert len(notes) == 1 and notes[0][0] == "Cleanup skipped"
    assert "timed out" in notes[0][1]


def test_cleanup_failure_notifies_once_per_streak():
    paster = FakePaster()
    c, _, notes, _ = build(Config(cleanup_model="qwen"), paster=paster, cleanup=_failing_cleanup)
    _dictate(c)
    _dictate(c)
    assert paster.pasted == ["hello world ", "hello world "]
    assert len(notes) == 1


def test_cleanup_failure_notifies_again_after_a_success():
    outcomes = [RuntimeError("down"), "ok", RuntimeError("down again")]

    def flaky(text, model):
        outcome = outcomes.pop(0)
        if isinstance(outcome, Exception):
            raise outcome
        return outcome

    c, _, notes, _ = build(Config(cleanup_model="qwen"), cleanup=flaky)
    _dictate(c)
    _dictate(c)
    _dictate(c)
    assert [n[0] for n in notes] == ["Cleanup skipped", "Cleanup skipped"]
