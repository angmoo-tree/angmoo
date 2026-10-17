"""Provider-wait mutations are checked against a new bounded canonical read."""
import asyncio
from dataclasses import replace
from datetime import timedelta
from time import monotonic

import pytest
from sqlalchemy import select, update
from sqlalchemy.orm import Session, sessionmaker

from app.domains.memory.contracts.hybrid_recall import HybridAxisResult, RecallAxisReceipt, RecallAxisStatus, RecallCurrentnessError
from app.domains.memory.models.items import MemoryItem, MemoryScopeSettingModel
from app.domains.memory.models.episode import MemoryEpisodeLink
from app.domains.social.models.posts import Post
from app.domains.relationships.models.social import SocialEvent
from app.domains.memory.service.hybrid_recall import HybridRecallService
from app.runtime.memory.canonical_worker import CanonicalReadWorker, DeadlineSessionFactory
from memory.recall_cost_fixture import build_cost_case, NOW
from memory.test_activity_situation_contract import stack


@pytest.mark.parametrize("change", ["none", "unrelated", "off", "source", "unrelated_post_body", "expired", "followup", "deleted"])
def test_fresh_delivery_guard_rejects_only_related_changes(tmp_path, change):
    engine, reader, request, candidates = build_cost_case(tmp_path / "delivery.sqlite", count=1)
    sessions = DeadlineSessionFactory(sessionmaker(engine))
    reader.factory = sessions
    worker = CanonicalReadWorker(sessions, reader)
    calls = []
    class Axis:
        def __init__(self, axis): self.axis = axis
        async def search(self, *_args, **_kwargs):
            calls.append(self.axis)
            return HybridAxisResult(candidates, RecallAxisReceipt(self.axis, RecallAxisStatus.READY, True, 1, 0))
    service = HybridRecallService(fts=Axis("fts"), vector=Axis("vector"), canonical=worker)
    async def run():
        try:
            result = await service.execute(request, deadline=monotonic()+4)
            ids = tuple(row.memory_item_id for row in result.records)
            assert ids
            await service.assert_current(result, ids, deadline=monotonic()+4)
            with Session(engine) as writer:
                root = writer.get(MemoryItem, ids[0])
                version = root.version
                if change == "off":
                    writer.execute(update(MemoryScopeSettingModel).values(enabled=False))
                elif change == "source":
                    writer.get(SocialEvent, "cost-event-0").retrieval_status = "excluded"
                elif change == "unrelated_post_body":
                    # This fixture delivered event facts, not the post body.
                    post = writer.get(Post, "situation-post")
                    post.body = "Changed source content"
                elif change == "expired":
                    root.valid_until = NOW + timedelta(seconds=1)
                    reader.clock = lambda: NOW + timedelta(seconds=2)
                elif change in {"unrelated", "followup"}:
                    copy = MemoryItem(**{col.name: getattr(root, col.name) for col in MemoryItem.__table__.columns})
                    copy.id = "another-memory"
                    writer.add(copy)
                    writer.flush()
                    if change == "followup":
                        writer.add(MemoryEpisodeLink(prior_item_id=root.id, following_item_id=copy.id, created_at=NOW))
                elif change == "deleted":
                    root.status = "deleted"
                    root.deleted_at = NOW
                writer.commit()
                assert writer.get(MemoryItem, ids[0]).version == version
            if change in {"none", "unrelated", "unrelated_post_body"}:
                await service.assert_current(result, ids, deadline=monotonic()+4)
            else:
                with pytest.raises(RecallCurrentnessError):
                    await service.assert_current(result, ids, deadline=monotonic()+4)
            assert calls == ["fts", "vector"]
        finally:
            await worker.stop()
    try: asyncio.run(run())
    finally: engine.dispose()


def test_previously_deleted_original_remains_a_permitted_summary_at_fresh_guard(stack):
    from types import SimpleNamespace
    from memory.test_activity_situation_application import real_source, receipt, apply
    from memory.test_activity_situation_recall import readers
    db, scope, setting, memory = stack
    post = real_source(db, scope)
    admitted = receipt(db, scope, post)
    post.deleted_at = NOW
    db.commit()
    apply(db, setting, memory)
    item = db.get(MemoryItem, admitted.applied_item_id)
    reader, request, candidate, _ = readers(db, scope, item)
    hydration = reader.resolve(request, (candidate,)).hydration
    assert hydration.records and post.body not in hydration.records[0].text
    result = SimpleNamespace(scope=scope, records=hydration.records, validation_snapshot=hydration.validation_snapshot)
    reader.assert_current(result, (item.id,))
