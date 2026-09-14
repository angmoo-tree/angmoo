"""Real extension tests. An explicit verified build is required; no fake NN."""
from dataclasses import replace
from datetime import UTC, datetime
import hashlib
import os
import asyncio
from pathlib import Path
from time import monotonic

import pytest

from app.domains.memory.contracts.scope import MemoryScope
from app.domains.memory.contracts.vector_projection import MemoryVectorDocument, MemoryVectorQuery
from app.runtime.memory.sqlite_vec1 import (
    MemoryVectorProjectionError, SqliteMemoryVectorIndex, VectorCancellation, vector_blob,
)

SCOPE = MemoryScope("owner", "world", "self")
A = [1.0] + [0.0] * 767
B = [0.0, 1.0] + [0.0] * 766
PROFILE = "gemini-embedding-2.768.cos.v1"


@pytest.fixture
def index(tmp_path):
    path = os.environ.get("ANGMOO_TEST_VEC1_EXTENSION")
    if not path:
        pytest.skip("real Vec1 extension build not supplied")
    extension = Path(path)
    value = SqliteMemoryVectorIndex(tmp_path / "memory-vectors.sqlite3", extension_path=extension,
                                   extension_sha256=hashlib.sha256(extension.read_bytes()).hexdigest())
    assert "version 0.7" in value.open()
    return value


def document(identifier="one", vector=A, **kw):
    return replace(MemoryVectorDocument(identifier, identifier, SCOPE, 1, "a" * 64,
                                       PROFILE, vector, datetime(2026, 9, 14, tzinfo=UTC)), **kw)


def search(index, **kw):
    return index.search(replace(MemoryVectorQuery(SCOPE, PROFILE, A), **kw),
                        cancellation=VectorCancellation(monotonic()+5))


def test_real_empty_first_second_update_delete_and_restart(index):
    assert search(index).hits == ()
    index.upsert((document(),))
    assert [(h.document_id, h.distance) for h in search(index).hits] == [("one", 0)]
    index.upsert((document("two", B),))
    assert [(h.document_id, h.distance) for h in search(index).hits] == [("one", 0), ("two", 1)]
    index.open()
    assert len(search(index).hits) == 2
    index.upsert((document("one", [-x for x in A], version=2),))
    assert [h.document_id for h in search(index).hits] == ["two", "one"]
    index.upsert((document("one", A, version=1),))
    assert search(index).hits[-1].version == 2
    index.delete("one")
    assert [h.document_id for h in search(index).hits] == ["two"]
    index.delete("two")
    assert search(index).hits == ()


def test_filter_precedes_top_k_and_profile_isolation(index):
    foreign = MemoryScope("other", "world", "self")
    index.upsert(tuple(document(f"outside-{i}", A, scope=foreign) for i in range(30)) + (
        document("allowed", B), document("wrong-profile", A, profile="different"),
    ))
    result = search(index, limit=1)
    assert result.allowed_count == 1
    assert [h.document_id for h in result.hits] == ["allowed"]
    assert result.index_kind == "flat" and result.search_mode == "nn"


def test_cancelled_before_query_has_no_late_success(index):
    token = VectorCancellation(monotonic()+5)
    token.cancel()
    with pytest.raises(MemoryVectorProjectionError, match="cancelled"):
        index.search(MemoryVectorQuery(SCOPE, PROFILE, A), cancellation=token)


@pytest.mark.parametrize("vector", [[0.] * 768, [1.], [float("nan")] * 768,
                                    [float("inf")] * 768, [1e100] * 768, [True] * 768])
def test_invalid_vectors_never_reach_extension(vector):
    with pytest.raises(ValueError, match="memory_vector_invalid"):
        vector_blob(vector)


def test_process_worker_search_and_cancellation_leave_no_native_worker(index):
    from app.runtime.memory.vector_worker import VectorReadWorkers
    extension = Path(os.environ["ANGMOO_TEST_VEC1_EXTENSION"])
    workers = VectorReadWorkers(database_path=index.database_path, extension_path=extension,
        extension_sha256=hashlib.sha256(extension.read_bytes()).hexdigest())
    index.upsert((document(),))
    async def run():
        result = await workers.search(MemoryVectorQuery(SCOPE, PROFILE, A), deadline=monotonic()+10)
        assert result.hits[0].document_id == "one"
        assert not workers.active_processes
        task = asyncio.create_task(workers.search(MemoryVectorQuery(SCOPE, PROFILE, A), deadline=monotonic()+10))
        while not workers.active_processes:
            await asyncio.sleep(0)
        task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await task
        assert not workers.active_processes
    asyncio.run(run())
