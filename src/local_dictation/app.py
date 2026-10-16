"""Application wiring: logging, single instance, tray, hotkey, controller."""
from __future__ import annotations

import ctypes
import logging
import logging.handlers
import sys
from dataclasses import replace
from pathlib import Path

from PySide6.QtCore import QObject, Signal
from PySide6.QtWidgets import QApplication, QDialog

from . import startup
from .audio import Recorder
from .cleanup import ollama_cleanup
from .config import Config, ConfigStore, default_config_path
from .controller import Controller
from .hotkey import WindowsHotkeyListener
from .paste import Paster
from .transcribe import Transcriber
from .ui.settings import SettingsDialog
from .ui.tray import TrayIcon
from .ui.welcome import WelcomeWindow

log = logging.getLogger("local_dictation")
_mutex_handle = None  # keep the mutex alive for the life of the process


def setup_logging() -> None:
    log_dir = default_config_path().parent
    log_dir.mkdir(parents=True, exist_ok=True)
    handlers: list[logging.Handler] = [
        logging.handlers.RotatingFileHandler(log_dir / "dictation.log", maxBytes=500_000,
                                             backupCount=2, encoding="utf-8")
    ]
    if sys.stderr is not None:
        handlers.append(logging.StreamHandler())
    logging.basicConfig(level=logging.INFO, handlers=handlers,
                        format="%(asctime)s %(levelname)s %(name)s: %(message)s")


def acquire_single_instance() -> bool:
    global _mutex_handle
    kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
    _mutex_handle = kernel32.CreateMutexW(None, False, "Local\\LocalDictationSingleton")
    return ctypes.get_last_error() != 183  # ERROR_ALREADY_EXISTS


def apply_startup(enabled: bool, notify, set_enabled=startup.set_enabled) -> bool:
    """Apply the start-with-Windows setting; a registry failure is reported, never raised."""
    try:
        set_enabled(enabled)
    except OSError as e:
        log.exception("could not update the start-with-Windows setting")
        notify("Start with Windows failed", str(e))
        return False
    return True


def apply_shortcut_change(store, value: str, apply_runtime) -> list[str]:
    """Save a new record shortcut; returns error messages (nothing is saved or applied then)."""
    previous = store.config
    new = replace(previous, record_shortcut=value)
    errors = new.validate()
    if errors:
        return errors
    try:
        store.update(new)
    except OSError as e:
        log.exception("could not save the new shortcut")
        return [f"Could not save the shortcut: {e}"]
    apply_runtime(new, previous)
    return []


def mark_welcome_shown(store) -> None:
    """Remember that the welcome window was shown; never overwrites a config file we could not read."""
    if store.invalid:
        return
    try:
        store.update(replace(store.config, welcome_shown=True))
    except OSError:
        log.exception("could not record that the welcome window was shown")


class Bridge(QObject):
    """Turns callbacks from worker threads into queued Qt signals."""
    state_changed = Signal(str)
    notified = Signal(str, str)
    model_status = Signal(str)


def main() -> int:
    if len(sys.argv) == 3 and sys.argv[1] == "--self-test":
        from .selftest import run
        return run(Path(sys.argv[2]))
    setup_logging()
    if not acquire_single_instance():
        log.warning("Local Dictation is already running")
        return 1

    qapp = QApplication(sys.argv)
    qapp.setQuitOnLastWindowClosed(False)

    store = ConfigStore()
    bridge = Bridge()
    tray = TrayIcon()
    listener = WindowsHotkeyListener()
    transcriber = Transcriber(on_status=bridge.model_status.emit)
    controller = Controller(
        get_config=lambda: store.config,
        recorder=Recorder(),
        transcriber=transcriber,
        cleanup=ollama_cleanup,
        paster=Paster(),
        notify=bridge.notified.emit,
        on_state=bridge.state_changed.emit,
    )
    bridge.state_changed.connect(tray.set_state)
    bridge.notified.connect(tray.notify)
    bridge.model_status.connect(tray.set_model_status)
    listener.set_handler(controller.handle_hotkey)

    def apply_runtime(new: Config, previous: Config | None) -> None:
        if previous is None or (new.model, new.device) != (previous.model, previous.device):
            transcriber.configure(new.model, new.device)
        listener.set_bindings(new.bindings())
        apply_startup(new.start_with_windows, tray.notify)

    def start_listener() -> None:
        try:
            listener.start()
        except RuntimeError as e:
            log.exception("hotkey failed to start")
            tray.notify("Hotkey error", str(e))

    def restart_listener() -> None:
        listener.stop()
        listener.set_bindings(store.config.bindings())
        start_listener()

    dialog_open = False

    def open_settings() -> None:
        nonlocal dialog_open
        if dialog_open:
            return
        if welcome is not None:
            welcome.shortcut_edit.cancel()  # the hook has one capture slot; do not let two widgets share it
        dialog_open = True
        try:
            dialog = SettingsDialog(store.config, listener)
            if dialog.exec() == QDialog.Accepted:
                previous, new = store.config, dialog.to_config()
                try:
                    store.update(new)
                    apply_runtime(new, previous)
                except (OSError, ValueError) as e:
                    log.exception("could not save or apply settings")
                    tray.notify("Settings not saved", str(e))
        finally:
            dialog_open = False

    welcome: WelcomeWindow | None = None

    def on_welcome_shortcut(value: str) -> None:
        assert welcome is not None  # connected only after the window exists
        errors = apply_shortcut_change(store, value, apply_runtime)
        welcome.set_shortcut(store.config.record_shortcut)  # also clears any old message
        if errors:
            welcome.show_error("\n".join(errors))

    def open_welcome() -> None:
        nonlocal welcome
        if welcome is None:
            welcome = WelcomeWindow(store.config.record_shortcut, listener, tray.model_status)
            welcome.shortcut_changed.connect(on_welcome_shortcut)
            bridge.model_status.connect(welcome.set_status)
        else:
            welcome.set_shortcut(store.config.record_shortcut)
            welcome.set_status(tray.model_status)
        welcome.show()
        welcome.raise_()
        welcome.activateWindow()

    def quit_app() -> None:
        listener.stop()
        qapp.quit()

    tray.welcome_requested.connect(open_welcome)
    tray.settings_requested.connect(open_settings)
    tray.restart_requested.connect(restart_listener)
    tray.quit_requested.connect(quit_app)

    apply_runtime(store.config, None)
    start_listener()
    if not store.config.welcome_shown:
        mark_welcome_shown(store)
        open_welcome()
    log.info("Local Dictation started (shortcut: %s)", store.config.record_shortcut)
    return qapp.exec()
