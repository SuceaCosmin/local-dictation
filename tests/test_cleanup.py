import io
import json
import urllib.error

import pytest

from local_dictation import cleanup


class FakeResponse(io.BytesIO):
    def __enter__(self): return self
    def __exit__(self, *a): return False


def fake_urlopen(payload):
    def _open(req, timeout=None):
        _open.request = req
        return FakeResponse(json.dumps(payload).encode())
    return _open


def test_returns_cleaned_text_and_posts_expected_body(monkeypatch):
    opener = fake_urlopen({"response": " Hello, world. "})
    monkeypatch.setattr(cleanup.urllib.request, "urlopen", opener)
    assert cleanup.ollama_cleanup("um hello world", "qwen2.5:1.5b") == "Hello, world."
    body = json.loads(opener.request.data)
    assert body["model"] == "qwen2.5:1.5b" and body["stream"] is False
    assert "um hello world" in body["prompt"]
    assert opener.request.full_url == "http://localhost:11434/api/generate"


def test_request_disables_thinking(monkeypatch):
    opener = fake_urlopen({"response": "ok"})
    monkeypatch.setattr(cleanup.urllib.request, "urlopen", opener)
    cleanup.ollama_cleanup("hello", "qwen3.5:0.8b")
    assert json.loads(opener.request.data)["think"] is False


def test_empty_reply_raises(monkeypatch):
    monkeypatch.setattr(cleanup.urllib.request, "urlopen", fake_urlopen({"response": "  "}))
    with pytest.raises(cleanup.CleanupError, match="empty"):
        cleanup.ollama_cleanup("raw", "m")


def test_connection_error_raises(monkeypatch):
    def boom(req, timeout=None):
        raise urllib.error.URLError("refused")
    monkeypatch.setattr(cleanup.urllib.request, "urlopen", boom)
    with pytest.raises(cleanup.CleanupError, match="refused"):
        cleanup.ollama_cleanup("raw", "m")


def test_timeout_raises_with_readable_message(monkeypatch):
    def slow(req, timeout=None):
        raise TimeoutError("timed out")
    monkeypatch.setattr(cleanup.urllib.request, "urlopen", slow)
    with pytest.raises(cleanup.CleanupError, match="timed out"):
        cleanup.ollama_cleanup("raw", "m")


def test_malformed_json_raises(monkeypatch):
    monkeypatch.setattr(cleanup.urllib.request, "urlopen",
                        lambda req, timeout=None: FakeResponse(b"not json"))
    with pytest.raises(cleanup.CleanupError):
        cleanup.ollama_cleanup("raw", "m")


def test_list_models_returns_names_and_sizes(monkeypatch):
    payload = {"models": [{"name": "qwen3.5:0.8b", "size": 1322069277},
                          {"name": "gemma4:26b", "size": 17_000_000_000},
                          {"name": "tiny:1b", "size": 300_000_000}]}
    monkeypatch.setattr(cleanup.urllib.request, "urlopen", fake_urlopen(payload))
    models = cleanup.list_models()
    assert [m.name for m in models] == ["qwen3.5:0.8b", "gemma4:26b", "tiny:1b"]
    assert [m.size for m in models] == ["1.2 GB", "15.8 GB", "286 MB"]


def test_list_models_returns_none_when_ollama_is_unreachable(monkeypatch):
    def boom(req, timeout=None):
        raise urllib.error.URLError("refused")
    monkeypatch.setattr(cleanup.urllib.request, "urlopen", boom)
    assert cleanup.list_models() is None


def test_list_models_returns_none_on_garbage(monkeypatch):
    monkeypatch.setattr(cleanup.urllib.request, "urlopen",
                        lambda req, timeout=None: FakeResponse(b"<html>"))
    assert cleanup.list_models() is None


def test_list_models_skips_entries_without_a_name(monkeypatch):
    monkeypatch.setattr(cleanup.urllib.request, "urlopen",
                        fake_urlopen({"models": [{"size": 1}, {"name": "a:1b", "size": 1_000_000}]}))
    assert [m.name for m in cleanup.list_models()] == ["a:1b"]
