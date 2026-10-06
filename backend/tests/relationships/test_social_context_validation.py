"""Frozen input receipts, fresh SQLite truth and strictly bounded legacy proof."""
from copy import deepcopy
from dataclasses import replace
from datetime import UTC, datetime, timedelta, timezone
import json

import pytest
from sqlalchemy import create_engine, event, update
from sqlalchemy.orm import Session

from model_fixture_support import models
from app.models import Base
from app.domains.relationships.contracts.social_context import (
    CURRENTNESS_REVISION, LEGACY_CURRENTNESS, MAX_RECEIPT_BYTES,
    RelationshipValidationBinding, RelationshipValidationReceipt, SocialContextItem,
    SocialContextValidationError,
)
from app.domains.relationships.policies.social_context_validation import facts_digest, receipt_for_snapshot
from app.domains.relationships.service.social_context_validation import SocialContextValidationService
from app.runtime.graph_projection.relationship_graph_read import SqlAlchemyRelationshipGraphReadGateway
from app.domains.relationships.policies.graph_recall import _relationship_record
from runtime.test_activity_relationship_validation import relation_case

pytestmark = pytest.mark.usefixtures("deny_external_network")


def binding(case):
    return RelationshipValidationBinding(case.ctx.run_id, "feed", "post-target", "world-character-author")


def prepared(case, snapshot=None):
    snapshot = snapshot or case.snapshot(case.relations)
    return snapshot.prompt_view(), receipt_for_snapshot(snapshot, scope=case.scope, binding=binding(case)).to_dict()


def validate(case, prompt, receipt, *, policy=CURRENTNESS_REVISION, scope=None, target_binding=None):
    return SocialContextValidationService(case.gateway).validate(scope=scope or case.scope,
        binding=target_binding or binding(case), prompt=prompt, receipt=receipt, policy=policy)


def test_t01_t03_frozen_facts_survive_order_status_ranking_and_unselected_churn(relation_case):
    case = relation_case
    prompt, receipt = prepared(case)
    original = deepcopy((prompt, receipt))
    case.gateway.open_graph_repository = lambda: pytest.fail("validator opened graph")
    case.gateway.canonical_direct_hits = lambda **_: pytest.fail("validator reselected ranking")
    assert validate(case, prompt, receipt).checked_count == 2
    # The hash of the newly ranked input may differ; the old input is untouched.
    fresh = case.snapshot(list(reversed(case.relations)))
    assert fresh.content_hash != prompt["content_hash"]
    assert validate(case, prompt, receipt).outcome == "valid"
    subset_prompt, subset_receipt = prepared(case, case.snapshot(case.relations[:1]))
    case.rows[1].version += 1
    case.rows[1].affinity -= 4
    case.db.commit()
    assert validate(case, subset_prompt, subset_receipt).outcome == "valid"
    assert (prompt, receipt) == original


@pytest.mark.parametrize("field, delta, reason", [
    ("version", 1, "version_changed"), ("view_version", 1, "view_changed"),
    ("affinity", 1, "facts_changed"), ("trust", 1, "facts_changed"),
    ("familiarity", 1, "facts_changed"), ("tension", 1, "facts_changed"),
    ("interaction_count", 1, "facts_changed"), ("perception", "New view", "facts_changed"),
    ("relationship_label", "Friend", "facts_changed"), ("last_event_at", datetime(2026, 10, 5), "facts_changed"),
])
def test_t04_t05_t07_actual_versions_and_used_facts_change(relation_case, field, delta, reason):
    case = relation_case
    prompt, receipt = prepared(case)
    current = getattr(case.rows[0], field)
    setattr(case.rows[0], field, current + delta if type(delta) is int else delta)
    case.db.commit()
    with pytest.raises(SocialContextValidationError, match=reason):
        validate(case, prompt, receipt)


@pytest.mark.parametrize("version", ["version", "view_version"])
def test_t04_t05_aba_is_not_hidden_by_equal_current_values(relation_case, version):
    case = relation_case
    prompt, receipt = prepared(case)
    case.rows[0].affinity += 2
    setattr(case.rows[0], version, getattr(case.rows[0], version) + 1)
    case.db.commit()
    case.rows[0].affinity -= 2
    setattr(case.rows[0], version, getattr(case.rows[0], version) + 1)
    case.db.commit()
    with pytest.raises(SocialContextValidationError, match="version_changed|view_changed"):
        validate(case, prompt, receipt)


