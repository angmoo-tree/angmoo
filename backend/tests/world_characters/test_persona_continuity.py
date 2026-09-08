from __future__ import annotations

import asyncio
from datetime import datetime, UTC, timedelta
from types import SimpleNamespace

import pytest
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.domains.characters.schemas import AgentPersonaUpdate
from app.domains.characters.service.profile import update_character_persona
from app.domains.world_characters import models
from app.domains.world_characters.exceptions import WorldCharacterSetupConflictError, WorldCharacterSetupError
from app.domains.world_characters.schemas import setup as schemas
from app.domains.world_characters.service import autonomous_setup as setup
from app.domains.world_characters.service.readiness import evaluate
from app.runtime.routines.plan_references import SqlAlchemyPlanReferences
from app.domains.routines.service.plans import _ready_repertoire
from world_characters.test_setup_service import FakeProvider, _engine, _generate, _seed
from model_fixture_support import models as fixture_models
from app.domains.routines.service.plans import prepare_activity_plan
from app.domains.routines.schemas import DailyActivityPlanPrepareCreate


def _approved(db):
    owner, entry = _seed(db)
    result = _generate(db, owner=owner, provider=FakeProvider())
    result = setup.approve_setup(db, world_character_id=entry.id, user=owner,
        data=schemas.WorldCharacterSetupApproveCreate(
            idempotency_key="initial-approve", profile_id=result.profile.id,
            repertoire_id=result.repertoire.id,
        ))
    entry.activity_runtime_mode = "routine_resident_v1"
    db.commit()
    return owner, entry, result


def _regenerate(db, owner, entry, provider, key="explicit-regenerate"):
    return asyncio.run(setup.generate_setup(db, world_character_id=entry.id, user=owner,
        data=schemas.WorldCharacterSetupGenerateCreate(
            idempotency_key=key, consent_policy_version="p2-consent-v1",
            consented=True, regenerate=True,
        ), provider=provider))


@pytest.mark.parametrize("personality", ["작은 변경", "차분하고 호기심이 많다. " * 90])
@pytest.mark.parametrize("enabled", [False, True])
def test_persona_save_preserves_execution_and_generation_provenance(personality, enabled):
    with Session(_engine(), expire_on_commit=False) as db:
        owner, entry, approved = _approved(db)
        entry.autonomous_enabled = enabled
        character = db.get(fixture_models.Character, entry.character_id)
        original_hash = entry.character_contract_hash
        update_character_persona(db, character, AgentPersonaUpdate(
            personality=personality, speech_style=character.speech_style,
            worldview=character.worldview, topic_preferences=character.topic_preferences,
            safety_rules=character.safety_rules,
        ))
        result = setup.get_setup(db, world_character_id=entry.id, user=owner)
        assert result.autonomy_ready and result.persona_changed
        assert result.active_profile.id == approved.profile.id
        assert result.active_repertoire.id == approved.repertoire.id
        assert result.active_profile.character_contract_hash == original_hash
        assert entry.character_contract_hash == original_hash
        assert result.autonomous_enabled is enabled
        assert result.can_regenerate and not result.can_reject and not result.can_approve
        assert evaluate(db, character=character, setting=SimpleNamespace()).ready
        repertoire, candidates = _ready_repertoire(SqlAlchemyPlanReferences(db), scope=SimpleNamespace(
            character=character, world_character=entry, world=db.get(fixture_models.World, entry.world_id),
        ))
        assert repertoire.id == approved.repertoire.id and len(candidates) == 40
        # Re-loading has the same result, without repairing hashes or regenerating.
        db.expire_all()
        assert setup.get_setup(db, world_character_id=entry.id, user=owner).autonomy_ready
        assert db.scalar(select(func.count(models.WorldCharacterSetupAttempt.id))) == 3


def test_same_input_regeneration_keeps_active_pair_and_rejects_only_target_candidate():
    with Session(_engine(), expire_on_commit=False) as db:
        owner, entry, approved = _approved(db)
        provider = FakeProvider()
        generated = _regenerate(db, owner, entry, provider)
        assert provider.profile_calls == 1 and provider.repertoire_calls == 1
        assert generated.profile.id != approved.profile.id
        assert generated.repertoire.id != approved.repertoire.id
        assert generated.autonomy_ready and generated.can_approve and generated.can_reject
        assert generated.active_profile.id == approved.profile.id
        replay_provider = FakeProvider()
        replay = _regenerate(db, owner, entry, replay_provider)
        assert replay.reused and replay.profile.id == generated.profile.id
        assert replay_provider.profile_calls == replay_provider.repertoire_calls == 0
        rejected_request = schemas.WorldCharacterSetupRejectCreate(
            idempotency_key="reject-review-candidate", profile_id=generated.profile.id,
            repertoire_id=generated.repertoire.id,
        )
        rejected = setup.reject_setup(db, world_character_id=entry.id, user=owner, data=rejected_request)
        assert rejected.autonomy_ready and rejected.can_regenerate and not rejected.can_reject
        assert rejected.active_profile.id == approved.profile.id
        assert rejected.active_repertoire.id == approved.repertoire.id
        count = db.scalar(select(func.count(models.WorldCharacterSetupAttempt.id)))
        setup.reject_setup(db, world_character_id=entry.id, user=owner, data=rejected_request)
        assert db.scalar(select(func.count(models.WorldCharacterSetupAttempt.id))) == count
        with pytest.raises(WorldCharacterSetupConflictError):
            setup.reject_setup(db, world_character_id=entry.id, user=owner,
                data=schemas.WorldCharacterSetupRejectCreate(idempotency_key="reject-without-target"))


