from datetime import UTC, datetime, timedelta
from dataclasses import asdict
import json

import pytest

from app.domains.memory.models.items import MemoryItem
from app.domains.memory.models.episode import MemoryEpisodeLink
from app.runtime.autonomous_activity import revalidation
from app.runtime.autonomous_activity import recall
from app.runtime.autonomous_activity.recall import bounded_records
from memory.test_episode_hybrid_reader import fixture
from memory.test_p8_l_g_memory_write_lifecycle import memory_session


def test_existing_bounded_followups_are_not_concurrent_changes_but_new_edges_are(memory_session, monkeypatch):
    db = memory_session
    reader, request, candidate, details = fixture(db)
    records = reader.hydrate(request, reader.revalidate(request, (candidate,))).records
    original = db.get(MemoryItem, records[0].memory_item_id)
    now = datetime.now(UTC)
    extra = MemoryItem(**{column.name: getattr(original, column.name) for column in MemoryItem.__table__.columns})
    extra.id = "omitted-old-followup"
    extra.created_at = now - timedelta(days=1)
    db.add(extra); db.flush()
    link = MemoryEpisodeLink(prior_item_id=original.id, following_item_id=extra.id, created_at=now - timedelta(hours=1))
    db.add(link); db.commit()
    packet = json.loads(records[0].text)
    packet["followup_truncated"] = True
    memory = {"ranked_memory_ids": [original.id], "packets": [packet], "retrieved_after": now.isoformat()}
    monkeypatch.setattr(revalidation, "RuntimeEpisodeDetailReader", lambda _: details)
    args = dict(owner_id=request.scope.owner_id, world_id=request.scope.world_id,
        actor_id=request.scope.subject_world_character_id, memories={"target": memory})
    revalidation.assert_memories_current(db, **args)
    link.created_at = now + timedelta(seconds=1); db.commit()
    with pytest.raises(ValueError, match="activity_memory_followup_changed"):
        revalidation.assert_memories_current(db, **args)
    link.created_at = now - timedelta(hours=1)
    original.summary = "The remembered situation was edited."
    db.commit()
    with pytest.raises(ValueError, match="activity_memory_changed"):
        revalidation.assert_memories_current(db, **args)


def test_followup_seen_by_hydration_is_not_new_at_guard(memory_session, monkeypatch):
    db = memory_session
    reader, request, candidate, details = fixture(db)
    original = db.get(MemoryItem, candidate.candidate.memory_item_id)
    previous = original
    now = datetime.now(UTC)
    for index in range(5):
        following = MemoryItem(**{column.name: getattr(original, column.name) for column in MemoryItem.__table__.columns})
        following.id = f"older-linked-{index}"
        following.summary = f"Earlier update {index}: " + "context " * 220
        following.created_at = now - timedelta(days=1)
        db.add(following)
        db.flush()
        db.add(MemoryEpisodeLink(prior_item_id=previous.id, following_item_id=following.id,
            created_at=now + timedelta(seconds=1)))
        previous = following
    db.commit()

    hydration = reader.hydrate(request, reader.revalidate(request, (candidate,)))
    records = hydration.records
    assert 1 <= len(records) < 6
    packets = bounded_records(records)
    assert packets["packets"]
    assert packets["omitted_packets"] or len(records) < 6
    memory = {**packets, "ranked_memory_ids": [record.memory_item_id for record in records],
        "retrieved_after": now.isoformat()}
    monkeypatch.setattr(revalidation, "RuntimeEpisodeDetailReader", lambda _: details)
    revalidation.assert_memories_current(db, owner_id=request.scope.owner_id,
        world_id=request.scope.world_id, actor_id=request.scope.subject_world_character_id,
        memories={"target": memory},
        validations={"target": json.loads(json.dumps(asdict(hydration.validation_snapshot), default=str))})