def test_t07_display_name_normalization_and_actual_change(relation_case):
    case = relation_case
    prompt, receipt = prepared(case)
    from app.domains.world_characters.configuration_models import WorldCharacterConfiguration
    stored = case.db.get(WorldCharacterConfiguration, "world-character-author")
    stored.profile = {**stored.profile, "display_name": "  Character author  "}
    case.db.commit()
    assert validate(case, prompt, receipt).outcome == "valid"
    stored.profile = {**stored.profile, "display_name": "Changed name"}
    case.db.commit()
    with pytest.raises(SocialContextValidationError, match="facts_changed"):
        validate(case, prompt, receipt)


@pytest.mark.parametrize("kind", ["owner", "world", "subject", "binding", "direction", "swap"])
def test_t08_scope_direction_and_binding_are_not_interchangeable(relation_case, kind):
    case = relation_case
    prompt, receipt = prepared(case)
    if kind in {"owner", "world", "subject"}:
        field = {"owner": "owner_id", "world": "world_id", "subject": "subject_world_character_id"}[kind]
        with pytest.raises(SocialContextValidationError, match="receipt_invalid"):
            validate(case, prompt, receipt, scope=replace(case.scope, **{field: "another"}))
    elif kind == "binding":
        with pytest.raises(SocialContextValidationError, match="receipt_invalid"):
            validate(case, prompt, receipt, target_binding=replace(binding(case), lane="inbox"))
    else:
        case.rows[0].actor_world_character_id, case.rows[0].target_world_character_id = (
            case.rows[0].target_world_character_id, case.rows[0].actor_world_character_id)
        case.db.commit()
        with pytest.raises(SocialContextValidationError, match="visibility_lost"):
            validate(case, prompt, receipt)


@pytest.mark.parametrize("loss", ["relation", "replacement", "membership", "character", "block", "observed", "actor"])
def test_t09_removed_or_invisible_facts_stop_validation(relation_case, loss):
    case = relation_case
    prompt, receipt = prepared(case)
    if loss == "relation":
        case.db.delete(case.rows[0])
    elif loss == "replacement":
        case.rows[0].id = "replacement-state"
    elif loss == "membership":
        case.db.get(models.WorldMembership, "membership-author").status = "left"
    elif loss == "character":
        case.db.get(models.Character, "character-author").deleted_at = datetime.now(UTC)
    elif loss == "block":
        case.db.add(models.WorldCharacterBlock(id="test-block", world_id=case.actor.world_id,
            blocker_world_character_id="world-character-author", blocked_world_character_id=case.actor.id))
    elif loss == "observed":
        case.rows[0].last_metric_at = None
    else:
        case.actor.status = "inactive"
    case.db.commit()
    with pytest.raises(SocialContextValidationError, match="visibility_lost"):
        validate(case, prompt, receipt)


@pytest.mark.parametrize("damage", ["missing", "revision", "hash", "snapshot", "duplicate_state", "duplicate_target", "bool_version", "negative_version", "extra", "too_large", "too_many", "scope", "binding", "text", "basis", "invalid_state", "invalid_scope", "invalid_binding"])
def test_t10_corrupt_receipts_fail_without_a_legacy_escape(relation_case, damage):
    case = relation_case
    prompt, receipt = prepared(case)
    if damage == "missing": receipt = None
    elif damage == "revision": receipt["revision"] = "unknown"
    elif damage == "hash": receipt["input_content_hash"] = "b" * 64
    elif damage == "snapshot": receipt["snapshot_id"] = "different"
    elif damage == "duplicate_state": receipt["references"][1]["relationship_state_id"] = receipt["references"][0]["relationship_state_id"]
    elif damage == "duplicate_target": receipt["references"][1]["target_world_character_id"] = receipt["references"][0]["target_world_character_id"]
    elif damage == "bool_version": receipt["references"][0]["view_version"] = True
    elif damage == "negative_version": receipt["references"][0]["relationship_version"] = -1
    elif damage == "extra": receipt["untrusted_extra"] = "field"
    elif damage == "too_large": receipt["binding"]["target_id"] = "x" * MAX_RECEIPT_BYTES
    elif damage == "too_many": receipt["references"] *= 7
    elif damage == "scope": receipt["scope"]["owner_id"] = "another"
    elif damage == "binding": receipt["binding"]["activity_id"] = "another"
    elif damage == "text": prompt["context"] = prompt["context"].replace("A familiar peer", "A forged fact")
    elif damage == "invalid_state": receipt["references"][0]["relationship_state_id"] = " "
    elif damage == "invalid_scope": receipt["scope"]["owner_id"] = "x" * 257
    elif damage == "invalid_binding": receipt["binding"]["target_id"] = " target "
    else: receipt["basis"] = "no_facts"
    with pytest.raises(SocialContextValidationError, match="receipt_invalid"):
        validate(case, prompt, receipt)


