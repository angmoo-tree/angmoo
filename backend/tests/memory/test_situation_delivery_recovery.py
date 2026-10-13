"""Real source readers on an isolated durable SQLite DB, with no provider I/O."""
from dataclasses import replace

import pytest
from sqlalchemy import create_engine, event, select
from sqlalchemy.orm import Session

from app.runtime.persistence.model_registration import register_models
from app.domains.memory.contracts.activity_situation import CommittedEffect, FinalDeliveredFragment, RelationshipDeliveryBasis, stable_digest
from app.domains.memory.models.items import MemoryItem
from app.domains.memory.repository.situation_admission import admit
from app.domains.relationships.models.social import RelationshipState
from app.domains.social.models.posts import Post
from app.runtime.memory.situation_sources import SituationSources, relationship_digest
from memory.test_p8_l_o_memory_consolidation import _stack
from memory.test_activity_situation_contract import values, NOW
from memory.test_activity_situation_application import apply, real_source


@pytest.fixture
def durable_stack(tmp_path):
    engine = create_engine(f"sqlite:///{tmp_path / 'situations.sqlite3'}")
    event.listen(engine, "connect", lambda connection, _: connection.execute("PRAGMA foreign_keys=ON"))
    register_models().create_all(engine)
    with Session(engine, expire_on_commit=False) as db:
        scope, setting, _, memory, *_ = _stack(db)
        yield db, scope, setting, memory
    engine.dispose()


def delivered_reply(db, scope):
    root = real_source(db, scope)
    reply = Post(id="delivered-counterpart-reply", world_id=scope.world_id,
        author_world_character_id="consolidation-counterpart",
        author_character_id="consolidation-counterpart-character", author_name="counterpart",
        reply_to_post_id=root.id, title="안부 답글", body="따뜻한 차를 마시고 잠깐 쉬어요.", created_at=NOW)
    response = Post(id="committed-subject-reply", world_id=scope.world_id,
        author_world_character_id=scope.subject_world_character_id,
        author_character_id="consolidation-subject-character", author_name="subject",
        reply_to_post_id=reply.id, title="감사 답글", body="고마워요. 차를 마시며 잠깐 쉴게요.", created_at=NOW)
    db.add_all([reply, response])
    db.commit()
    sources = SituationSources(db)
    payload = {"selected_targets": [{"text": reply.body}]}
    payload_digest = stable_digest(payload)
    entry = sources.describe(scope, kind="REPLY", identifier=reply.id, delivered=reply.body,
        path="/selected_targets/0/text", role="core", ordinal=0, target=reply.id,
        delivery=FinalDeliveredFragment.capture(payload, path="/selected_targets/0/text", text=reply.body, payload_digest=payload_digest))
    output = sources.describe(scope, kind="REPLY", identifier=response.id, delivered=response.body,
        path="/committed_result/body", role="committed_result", ordinal=1, target=reply.id)
    manifest, draft, result = values(db, scope, target=reply.id)
    manifest = replace(manifest, sources=(entry,), payload_digest=payload_digest, version=2)
    result = replace(result, lane="inbox", planned_effects=("reply",),
        effects=(CommittedEffect("reply", "REPLY", response.id, "succeeded"),), result_sources=(output,),
        counterpart_id=reply.author_world_character_id)
    return admit(db, manifest=manifest, draft=draft, result=result, now=NOW), reply


def test_actual_inbox_reply_without_feed_observation_is_saved(durable_stack):
    db, scope, setting, memory = durable_stack
    row, _ = delivered_reply(db, scope)
    db.commit()
    apply(db, setting, memory)
    assert row.state == "applied", row.error_code
    assert db.get(MemoryItem, row.applied_item_id) is not None


def test_normal_relationship_update_preserves_delivered_experience(durable_stack):
    db, scope, setting, memory = durable_stack
    post = real_source(db, scope)
    relationship = RelationshipState(id="delivered-relationship", world_id=scope.world_id,
        actor_world_character_id=scope.subject_world_character_id,
        target_world_character_id="consolidation-counterpart", version=6)
    db.add(relationship)
    db.commit()
    reader = SituationSources(db)
    payload = {"relationship": "서로의 안부를 묻는 사이", "target": {"body": post.body}}
    payload_digest = stable_digest(payload)
    core = reader.describe(scope, kind="POST", identifier=post.id, delivered=post.body,
        path="/target/body", role="core", ordinal=0, target=post.id,
        delivery=FinalDeliveredFragment.capture(payload, path="/target/body", text=post.body, payload_digest=payload_digest))
    background = reader.describe(scope, kind="RELATIONSHIP", identifier=relationship.id,
        delivered=payload["relationship"], path="/relationship", role="background", ordinal=1,
        relationship_basis=RelationshipDeliveryBasis(relationship.id, relationship.actor_world_character_id,
            relationship.target_world_character_id, relationship.version, relationship.view_version, relationship_digest(relationship)),
        delivery=FinalDeliveredFragment.capture(payload, path="/relationship", text=payload["relationship"], payload_digest=payload_digest))
    manifest, draft, result = values(db, scope, target=post.id)
    output = reader.describe(scope, kind="POST", identifier=post.id, delivered=post.body,
        path="/committed_result/body", role="committed_result", ordinal=2, target=post.id)
    result = replace(result, planned_effects=("post",), effects=(CommittedEffect("post", "POST", post.id, "succeeded"),), result_sources=(output,))
    row = admit(db, manifest=replace(manifest, sources=(core, background), payload_digest=payload_digest, version=2), draft=draft, result=result, now=NOW)
    relationship.version = 7
    db.commit()
    apply(db, setting, memory)
    assert row.state == "applied", row.error_code
