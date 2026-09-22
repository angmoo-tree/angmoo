import pytest
from sqlalchemy import select, event
from sqlalchemy.orm import Session
from app.domains.characters.schemas import AgentPersonaUpdate
from app.domains.characters.service.profile import update_character_persona
from app.runtime.social.world_feed_queries import WorldFeedQueries
from app.domains.social.service.world_feed import load_ready_search_profile
from world_characters.test_persona_continuity import _approved, _engine
from model_fixture_support import models


@pytest.mark.parametrize("personality", ["새로운 성격", "완전히 다른 성격 " * 90])
def test_feed_preserves_approved_pair_after_persona_save(personality):
    with Session(_engine(), expire_on_commit=False) as db:
        owner, entry, approved = _approved(db)
        entry.feed_runtime_mode = "topic_recommendation_v1"
        character = db.get(models.Character, entry.character_id)
        original = entry.character_contract_hash
        update_character_persona(db, character, AgentPersonaUpdate(
            personality=personality, speech_style=character.speech_style,
            worldview=character.worldview, topic_preferences=character.topic_preferences,
            safety_rules=character.safety_rules))
        profile = load_ready_search_profile(db, references=WorldFeedQueries(db), world_character_id=entry.id)
        assert profile.profile.id == approved.profile.id
        assert entry.character_contract_hash == original


@pytest.mark.parametrize("invalid", ["missing", "profile_status", "repertoire_hash", "world_hash", "membership", "character_deleted", "inactive", "owner_controlled"])
def test_invalid_scope_or_pair_remains_blocked(invalid):
    from datetime import datetime, UTC
    from app.domains.social.exceptions import WorldFeedReadinessError
    from app.runtime.social.feed_status import read_feed_status
    with Session(_engine(), expire_on_commit=False) as db:
        owner, entry, approved = _approved(db)
        entry.feed_runtime_mode = "topic_recommendation_v1"
        profile = db.get(models.WorldCommunityProfile, approved.profile.id)
        repertoire = db.get(models.WorldActivityRepertoire, approved.repertoire.id)
        if invalid == "missing": repertoire.status = "draft"
        elif invalid == "profile_status": profile.status = "stale"
        elif invalid == "repertoire_hash": repertoire.character_contract_hash = "invalid"
        elif invalid == "world_hash": db.get(models.World, entry.world_id).contract_hash = "invalid"
        elif invalid == "membership": db.get(models.WorldMembership, entry.membership_id).status = "left"
        elif invalid == "character_deleted": db.get(models.Character, entry.character_id).deleted_at = datetime.now(UTC)
        elif invalid == "inactive": entry.status = "inactive"
        elif invalid == "owner_controlled":
            entry.control_mode = "owner_controlled"
            entry.owner_user_id = owner.id
            entry.autonomous_enabled = False
        db.flush()
        with pytest.raises(WorldFeedReadinessError):
            load_ready_search_profile(db, references=WorldFeedQueries(db), world_character_id=entry.id)
        assert read_feed_status(db, world_character_id=entry.id).readiness.state == "blocked"


def test_status_is_read_only_and_scope_bound_and_survives_compaction():
    from datetime import datetime, UTC, timedelta
    from app.domains.routines.service.run_results import _stored_gateway_result
    from app.runtime.social.feed_status import read_feed_status
    with Session(_engine(), expire_on_commit=False) as db:
        owner, entry, approved = _approved(db)
        entry.feed_runtime_mode = "topic_recommendation_v1"
        entry.autonomous_enabled = True
        payload = {"world_id": entry.world_id, "world_character_id": entry.id,
            "feed_outcome": "model_abstained", "delivery_state": "delivered", "delivered_count": 1,
            "body": "private body", "feed_cycle_summary": {"filtered_candidate_count": 2, "prompt": "private prompt"}}
        compact = _stored_gateway_result({"feed_result": payload})
        assert compact == _stored_gateway_result(compact)
        assert "private" not in str(compact)
        now = datetime.now(UTC)
        for offset, value in enumerate([compact, {"feed_result": {**compact["feed_result"], "world_id": "other"}}, {}]):
            db.add(models.AgentRun(id=f"status-{offset}", user_id=owner.id, character_id=entry.character_id,
                agent_id="test", session_key="test", status="completed", gateway_result=value,
                created_at=now + timedelta(seconds=offset)))
        db.commit()
        writes = []
        def inspect(conn, cursor, statement, parameters, context, many):
            if statement.lstrip().split()[0].upper() in {"INSERT", "UPDATE", "DELETE"}: writes.append(statement)
        event.listen(db.bind, "before_cursor_execute", inspect)
        status = read_feed_status(db, world_character_id=entry.id)
        assert status.readiness.state == "ready"
        assert status.last_attempt.run_id == "status-0"
        assert status.last_attempt.delivered_count == 1
        assert not writes
        event.remove(db.bind, "before_cursor_execute", inspect)
        db.get(models.WorldActivityRepertoire, approved.repertoire.id).status = "stale"
        db.commit()
        status = read_feed_status(db, world_character_id=entry.id)
        assert status.readiness.state == "blocked"
        assert status.last_attempt.result == "model_abstained"


