"""Vector pool configuration; the child loads the native implementation."""
from app.runtime.memory.search_worker_pool import SearchReadWorkers


class VectorReadWorkers(SearchReadWorkers):
    _axis = "vector"

    def __init__(self, *, database_path, extension_path, extension_sha256,
                 generation="v1", concurrency=2, control=None):
        super().__init__(arguments=(database_path, extension_path, extension_sha256, generation),
                         generation=generation, concurrency=concurrency, control=control)
