"""Build verification: `LocalDictation.exe --self-test <outfile>` proves a frozen build is complete."""
from __future__ import annotations

from pathlib import Path

import numpy as np

from .transcribe import _default_factory, _model_source


def run(out_path: Path, factory=_default_factory) -> int:
    try:
        # Every heavy dependency must import inside the frozen build.
        import ctranslate2  # noqa: F401
        import faster_whisper  # noqa: F401
        import onnxruntime  # noqa: F401
        import pynput.keyboard  # noqa: F401
        import pyperclip  # noqa: F401
        import sounddevice  # noqa: F401
        from PySide6 import QtWidgets  # noqa: F401

        from . import hotkey  # noqa: F401  (ctypes hook module)

        model = factory("base.en", "cpu")
        # Silence still runs the VAD (onnxruntime + the Silero asset) and the decoder.
        segments, _ = model.transcribe(np.zeros(32000, dtype="float32"), beam_size=1, vad_filter=True)
        "".join(s.text for s in segments)
        result, code = f"OK source={_model_source('base.en')}", 0
    except Exception as e:  # report every failure; the build reads this file
        result, code = f"FAIL {type(e).__name__}: {e}", 1
    Path(out_path).write_text(result, encoding="utf-8")
    return code
