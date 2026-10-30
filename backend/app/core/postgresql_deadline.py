"""Cancel a single owned PostgreSQL read without leaking timers into the pool."""
from contextlib import contextmanager
from threading import Event, Thread
from time import monotonic
from sqlalchemy import event
from sqlalchemy.exc import DBAPIError


@contextmanager
def read_deadline(connection, deadline, *, cancelled=None):
    driver=connection.connection.driver_connection
    finished=Event()
    def expired():
        return monotonic()>=deadline or (cancelled is not None and cancelled.is_set())
    def watch():
        while not finished.wait(min(.02,max(.001,deadline-monotonic()))):
            if expired():
                try:driver.cancel_safe(timeout=.5)
                except Exception:pass
                return
    def before(*_):
        if expired():raise TimeoutError("canonical_read_deadline")
    event.listen(connection,"before_cursor_execute",before)
    watcher=Thread(target=watch,name="angmoo-pg-read-deadline",daemon=True)
    watcher.start()
    try:
        if expired():raise TimeoutError("canonical_read_deadline")
        yield
    except DBAPIError as exc:
        if getattr(exc.orig,"sqlstate",None)=="57014" and expired():
            raise TimeoutError("canonical_read_deadline") from exc
        raise
    finally:
        # Join before the owner may release this connection. The cancel cannot
        # race with a later borrower executing an unrelated request.
        finished.set()
        watcher.join()
        event.remove(connection,"before_cursor_execute",before)
