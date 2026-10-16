"""Prepared-work batching boundary with the real pinned SDK and mock HTTP.

Canonical preparation/fences are covered by the projection/recovery suites.
Here controlled prepared inputs isolate group, byte and cardinality boundaries.
"""
import asyncio
from types import SimpleNamespace
import json
import pytest
from app.core import work_observation as observation
from app.domains.memory.contracts.embedding import MemoryEmbeddingConfiguration
from app.domains.memory.contracts.scope import MemoryScope
from app.providers.gemini import GeminiAdapter
from app.runtime.memory import vector_batches
from app.runtime.memory.vector_delivery import PreparedVector
from memory.test_embedding_batch_transport import transport


@pytest.mark.parametrize("case,count,expected", [
    ("item", 21, [20, 1]), ("byte", 20, [5, 5, 5, 5]),
    ("actor", 2, [1, 1]), ("credential_revision", 2, [1, 1]), ("configuration", 2, [1, 1]),
])
def test_prepared_groups_match_independent_transport_and_membership(transport, monkeypatch, case, count, expected):
    prepared = {}
    for number in range(count):
        actor = f"actor-{number}" if case == "actor" else "actor"
        revision = number + 1 if case == "credential_revision" else 1
        configuration = MemoryEmbeddingConfiguration(enabled=True, version=number if case == "configuration" else 1)
        identifier = f"item-{number}"
        prepared[identifier] = PreparedVector(identifier,
            (MemoryScope("owner", "world", actor), configuration, f"digest-{number}", 1),
            SimpleNamespace(text="가" * 2000 if case == "byte" else f"independent {number}"),
            SimpleNamespace(credential_id="synthetic-key", reveal=lambda: "synthetic-only"),
            revision, f"revision-{revision}", f"binding-{number}", None)
    stored, events = {}, []
    class Worker:
        async def call(self, operation, *args, **kwargs):
            return operation(*args, **kwargs)
    projection = SimpleNamespace(_closing=False, _received={}, _claims={}, _canonical=Worker(),
        generation="v1", _provider=GeminiAdapter(), logical_calls=0, physical_attempts=0,
        index=SimpleNamespace(identity=lambda _: None),
        journal=SimpleNamespace(read=lambda *_: None, write=lambda *_: None),
        _claim_attempts=lambda keys, **_: {key[0] for key in keys})
    monkeypatch.setattr(vector_batches, "prepare", lambda _p, identifier, *_: prepared[identifier])
    def persist(_p, item, receipt):
        stored[item.item_id] = tuple(receipt["vector"])
        return "indexed"
    monkeypatch.setattr(vector_batches, "persist", persist)
    remove = observation.install(events.append)
    try:
        result = asyncio.run(vector_batches.sync_items(projection, tuple(prepared)))
    finally:
        remove()
    assert set(result.values()) == {"indexed"}
    requests = [json.loads(request.content)["requests"] for request in transport[0]]
    assert [len(rows) for rows in requests] == expected
    assert len([row for row in events if row.get("boundary") == "attempt_start"]) == len(requests)
    batches = [row for row in events if row["event"] == "embedding_batch" and row.get("boundary") == "candidates"]
    assert [member["item_id"] for row in batches for member in row["members"]] == list(prepared)
    for batch in batches:
        assert [stored[member["item_id"]][0] for member in batch["members"]] == list(range(1, len(batch["members"]) + 1))
    if case in {"item", "byte"}:
        assert batches[0]["reason"] == f"{case}_limit"
    else:
        assert all(row["group_size"] == 1 for row in batches)
