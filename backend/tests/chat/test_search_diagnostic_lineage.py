"""Canonical-reference duplication is observable without changing recall policy."""
from dataclasses import replace
from datetime import UTC, datetime
from types import SimpleNamespace
import json

from app.contracts.retrieval_observation import Observation, current
from app.domains.memory.contracts.recall import CanonicalRecallRecord, RecallDocumentKind
from app.domains.memory.contracts.provenance import MemorySourceTypeV1
from app.domains.memory.contracts.scope import MemoryScope
from app.domains.memory.contracts.hybrid_recall import HybridRecallResult, HybridEmbeddingUsage, RecallAxisReceipt, RecallAxisStatus
from app.domains.memory.repository.hybrid_recall import SqlAlchemyHybridCanonicalReader
from app.domains.chat.service.hybrid_canonical import HybridCanonicalResult
from app.domains.chat.service.canonical_retrieval import CanonicalPlanningMetrics
from app.domains.chat.service.evidence_assembly import EvidenceBundleAssembler


def test_four_sources_become_eight_different_references_and_diagnostics_do_not_change_bundle():
    scope = MemoryScope("owner", "world", "character")
    records = tuple(CanonicalRecallRecord(reference=f"memory-source:m{i}:e{i}",
        kind=RecallDocumentKind.THREAD_MESSAGE, canonical_source_id=str(i),
        text=f"private-canary source {i}", occurred_at=datetime(2026,9,15,tzinfo=UTC),
        memory_item_id=f"m{i}", source_type=MemorySourceTypeV1.CHAT_MESSAGE,
        evidence_references=(f"chat_message:{i}",)) for i in range(4))
    class Canonical:
        def read_exact_sources(self, *, scope, references, now):
            return tuple(replace(r, reference=r.evidence_references[0]) for r in records)
    reader = SqlAlchemyHybridCanonicalReader(None, source_reader_factory=None, canonical=Canonical())
    payloads = []
    for detailed in (False, True):
        observation = Observation(detailed=detailed)
        token = current.set(observation)
        try:
            hydrated, receipts = reader.hydrate(SimpleNamespace(scope=scope), records)
            assert len(hydrated) == 8
            recall = HybridRecallResult("request", "call", "a"*64, scope, RecallAxisStatus.READY,
                hydrated, tuple(RecallAxisReceipt(a, RecallAxisStatus.READY, True, 4, 1) for a in ("fts", "vector")),
                receipts, HybridEmbeddingUsage(), 4, 0, 1)
            metrics = CanonicalPlanningMetrics(True, False, False, None, 0, 0, 1, 0, 8, None, None)
            bundle = EvidenceBundleAssembler().canonical(request_scope_hash="b"*64,
                result=HybridCanonicalResult("request", recall, metrics, {}))
            payloads.append((bundle.evidence_hash, bundle.provider_payload(), bundle.inspector_snapshot()))
            assert len(bundle.items) == 8
            if detailed:
                trace = observation.search_trace.payload()
                edges = trace["lineage"]
                linked = [r for r in edges if r["stage"] == "evidence"]
                assert len({r["source_ref"] for r in linked}) == 4
                assert len({r["evidence_ref"] for r in linked}) == 8
                dedup = [r for r in edges if r["stage"] == "dedup"]
                assert len(dedup) == 8 and all(r["action"] == "kept" for r in dedup)
                assert len({r["key_ref"] for r in dedup}) == 8
                assert len([r for r in edges if r["stage"] == "inspector"]) == 8
                assert "private-canary" not in json.dumps(trace)
        finally:
            current.reset(token)
    assert payloads[0] == payloads[1]