def test_snapshot_detects_new_edge_and_summary_but_ignores_unrelated_item(memory_session, monkeypatch):
    db = memory_session
    reader, request, candidate, details = fixture(db)
    hydration = reader.hydrate(request, reader.revalidate(request, (candidate,)))
    records = hydration.records
    memory = {**bounded_records(records), "ranked_memory_ids": [r.memory_item_id for r in records]}
    snapshot = json.loads(json.dumps(asdict(hydration.validation_snapshot), default=str))
    monkeypatch.setattr(revalidation, "RuntimeEpisodeDetailReader", lambda _: details)
    args = dict(owner_id=request.scope.owner_id, world_id=request.scope.world_id,
        actor_id=request.scope.subject_world_character_id,
        memories={"target": memory}, validations={"target": snapshot})
    revalidation.assert_memories_current(db, **args)
    original = db.get(MemoryItem, candidate.candidate.memory_item_id)
    unrelated = MemoryItem(**{column.name: getattr(original, column.name) for column in MemoryItem.__table__.columns})
    unrelated.id = "unrelated-new-memory"
    db.add(unrelated); db.commit()
    revalidation.assert_memories_current(db, **args)
    db.add(MemoryEpisodeLink(prior_item_id=original.id, following_item_id=unrelated.id,
        created_at=datetime.now(UTC)))
    db.commit()
    with pytest.raises(ValueError, match="activity_memory_followup_changed"):
        revalidation.assert_memories_current(db, **args)
    db.query(MemoryEpisodeLink).filter_by(following_item_id=unrelated.id).delete()
    db.commit()
    original.summary = "A changed remembered situation"
    db.commit()
    with pytest.raises(ValueError, match="activity_memory_changed"):
        revalidation.assert_memories_current(db, **args)


def test_snapshot_rejects_wrong_scope_or_policy(memory_session):
    db = memory_session
    reader, request, candidate, _details = fixture(db)
    hydration = reader.hydrate(request, reader.revalidate(request, (candidate,)))
    memory = {**bounded_records(hydration.records),
        "ranked_memory_ids": [r.memory_item_id for r in hydration.records]}
    snapshot = json.loads(json.dumps(asdict(hydration.validation_snapshot), default=str))
    args = dict(owner_id=request.scope.owner_id, world_id=request.scope.world_id,
        actor_id=request.scope.subject_world_character_id, memories={"target": memory})
    for changed in ({**snapshot, "policy_version": "future"},
                    {**snapshot, "scope": {**snapshot["scope"], "world_id": "other"}},
                    {**snapshot, "item_revisions": [["malformed"]]}):
        with pytest.raises(ValueError, match="activity_memory_validation_unavailable"):
            revalidation.assert_memories_current(db, **args, validations={"target": changed})


def test_same_snapshot_validates_distinct_sns_packet_budgets(memory_session, monkeypatch):
    reader, request, candidate, details = fixture(memory_session)
    hydration = reader.hydrate(request, reader.revalidate(request, (candidate,)))
    full = bounded_records(hydration.records)
    assert full["packets"] and full["packets"][0]["units"]
    first = full["packets"][0]
    minimum = {**first, "units": [],
        "omitted_units": len(first["units"]) + first.get("omitted_units", 0)}
    monkeypatch.setattr(recall, "MEMORY_CHARS", len(json.dumps([minimum], ensure_ascii=False)) + 20)
    compact = bounded_records(hydration.records)
    assert compact["packets"] and compact != full
    snapshot = json.loads(json.dumps(asdict(hydration.validation_snapshot), default=str))
    monkeypatch.setattr(revalidation, "RuntimeEpisodeDetailReader", lambda _: details)
    for packet_group in (full, compact):
        revalidation.assert_memories_current(memory_session, owner_id=request.scope.owner_id,
            world_id=request.scope.world_id,
            actor_id=request.scope.subject_world_character_id,
            memories={"target": {**packet_group,
                "ranked_memory_ids": [row.memory_item_id for row in hydration.records]}},
            validations={"target": snapshot})
