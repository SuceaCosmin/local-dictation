"""Queue + thread between the keyboard hook and the controller, so the hook only enqueues."""
from __future__ import annotations

import logging
import queue
import threading
from typing import Callable

log = logging.getLogger(__name__)


class EventDispatcher:
    def __init__(self):
        self._queue: queue.Queue = queue.Queue()
        self._handler: Callable[[str, str], None] | None = None
        self._thread: threading.Thread | None = None

    def set_handler(self, handler: Callable[[str, str], None]) -> None:
        self._handler = handler

    def start(self) -> None:
        self._thread = threading.Thread(target=self._loop, name="hotkey-dispatch", daemon=True)
        self._thread.start()

    def stop(self) -> None:
        if self._thread is not None:
            self._queue.put(None)
            self._thread.join()
            self._thread = None

    def submit(self, binding: str, kind: str) -> None:
        self._queue.put((binding, kind))

    def _loop(self) -> None:
        while True:
            item = self._queue.get()
            if item is None:
                return
            handler = self._handler
            if handler is None:
                continue
            try:
                handler(*item)
            except Exception:
                log.exception("hotkey handler failed for %s", item)