def test_regeneration_failure_keeps_approved_execution_pair():
    with Session(_engine(), expire_on_commit=False) as db:
        owner, entry, approved = _approved(db)
        with pytest.raises(WorldCharacterSetupError):
            _regenerate(db, owner, entry, FakeProvider(fail_repertoire=True))
        result = setup.get_setup(db, world_character_id=entry.id, user=owner)
        assert result.autonomy_ready
        assert result.active_repertoire.id == approved.repertoire.id
        assert result.can_retry_stage == "repertoire"
        assert result.profile.id != result.active_profile.id


def test_initial_candidate_rejection_leaves_a_generation_path():
    with Session(_engine(), expire_on_commit=False) as db:
        owner, entry = _seed(db)
        generated = _generate(db, owner=owner, provider=FakeProvider())
        result = setup.reject_setup(db, world_character_id=entry.id, user=owner,
            data=schemas.WorldCharacterSetupRejectCreate(
                idempotency_key="reject-initial-candidate", profile_id=generated.profile.id,
                repertoire_id=generated.repertoire.id,
            ))
        assert not result.autonomy_ready and result.can_regenerate
        assert not result.can_reject and not result.can_approve
        assert result.active_profile is None


def test_reviewed_inputs_changing_does_not_expire_active_pair():
    with Session(_engine(), expire_on_commit=False) as db:
        owner, entry, approved = _approved(db)
        candidate = _regenerate(db, owner, entry, FakeProvider())
        character = db.get(fixture_models.Character, entry.character_id)
        character.personality = "Changed while reviewing a candidate"
        db.commit()
        with pytest.raises(WorldCharacterSetupConflictError, match="contract_hash_stale"):
            setup.approve_setup(db, world_character_id=entry.id, user=owner,
                data=schemas.WorldCharacterSetupApproveCreate(
                    idempotency_key="approve-stale-candidate", profile_id=candidate.profile.id,
                    repertoire_id=candidate.repertoire.id,
                ))
        result = setup.get_setup(db, world_character_id=entry.id, user=owner)
        assert result.autonomy_ready and result.can_reject and not result.can_approve
        assert result.active_profile.id == approved.profile.id


def test_new_approval_keeps_todays_plan_and_only_changes_future_plans():
    with Session(_engine(), expire_on_commit=False) as db:
        owner, entry, approved = _approved(db)
        now = datetime(2026, 9, 8, 1, tzinfo=UTC)
        def plan(when):
            return prepare_activity_plan(db, character_id=entry.character_id,
                world_id=entry.world_id, user=owner, references=SqlAlchemyPlanReferences(db),
                data=DailyActivityPlanPrepareCreate(idempotency_key="plan-continuity"), now=when)
        today = plan(now)
        candidate = _regenerate(db, owner, entry, FakeProvider())
        request = schemas.WorldCharacterSetupApproveCreate(idempotency_key="approve-new-pair",
            profile_id=candidate.profile.id, repertoire_id=candidate.repertoire.id)
        result = setup.approve_setup(db, world_character_id=entry.id, user=owner, data=request)
        assert result.active_repertoire.id == candidate.repertoire.id
        retained = plan(now)
        assert retained.id == today.id and retained.repertoire_id == approved.repertoire.id
        assert [item.model_dump() for item in retained.items] == [item.model_dump() for item in today.items]
        tomorrow = plan(now + timedelta(days=1))
        assert tomorrow.repertoire_id == candidate.repertoire.id
        assert db.get(models.WorldActivityRepertoire, approved.repertoire.id).status == "superseded"
        # Replaying an old approval never replaces the active pair or rewrites plans.
        setup.approve_setup(db, world_character_id=entry.id, user=owner,
            data=schemas.WorldCharacterSetupApproveCreate(idempotency_key="initial-approve",
                profile_id=approved.profile.id, repertoire_id=approved.repertoire.id))
        assert setup.get_setup(db, world_character_id=entry.id, user=owner).active_repertoire.id == candidate.repertoire.id


def test_concurrent_request_during_provider_work_does_not_call_another_provider():
    with Session(_engine(), expire_on_commit=False) as db:
        owner, entry, approved = _approved(db)
        calls = []
        class InterleavingProvider(FakeProvider):
            async def generate_community_profile(self, **kwargs):
                other = FakeProvider()
                with pytest.raises(WorldCharacterSetupConflictError, match="setup_in_progress"):
                    await setup.generate_setup(db, world_character_id=entry.id, user=owner,
                        data=schemas.WorldCharacterSetupGenerateCreate(idempotency_key="competing-request",
                            consent_policy_version="p2-consent-v1", consented=True, regenerate=True), provider=other)
                calls.append(other.profile_calls + other.repertoire_calls)
                return await super().generate_community_profile(**kwargs)
        result = _regenerate(db, owner, entry, InterleavingProvider())
        assert calls == [0]
        assert result.active_repertoire.id == approved.repertoire.id
