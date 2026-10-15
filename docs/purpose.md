# Purpose

A fully local, Windows push-to-talk dictation tool, in the spirit of Wispr Flow but using local models (faster-whisper for speech-to-text, optional Ollama model for punctuation/filler cleanup) instead of an online service.

## Target behavior
1. User holds the record shortcut (default **Ctrl+Win**). The shortcut is swallowed: no application (VS Code, Notepad, GitHub Copilot chat, ...) sees it and the Start menu does not open.
2. Audio is captured only while the shortcut is held.
3. On release (default stop mode) the audio is transcribed, optionally cleaned up, and pasted into the control that currently has keyboard focus.
4. Alternative stop mode "combo": release ends recording, a second configurable shortcut triggers the paste.
5. A tray icon shows state (loading, idle, recording, transcribing, ready, pasting); a small settings window changes the shortcut, stop mode, model, device, language, cleanup model and start-with-Windows.

## Non-goals (for now)
Installer (planned; layout must not block it), macOS/Linux, streaming/partial transcription, per-app formatting, custom vocabulary, on-screen recording overlay.

## Origin
Started as a single script, `dictate.py` (faster-whisper + sounddevice + pynput + pyperclip, optional Ollama cleanup, launched by `run.bat`). Its hotkey leaked into the focused app (seen in VS Code), which motivated the rework.
