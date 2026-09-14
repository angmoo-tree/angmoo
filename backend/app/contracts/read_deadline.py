"""Request-local native read deadline shared with storage adapters."""
from contextlib import contextmanager
from contextvars import ContextVar
from time import monotonic

current_read_deadline: ContextVar[float | None] = ContextVar("current_read_deadline", default=None)


@contextmanager
def bounded_read(seconds: float):
    previous = current_read_deadline.get()
    deadline = monotonic() + max(0.0, seconds)
    token = current_read_deadline.set(min(previous, deadline) if previous is not None else deadline)
    try:
        yield
    finally:
        current_read_deadline.reset(token)
