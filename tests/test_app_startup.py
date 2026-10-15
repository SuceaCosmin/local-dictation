from local_dictation.app import apply_startup


def test_apply_startup_swallows_oserror_and_notifies_once():
    calls = []

    def boom(enabled):
        raise OSError("denied")

    assert apply_startup(True, lambda t, m: calls.append((t, m)), set_enabled=boom) is False
    assert len(calls) == 1
    assert calls[0][0] == "Start with Windows failed"


def test_apply_startup_success_does_not_notify():
    calls, seen = [], []
    assert apply_startup(True, lambda t, m: calls.append((t, m)), set_enabled=seen.append) is True
    assert seen == [True]
    assert calls == []