def test_preflight_failure_has_no_candidate_zero_or_delivery_claim():
    import asyncio
    from social.test_recommendation_cycle import _seed
    from social.test_feed_reaction_intent import _engine as cycle_engine, FakeFeedProvider
    from app.domains.social.schemas.feed import FeedReactionDecision
    from app.domains.routines.service.run_results import _stored_gateway_result
    from app.runtime.social.feed_cycle import run_world_keyword_feed
    from app.domains.social.models.topics import RecommendationDelivery
    with Session(cycle_engine(), expire_on_commit=False) as db:
        ctx, _ = _seed(db, with_candidate=True)
        wc = db.scalar(select(models.WorldCharacter).where(models.WorldCharacter.character_id == ctx.character.id))
        wc.feed_runtime_mode = "topic_recommendation_v1"
        db.get(models.WorldActivityRepertoire, "feed-approved-repertoire").status = "stale"
        db.commit()
        provider = FakeFeedProvider(FeedReactionDecision(reason_code="model_abstained"))
        result = asyncio.run(run_world_keyword_feed(ctx, provider=provider))
        compact = _stored_gateway_result({"feed_result": result})["feed_result"]
        assert compact["result"] == "approved_setup_required"
        assert "candidate_count" not in compact and compact["delivered_count"] == 0
        assert provider.plan_calls == provider.writer_calls == 0
        assert db.scalar(select(RecommendationDelivery)) is None
        assert db.scalar(select(models.WorldCharacterFeedCursor)) is None


def test_candidate_revalidation_rejects_world_change_after_planning():
    from social.test_recommendation_cycle import _seed
    from social.test_feed_reaction_intent import _engine as cycle_engine
    from app.domains.social.service.world_feed import revalidate_candidate_actions
    from app.domains.social.service.recommendation_topics import enroll_native_post
    with Session(cycle_engine(), expire_on_commit=False) as db:
        ctx, target = _seed(db, with_candidate=True)
        wc = db.scalar(select(models.WorldCharacter).where(models.WorldCharacter.character_id == ctx.character.id))
        wc.feed_runtime_mode = "topic_recommendation_v1"
        enroll_native_post(db, target)
        db.commit()
        refs = WorldFeedQueries(db)
        profile = load_ready_search_profile(db, references=refs, world_character_id=wc.id)
        candidates = refs.recommendation_candidates(profile=profile, allowed_policy_actions=ctx.activity_policy.allowed_actions, now=ctx.run_started_at)
        assert candidates.candidates
        db.get(models.World, wc.world_id).contract_hash = "changed-world"
        db.commit()
        assert revalidate_candidate_actions(db, references=refs, profile=profile,
            candidate=candidates.candidates[0], allowed_policy_actions=ctx.activity_policy.allowed_actions) is None


