from local_dictation.shortcut import Shortcut, ShortcutCapture, ShortcutMatcher

REC = {"record": Shortcut.parse("ctrl+win")}


def make(bindings=REC):
    return ShortcutMatcher(dict(bindings))


def test_ctrl_then_win_swallows_win_and_masks_start_menu():
    m = make()
    assert m.on_key("ctrl", True).swallow is False
    d = m.on_key("win", True)
    assert d.swallow is True
    assert d.events == (("record", "pressed"),)
    assert d.inject_mask is True
    d = m.on_key("ctrl", False)               # ctrl-down was passed, so ctrl-up must pass
    assert d.swallow is False
    assert d.events == (("record", "released"),)
    assert m.on_key("win", False).swallow is True   # win-down was swallowed


def test_win_then_ctrl_swallows_ctrl():
    m = make()
    assert m.on_key("win", True).swallow is False
    d = m.on_key("ctrl", True)
    assert d.swallow is True and d.events == (("record", "pressed"),) and d.inject_mask is True
    d = m.on_key("ctrl", False)
    assert d.swallow is True and d.events == (("record", "released"),)
    assert m.on_key("win", False).swallow is False


def test_other_keys_pass_when_idle_and_are_swallowed_while_active():
    m = make()
    assert m.on_key("a", True).swallow is False
    assert m.on_key("a", False).swallow is False
    m.on_key("ctrl", True)
    m.on_key("win", True)
    assert m.on_key("b", True).swallow is True
    assert m.on_key("b", False).swallow is True


def test_auto_repeat_of_passed_key_never_leaves_stuck_key():
    m = make()
    m.on_key("ctrl", True)
    m.on_key("win", True)
    assert m.on_key("ctrl", True).swallow is False     # auto-repeat of a passed key stays passed
    assert m.on_key("ctrl", False).swallow is False    # so its key-up must pass too


def test_auto_repeat_of_swallowed_key_is_swallowed_without_new_event():
    m = make()
    m.on_key("ctrl", True)
    m.on_key("win", True)
    d = m.on_key("win", True)
    assert d.swallow is True and d.events == ()


def test_pressing_again_after_release_triggers_again():
    m = make()
    m.on_key("ctrl", True); m.on_key("win", True)
    m.on_key("ctrl", False)
    d = m.on_key("ctrl", True)
    assert d.events == (("record", "pressed"),)


def test_second_binding_while_first_active():
    m = make({"record": Shortcut.parse("ctrl+win"), "paste": Shortcut.parse("ctrl+win+space")})
    m.on_key("ctrl", True); m.on_key("win", True)
    d = m.on_key("space", True)
    assert d.swallow is True and d.events == (("paste", "pressed"),)


def test_function_key_binding():
    m = make({"record": Shortcut.parse("f9")})
    d = m.on_key("f9", True)
    assert d.swallow is True and d.events == (("record", "pressed"),) and d.inject_mask is False
    d = m.on_key("f9", False)
    assert d.swallow is True and d.events == (("record", "released"),)


def test_set_bindings_replaces_and_clears_active():
    m = make()
    m.on_key("ctrl", True); m.on_key("win", True)
    m.set_bindings({"record": Shortcut.parse("f9")})
    m.on_key("ctrl", False); m.on_key("win", False)    # held keys would otherwise block the f9 match
    assert m.on_key("f9", True).events == (("record", "pressed"),)


def test_prune_releases_when_passed_key_missed_its_key_up():
    m = make()
    m.on_key("ctrl", True); m.on_key("win", True)
    events = m.prune(lambda name: False)          # OS says nothing is held
    assert events == (("record", "released"),)


def test_prune_never_drops_swallowed_keys_or_keep():
    m = make()
    m.on_key("win", True)                         # passed
    assert m.prune(lambda name: False, keep="win") == ()
    m.on_key("ctrl", True)                        # swallowed, binding active
    # swallowed keys are invisible to the OS, so "not held" must not count against them
    assert m.prune(lambda name: name == "win") == ()


def test_capture_collects_peak_set_and_finishes_when_all_released():
    c = ShortcutCapture()
    assert c.on_key("ctrl", True).swallow is True
    assert c.on_key("win", True).swallow is True
    assert c.preview() == "ctrl+win"
    assert c.on_key("ctrl", False).done is None
    step = c.on_key("win", False)
    assert step.swallow is True and step.done == Shortcut.parse("ctrl+win")


def test_capture_esc_first_cancels():
    step = ShortcutCapture().on_key("esc", True)
    assert step.cancelled is True


def test_capture_passes_key_up_of_unseen_key():
    assert ShortcutCapture().on_key("shift", False).swallow is False
