import pytest

from local_dictation.shortcut import Shortcut, keycaps, name_to_vks, vk_to_name


@pytest.mark.parametrize("vk, name", [
    (0xA2, "ctrl"), (0xA3, "ctrl"), (0x11, "ctrl"),
    (0x5B, "win"), (0x5C, "win"),
    (0xA4, "alt"), (0xA0, "shift"),
    (0x78, "f9"), (0x70, "f1"), (0x41, "a"), (0x31, "1"),
    (0x20, "space"), (0x0D, "enter"), (0x1B, "esc"),
    (0xFE, "vkfe"),
])
def test_vk_to_name(vk, name):
    assert vk_to_name(vk) == name


@pytest.mark.parametrize("name", ["ctrl", "win", "alt", "shift", "f9", "a", "7", "space", "esc", "vkfe"])
def test_name_to_vks_roundtrip(name):
    vks = name_to_vks(name)
    assert vks and all(vk_to_name(vk) == name for vk in vks)


def test_parse_and_format_normalize_order_and_case():
    assert Shortcut.parse("Win + Ctrl").format() == "ctrl+win"
    assert Shortcut.parse("space+ctrl+win").format() == "ctrl+win+space"


def test_parse_empty_raises():
    with pytest.raises(ValueError):
        Shortcut.parse(" + ")


@pytest.mark.parametrize("text, safe", [
    ("ctrl+win", True), ("ctrl+alt+space", True), ("f9", True), ("shift+f9", True),
    ("ctrl+shift+space", True), ("alt+f4", True),
    ("ctrl", False), ("shift", False), ("alt", False), ("win", False), ("shift+a", False),
    ("a", False), ("space", False), ("ctrl+a+b", False), ("esc", False),
])
def test_is_safe(text, safe):
    assert Shortcut.parse(text).is_safe() is safe


def test_keycaps_modifiers_use_canonical_order():
    assert keycaps("win+ctrl") == ["Ctrl", "Win"]
    assert keycaps("ctrl+shift+space") == ["Ctrl", "Shift", "Space"]


def test_keycaps_function_and_letter_keys():
    assert keycaps("f9") == ["F9"]
    assert keycaps("ctrl+alt+a") == ["Ctrl", "Alt", "A"]


def test_keycaps_empty_and_unknown_do_not_crash():
    assert keycaps("") == []
    assert keycaps("  ") == []
    assert keycaps("ctrl+vk5d") == ["Ctrl", "Vk5d"]
