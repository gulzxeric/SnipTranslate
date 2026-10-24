"""Cooperative cancellation at safe OCR and translation boundaries."""
from concurrent.futures import CancelledError
from threading import Event, Lock


class CancellationToken(Event):
    def __init__(self):
        super().__init__()
        self._callback_lock = Lock()
        self._callbacks = set()

    def register(self, callback):
        with self._callback_lock:
            cancelled = self.is_set()
            if not cancelled:
                self._callbacks.add(callback)
        if cancelled:
            callback()
        def unregister():
            with self._callback_lock:
                self._callbacks.discard(callback)
        return unregister

    def set(self):
        with self._callback_lock:
            if self.is_set():
                return
            super().set()
            callbacks = list(self._callbacks)
        for callback in callbacks:
            callback()


def check_cancelled(event=None):
    if event is not None and event.is_set():
        raise CancelledError()
