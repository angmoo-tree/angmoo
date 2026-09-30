"""The single backend's media composition shared with the resident runtime."""
from threading import RLock

_lock = RLock()
_runtime = None


def register(runtime):
    global _runtime
    with _lock:
        _runtime = runtime


def current():
    with _lock:
        return _runtime


def unregister(runtime):
    global _runtime
    with _lock:
        if _runtime is runtime:
            _runtime = None
