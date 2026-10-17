"""Synthetic file-backed SNS provenance; never reads user data or calls a model."""
from dataclasses import replace
from hashlib import sha256

from sqlalchemy import create_engine, event, select
from sqlalchemy.orm import Session

from app.runtime.persistence.model_registration import register_models
from app.domains.relationships.models.social import SocialEvent, SocialEventEvidence
from app.domains.memory.models.items import MemoryItem
from app.domains.memory.contracts.hybrid_recall import RankedMemoryCandidate
from app.domains.memory.contracts.recall import MemoryRecallCandidate, RecallDocumentKind
from app.domains.memory.repository.situation_admission import admit
from app.runtime.memory.situation_sources import SituationSources
from memory.test_p8_l_o_memory_consolidation import _stack
from memory.test_activity_situation_contract import values, NOW
from memory.test_activity_situation_application import real_source, apply
from memory.test_activity_situation_recall import readers


def build_cost_case(path, *, count=50, stride=5):
    engine = create_engine(f"sqlite:///{path}")
    def configure(db, _):
        db.execute("PRAGMA foreign_keys=ON")
        db.execute("PRAGMA journal_mode=WAL")
    event.listen(engine, "connect", configure)
    register_models().create_all(engine)
    with Session(engine) as db:
        scope, setting, _, memory, *_ = _stack(db)
        post = real_source(db, scope)
        source_count = (count - 1) * stride + 10
        for n in range(source_count):
            db.add(SocialEvent(id=f"cost-event-{n}", world_id=scope.world_id,
                actor_world_character_id=scope.subject_world_character_id,
                event_type="post_published", occurred_at=NOW, created_at=NOW,
                idempotency_key=f"cost-event-{n}"))
        db.flush()
        for n in range(source_count):
            db.add(SocialEventEvidence(id=f"cost-evidence-{n}", social_event_id=f"cost-event-{n}",
                evidence_kind="post", source_object_type="post", source_object_id=post.id,
                source_post_id=post.id, occurred_at=NOW))
        db.commit()
        source_reader = SituationSources(db)
        sources = [source_reader.describe(scope, kind="SOCIAL_EVENT", identifier=f"cost-event-{n}",
            delivered="A successful synthetic social activity.", path="/events/0", role="core",
            ordinal=0, target=post.id) for n in range(source_count)]
        for n in range(count):
            manifest, draft, result = values(db, scope, target=post.id,
                logical=f"cost-{n}", call=f"cost-call-{n}")
            entries = tuple(replace(source, ordinal=i, payload_path=f"/events/{i}")
                for i, source in enumerate(sources[n*stride:n*stride+10]))
            admit(db, manifest=replace(manifest, sources=entries), draft=draft, result=result, now=NOW)
        db.commit()
        apply(db, setting, memory)
        items = tuple(db.scalars(select(MemoryItem).order_by(MemoryItem.id)))
        assert len(items) == count
        reader, request, _, _ = readers(db, scope, items[0])
        request = replace(request, episode_source_kinds=())
        candidates = tuple(RankedMemoryCandidate(MemoryRecallCandidate(
            f"memory-item:{item.id}", item.id, RecallDocumentKind.MEMORY_ITEM,
            item.id, 1.0, item.summary, metadata={"item_version": str(item.version)}),
            item.version, sha256(item.summary.encode()).hexdigest()) for item in items)
    return engine, reader, request, candidates
