"""Account/character scrub removes only owned vector state in the same UoW."""
import pytest
from sqlalchemy import select

from app.domains.memory.contracts.provenance import MemoryKindV1
from app.domains.memory.models.items import MemoryItem
from app.domains.memory.models.vector_work import (
    MemoryVectorAttempt, MemoryVectorChange, MemoryVectorDependency,
    MemoryVectorMaintenance, MemoryVectorRevision, MemoryVectorWork,
)
from app.runtime.memory_privacy import scrub_memory_data
from model_fixture_support import models
from memory.test_p8_l_o_memory_consolidation import memory_session, _stack


@pytest.mark.parametrize("character_only", [False, True])
@pytest.mark.parametrize("commit", [False, True])
def test_scrub_vector_state_is_scoped_atomic_and_preserves_recovery(memory_session, character_only, commit):
    db = memory_session
    scope, *_ = _stack(db)
    db.add(models.User(id="other-owner", email="other@example.test", display_name="Other"))
    db.flush()
    items = [
        ("owned", scope.owner_id, scope.subject_world_character_id),
        ("sibling", scope.owner_id, "consolidation-counterpart"),
        ("foreign", "other-owner", "consolidation-counterpart"),
    ]
    for identity, owner, subject in items:
        db.add(MemoryItem(id=identity, owner_id=owner, world_id=scope.world_id,
            subject_world_character_id=subject, memory_kind=MemoryKindV1.AUTOBIOGRAPHICAL_EVENT.value, summary="Synthetic memory",
            confidence=0.9, salience=0.8))
        db.add(MemoryVectorWork(generation="v1", item_id=identity, world_id=scope.world_id))
        db.add(MemoryVectorDependency(item_id=identity, source_kind="memory", source_key=identity))
        db.add(MemoryVectorAttempt(item_id=identity, profile="test", content_hash="a" * 64,
            credential_revision="1", attempts=1, retry_after=0))
    db.add(MemoryVectorMaintenance(generation="v1", phase="ready"))
    db.commit()
    revisions = set(db.scalars(select(MemoryVectorRevision.scope_key)))

    scrub_memory_data(db, owner_id=scope.owner_id,
        character_id="consolidation-subject-character" if character_only else None)
    expected = {"sibling", "foreign"} if character_only else {"foreign"}
    for model in (MemoryVectorWork, MemoryVectorDependency, MemoryVectorAttempt):
        assert set(db.scalars(select(model.item_id))) == expected
    assert set(db.scalars(select(MemoryItem.id))) == expected
    # Source invalidation must survive to erase derived index entries and fan
    # out to other memories. Monotonic fences and shared generation state stay.
    assert db.scalar(select(MemoryVectorChange.sequence).where(
        MemoryVectorChange.source_kind == "memory", MemoryVectorChange.source_key == "owned"))
    assert db.get(MemoryVectorMaintenance, "v1") is not None
    assert revisions <= set(db.scalars(select(MemoryVectorRevision.scope_key)))

    if commit:
        db.commit()
    else:
        db.rollback()
        expected = {"owned", "sibling", "foreign"}
    db.expire_all()
    for model in (MemoryVectorWork, MemoryVectorDependency, MemoryVectorAttempt):
        assert set(db.scalars(select(model.item_id))) == expected
    assert set(db.scalars(select(MemoryItem.id))) == expected
