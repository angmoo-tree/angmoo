"""One bounded canonical read worker; Sessions never enter from the caller."""
import asyncio
from contextlib import contextmanager
from dataclasses import dataclass
from threading import Event, local
from time import monotonic
from sqlalchemy import event
from sqlalchemy.exc import OperationalError, TimeoutError as CheckoutTimeout
from app.core.sqlite_concurrency import SqliteAsyncTaskQueue
from app.exceptions import SqliteTaskQueueFull


@dataclass(frozen=True, slots=True)
class CanonicalReadReceipt:
    stage: str
    wait_ms: float
    elapsed_ms: float
    sql_count: int
    cleaned: bool
    unique_nodes: int | None
    memo_hits: int | None


class DeadlineSessionFactory:
    def __init__(self, factory):
        self.factory, self.local = factory, local()

    def record_access(self, metrics):
        work = getattr(self.local, "work", None)
        if work is not None:
            counters = work[2]
            counters[2] = (counters[2] or 0) + metrics.unique_nodes
            counters[3] = (counters[3] or 0) + metrics.memo_hits

    @contextmanager
    def __call__(self):
        work = getattr(self.local, "work", None)
        if work is None:
            raise RuntimeError("canonical_worker_context_missing")
        deadline, cancelled, counters = work
        if cancelled.is_set() or monotonic() >= deadline:
            raise TimeoutError("canonical_read_deadline")
        with self.factory() as session:
            driver, connection, timeout, listening = None, None, None, False
            def count(*_):
                counters[0] += 1
                if cancelled.is_set() or monotonic() >= deadline:
                    raise TimeoutError("canonical_read_deadline")
            try:
                connection = session.connection()
                driver = connection.connection.driver_connection
                timeout = driver.execute("PRAGMA busy_timeout").fetchone()[0]
                driver.execute(f"PRAGMA busy_timeout={max(1, min(50, int((deadline-monotonic())*1000)))}")
                driver.set_progress_handler(lambda: int(cancelled.is_set() or monotonic() >= deadline), 1000)
                event.listen(connection, "before_cursor_execute", count)
                listening = True
                yield session
            finally:
                # Rollback while the worker still owns the connection. Reset
                # interruption and busy policy before returning it to the pool.
                if listening:
                    event.remove(connection, "before_cursor_execute", count)
                if driver is not None:
                    driver.set_progress_handler(None, 0)
                    if timeout is not None:
                        driver.execute(f"PRAGMA busy_timeout={timeout}")
                session.rollback()
                counters[1] = 1


class CanonicalReadWorker:
    def __init__(self, sessions, reader):
        self.sessions, self.reader = sessions, reader
        self.queue = SqliteAsyncTaskQueue(capacity=8, closed_code="canonical_worker_closed")
        self.signals = set()

    def axis_request(self, request):
        return getattr(self.reader, "axis_request", lambda value: value)(request)

    async def _call(self, stage, request, rows, deadline):
        submitted, signal = monotonic(), Event()
        self.signals.add(signal)
        def execute():
            started, counters = monotonic(), [0, 0, None, None]
            self.sessions.local.work = deadline, signal, counters
            try:
                if signal.is_set() or started >= deadline:
                    raise TimeoutError("canonical_read_deadline")
                result = getattr(self.reader, stage)(request, rows)
                if signal.is_set() or monotonic() >= deadline:
                    raise TimeoutError("canonical_read_deadline")
                return result, CanonicalReadReceipt(stage, (started-submitted)*1000,
                    (monotonic()-started)*1000, counters[0], bool(counters[1]), counters[2], counters[3])
            finally:
                del self.sessions.local.work
        try:
            async with asyncio.timeout(max(0, deadline-monotonic())):
                result, receipt = await self.queue.call(execute)
            # Merge only immutable, bounded facts on the parent task. No request
            # collector/ContextVar or raw values are shared with this thread.
            from app.contracts.search_diagnostics import canonical_read
            canonical_read(receipt)
            return result
        except (TimeoutError, asyncio.CancelledError) as exc:
            from app.contracts.search_diagnostics import canonical_read
            canonical_read(stage=stage, status="cancelled" if isinstance(exc, asyncio.CancelledError) else "deadline")
            raise
        except (SqliteTaskQueueFull, CheckoutTimeout) as exc:
            from app.contracts.search_diagnostics import canonical_read
            canonical_read(stage=stage, status="unavailable")
            raise RuntimeError("canonical_read_unavailable") from exc
        except OperationalError as exc:
            if signal.is_set() or monotonic() >= deadline:
                raise TimeoutError("canonical_read_deadline") from exc
            raise
        finally:
            signal.set()
            self.signals.discard(signal)

    async def revalidate_async(self, request, candidates, *, deadline):
        return await self._call("revalidate", request, candidates, deadline)

    async def hydrate_async(self, request, records, *, deadline):
        return await self._call("hydrate", request, records, deadline)

    async def stop(self):
        self.queue.close()
        for signal in tuple(self.signals):
            signal.set()
        await self.queue.drain()
