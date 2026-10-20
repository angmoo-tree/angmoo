"""FTS pool configuration, independent of the vector implementation."""
from app.runtime.memory.search_worker_pool import SearchReadWorkers


class FtsReadWorkers(SearchReadWorkers):
    _axis = "fts"

    def __init__(self, *, database_path, settings=None, concurrency=2, control=None):
        super().__init__(arguments=(database_path, settings),
                         concurrency=concurrency, control=control)
