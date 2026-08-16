"""Process signal bridge for cooperative runtime shutdown.

The host launcher and Compose only deliver operating-system signals. Runtime
workers remain responsible for turning those signals into domain-safe stop
requests before the container grace period expires.
"""

from __future__ import annotations

from collections.abc import Callable, Iterator
from contextlib import contextmanager
import signal
from types import FrameType


ShutdownCallback = Callable[[int], None]


@contextmanager
def installed_shutdown_signal_handlers(
    callback: ShutdownCallback,
) -> Iterator[None]:
    """Install SIGTERM/SIGINT handlers and restore the previous handlers."""

    watched = tuple(
        item
        for item in (getattr(signal, "SIGTERM", None), getattr(signal, "SIGINT", None))
        if item is not None
    )
    previous: dict[int, signal.Handlers] = {}

    def handle(signum: int, _frame: FrameType | None) -> None:
        callback(signum)

    try:
        for item in watched:
            previous[int(item)] = signal.getsignal(item)
            signal.signal(item, handle)
        yield
    finally:
        for signum, handler in previous.items():
            signal.signal(signum, handler)
