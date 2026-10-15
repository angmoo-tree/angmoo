"""Complete keyset collection, fresh authority and per-target atomic roots."""
from datetime import timedelta
import json
import os
from pathlib import Path
import pytest
from sqlalchemy import create_engine, event, select, func
from sqlalchemy.orm import Session, sessionmaker
from memory.test_p8_l_o_memory_consolidation import _stack
from memory.test_activity_situation_relationships import test_old_and_new_memory_union_uses_core_counterpart_and_keeps_deleted_new_summary as seed_memories
from memory.test_activity_situation_contract import NOW
from app.runtime.persistence.model_registration import register_models
from app.domains.memory.models.items import MemoryItem, MemoryItemEvidence
from app.domains.memory.models.episode import MemoryEpisodeInfo
from app.domains.memory.models.batch import MemoryBatchSetting
from app.domains.memory.models.activity_configuration import MemorySubjectProfile
from app.domains.social.models.posts import Post
from app.domains.identity.schemas import WorldCredentialWrite
from app.domains.identity.service import world_credentials
from app.domains.relationships.models.personalization import RelationshipReviewWork as Work, RelationshipReviewMemoryReceipt as Receipt
from app.runtime.relationships import review_preparation as preparation


@pytest.mark.parametrize("change", [False, True])
def test_complete_cutoff_read_does_not_hold_writer_and_rechecks_consent(tmp_path, monkeypatch, change):
    engine = create_engine(f"sqlite:///{tmp_path / 'review-preparation.sqlite'}")
    @event.listens_for(engine, "connect")
    def configure(raw, _):
        raw.execute("PRAGMA foreign_keys=ON"); raw.execute("PRAGMA journal_mode=WAL")
    register_models().create_all(engine)
    factory = sessionmaker(engine, expire_on_commit=False)
    with factory() as db:
        scope, setting, _, memory, *_ = _stack(db)
        seed_memories((db, scope, setting, memory))
        db.get(Post, "situation-post").deleted_at = None
        original = db.get(MemoryItem, "historical-episode")
        source = db.scalar(select(MemoryItemEvidence).where(MemoryItemEvidence.memory_item_id == original.id))
        for n in range(150):
            item = MemoryItem(**{**{c.key: getattr(original, c.key) for c in MemoryItem.__table__.columns}, "id": f"page-memory-{n:03}"})
            db.add(item); db.flush()
            db.add(MemoryEpisodeInfo(memory_item_id=item.id, bundle_id="historical-bundle", policy_version="episode-selection.v1"))
            db.add(MemoryItemEvidence(**{**{c.key: getattr(source, c.key) for c in MemoryItemEvidence.__table__.columns},
                "id": f"page-evidence-{n:03}", "memory_item_id": item.id}))
        batch = db.get(MemoryBatchSetting, setting.id)
        if batch is None:
            batch = MemoryBatchSetting(scope_setting_id=setting.id, timezone="Asia/Seoul")
            db.add(batch)
        batch.ai_enabled, batch.consent_version, batch.schedule_enabled, batch.local_time = True, "synthetic", True, "00:00"
        db.add(MemorySubjectProfile(scope_setting_id=setting.id, model_id="gemini-3.1-flash-lite", thinking_level="high", version=1, updated_at=NOW))
        world_credentials.save(db, owner_id=scope.owner_id, world_id=scope.world_id,
            world_character_id=scope.subject_world_character_id, purpose="consolidation",
            data=WorldCredentialWrite(expected_revision=0, provider="google", model="gemini-3.1-flash-lite", thinking_level="high", api_key="synthetic-preparation-only"))
        db.commit()
        setting_id = setting.id
    original_collect = preparation.collect_new_review_memories
    collections, writer_facts = [], []
    def collect(db, **kwargs):
        grouped = original_collect(db, **kwargs)
        assert not db.new and not db.dirty
        assert db.scalar(select(func.count()).select_from(Work)) == 0
        with engine.connect() as writer:
            writer.exec_driver_sql("BEGIN IMMEDIATE")
            writer.exec_driver_sql("UPDATE users SET display_name=display_name")
            writer.commit()
        if change:
            with factory() as writer:
                row = writer.get(MemoryBatchSetting, setting_id)
                row.ai_enabled = False; row.version += 1; writer.commit()
        collections.append(sum(map(len, grouped.values())))
        return grouped
    monkeypatch.setattr(preparation, "collect_new_review_memories", collect)
    original_writer = preparation.run_sqlite_session_immediate
    def write(db, operation, **kwargs):
        return original_writer(db, operation, observer=writer_facts.append, **kwargs)
    monkeypatch.setattr(preparation, "run_sqlite_session_immediate", write)
    preparation.prepare_due_reviews(factory, NOW+timedelta(seconds=1))
    assert collections == [152]
    with factory() as db:
        roots = list(db.scalars(select(Work).where(Work.parent_id.is_(None))))
        assert len(roots) == (0 if change else 1)
        assert db.scalar(select(func.count()).select_from(Receipt)) == (0 if change else 152)
        if roots:
            assert len(roots[0].manifest["memories"]) == 152
    facts = {"memories": 152, "consent_changed": change,
        "writer_ms": [f["transaction_ms"] for f in writer_facts if f["result"] == "committed"]}
    print("RELATIONSHIP_PREPARATION_COST " + json.dumps(facts))
    output = os.environ.get("ANGMOO_RELATION_COST_OUTPUT")
    if output and not change:
        Path(output).write_text(json.dumps(facts, indent=2), encoding="utf-8")
    engine.dispose()
