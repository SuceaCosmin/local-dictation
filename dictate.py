"""Local push-to-talk dictation (a minimal, offline Wispr Flow alternative).

Hold the hotkey, speak, release: the transcription is pasted into whatever
window has focus. Everything runs on this computer.
"""
import argparse
import json
import threading
import time
import urllib.request

import numpy as np
import pyperclip
import sounddevice as sd
from faster_whisper import WhisperModel
from pynput import keyboard

SAMPLE_RATE = 16000

CLEANUP_PROMPT = """Clean up this dictated text. Fix punctuation and capitalization, \
remove filler words (um, uh, like, you know) and false starts. Keep the meaning and \
wording otherwise unchanged. Output ONLY the cleaned text, nothing else.

Text: {text}"""


def parse_args():
    p = argparse.ArgumentParser(description="Local push-to-talk dictation")
    p.add_argument("--model", default="base.en",
                   help="Whisper model: tiny, base, small, medium, large-v3, or *.en variants (default: base.en)")
    p.add_argument("--device", default="cpu", choices=["cpu", "cuda"])
    p.add_argument("--language", default=None, help="e.g. en, ro, de. Default: auto-detect")
    p.add_argument("--key", default="ctrl_r",
                   help="Hold-to-talk key name from pynput.keyboard.Key (default: ctrl_r = Right Ctrl)")
    p.add_argument("--cleanup", metavar="OLLAMA_MODEL",
                   help="Polish text with a local Ollama model, e.g. qwen2.5:1.5b")
    return p.parse_args()


def ollama_cleanup(text, model):
    body = json.dumps({"model": model, "prompt": CLEANUP_PROMPT.format(text=text),
                       "stream": False, "options": {"temperature": 0}}).encode()
    req = urllib.request.Request("http://localhost:11434/api/generate", data=body,
                                 headers={"Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=30) as r:
            return json.loads(r.read())["response"].strip() or text
    except Exception as e:
        print(f"  (cleanup skipped: {e})")
        return text


def paste(text):
    """Paste via the clipboard, then restore whatever was there before."""
    try:
        previous = pyperclip.paste()
    except Exception:
        previous = None
    pyperclip.copy(text)
    time.sleep(0.05)
    kb = keyboard.Controller()
    with kb.pressed(keyboard.Key.ctrl):
        kb.press("v")
        kb.release("v")
    time.sleep(0.3)
    if previous is not None:
        pyperclip.copy(previous)


class Dictation:
    def __init__(self, args):
        self.args = args
        self.hotkey = getattr(keyboard.Key, args.key)
        compute = "int8" if args.device == "cpu" else "float32"
        print(f"Loading Whisper '{args.model}' on {args.device} ({compute})...")
        self.model = WhisperModel(args.model, device=args.device, compute_type=compute, cpu_threads=8)
        self.recording = False
        self.chunks = []
        self.stream = sd.InputStream(samplerate=SAMPLE_RATE, channels=1, dtype="float32",
                                     callback=self._on_audio)
        self.stream.start()

    def _on_audio(self, indata, frames, t, status):
        if self.recording:
            self.chunks.append(indata.copy())

    def on_press(self, key):
        if key == self.hotkey and not self.recording:
            self.chunks = []
            self.recording = True
            print("● Recording...", end="", flush=True)

    def on_release(self, key):
        if key == self.hotkey and self.recording:
            self.recording = False
            audio = np.concatenate(self.chunks).flatten() if self.chunks else np.zeros(0)
            threading.Thread(target=self.process, args=(audio,), daemon=True).start()

    def process(self, audio):
        seconds = len(audio) / SAMPLE_RATE
        if seconds < 0.3:
            print(" too short, ignored")
            return
        start = time.time()
        segments, _ = self.model.transcribe(audio, language=self.args.language,
                                            beam_size=1, vad_filter=True)
        text = " ".join(s.text.strip() for s in segments).strip()
        if not text:
            print(" (no speech detected)")
            return
        if self.args.cleanup:
            text = ollama_cleanup(text, self.args.cleanup)
        print(f" {seconds:.1f}s audio → {time.time() - start:.1f}s: {text}")
        paste(text + " ")

    def run(self):
        print(f"Ready. Hold [{self.args.key}] and speak; release to paste. Ctrl+C to quit.")
        with keyboard.Listener(on_press=self.on_press, on_release=self.on_release) as listener:
            listener.join()


if __name__ == "__main__":
    try:
        Dictation(parse_args()).run()
    except KeyboardInterrupt:
        pass
