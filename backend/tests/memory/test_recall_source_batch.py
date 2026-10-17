"""Batch facts must preserve the scalar evidence policy, including absent facts."""
from dataclasses import replace
from datetime import timedelta
from sqlalchemy import event
from app.domains.memory.contracts.scope import MemoryScope
from app.domains.memory.contracts.provenance import MemorySourceTypeV1
from app.domains.memory.service.source_evidence import SqlAlchemyMemorySourceEvidenceReader
from app.runtime.memory.episode_details import _SourceQueries
from app.runtime.memory import source_queries
from app.runtime.memory.subjective_source import read_subjective_source
from app.runtime.memory.subjective_source_batch import read_subjective_batch
from test_p8_l_r_today_sns_activity import _seed_today_activity, today_session, NOW


def test_source_facts_and_subjective_declarations_match_scalar_policy(today_session):
    db, fixture = today_session
    _, social_event = _seed_today_activity(db, fixture)
    scope = MemoryScope(fixture["owner"].id, fixture["world"].id, fixture["subject"].id)
    identities = (("POST", "subject-root"), ("REPLY", "subject-reply"),
        ("REPLY", "peer-unrelated-sibling"), ("SOCIAL_EVENT", social_event.id), ("SOCIAL_EVENT", "missing"))
    for current in (scope, replace(scope, world_id="other-world"), replace(scope, subject_world_character_id="other-subject")):
        queries = _SourceQueries(db, ())
        queries.prepare(db, identities, (current,))
        scalar = SqlAlchemyMemorySourceEvidenceReader(db, queries=source_queries)
        batched = SqlAlchemyMemorySourceEvidenceReader(db, queries=queries)
        for kind, identifier in identities:
            assert batched.read_evidence(scope=current, source_type=MemorySourceTypeV1(kind), source_id=identifier) == scalar.read_evidence(
                scope=current, source_type=MemorySourceTypeV1(kind), source_id=identifier)
        assert read_subjective_batch(db, current, identities) == {identity: read_subjective_source(
            db, current, source_type=identity[0], source_id=identity[1]) for identity in identities}


def test_negative_facts_cross_chunk_boundary_without_per_source_queries(today_session):
    db, fixture = today_session
    _seed_today_activity(db, fixture)
    scope = MemoryScope(fixture["owner"].id, fixture["world"].id, fixture["subject"].id)
    queries = _SourceQueries(db, ())
    identities = tuple(("SOCIAL_EVENT", f"absent-{n}") for n in range(410))
    sql = []
    def count(*args): sql.append(args[2])
    event.listen(db.get_bind(), "before_cursor_execute", count)
    try:
        queries.prepare(db, identities, (scope,))
        first = len(sql)
        reader = SqlAlchemyMemorySourceEvidenceReader(db, queries=queries)
        for kind, identifier in identities:
            assert reader.read_evidence(scope=scope, source_type=MemorySourceTypeV1(kind), source_id=identifier) is None
        queries.prepare(db, identities, (scope,))
        assert len(sql) == first
        assert first <= 8  # Two chunks, not 410 individual reads; no full-table query.
    finally:
        event.remove(db.get_bind(), "before_cursor_execute", count)


def test_subjective_limit_is_per_source_and_applied_before_event_kind_filter(today_session):
    from app.domains.relationships.models.social import SocialEvent, SocialEventEvidence
    db, fixture = today_session
    _seed_today_activity(db, fixture)
    scope = MemoryScope(fixture["owner"].id, fixture["world"].id, fixture["subject"].id)
    assert read_subjective_source(db, scope, source_type="POST", source_id="subject-root") is not None
    for n in range(9):
        db.add(SocialEvent(id=f"newer-{n}", world_id=scope.world_id, actor_world_character_id=scope.subject_world_character_id,
            target_world_character_id=fixture["peer"].id,
            event_type="like_added", occurred_at=NOW, created_at=NOW+timedelta(days=365,seconds=n), idempotency_key=f"newer-{n}"))
    db.flush()
    for n in range(9):
        db.add(SocialEventEvidence(id=f"newer-evidence-{n}", social_event_id=f"newer-{n}",
            source_post_id="subject-root", evidence_kind="post", source_object_type="post", source_object_id="subject-root", occurred_at=NOW))
    db.commit()
    identities = (("POST", "subject-root"), ("REPLY", "subject-reply"))
    result = read_subjective_batch(db, scope, identities)
    assert result[("POST", "subject-root")] is None
    assert result[("REPLY", "subject-reply")] is not None
    assert result == {identity: read_subjective_source(db, scope, source_type=identity[0], source_id=identity[1]) for identity in identities}
