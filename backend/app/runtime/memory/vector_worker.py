"""Bound native Vec1 reads by terminating and joining their owning process.

Vec1 0.7 has no sqlite3_is_interrupted check inside its distance loop. Cancelling
an asyncio thread wrapper alone cannot enforce a hard native execution deadline.
The child owns its connection and never owns a canonical write or credential.
"""
import asyncio
import multiprocessing
from time import monotonic

from app.runtime.memory.sqlite_vec1 import (
    MemoryVectorProjectionError, SqliteMemoryVectorIndex, VectorCancellation,
)


def _search_child(pipe, database_path, extension_path, extension_sha256, generation, query, deadline):
    try:
        index = SqliteMemoryVectorIndex(database_path, extension_path=extension_path,
                                       extension_sha256=extension_sha256, generation=generation)
        result = index.search(query, cancellation=VectorCancellation(deadline))
        pipe.send((True, result))
    except BaseException:
        pipe.send((False, "memory_vector_worker_failed"))
    finally:
        pipe.close()


class VectorReadWorkers:
    _child_target = staticmethod(_search_child)
    def __init__(self, *, database_path, extension_path, extension_sha256,
                 generation="v1", concurrency=2):
        if not 1 <= concurrency <= 4:
            raise ValueError("memory_vector_worker_limit_invalid")
        self._slots = asyncio.Semaphore(concurrency)
        self._arguments = (database_path, extension_path, extension_sha256, generation)
        self.active_processes = set()

    async def search(self, query, *, deadline):
        remaining = deadline-monotonic()
        if remaining <= 0:
            raise TimeoutError("memory_vector_deadline")
        async with asyncio.timeout(remaining):
            async with self._slots:
                context = multiprocessing.get_context("spawn")
                receiver, sender = context.Pipe(duplex=False)
                process = context.Process(target=self._child_target,
                    args=(sender, *self._arguments, query, deadline), daemon=True)
                try:
                    process.start()
                    self.active_processes.add(process.pid)
                    sender.close()
                    while not receiver.poll():
                        if not process.is_alive():
                            raise MemoryVectorProjectionError("memory_vector_worker_exited")
                        await asyncio.sleep(0.005)
                    success, value = receiver.recv()
                    if not success:
                        raise MemoryVectorProjectionError(value)
                    return value
                finally:
                    # No await here: repeated cancellation cannot bypass cleanup.
                    # terminate only this private read process, never the app.
                    if process.pid is not None:
                        if process.is_alive():
                            process.terminate()
                        process.join(timeout=1.0)
                        if process.is_alive():
                            process.kill()
                            process.join(timeout=1.0)
                        self.active_processes.discard(process.pid)
                        process.close()
                    receiver.close()
                    sender.close()
