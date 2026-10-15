from local_dictation.paste import Paster


class FakeClipboard:
    def __init__(self, content="old", fail_read=False):
        self.content, self.fail_read, self.log = content, fail_read, []

    def paste(self):
        if self.fail_read:
            raise RuntimeError("clipboard unavailable")
        return self.content

    def copy(self, text):
        self.content = text
        self.log.append(("copy", text))


class FakeKeyboard:
    def __init__(self, log):
        self.log = log

    def pressed(self, key):
        outer = self

        class Ctx:
            def __enter__(self_inner): outer.log.append(("down", key)); return self_inner
            def __exit__(self_inner, *a): outer.log.append(("up", key)); return False
        return Ctx()

    def press(self, key): self.log.append(("press", key))
    def release(self, key): self.log.append(("release", key))


def make(clipboard, held=None, log=None):
    log = log if log is not None else []
    sleeps = []
    clock = {"t": 0.0}

    def sleep(seconds):
        sleeps.append(seconds)
        clock["t"] += seconds
        if held is not None and len(sleeps) == 1 and held.get("auto_release"):
            held.pop("ctrl", None); held.pop("win", None)

    paster = Paster(clipboard=clipboard,
                    keyboard_factory=lambda: FakeKeyboard(log),
                    is_held=lambda name: bool((held or {}).get(name)),
                    sleep=sleep, clock=lambda: clock["t"])
    return paster, log, sleeps


def test_sets_clipboard_sends_ctrl_v_and_restores_previous():
    clip = FakeClipboard("old")
    paster, log, _ = make(clip)
    paster.paste("hello ")
    assert clip.log == [("copy", "hello "), ("copy", "old")]
    assert [e[0] for e in log] == ["down", "press", "release", "up"]
    assert log[1][1] == "v"


def test_waits_for_modifiers_to_be_released_before_pasting():
    clip = FakeClipboard()
    held = {"ctrl": True, "win": True, "auto_release": True}
    paster, log, sleeps = make(clip, held)
    paster.paste("x")
    assert sleeps[0] == 0.02            # polled once while keys were held
    assert ("copy", "x") in clip.log


def test_gives_up_waiting_after_timeout_but_still_pastes():
    clip = FakeClipboard()
    paster, log, sleeps = make(clip, {"win": True})
    paster.paste("x")
    assert sum(s for s in sleeps if s == 0.02) >= 1.4   # polled until the 1.5 s deadline
    assert ("copy", "x") in clip.log and any(e[0] == "press" for e in log)


def test_unreadable_clipboard_does_not_block_paste_or_restore():
    clip = FakeClipboard(fail_read=True)
    paster, log, _ = make(clip)
    paster.paste("x")
    assert clip.log == [("copy", "x")]
