"""Optional Session write spans. Does not change SQL, transaction or retry policy."""
from contextlib import contextmanager
from functools import wraps
from uuid import uuid4
from time import monotonic_ns
from sqlalchemy import event
from app.core import work_observation as observation

_KEY = "_angmoo_write_observation"


def _safe(function):
    @wraps(function)
    def wrapped(*args, **kwargs):
        try:
            return function(*args, **kwargs)
        except Exception:
            return None
    return wrapped


class _SessionSpan:
    def __init__(self, session):
        self.session = session
        self.span_id = None
        self.finishing = False
        self.connections = []
        self.database_id = observation.database_id(session.get_bind().engine.url.database)

    @_safe
    def start(self):
        if not observation.enabled() or observation.facts().get("operation") == "sqlite_writer":
            return
        if self.span_id is None:
            self.span_id = uuid4().hex
            observation.emit("session_write", boundary="write_started", span_id=self.span_id, database_id=self.database_id)

    @_safe
    def execute(self, state):
        if state.is_insert or state.is_update or state.is_delete:
            self.start()
        elif getattr(state.statement, "text", "").lstrip().split(" ", 1)[0].upper() in {"INSERT", "UPDATE", "DELETE", "REPLACE", "CREATE", "DROP", "ALTER"}:
            self.start()

    @_safe
    def flush(self, session, flush_context, instances):
        if session.new or session.deleted or any(session.is_modified(row, include_collections=False) for row in session.dirty):
            self.start()

    @_safe
    def begin(self, session, transaction, connection):
        if connection not in self.connections:
            event.listen(connection, "before_cursor_execute", self.cursor)
            self.connections.append(connection)

    @_safe
    def cursor(self, connection, cursor, statement, parameters, context, executemany):
        # Classify locally; no SQL, parameter or path is retained or exported.
        if statement.lstrip().split(None, 1)[0].upper() in {"INSERT", "UPDATE", "DELETE", "REPLACE", "CREATE", "DROP", "ALTER"}:
            self.start()

    @_safe
    def end(self, session, transaction):
        if transaction.parent is None and not self.finishing:
            self.finish("end_unwrapped")

    @_safe
    def notify(self, boundary):
        if self.span_id is not None:
            observation.emit("session_write", boundary=boundary, span_id=self.span_id, database_id=self.database_id)

    @_safe
    def finish(self, boundary):
        self.notify(boundary)
        self.span_id = None


@contextmanager
def observe_session(session):
    if not observation.enabled() or _KEY in session.info:
        yield
        return
    tracker = _SessionSpan(session)
    session.info[_KEY] = tracker
    hooks = (("do_orm_execute", tracker.execute), ("before_flush", tracker.flush),
        ("after_begin", tracker.begin), ("after_transaction_end", tracker.end))
    installed = []
    try:
        for name, callback in hooks:
            event.listen(session, name, callback)
            installed.append((name, callback))
        yield
    finally:
        tracker.finish("end_missing")
        for name, callback in installed:
            _safe(event.remove)(session, name, callback)
        for connection in tracker.connections:
            _safe(event.remove)(connection, "before_cursor_execute", tracker.cursor)
        session.info.pop(_KEY, None)


def finish_session(session, *, rollback=False):
    """Measure the existing owner's call through return, without adding a call."""
    tracker = session.info.get(_KEY)
    if tracker is None:
        return session.rollback() if rollback else session.commit()
    tracker.finishing = True
    tracker.notify("rollback_started" if rollback else "commit_started")
    try:
        result = session.rollback() if rollback else session.commit()
    except BaseException:
        tracker.notify("finish_failed")
        raise
    else:
        tracker.finish("rolled_back" if rollback else "committed")
        return result
    finally:
        tracker.finishing = False


@contextmanager
def session_child(session):
    """Nested diagnostic persistence is part of the outer write, never another hold."""
    tracker = session.info.get(_KEY)
    if tracker is None or not observation.enabled():
        yield
        return
    started = _safe(monotonic_ns)()
    try:
        yield
    finally:
        ended = _safe(monotonic_ns)() if started is not None else None
        if tracker.span_id is not None and ended is not None:
            observation.emit("session_write", boundary="diagnostic_persist", span_id=tracker.span_id,
                elapsed_ms=(ended - started) / 1_000_000)