def test_new_candidate_failure_rejection_and_approval_keep_feed_pair_contract():
    from world_characters.test_persona_continuity import _regenerate, FakeProvider
    from app.domains.world_characters.service import autonomous_setup as setup
    from app.domains.world_characters.schemas import setup as schemas
    from app.domains.world_characters.exceptions import WorldCharacterSetupError
    with Session(_engine(), expire_on_commit=False) as db:
        owner, entry, approved = _approved(db)
        entry.feed_runtime_mode = "topic_recommendation_v1"
        refs = WorldFeedQueries(db)
        def current():
            return load_ready_search_profile(db, references=refs, world_character_id=entry.id).profile.id
        with pytest.raises(WorldCharacterSetupError):
            _regenerate(db, owner, entry, FakeProvider(fail_repertoire=True), key="failed-feed")
        assert current() == approved.profile.id
        candidate = _regenerate(db, owner, entry, FakeProvider(), key="candidate-feed")
        assert current() == approved.profile.id
        setup.reject_setup(db, world_character_id=entry.id, user=owner,
            data=schemas.WorldCharacterSetupRejectCreate(idempotency_key="reject-feed",
                profile_id=candidate.profile.id, repertoire_id=candidate.repertoire.id))
        assert current() == approved.profile.id
        candidate = _regenerate(db, owner, entry, FakeProvider(), key="new-feed")
        setup.approve_setup(db, world_character_id=entry.id, user=owner,
            data=schemas.WorldCharacterSetupApproveCreate(idempotency_key="approve-feed",
                profile_id=candidate.profile.id, repertoire_id=candidate.repertoire.id))
        assert current() == candidate.profile.id


def test_topic_regeneration_does_not_rewrite_approved_provenance(monkeypatch):
    import asyncio
    from types import SimpleNamespace
    from app.runtime.social import topic_preparation as topics
    from app.domains.social.schemas.recommendation import TopicGenerationResult, TopicDefinition
    with Session(_engine(), expire_on_commit=False) as db:
        owner, entry, approved = _approved(db)
        entry.feed_runtime_mode = "topic_recommendation_v1"
        refs = WorldFeedQueries(db)
        character = refs.character(entry.character_id)
        def baseline():
            pair = refs.approved_pair(entry.id)
            return (refs.character_hash(character), entry.character_contract_hash,
                    tuple((p.id, p.character_contract_hash, p.world_contract_hash) for p in pair))
        before = baseline()
        monkeypatch.setattr(topics, "find_world_character_credential", lambda *a, **k: SimpleNamespace(id="fixture"))
        monkeypatch.setattr(topics.CredentialResolver, "resolve_llm_credential", lambda *a, **k: SimpleNamespace(provider="google", credential_id="fixture", fingerprint="fixture-fingerprint"))
        async def generator(*args):
            return TopicGenerationResult(topics=[TopicDefinition(name="새로운 관심", scope="world")])
        result = asyncio.run(topics.regenerate(db, world_id=entry.world_id, owner_id=owner.id,
            world_character_id=entry.id, request_id="topic-feed-test", generator=generator))
        assert result["state"] == "ready"
        assert baseline() == before
        assert load_ready_search_profile(db, references=refs, world_character_id=entry.id).profile.id == approved.profile.id


@pytest.mark.parametrize("invalid", ["foreign_profile", "foreign_repertoire", "broken_link"])
def test_pair_identity_is_checked_even_if_adapter_returns_bad_pair(invalid):
    from types import SimpleNamespace
    from app.domains.social.exceptions import WorldFeedReadinessError
    with Session(_engine(), expire_on_commit=False) as db:
        _, entry, approved = _approved(db)
        entry.feed_runtime_mode = "topic_recommendation_v1"
        refs = WorldFeedQueries(db)
        profile, repertoire = refs.approved_pair(entry.id)
        fields = ("id", "world_character_id", "status", "character_contract_hash", "world_contract_hash")
        p = SimpleNamespace(**{name: getattr(profile, name) for name in fields})
        r = SimpleNamespace(**{name: getattr(repertoire, name) for name in fields}, community_profile_id=profile.id)
        if invalid == "foreign_profile": p.world_character_id = "foreign"
        elif invalid == "foreign_repertoire": r.world_character_id = "foreign"
        else: r.community_profile_id = "other-profile"
        refs.approved_pair = lambda identity: (p, r)
        with pytest.raises(WorldFeedReadinessError, match="approved_setup_invalid"):
            load_ready_search_profile(db, references=refs, world_character_id=entry.id)