@pytest.mark.parametrize("revision", [None, [], {}, 1, "unknown"])
def test_t10_unknown_policy_is_a_typed_invalid_receipt(relation_case, revision):
    from app.domains.relationships.contracts.social_context import read_currentness_policy
    with pytest.raises(SocialContextValidationError, match="receipt_invalid"):
        read_currentness_policy({"relationship_validation_policy": revision})


@pytest.mark.parametrize("field,value", [("status", []), ("coverage", {}), ("snapshot_id", " " ), ("validated_at", "2026-10-04T12:00:00")])
def test_t20_legacy_header_damage_is_typed_and_unprovable(relation_case, field, value):
    prompt, _receipt = prepared(relation_case)
    prompt[field] = value
    with pytest.raises(SocialContextValidationError, match="legacy_unprovable"):
        validate(relation_case, prompt, None, policy=LEGACY_CURRENTNESS)


def test_t11_fresh_other_connection_commit_is_detected(tmp_path):
    from social.test_feed_reaction_intent import _seed
    engine = create_engine("sqlite:///" + (tmp_path / "fresh.sqlite").as_posix())
    Base.metadata.create_all(engine)
    with Session(engine, expire_on_commit=False) as db:
        ctx, _ = _seed(db, with_candidate=True)
        actor = db.get(models.WorldCharacter, "world-character-actor")
        row = models.RelationshipState(id="fresh-rel", world_id=actor.world_id,
            actor_world_character_id=actor.id, target_world_character_id="world-character-author",
            version=1, view_version=1, last_metric_at=datetime.now(UTC))
        db.add(row); db.commit()
        from app.domains.relationships.contracts.graph_recall import GraphRecallScope
        scope = GraphRecallScope(ctx.user_id, actor.world_id, actor.id)
        gateway = SqlAlchemyRelationshipGraphReadGateway(db)
        from app.domains.relationships.policies.social_context_validation import SOCIAL_CONTEXT_INTRO, social_context_row, input_content_hash
        from app.domains.relationships.contracts.social_context import SocialContextSnapshot
        item = SocialContextItem(_relationship_record(gateway._relationship_hit(row)), "Character author", (), "canonical")
        text = SOCIAL_CONTEXT_INTRO + json.dumps(social_context_row(item), ensure_ascii=False, separators=(",", ":")) + "\n"
        snapshot = SocialContextSnapshot("fresh", scope, datetime.now(UTC), (item,), "ready", "partial", 1, 0, 0, (), text,
            input_content_hash(scope, [(row.id, 1)], text, "ready"))
        target_binding = RelationshipValidationBinding(ctx.run_id, "feed", "post-target", "world-character-author")
        receipt = receipt_for_snapshot(snapshot, scope=scope, binding=target_binding).to_dict()
        with engine.begin() as other:
            other.execute(update(models.RelationshipState).where(models.RelationshipState.id == row.id).values(version=2))
        assert row.version == 1  # Stale ORM identity map must NOT be authority.
        with pytest.raises(SocialContextValidationError, match="version_changed"):
            SocialContextValidationService(gateway).validate(scope=scope, binding=target_binding,
                prompt=snapshot.prompt_view(), receipt=receipt, policy=CURRENTNESS_REVISION)
    engine.dispose()


