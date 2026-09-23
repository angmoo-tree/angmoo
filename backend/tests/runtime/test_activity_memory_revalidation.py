from datetime import UTC, datetime, timedelta
import json

import pytest

from app.domains.memory.models.items import MemoryItem
from app.domains.memory.models.episode import MemoryEpisodeLink
from app.runtime.autonomous_activity import revalidation
from memory.test_episode_hybrid_reader import fixture
from memory.test_p8_l_g_memory_write_lifecycle import memory_session


def test_existing_bounded_followups_are_not_concurrent_changes_but_new_edges_are(memory_session, monkeypatch):
    db = memory_session
    reader, request, candidate, details = fixture(db)
    records, _ = reader.hydrate(request, reader.revalidate(request, (candidate,)))
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
