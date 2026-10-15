import winreg

from local_dictation import startup

TEST_KEY = r"Software\LocalDictationTest\Run"


def teardown_function(_):
    for sub in (TEST_KEY, r"Software\LocalDictationTest"):
        try:
            winreg.DeleteKey(winreg.HKEY_CURRENT_USER, sub)
        except OSError:
            pass


def test_enable_disable_roundtrip():
    assert startup.is_enabled(TEST_KEY) is False
    startup.set_enabled(True, TEST_KEY)
    assert startup.is_enabled(TEST_KEY) is True
    startup.set_enabled(False, TEST_KEY)
    assert startup.is_enabled(TEST_KEY) is False


def test_disable_when_not_enabled_is_harmless():
    startup.set_enabled(False, TEST_KEY)


def test_command_uses_pythonw_and_module():
    cmd = startup.launch_command()
    assert cmd.lower().endswith("-m local_dictation")
    assert "pythonw" in cmd.lower()