@pytest.mark.parametrize("basis", ["disabled", "no_facts", "unavailable"])
def test_t12_basis_preserves_meaning_and_always_validates_scope(relation_case, basis):
    case = relation_case
    snapshot = None if basis == "disabled" else case.snapshot([])
    if basis == "unavailable":
        from app.domains.relationships.policies.social_context_validation import input_content_hash
        snapshot = replace(snapshot, status="unavailable", content_hash=input_content_hash(case.scope, [], snapshot.context_text, "unavailable"))
    prompt = {} if snapshot is None else snapshot.prompt_view()
    receipt = receipt_for_snapshot(snapshot, scope=case.scope, binding=binding(case)).to_dict()
    assert validate(case, prompt, receipt).outcome == basis
    case.actor.status = "inactive"; case.db.commit()
    with pytest.raises(SocialContextValidationError, match="visibility_lost"):
        validate(case, prompt, receipt)


@pytest.mark.parametrize("failure", ["exception", "deadline"])
def test_t12_t25_canonical_failure_is_never_empty_success(relation_case, failure):
    case = relation_case
    prompt, receipt = prepared(case)
    if failure == "exception":
        case.gateway.canonical_social_context_facts = lambda **_: (_ for _ in ()).throw(RuntimeError("private SQL"))
        service = SocialContextValidationService(case.gateway)
    else:
        ticks = iter([0.0, 2.1])
        service = SocialContextValidationService(case.gateway, clock=lambda: next(ticks))
    with pytest.raises(SocialContextValidationError, match="canonical_unavailable"):
        service.validate(scope=case.scope, binding=binding(case), prompt=prompt, receipt=receipt, policy=CURRENTNESS_REVISION)


def test_t13_equal_utc_instants_and_strict_numbers(relation_case):
    relation = relation_case.relations[0]
    stamp = datetime(2026, 10, 4, tzinfo=UTC)
    item = SocialContextItem(replace(relation, last_event_at=stamp), "Character author", (), "canonical")
    assert facts_digest(item) == facts_digest(replace(item, relationship=replace(item.relationship, last_event_at=stamp.replace(tzinfo=None))))
    assert facts_digest(item) == facts_digest(replace(item, relationship=replace(item.relationship, last_event_at=stamp.astimezone(timezone(timedelta(hours=9))))))
    assert facts_digest(item) != facts_digest(replace(item, relationship=replace(item.relationship, last_event_at=stamp + timedelta(seconds=1))))
    for value in (float("nan"), True, 1.1, "2", None):
        with pytest.raises(SocialContextValidationError, match="facts_invalid"):
            facts_digest(replace(item, relationship=replace(item.relationship, affinity=value)))


def test_t19_t21_legacy_uses_original_rows_hash_and_does_not_invent_view_version(relation_case):
    case = relation_case
    prompt, _ = prepared(case)
    original = deepcopy(prompt)
    case.snapshot(list(reversed(case.relations)))
    assert validate(case, prompt, None, policy=LEGACY_CURRENTNESS).outcome == "valid_legacy_facts"
    case.rows[0].view_version += 2; case.db.commit()
    assert validate(case, prompt, None, policy=LEGACY_CURRENTNESS).outcome == "valid_legacy_facts"
    assert prompt == original and "view_version" not in prompt
    with pytest.raises(SocialContextValidationError, match="receipt_invalid"):
        validate(case, prompt, None, policy=CURRENTNESS_REVISION)


@pytest.mark.parametrize("damage", ["version", "facts", "state", "intro", "row_type", "key", "duplicate", "hash", "status"])
def test_t20_unprovable_legacy_never_rebaselines(relation_case, damage):
    case = relation_case
    prompt, _ = prepared(case)
    if damage == "version": case.rows[0].version += 1
    elif damage == "facts": case.rows[0].perception = "Changed"
    elif damage == "state": case.rows[0].id = "replaced"
    elif damage == "intro": prompt["context"] = "unknown intro\n"
    elif damage == "row_type": prompt["context"] = prompt["context"].replace('"affinity":10', '"affinity":true')
    elif damage == "key": prompt["context"] = prompt["context"].replace('"trust":12', '"trust":12,"unknown":1')
    elif damage == "duplicate": prompt["context"] += prompt["context"].splitlines()[-1] + "\n"
    elif damage == "hash": prompt["content_hash"] = "0" * 64
    else: prompt["status"] = "unknown"
    case.db.commit()
    original = deepcopy(prompt)
    with pytest.raises(SocialContextValidationError, match="legacy_unprovable"):
        validate(case, prompt, None, policy=LEGACY_CURRENTNESS)
    assert prompt == original


