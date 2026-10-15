# Local Dictation

Offline push-to-talk dictation for Windows, similar to Wispr Flow. Speech is transcribed on your own machine with [faster-whisper](https://github.com/SYSTRAN/faster-whisper); nothing is sent to an online service.

Hold **Right Ctrl**, speak, release, and the text is pasted into the focused window.

## Setup

```bash
python -m venv .venv
.venv\Scripts\pip install -r requirements.txt
```

## Run

```bash
run.bat
```

The Whisper model downloads automatically on first launch.

### Options

| Flag | Default | Description |
|---|---|---|
| `--model` | `base.en` | Whisper model: `tiny`, `base`, `small`, `medium`, `large-v3`, or `*.en` variants |
| `--device` | `cpu` | `cpu` or `cuda` |
| `--language` | auto | Language code such as `en` or `ro` (use a non-`.en` model for other languages) |
| `--key` | `ctrl_r` | Hold-to-talk key (any `pynput.keyboard.Key` name, e.g. `f9`) |
| `--cleanup` | off | Ollama model used to polish punctuation and remove filler words, e.g. `qwen2.5:1.5b` |

## Performance

On an i7-6700HQ (CPU, int8), a ~5 s utterance transcribes in about 1.6 s with `base.en` and 4.9 s with `small.en`.

## Ideas

- Tray icon and on-screen recording indicator
- Start with Windows
- Custom vocabulary / per-app formatting
