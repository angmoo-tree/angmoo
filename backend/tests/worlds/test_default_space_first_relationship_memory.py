"""New default SNS -> saved interaction -> relationship selection, without restart."""
from dataclasses import replace
from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import select

from test_local_creator_v2 import db
from memory.test_activity_situation_contract import values, NOW
from memory.test_activity_situation_application import real_source, apply
from memory.test_p8_l_o_memory_consolidation import _character, _world_character
from app.domains.memory.contracts.scope import MemoryScope
from app.domains.memory.contracts.provenance import MemoryProviderMode
from app.domains.memory.service.scope import MemoryScopeService
from app.domains.memory.repository.situation_admission import admit
from app.domains.memory.models.items import MemoryItem, MemoryScopeSettingModel
from app.domains.relationships.models.personalization import RelationshipPolicy, RelationshipReviewMemoryReceipt
from app.domains.social.models.feed import WorldCharacterFeedObservation
from app.domains.worlds.models import WorldMembership
from app.domains.worlds.service.default_space import ensure_default_space
from app.runtime.memory.composition import memory_consolidation_repository
from app.runtime.memory.situation_sources import SituationSources
from app.runtime.relationships.policy_activation import initialize_default_space_policy
from app.runtime.relationships.review_memories import collect_new_review_memories, resolve_memory_batch


@pytest.mark.parametrize("activation_offset,eligible", [(-1, True), (0, True), (1, False)])
def test_first_saved_interaction_obeys_experience_time_not_save_time(db, monkeypatch, activation_offset, eligible):
    import app.domains.relationships.service.policy_activation as activation
    import memory.test_activity_situation_application as application

    activation_time = NOW + timedelta(seconds=activation_offset)
    class Clock(datetime):
        @classmethod
        def now(cls, tz=None):
            return activation_time if tz else activation_time.replace(tzinfo=None)
    monkeypatch.setattr(activation, "datetime", Clock)
    # All three memories are saved AFTER enrollment. Only experience time varies.
    monkeypatch.setattr(application, "NOW", NOW + timedelta(seconds=10))
    session, owner = db
    world = ensure_default_space(session, owner_id=owner.id, initialize=initialize_default_space_policy)
    policy = session.get(RelationshipPolicy, world.id)
    assert policy.activated_at.replace(tzinfo=UTC) == activation_time
    membership = session.scalar(select(WorldMembership).where(WorldMembership.world_id == world.id))
    for name in ("subject", "counterpart"):
        character = _character(f"consolidation-{name}-character", owner.id, name)
        session.add(character)
        session.flush()
        participant = _world_character(f"consolidation-{name}", world.id, character.id, membership.id)
        participant.autonomous_enabled = False
        participant.world_contract_hash = world.contract_hash
        session.add(participant)
    session.commit()
    scope = MemoryScope(owner_id=owner.id, world_id=world.id,
        subject_world_character_id="consolidation-subject")
    memory = memory_consolidation_repository(session)
    settings = MemoryScopeService(memory)
    initial = settings.get_or_create(scope)
    setting = settings.update(scope, expected_version=initial.version, enabled=True,
        retention_days=180, provider_mode=MemoryProviderMode.NONE)
    session.commit()
    post = real_source(session, scope)
    post.author_world_character_id = "consolidation-counterpart"
    post.author_character_id = "consolidation-counterpart-character"
    session.add(WorldCharacterFeedObservation(id="first-observation", world_id=world.id,
        observer_world_character_id=scope.subject_world_character_id, post_id=post.id,
        status="observed", claim_token="fixture", cycle_key="fixture", run_id="fixture",
        lease_expires_at=NOW, observed_at=NOW, post_created_at=NOW, claimed_at=NOW))
    session.commit()
    manifest, draft, result = values(session, scope, target=post.id)
    source = SituationSources(session).describe(scope, kind="POST", identifier=post.id,
        delivered=post.body, path="/selected/body", role="core", ordinal=0, target=post.id)
    receipt = admit(session, manifest=replace(manifest, sources=(source,)), draft=draft,
        result=replace(result, counterpart_id=post.author_world_character_id), now=NOW)
    apply(session, setting, memory)
    item = session.get(MemoryItem, receipt.applied_item_id)
    assert item is not None and item.created_at.replace(tzinfo=UTC) > activation_time
    grouped = collect_new_review_memories(session,
        setting=session.get(MemoryScopeSettingModel, setting.id), now=NOW + timedelta(seconds=11))
    selected = {row["memory_id"] for rows in grouped.values() for row in rows}
    assert (item.id in selected) is eligible
    resolved, = resolve_memory_batch(session, scope=scope, items=[item],
        activation=activation_time, now=NOW + timedelta(seconds=11))
    assert resolved[2] == (None if eligible else "no_post_activation_experience")
    if not eligible:
        # Synthetic predecessor history only; never replay real user's five exclusions.
        for number in range(5):
            old = MemoryItem(id=f"old-excluded-{number}", owner_id=scope.owner_id,
                world_id=world.id, subject_world_character_id=scope.subject_world_character_id,
                summary="Historical interaction", memory_kind="AUTOBIOGRAPHICAL_EVENT",
                status="active", confidence=1, salience=.5, created_at=NOW,
                valid_from=NOW, valid_until=NOW + timedelta(days=180))
            session.add(old)
            session.flush()
            session.add(RelationshipReviewMemoryReceipt(id=f"old-receipt-{number}",
                world_id=world.id, actor_world_character_id=scope.subject_world_character_id,
                target_world_character_id=post.author_world_character_id, memory_id=old.id,
                memory_digest="a" * 64, status="excluded", reason="no_post_activation_experience",
                created_at=NOW + timedelta(seconds=10)))
        session.commit()
    # Re-ensure does not move the boundary or resurrect a previously excluded memory.
    session.rollback()
    ensure_default_space(session, owner_id=owner.id, initialize=initialize_default_space_policy)
    assert session.get(RelationshipPolicy, world.id).activated_at.replace(tzinfo=UTC) == activation_time
    if not eligible:
        history = list(session.scalars(select(RelationshipReviewMemoryReceipt)))
        assert len(history) == 5
        assert all(row.status == "excluded" and row.reason == "no_post_activation_experience"
            and row.memory_digest == "a" * 64 and row.work_id is None
            and row.created_at.replace(tzinfo=UTC) == NOW + timedelta(seconds=10) for row in history)
