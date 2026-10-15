"""Optional text polish through a local Ollama model."""
from __future__ import annotations

import json
import logging
import urllib.request

log = logging.getLogger(__name__)

OLLAMA_URL = "http://localhost:11434/api/generate"

CLEANUP_PROMPT = """Clean up this dictated text. Fix punctuation and capitalization, \
remove filler words (um, uh, like, you know) and false starts. Keep the meaning and \
wording otherwise unchanged. Output ONLY the cleaned text, nothing else.

Text: {text}"""


def ollama_cleanup(text: str, model: str) -> str:
    body = json.dumps({"model": model, "prompt": CLEANUP_PROMPT.format(text=text),
                       "stream": False, "options": {"temperature": 0}}).encode()
    request = urllib.request.Request(OLLAMA_URL, data=body,
                                     headers={"Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(request, timeout=30) as response:
            return json.loads(response.read())["response"].strip() or text
    except Exception as e:
        log.warning("cleanup skipped: %s", e)
        return text
