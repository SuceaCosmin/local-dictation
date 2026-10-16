"""Optional text polish through a local Ollama model."""
from __future__ import annotations

import json
import logging
import urllib.request
from dataclasses import dataclass

log = logging.getLogger(__name__)

OLLAMA_URL = "http://localhost:11434/api/generate"
OLLAMA_TAGS_URL = "http://localhost:11434/api/tags"

CLEANUP_PROMPT = """Clean up this dictated text. Fix punctuation and capitalization, \
remove filler words (um, uh, like, you know) and false starts. Keep the meaning and \
wording otherwise unchanged. Output ONLY the cleaned text, nothing else.

Text: {text}"""


class CleanupError(Exception):
    """The cleanup model could not polish the text; the caller pastes the raw text instead."""


@dataclass(frozen=True)
class OllamaModel:
    name: str
    size: str


def ollama_cleanup(text: str, model: str) -> str:
    # "think": False matters: thinking models (qwen3.5, ...) otherwise reason for minutes and time out
    body = json.dumps({"model": model, "prompt": CLEANUP_PROMPT.format(text=text),
                       "stream": False, "think": False,
                       "options": {"temperature": 0}}).encode()
    request = urllib.request.Request(OLLAMA_URL, data=body,
                                     headers={"Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(request, timeout=30) as response:
            reply = json.loads(response.read())["response"].strip()
    except Exception as e:
        raise CleanupError(f"Ollama request failed: {e}") from e
    if not reply:
        raise CleanupError("Ollama returned an empty reply")
    return reply


def _format_size(size: int) -> str:
    gib = size / 2**30
    return f"{gib:.1f} GB" if gib >= 1 else f"{size / 2**20:.0f} MB"


def list_models(timeout: float = 1.5) -> list[OllamaModel] | None:
    """Installed Ollama models, or None when Ollama cannot be reached."""
    try:
        with urllib.request.urlopen(OLLAMA_TAGS_URL, timeout=timeout) as response:
            entries = json.loads(response.read())["models"]
        return [OllamaModel(e["name"], _format_size(int(e.get("size", 0))))
                for e in entries if e.get("name")]
    except Exception as e:
        log.info("could not list Ollama models: %s", e)
        return None
