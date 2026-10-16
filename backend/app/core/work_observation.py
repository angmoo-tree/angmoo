"""Optional, process-local diagnostics port. Never owns business state or I/O.

Runtime supplies a non-blocking sink. Context values are explicit structural
facts; adapters must not pass request bodies, credentials or exception strings.
"""
from contextlib import contextmanager
from contextvars import ContextVar
from datetime import UTC, datetime
from functools import wraps
from hashlib import sha256
from inspect import iscoroutinefunction
from os.path import abspath, normcase
from time import monotonic_ns
from uuid import uuid4

_sink = None
_generation = None
_context = ContextVar("work_observation", default={})


def install(sink):
    global _sink, _generation
    previous, previous_generation = _sink, _generation
    _sink, _generation = sink, uuid4().hex
    def remove():
        global _sink, _generation
        if _sink is sink:
            _sink, _generation = previous, previous_generation
    return remove


def enabled():
    return _sink is not None


def facts():
    return dict(_context.get())


@contextmanager
def scope(**values):
    if _sink is None:
        yield
        return
    token = _context.set({"_observation_generation": _generation, **_context.get(), **values})
    try:
        yield
    finally:
        _context.reset(token)


def emit(event, **values):
    sink = _sink
    if sink is not None:
        try:
            if _context.get().get("_observation_generation", _generation) != _generation:
                sink({"event": "diagnostic_loss", "reason": "previous_observer_generation"})
                return
            sink({**_context.get(), **values, "event": event,
                  "monotonic_ns": monotonic_ns(), "occurred_at": datetime.now(UTC).isoformat()})
        except Exception:
            pass  # Diagnostic failure never replays or fails business work.


@contextmanager
def span(operation, **values):
    if _sink is None:
        yield
        return
    with scope(**{**values, "operation": operation, "span_id": uuid4().hex,
                  "parent_span_id": _context.get().get("span_id")}):
        emit("stage", boundary="start")
        try:
            yield
        except BaseException:
            emit("stage", boundary="end", outcome="interrupted")
            raise
        else:
            emit("stage", boundary="end", outcome="completed")


def observed(operation):
    def decorate(function):
        if iscoroutinefunction(function):
            @wraps(function)
            async def asynchronous(*args, **kwargs):
                with span(operation):
                    return await function(*args, **kwargs)
            return asynchronous
        @wraps(function)
        def synchronous(*args, **kwargs):
            with span(operation):
                return function(*args, **kwargs)
        return synchronous
    return decorate


def database_id(path):
    return sha256(normcase(abspath(str(path))).encode()).hexdigest() if path and path != ":memory:" else "in_memory"


def sqlite_observed(function):
    @wraps(function)
    def wrapped(owner, operation, *args, **kwargs):
        if _sink is None:
            return function(owner, operation, *args, **kwargs)
        bind = owner.get_bind() if hasattr(owner, "get_bind") else owner
        identity = database_id(bind.engine.url.database)
        label = f"{getattr(operation, '__module__', 'unknown')}.{getattr(operation, '__qualname__', type(operation).__name__)}".replace("<", "").replace(">", "")
        with span("sqlite_writer", database_id=identity, writer=label):
            try:
                return function(owner, operation, *args, **kwargs)
            finally:
                emit("sqlite", boundary="cleanup_complete")
    return wrapped
