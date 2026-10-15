import io
import json
import urllib.error

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


def test_empty_reply_falls_back_to_raw_text(monkeypatch):
    monkeypatch.setattr(cleanup.urllib.request, "urlopen", fake_urlopen({"response": "  "}))
    assert cleanup.ollama_cleanup("raw", "m") == "raw"


def test_connection_error_falls_back(monkeypatch):
    def boom(req, timeout=None):
        raise urllib.error.URLError("refused")
    monkeypatch.setattr(cleanup.urllib.request, "urlopen", boom)
    assert cleanup.ollama_cleanup("raw", "m") == "raw"


def test_malformed_json_falls_back(monkeypatch):
    monkeypatch.setattr(cleanup.urllib.request, "urlopen",
                        lambda req, timeout=None: FakeResponse(b"not json"))
    assert cleanup.ollama_cleanup("raw", "m") == "raw"
