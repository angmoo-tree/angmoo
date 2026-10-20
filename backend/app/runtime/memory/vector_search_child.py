"""Request-local vector connection and cancellation; no parent pool imports."""
from app.runtime.memory.sqlite_vec1 import SqliteMemoryVectorIndex, VectorCancellation
from app.runtime.memory.worker_diagnostics import current_worker, phase


def search(pipe, database_path, extension_path, extension_sha256, generation, query, deadline):
    try:
        trace = current_worker.get()
        if trace is not None:
            trace.metadata.update(requested_generation=generation, requested_profile=query.profile)
        with phase("extension_verify"):
            index = SqliteMemoryVectorIndex(database_path, extension_path=extension_path,
                extension_sha256=extension_sha256, generation=generation)
        result = index.search(query, cancellation=VectorCancellation(deadline))
        pipe.send((True, result))
    finally:
        pipe.close()
