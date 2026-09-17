import pytest

from app.domains.chat.contracts.generation_lifecycle import GenerationContractError
from app.domains.chat.repository.response_lifecycle import _validate_evidence_inspector_snapshot


@pytest.mark.parametrize("kind,length,accepted", [
    ("episode_memory", 8000, True), ("episode_memory", 8001, False),
    ("canonical_source", 2000, True), ("canonical_source", 2001, False),
])
def test_episode_receipt_accepts_bounded_packet_without_relaxing_legacy(kind, length, accepted):
    snapshot = {"version": "evidence-inspector.v1", "items": [{
        "ref": "test-ref", "kind": kind, "text": "x" * length,
        "occurred_at": None, "axes": [], "locator": None,
    }]}
    if accepted:
        _validate_evidence_inspector_snapshot(snapshot, public_evidence_count=1)
    else:
        with pytest.raises(GenerationContractError):
            _validate_evidence_inspector_snapshot(snapshot, public_evidence_count=1)