def test_t25_bounded_batch_query_count_and_receipt_size(relation_case):
    case = relation_case
    prompt, receipt = prepared(case)
    statements = []
    def count(_conn, _cursor, statement, _params, _context, _many): statements.append(statement)
    event.listen(case.db.get_bind(), "before_cursor_execute", count)
    try:
        assert validate(case, prompt, receipt).checked_count == 2
    finally:
        event.remove(case.db.get_bind(), "before_cursor_execute", count)
    assert len(statements) <= 13
    size = len(json.dumps(receipt, ensure_ascii=False).encode())
    assert size < MAX_RECEIPT_BYTES
    assert all(" IN " in sql or " = " in sql for sql in statements)
    decoded = RelationshipValidationReceipt.from_dict(json.loads(json.dumps(receipt)))
    assert decoded.to_dict() == receipt


@pytest.mark.parametrize("count", [0, 1, 12])
def test_t25_zero_one_and_maximum_references_are_bounded(relation_case, count, record_property):
    from social.test_feed_reaction_intent import _user, _character
    from app.domains.relationships.contracts.graph_recall import GraphRecallResult, GraphRecallStatus, GraphRecallSource
    from app.domains.relationships.service.social_context import SocialContextService
    from app.runtime.world_characters.creation_configuration import initialize_created_world_character
    case = relation_case
    for index in range(max(0, count - 2)):
        owner = _user("bound-" + str(index))
        character = _character(owner, "bound-" + str(index))
        case.db.add_all([owner, character]); case.db.flush()
        member = models.WorldMembership(id="bound-member-" + str(index), world_id=case.actor.world_id,
            user_id=owner.id, role="member", status="active")
        case.db.add(member); case.db.flush()
        peer = models.WorldCharacter(id="bound-peer-" + str(index), world_id=case.actor.world_id,
            character_id=character.id, membership_id=member.id, role_key="student", status="active")
        case.db.add(peer); case.db.flush()
        initialize_created_world_character(case.db, character=character, world_character=peer)
        case.db.add(models.RelationshipState(id="bound-state-" + str(index), world_id=case.actor.world_id,
            actor_world_character_id=case.actor.id, target_world_character_id=peer.id,
            familiarity=20, affinity=10, trust=12, tension=3, interaction_count=4,
            version=1, view_version=1, last_metric_at=datetime(2026, 10, 4, tzinfo=UTC)))
    case.db.commit()
    from sqlalchemy import select
    rows = case.db.scalars(select(models.RelationshipState).where(
        models.RelationshipState.actor_world_character_id == case.actor.id).order_by(models.RelationshipState.id)).all()[:count]
    relations = tuple(_relationship_record(case.gateway._relationship_hit(row)) for row in rows)
    labels = {node.world_character_id: node.display_name for node in case.gateway.node_candidates(
        world_id=case.actor.world_id, world_character_ids={ref.target_world_character_id for ref in relations})}
    snapshot = SocialContextService(lambda query: GraphRecallResult(query.operation, GraphRecallStatus.READY,
        GraphRecallSource.GRAPH, relationships=relations, candidate_count=count)).prepare(case.scope, labels=labels)
    prompt, receipt = prepared(case, snapshot)
    statements = []
    native_statements = []
    driver = case.db.connection().connection.driver_connection
    driver.set_trace_callback(native_statements.append)
    def count_sql(_conn, _cursor, statement, _params, _context, _many): statements.append(statement)
    event.listen(case.engine, "before_cursor_execute", count_sql)
    try:
        assert validate(case, prompt, receipt).checked_count == count
    finally:
        event.remove(case.engine, "before_cursor_execute", count_sql)
        driver.set_trace_callback(None)
    size = len(json.dumps(receipt, ensure_ascii=False).encode())
    record_property("reference_count", count)
    record_property("canonical_sql_statements", len(statements))
    native_timeouts = sum(sql.upper().startswith("PRAGMA BUSY_TIMEOUT") for sql in native_statements)
    record_property("native_timeout_statements", native_timeouts)
    record_property("receipt_bytes", size)
    assert len(statements) <= (3 if count == 0 else 13)
    assert native_timeouts == len(statements) + 2
    assert size <= MAX_RECEIPT_BYTES
    assert len(receipt["references"]) == count


