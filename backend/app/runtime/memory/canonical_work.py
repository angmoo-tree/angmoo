"""Memory's owned, bounded SQL execution boundary."""
from app.core.sqlite_concurrency import SqliteAsyncTaskQueue


class MemoryCanonicalWork(SqliteAsyncTaskQueue):
    def __init__(self):
        super().__init__(closed_code="memory_canonical_worker_closed")
