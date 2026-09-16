"""Independent process/connection for bounded FTS5 reads, including fallback."""
import asyncio
from time import monotonic
from app.contracts.retrieval_observation import Observation, current
from app.domains.memory.contracts.hybrid_recall import RankedMemoryCandidate
from app.domains.memory.contracts.hybrid_recall import HybridAxisResult, RecallAxisReceipt, RecallAxisStatus
from app.domains.memory.contracts.recall import MemoryRecallSearchIncomplete, MemoryRecallLexicalPolicy
from app.domains.memory.contracts.fts_recall import FtsWorkerRequest
from app.runtime.memory.sqlite_fts5_recall import SqliteMemoryRecallIndex
from app.runtime.memory.vector_worker import VectorReadWorkers
from app.runtime.memory.worker_diagnostics import phase, capture_failure


def _fts_child(pipe, database_path, settings, query, deadline):
    started = monotonic()
    request = query if isinstance(query, FtsWorkerRequest) else FtsWorkerRequest(query)
    query = request.query
    observation = Observation(detailed=request.capture_details)
    token = current.set(observation)
    try:
        with phase("db_open"):
            index = SqliteMemoryRecallIndex.reader(database_path, settings=settings)
        with phase("fts_search"):
            batch = index.search_grouped(query, deadline=deadline) if query.lexical_policy == MemoryRecallLexicalPolicy.GROUP_OR_V1 else None
            candidates = batch.candidates if batch is not None else index.search(query)
        ranked = tuple(RankedMemoryCandidate(row,
            int(row.metadata["item_version"]), row.metadata["document_content_hash"])
            for row in candidates[:query.limit])
        failed = any(row.get("reason") == "fts_execution_error" for row in observation.events)
        status = batch.status if batch is not None else (RecallAxisStatus.PARTIAL if failed else RecallAxisStatus.READY)
        result = HybridAxisResult(ranked, RecallAxisReceipt("fts", status,
            batch.executed if batch is not None else True, len(ranked), (monotonic()-started)*1000,
            batch.reason_code if batch is not None else ("fts_execution_error" if failed else None)))
        payload = observation.payload()
        if request.capture_details:
            payload["details"] = observation.details
            payload["detail_omitted"] = observation.detail_omitted
        pipe.send((True, (result, payload)))
    except MemoryRecallSearchIncomplete:
        pipe.send((True, (HybridAxisResult((), RecallAxisReceipt("fts", RecallAxisStatus.UNAVAILABLE,
            True, 0, (monotonic()-started)*1000, "memory_fts_incomplete")), observation.payload())))
    except BaseException as exc:
        capture_failure(exc)
        pipe.send((False, "memory_fts_worker_failed"))
    finally:
        current.reset(token)
        pipe.close()


class FtsReadWorkers(VectorReadWorkers):
    _axis = "fts"
    _child_target = staticmethod(_fts_child)

    def __init__(self, *, database_path, settings=None, concurrency=2):
        if not 1 <= concurrency <= 4:
            raise ValueError("memory_fts_worker_limit_invalid")
        self._slots = asyncio.Semaphore(concurrency)
        self._arguments = (database_path, settings)
        self.active_processes = set()