def test_t11_distinct_actors_keep_independent_outgoing_facts(relation_case):
    from app.domains.relationships.contracts.graph_recall import GraphRecallScope, GraphRecallResult, GraphRecallStatus, GraphRecallSource
    from app.domains.relationships.service.social_context import SocialContextService
    case = relation_case
    prompt, receipt = prepared(case)
    peer = case.db.get(models.WorldCharacter, "world-character-peer")
    character = case.db.get(models.Character, peer.character_id)
    scope = GraphRecallScope(character.owner_id, peer.world_id, peer.id)
    row = models.RelationshipState(id="peer-outgoing", world_id=peer.world_id,
        actor_world_character_id=peer.id, target_world_character_id=case.actor.id,
        familiarity=15, affinity=2, trust=4, tension=1, interaction_count=3,
        version=1, view_version=1, last_metric_at=datetime(2026, 10, 4, tzinfo=UTC))
    case.db.add(row); case.db.commit()
    snapshot = SocialContextService(lambda query: GraphRecallResult(query.operation, GraphRecallStatus.READY,
        GraphRecallSource.GRAPH, relationships=(_relationship_record(case.gateway._relationship_hit(row)),),
        candidate_count=1)).prepare(scope, labels={case.actor.id: case.ctx.character.name})
    peer_binding = RelationshipValidationBinding("peer-activity", "inbox", "peer-target", case.actor.id)
    peer_receipt = receipt_for_snapshot(snapshot, scope=scope, binding=peer_binding).to_dict()
    row.version += 1; case.db.commit()
    assert validate(case, prompt, receipt).outcome == "valid"
    with pytest.raises(SocialContextValidationError, match="version_changed"):
        SocialContextValidationService(case.gateway).validate(scope=scope, binding=peer_binding,
            prompt=snapshot.prompt_view(), receipt=peer_receipt, policy=CURRENTNESS_REVISION)


@pytest.mark.parametrize("relation_case", ["file"], indirect=True)
@pytest.mark.parametrize("blocked", ["lock", "query"])
def test_t25_native_sqlite_deadline_interrupts_and_restores_connection(relation_case, monkeypatch, blocked):
    from time import monotonic
    from sqlalchemy import text
    case = relation_case
    prompt, receipt = prepared(case)
    driver = case.db.connection().connection.driver_connection
    original_timeout = driver.execute("PRAGMA busy_timeout").fetchone()[0]
    other = case.engine.connect()
    try:
        if blocked == "lock":
            case.db.commit()  # Close the owned preparation read before the exclusive fixture writer.
            other.exec_driver_sql("BEGIN EXCLUSIVE")
        else:
            def slow_scope(**_kwargs):
                case.db.scalar(text("WITH RECURSIVE n(x) AS (VALUES(0) UNION ALL SELECT x+1 FROM n WHERE x<100000000) SELECT SUM(x) FROM n"))
                pytest.fail("native deadline did not interrupt SQLite")
            monkeypatch.setattr(case.gateway, "graph_recall_scope_access", slow_scope)
        started = monotonic()
        with pytest.raises(SocialContextValidationError, match="canonical_unavailable"):
            SocialContextValidationService(case.gateway, deadline_seconds=0.05).validate(scope=case.scope,
                binding=binding(case), prompt=prompt, receipt=receipt, policy=CURRENTNESS_REVISION)
        assert monotonic() - started < 1
        assert driver.execute("PRAGMA busy_timeout").fetchone()[0] == original_timeout
        other.rollback()
        case.db.rollback()  # The reader leaves transaction cleanup to its owner.
        assert case.db.scalar(text("SELECT 1")) == 1
    finally:
        other.close()
