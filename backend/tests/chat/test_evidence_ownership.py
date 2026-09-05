"""Live-source eligibility remains Chat policy across reader composition."""

from dataclasses import replace
from datetime import UTC, datetime
from types import SimpleNamespace

import pytest

from app.domains.chat.service.evidence import EvidenceService
from app.domains.memory.contracts.source_evidence import CanonicalMemoryEvidence
from app.domains.memory.contracts.scope import MemoryScope
from app.domains.memory.contracts.provenance import MemorySourceTypeV1


@pytest.mark.parametrize(
    ("changed", "availability"),
    [
        ({}, "available"),
        ({"source_world_id": "another-world"}, "unavailable"),
        ({"visible": False}, "deleted"),
        ({"membership_active": False}, "unavailable"),
        ({"source_digest": "b" * 64}, "unavailable"),
    ],
)
def test_inspector_rechecks_live_scope_revision_and_visibility_before_excerpt(
    changed, availability
) -> None:
    session = object()
    scope = MemoryScope(
        owner_id="owner", world_id="world", subject_world_character_id="subject"
    )
    occurred_at = datetime(2026, 9, 5, tzinfo=UTC)
    evidence = replace(
        CanonicalMemoryEvidence(
            source_type=MemorySourceTypeV1.POST,
            source_id="post",
            source_world_id="world",
            source_digest="a" * 64,
            source_created_at=occurred_at,
            deterministic_summary="current source",
            successful=True,
            visible=True,
            observed_by_subject=True,
            membership_active=True,
            blocked=False,
            actor_world_character_id="subject",
            target_world_character_id="other",
        ),
        **changed,
    )
    source_calls = []
    name_calls = []

    def read_evidence(**kwargs):
        source_calls.append(kwargs)
        return evidence

    def world_character_name(db, character_id, *, world_id):
        name_calls.append((db, character_id, world_id))
        return "Current character"

    service = EvidenceService(
        thread_service=object(),
        reads=SimpleNamespace(world_character_name=world_character_name),
    )
    result = service._chat_evidence_item(
        session,
        scope,
        {
            "ref": "source-ref",
            "kind": "canonical_source",
            "text": "x" * 600,
            "occurred_at": occurred_at.isoformat(),
            "locator": {
                "kind": "canonical_source",
                "source_type": MemorySourceTypeV1.POST.value,
                "source_id": "post",
                "source_revision": "a" * 64,
            },
        },
        source_reader=SimpleNamespace(read_evidence=read_evidence),
    )

    assert source_calls == [
        {"scope": scope, "source_type": MemorySourceTypeV1.POST, "source_id": "post"}
    ]
    assert result.availability == availability
    if availability == "available":
        assert result.excerpt == "x" * 500
        assert result.canonical_href == "/worlds/world/posts/post"
        assert result.related_character == "Current character"
        assert name_calls == [(session, "other", "world")]
    else:
        assert result.excerpt is None
        assert result.canonical_href is None
        assert result.related_character is None
        assert name_calls == []
