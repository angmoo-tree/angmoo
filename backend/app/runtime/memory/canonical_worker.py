"""One bounded canonical read worker; Sessions never enter from the caller."""
import asyncio
from contextlib import contextmanager
from threading import Event, local
from time import monotonic
from sqlalchemy import event
from sqlalchemy.exc import OperationalError, TimeoutError as CheckoutTimeout
from app.core.sqlite_concurrency import SqliteAsyncTaskQueue
from app.exceptions import SqliteTaskQueueFull
from app.runtime.memory.canonical_metrics import ReadProgress


class DeadlineSessionFactory:
    def __init__(self, factory):
        self.factory, self.local = factory, local()

    def record_access(self, metrics):
        work = getattr(self.local, "work", None)
        if work is not None:
            counters = work[2]
            counters[2] = (counters[2] or 0) + metrics.unique_nodes
            counters[3] = (counters[3] or 0) + metrics.memo_hits
            if work[3] is not None:
                work[3].update(counters)

    @contextmanager
    def phase(self, name):
        _, _, counters, progress = self.local.work
        if progress is not None:
            progress.phase_start(name, counters[0])
        completed = False
        try:
            yield
            completed = True
        finally:
            if progress is not None:
                progress.phase_end(counters[0], completed)

    @contextmanager
    def __call__(self):
        work = getattr(self.local, "work", None)
        if work is None:
            raise RuntimeError("canonical_worker_context_missing")
        deadline, cancelled, counters, progress = work
        if cancelled.is_set() or monotonic() >= deadline:
            raise TimeoutError("canonical_read_deadline")
        with self.factory() as session:
            if session.get_bind().dialect.name == "postgresql":
                from app.core.postgresql_deadline import read_deadline
                from app.core.postgresql_reads import begin_owned_read
                connection = session.connection()
                def pg_count(*_):
                    counters[0] += 1
                    if progress is not None:
                        progress.update(counters)
                event.listen(connection,"before_cursor_execute",pg_count)
                try:
                    with read_deadline(connection,deadline,cancelled=cancelled):
                        begin_owned_read(connection)
                        yield session
                finally:
                    event.remove(connection,"before_cursor_execute",pg_count)
                    session.rollback()
                    counters[1] = 1
                    if progress is not None:
                        progress.update(counters)
                return
            driver, connection, timeout, listening = None, None, None, False
            def count(*_):
                counters[0] += 1
                if progress is not None:
                    progress.update(counters)
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
                # sqlite3 legacy transaction control does not BEGIN for SELECT.
                # Pin one read snapshot without reserving the database writer.
                if not driver.in_transaction:
                    connection.exec_driver_sql("BEGIN DEFERRED")
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
                if progress is not None:
                    progress.update(counters)


class CanonicalReadWorker:
    def __init__(self, sessions, reader, *, separate_guard=False):
        self.sessions, self.reader = sessions, reader
        self.queue = SqliteAsyncTaskQueue(capacity=8, closed_code="canonical_worker_closed")
        # A final delivered-evidence guard must not sit behind new bulk recalls.
        # Both lanes open their own fresh Session and share the existing DB pool.
        # PostgreSQL enables one extra reader; no unbounded executor or new pool.
        self.guard_queue = (SqliteAsyncTaskQueue(capacity=4, closed_code="canonical_worker_closed")
                            if separate_guard else self.queue)
        self.signals = set()

    def axis_request(self, request):
        return getattr(self.reader, "axis_request", lambda value: value)(request)

    async def _call(self, stage, request, rows, deadline, *, diagnostics=True):
        from app.contracts.search_diagnostics import canonical_read, collector
        submitted, signal = monotonic(), Event()
        progress = ReadProgress(stage, submitted) if diagnostics and collector() is not None else None
        def report(receipt, *, status="completed"):
            if diagnostics:
                canonical_read(receipt, stage=stage, status=status)
        self.signals.add(signal)
        def execute():
            started, counters = monotonic(), [0, 0, None, None]
            self.sessions.local.work = deadline, signal, counters, progress
            if progress is not None:
                progress.start()
            try:
                if signal.is_set() or started >= deadline:
                    raise TimeoutError("canonical_read_deadline")
                from app.core.postgresql_reads import retry_read
                # Every reader entrypoint owns a fresh Session and validation
                # memo. Only PostgreSQL SQLSTATE aborts retry; SQLite errors,
                # changed evidence and provider work are never replayed here.
                result = retry_read(lambda: getattr(self.reader, stage)(request, rows),
                    deadline=deadline, cancelled=signal)
                if signal.is_set() or monotonic() >= deadline:
                    raise TimeoutError("canonical_read_deadline")
                return result
            finally:
                if progress is not None:
                    progress.finish(counters)
                del self.sessions.local.work
        try:
            async with asyncio.timeout(max(0, deadline-monotonic())):
                queue = self.guard_queue if stage == "assert_current" else self.queue
                result = await queue.call(execute)
            # Merge only immutable, bounded facts on the parent task. No request
            # collector/ContextVar or raw values are shared with this thread.
            report(None if progress is None else progress.receipt())
            return result
        except (TimeoutError, asyncio.CancelledError) as exc:
            report(None if progress is None else progress.receipt(),
                status="cancelled" if isinstance(exc, asyncio.CancelledError) else "deadline")
            raise
        except (SqliteTaskQueueFull, CheckoutTimeout) as exc:
            report(None if progress is None else progress.receipt(), status="unavailable")
            raise RuntimeError("canonical_read_unavailable") from exc
        except OperationalError as exc:
            expired = signal.is_set() or monotonic() >= deadline
            report(None if progress is None else progress.receipt(), status="deadline" if expired else "unavailable")
            if expired:
                raise TimeoutError("canonical_read_deadline") from exc
            raise
        except Exception:
            report(None if progress is None else progress.receipt(), status="unavailable")
            raise
        finally:
            signal.set()
            self.signals.discard(signal)

    async def revalidate_async(self, request, candidates, *, deadline):
        return await self._call("revalidate", request, candidates, deadline)

    async def resolve_async(self, request, candidates, *, deadline):
        return await self._call("resolve", request, candidates, deadline)

    async def hydrate_async(self, request, records, *, deadline):
        return await self._call("hydrate", request, records, deadline)

    async def assert_current_async(self, result, delivered_ids, *, deadline):
        # These are application-boundary guards, not another search. They use
        # the same bounded worker/cleanup without overwriting search receipts.
        return await self._call("assert_current", result, delivered_ids, deadline, diagnostics=False)

    async def stop(self):
        self.queue.close()
        if self.guard_queue is not self.queue:
            self.guard_queue.close()
        for signal in tuple(self.signals):
            signal.set()
        await self.queue.drain()
        if self.guard_queue is not self.queue:
            await self.guard_queue.drain()
