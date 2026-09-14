"""Independent process/connection for bounded FTS5 reads, including fallback."""
import asyncio
from time import monotonic
from app.contracts.retrieval_observation import Observation, current
from app.domains.memory.contracts.hybrid_recall import RankedMemoryCandidate
from app.domains.memory.contracts.hybrid_recall import HybridAxisResult, RecallAxisReceipt, RecallAxisStatus
from app.domains.memory.contracts.recall import MemoryRecallSearchIncomplete
from app.runtime.memory.sqlite_fts5_recall import SqliteMemoryRecallIndex
from app.runtime.memory.vector_worker import VectorReadWorkers


def _fts_child(pipe, database_path, settings, query, deadline):
    started = monotonic()
    observation = Observation()
    token = current.set(observation)
    try:
        index = SqliteMemoryRecallIndex.reader(database_path, settings=settings)
        candidates = index.search(query)
        ranked = tuple(RankedMemoryCandidate(row,
            int(row.metadata["item_version"]), row.metadata["document_content_hash"])
            for row in candidates[:query.limit])
        failed = any(row.get("reason") == "fts_execution_error" for row in observation.events)
        result = HybridAxisResult(ranked, RecallAxisReceipt("fts", RecallAxisStatus.PARTIAL if failed else RecallAxisStatus.READY,
            True, len(ranked), (monotonic()-started)*1000, "fts_execution_error" if failed else None))
        pipe.send((True, (result, observation.payload())))
    except MemoryRecallSearchIncomplete:
        pipe.send((True, (HybridAxisResult((), RecallAxisReceipt("fts", RecallAxisStatus.UNAVAILABLE,
            True, 0, (monotonic()-started)*1000, "memory_fts_incomplete")), observation.payload())))
    except BaseException:
        pipe.send((False, "memory_fts_worker_failed"))
    finally:
        current.reset(token)
        pipe.close()


class FtsReadWorkers(VectorReadWorkers):
    _child_target = staticmethod(_fts_child)

    def __init__(self, *, database_path, settings=None, concurrency=2):
        if not 1 <= concurrency <= 4:
            raise ValueError("memory_fts_worker_limit_invalid")
        self._slots = asyncio.Semaphore(concurrency)
        self._arguments = (database_path, settings)
        self.active_processes = set()
