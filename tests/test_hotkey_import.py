def test_modules_import_and_listener_constructs():
    from local_dictation.hotkey import WindowsHotkeyListener
    from local_dictation.keystate import is_held

    listener = WindowsHotkeyListener()
    assert callable(listener.start) and callable(listener.begin_capture)
    assert isinstance(is_held("ctrl"), bool)
