from __future__ import annotations

import asyncio
from datetime import UTC, datetime

from fastapi import FastAPI
import httpx
import pytest
from sqlalchemy import create_engine, event, func, select
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

from app import models, schemas
from app.api.v1 import deps as api_deps
from app.api.v1.routes import worlds as world_routes
from app.api.v1.routes import world_character_setup as setup_routes
from app.core import security
from app.core.db import Base
from app.domains.worlds.domain.reserved_roles import (
    NO_SPECIFIC_ROLE_DESCRIPTION,
    NO_SPECIFIC_ROLE_KEY,
    NO_SPECIFIC_ROLE_NAME,
)
from app.runtime.migrations.sqlite_versions.v2_to_v3_no_specific_role import (
    upgrade_v2_to_v3,
)
from app.services import world_character_provider, world_character_setup


DAYPARTS = ("dawn", "morning", "afternoon", "evening")
ACTIVITIES = (
    "catalog crystal samples",
    "map hidden stairways",
    "practice ward patterns",
    "repair an old astrolabe",
    "compare potion aromas",
    "translate a rune fragment",
    "organize familiar records",
    "sketch greenhouse herbs",
    "review duel etiquette",
    "prepare observatory notes",
)
DAYPART_SCENES = {
    "dawn": "before sunrise, silent blue lanterns guide solitary preparation",
    "morning": "after breakfast, busy lecture bells begin a structured class session",
    "afternoon": "following lunch, lively club rooms support collaborative experiments",
    "evening": "after sunset, warm dormitory lamps invite reflective peer discussion",
}
ACTIVITY_OUTCOMES = (
    "produce a labeled mineral drawer for the next laboratory group",
    "leave a verified route card beside the west corridor notice board",
    "complete a safe barrier diagram with three corrected anchor points",
    "restore the instrument so tomorrow's astronomy lesson can use it",
    "write a sensory comparison table without tasting unknown mixtures",
    "prepare a glossary note that classmates can review during seminar",
    "find one missing care interval and update the shared handbook",
    "identify two medicinal leaves and mark their watering schedule",
    "summarize a respectful opening and closing sequence for practice",
    "assemble a concise sky log for the academy weather archive",
)


def _engine():
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )

    @event.listens_for(engine, "connect")
    def _foreign_keys(dbapi_connection, _connection_record) -> None:
        dbapi_connection.execute("PRAGMA foreign_keys=ON")

    Base.metadata.create_all(engine)
    return engine


def _request(app: FastAPI, method: str, path: str, **kwargs) -> httpx.Response:
    async def call() -> httpx.Response:
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(
            transport=transport,
            base_url="http://testserver",
        ) as client:
            return await client.request(method, path, **kwargs)

    return asyncio.run(call())


def _app(engine, principal: dict[str, models.User | None]) -> FastAPI:
    app = FastAPI()
    app.include_router(world_routes.router, prefix="/api/v1")
    app.include_router(setup_routes.router, prefix="/api/v1")

    def get_db():
        with Session(engine) as db:
            yield db

    def current_user() -> models.User:
        assert principal["user"] is not None
        return principal["user"]

    app.dependency_overrides[api_deps.get_db] = get_db
    app.dependency_overrides[api_deps.get_current_user] = current_user
    return app


def _profile_payload() -> dict:
    return {
        "visible_summary": "A careful academy student who likes practical collaboration.",
        "core_interests": ["alchemy", "runes", "friendship"],
        "adjacent_interests": ["library", "observatory"],
        "avoid_topics": ["dangerous magic"],
        "discovery_openness": 72,
        "search_keywords": [
            "alchemy",
            "runes",
            "library",
            "practice",
            "dormitory",
            "friends",
            "classes",
            "academy event",
        ],
        "action_profile": {
            key: {"weight": 50, "note": f"Use {key} when it fits the scene."}
            for key in schemas.WORLD_COMMUNITY_ACTION_KEYS
        },
    }


def _repertoire_payload() -> dict:
    activity_kinds = [
        "duty",
        "rest",
        "self_care",
        "hobby",
        "exploration",
        "social",
        "maintenance",
        "challenge",
        "duty",
        "rest",
    ]
    candidates: list[dict] = []
    for daypart in DAYPARTS:
        for index, activity in enumerate(ACTIVITIES):
            outcome = ACTIVITY_OUTCOMES[index]
            candidates.append(
                {
                    "daypart": daypart,
                    "activity_kind": activity_kinds[index],
                    "title": f"{daypart} {activity}",
                    "activity_seed": (
                        f"{DAYPART_SCENES[daypart]}. Mira will {activity}, then "
                        f"{outcome}. This is scenario {daypart}-{index + 1}."
                    ),
                    "place_key": "academy-lab",
                    "social_mode": "open_to_interaction",
                }
            )
    return {"candidates": candidates}


class FakeProvider:
    def __init__(self, *, fail_repertoire: bool = False) -> None:
        self.profile_calls = 0
        self.repertoire_calls = 0
        self.fail_repertoire = fail_repertoire

    async def generate_community_profile(self, **_kwargs):
        self.profile_calls += 1
        return world_character_provider.WorldCharacterProviderResult(
            payload=_profile_payload(),
            physical_request_count=1,
            prompt_token_count=100,
            output_token_count=50,
            total_token_count=150,
            latency_ms=25,
        )

    async def generate_repertoire(self, *, validator, **_kwargs):
        self.repertoire_calls += 1
        if self.fail_repertoire:
            raise TimeoutError("synthetic provider timeout")
        validated = validator(_repertoire_payload())
        return world_character_provider.WorldCharacterProviderResult(
            payload=validated,
            physical_request_count=2,
            prompt_token_count=200,
            output_token_count=500,
            total_token_count=700,
            latency_ms=50,
        )


def _seed(db: Session) -> tuple[models.User, models.WorldCharacter]:
    now = datetime.now(UTC)
    owner = models.User(
        id="owner",
        email="owner@example.test",
        display_name="owner",
        display_name_normalized="owner",
        privacy_policy_version="test",
        terms_version="test",
        profile_setup_completed=True,
    )
    character = models.Character(
        id="character-a",
        owner_id=owner.id,
        name="Mira",
        handle="mira",
        one_liner="An observant magic academy student",
        personality="Careful, curious, and warm.",
        speech_style="Calm and considerate.",
        worldview="Learning deepens through cooperation.",
        topic_preferences="Alchemy, runes, and friends",
        safety_rules="Never use dangerous spells alone.",
        persona_summary="A second-year alchemy student at Arcana Academy.",
        moderation_status="active",
    )
    world = models.World(
        id="world-a",
        slug="arcana-academy",
        owner_user_id=owner.id,
        name="Arcana Academy",
        tagline="A residential school of practical magic",
        setting_description="Students learn magic through classes and clubs.",
        daily_life_description="Classes, meals, practice, and friendship shape each day.",
        genre_tags=["fantasy"],
        tone_tags=["warm"],
        timezone="Asia/Seoul",
        language="ko",
        visibility="public",
        join_policy="open",
        status="published",
        contract_version="world-v1",
        contract_hash="b" * 64,
        readiness_status="publish_ready",
        create_idempotency_key="create-world-a",
    )
    membership = models.WorldMembership(
        id="membership-a",
        world_id=world.id,
        user_id=owner.id,
        role="member",
        status="active",
        joined_at=now,
    )
    world_character = models.WorldCharacter(
        id="world-character-a",
        world_id=world.id,
        character_id=character.id,
        membership_id=membership.id,
        role_key="student",
        status="pending",
        autonomous_enabled=False,
        activity_runtime_mode="routine_resident_v1",
        feed_runtime_mode="keyword_search_v1",
        local_profile={"background": "second-year alchemy student"},
    )
    credential = models.LlmCredential(
        id="credential-a",
        owner_id=owner.id,
        character_id=character.id,
        provider="google",
        purpose="agent",
        model="gemini-3.1-flash-lite",
        auth_profile_id="test-profile",
        label="test key",
        encrypted_api_key=security.encrypt_secret(
            "synthetic-api-key",
            scope=security.SecretScope(
                owner_id=owner.id,
                character_id=character.id,
                provider="google",
                purpose="agent",
            ),
        ),
        enabled=True,
    )
    db.add(owner)
    db.flush()
    db.add_all([character, world])
    db.flush()
    db.add_all(
        [
            membership,
            models.WorldPlace(
                id="place-a",
                world_id=world.id,
                place_key="academy-lab",
                name="Academy Lab",
                available_dayparts=list(DAYPARTS),
                access_role_keys=["student"],
                status="enabled",
            ),
            models.WorldRole(
                id="role-a",
                world_id=world.id,
                role_key="student",
                name="Student",
                autonomous_allowed=True,
                status="enabled",
            ),
            credential,
        ]
    )
    db.flush()
    db.add(world_character)
    db.commit()
    return owner, world_character


def _generate(
    db: Session,
    *,
    owner: models.User,
    provider: FakeProvider,
    idempotency_key: str = "generate-world-character-a",
):
    return asyncio.run(
        world_character_setup.generate_setup(
            db,
            world_character_id="world-character-a",
            user=owner,
            data=schemas.WorldCharacterSetupGenerateCreate(
                idempotency_key=idempotency_key,
                consent_policy_version="p2-consent-v1",
                consented=True,
            ),
            provider=provider,
        )
    )


def test_two_logical_calls_create_profile_and_exact_forty_candidates() -> None:
    engine = _engine()
    with Session(engine, expire_on_commit=False) as db:
        owner, world_character = _seed(db)
        provider = FakeProvider()

        result = _generate(db, owner=owner, provider=provider)

        assert provider.profile_calls == 1
        assert provider.repertoire_calls == 1
        assert sum(
            db.scalars(
                select(models.WorldCharacterSetupAttempt.physical_request_count)
            )
        ) == 3
        assert result.state == "ready"
        assert result.can_approve is True
        assert result.autonomy_ready is False
        assert result.autonomous_enabled is False
        assert result.repertoire is not None
        assert len(result.repertoire.candidates) == 40
        assert {
            daypart: sum(
                candidate.daypart == daypart
                for candidate in result.repertoire.candidates
            )
            for daypart in DAYPARTS
        } == {daypart: 10 for daypart in DAYPARTS}
        assert world_character.autonomous_enabled is False


def test_approval_activates_contract_but_not_autonomous_execution() -> None:
    engine = _engine()
    with Session(engine, expire_on_commit=False) as db:
        owner, world_character = _seed(db)
        generated = _generate(db, owner=owner, provider=FakeProvider())
        assert generated.profile is not None
        assert generated.repertoire is not None

        approved = world_character_setup.approve_setup(
            db,
            world_character_id=world_character.id,
            user=owner,
            data=schemas.WorldCharacterSetupApproveCreate(
                idempotency_key="approve-world-character-a",
                profile_id=generated.profile.id,
                repertoire_id=generated.repertoire.id,
            ),
        )

        assert approved.autonomy_ready is True
        assert approved.autonomous_enabled is False
        assert approved.profile is not None and approved.profile.status == "ready"
        assert approved.repertoire is not None
        assert approved.repertoire.status == "ready"
        assert world_character.status == "active"
        assert world_character.autonomous_enabled is False
        active_world = db.get(models.CharacterActiveWorld, world_character.character_id)
        assert active_world is not None
        assert active_world.world_character_id == world_character.id
        assert active_world.version == 1


def test_ready_same_hash_pair_is_reused_without_provider_calls() -> None:
    engine = _engine()
    with Session(engine, expire_on_commit=False) as db:
        owner, world_character = _seed(db)
        generated = _generate(db, owner=owner, provider=FakeProvider())
        assert generated.profile is not None and generated.repertoire is not None
        world_character_setup.approve_setup(
            db,
            world_character_id=world_character.id,
            user=owner,
            data=schemas.WorldCharacterSetupApproveCreate(
                idempotency_key="approve-world-character-a",
                profile_id=generated.profile.id,
                repertoire_id=generated.repertoire.id,
            ),
        )
        provider = FakeProvider()

        reused = _generate(
            db,
            owner=owner,
            provider=provider,
            idempotency_key="generate-reused-world-character-a",
        )

        assert reused.reused is True
        assert reused.autonomy_ready is True
        assert provider.profile_calls == 0
        assert provider.repertoire_calls == 0


def test_owner_controlled_identity_is_rejected_before_provider_or_writes() -> None:
    engine = _engine()
    with Session(engine, expire_on_commit=False) as db:
        owner, world_character = _seed(db)
        world_character.control_mode = "owner_controlled"
        world_character.owner_user_id = owner.id
        db.commit()
        provider = FakeProvider()

        with pytest.raises(
            world_character_setup.WorldCharacterSetupValidationError
        ) as exc:
            _generate(db, owner=owner, provider=provider)

        assert exc.value.reason_code == "owner_controlled_automation_disabled"
        assert provider.profile_calls == 0
        assert provider.repertoire_calls == 0
        assert db.scalar(select(func.count(models.WorldCharacterSetupAttempt.id))) == 0
        assert db.scalar(select(func.count(models.WorldCommunityProfile.id))) == 0
        assert db.scalar(select(func.count(models.WorldActivityRepertoire.id))) == 0
        assert db.scalar(select(func.count(models.WorldActivityCandidate.id))) == 0
        assert db.scalar(select(func.count(models.Post.id))) == 0
        assert db.scalar(select(func.count(models.AgentRun.id))) == 0


def test_credential_deletion_preserves_approved_setup_and_zero_call_reentry() -> None:
    engine = _engine()
    with Session(engine, expire_on_commit=False) as db:
        owner, world_character = _seed(db)
        generated = _generate(db, owner=owner, provider=FakeProvider())
        assert generated.profile is not None and generated.repertoire is not None
        world_character_setup.approve_setup(
            db,
            world_character_id=world_character.id,
            user=owner,
            data=schemas.WorldCharacterSetupApproveCreate(
                idempotency_key="approve-before-credential-delete",
                profile_id=generated.profile.id,
                repertoire_id=generated.repertoire.id,
            ),
        )
        credential = db.get(models.LlmCredential, "credential-a")
        assert credential is not None
        db.delete(credential)
        db.commit()

        restored = world_character_setup.get_setup(
            db,
            world_character_id=world_character.id,
            user=owner,
        )
        preflight = world_character_setup.preflight_setup(
            db,
            world_character_id=world_character.id,
            user=owner,
        )

        assert restored.autonomy_ready is True
        assert restored.profile is not None
        assert restored.repertoire is not None
        assert len(restored.repertoire.candidates) == 40
        assert preflight.credential_ready is False
        assert preflight.safe_reason_code == "credential_required"
        assert preflight.reused is True
        assert preflight.logical_call_count == 0
        assert preflight.physical_request_count == 0
        assert db.scalar(select(func.count(models.WorldCommunityProfile.id))) == 1
        assert db.scalar(select(func.count(models.WorldActivityRepertoire.id))) == 1
        assert db.scalar(select(func.count(models.WorldActivityCandidate.id))) == 40


def test_character_privacy_cleanup_removes_setup_outputs_only() -> None:
    engine = _engine()
    with Session(engine, expire_on_commit=False) as db:
        owner, world_character = _seed(db)
        generated = _generate(db, owner=owner, provider=FakeProvider())
        assert generated.profile is not None
        assert generated.repertoire is not None

        world_character_setup.delete_setup_data_for_characters(
            db, character_ids=["character-a"]
        )
        db.commit()

        assert db.scalar(select(func.count(models.WorldCommunityProfile.id))) == 0
        assert db.scalar(select(func.count(models.WorldActivityRepertoire.id))) == 0
        assert db.scalar(select(func.count(models.WorldActivityCandidate.id))) == 0
        assert db.scalar(select(func.count(models.WorldCharacterSetupAttempt.id))) == 0
        assert db.get(models.WorldCharacter, world_character.id) is not None


def test_repertoire_failure_preserves_profile_and_retry_calls_only_repertoire() -> None:
    engine = _engine()
    with Session(engine, expire_on_commit=False) as db:
        owner, _world_character = _seed(db)
        failing = FakeProvider(fail_repertoire=True)
        with pytest.raises(world_character_setup.WorldCharacterSetupValidationError) as exc:
            _generate(db, owner=owner, provider=failing)
        assert exc.value.reason_code == "provider_timeout"
        assert failing.profile_calls == 1
        assert failing.repertoire_calls == 1
        profile_count = db.scalar(select(models.WorldCommunityProfile))
        assert profile_count is not None

        retry_provider = FakeProvider()
        result = asyncio.run(
            world_character_setup.retry_setup(
                db,
                world_character_id="world-character-a",
                user=owner,
                data=schemas.WorldCharacterSetupRetryCreate(
                    idempotency_key="retry-repertoire-world-character-a",
                    consent_policy_version="p2-consent-v1",
                    consented=True,
                    stage="repertoire",
                ),
                provider=retry_provider,
            )
        )

        assert retry_provider.profile_calls == 0
        assert retry_provider.repertoire_calls == 1
        assert result.repertoire is not None
        assert len(result.repertoire.candidates) == 40


def test_approval_rejects_stored_candidate_signature_drift() -> None:
    engine = _engine()
    with Session(engine, expire_on_commit=False) as db:
        owner, world_character = _seed(db)
        generated = _generate(db, owner=owner, provider=FakeProvider())
        assert generated.profile is not None and generated.repertoire is not None
        candidate = db.scalar(select(models.WorldActivityCandidate))
        assert candidate is not None
        candidate.canonical_signature = "0" * 64
        db.commit()

        with pytest.raises(world_character_setup.WorldCharacterSetupConflictError) as exc:
            world_character_setup.approve_setup(
                db,
                world_character_id=world_character.id,
                user=owner,
                data=schemas.WorldCharacterSetupApproveCreate(
                    idempotency_key="approve-signature-drift",
                    profile_id=generated.profile.id,
                    repertoire_id=generated.repertoire.id,
                ),
            )

        assert exc.value.reason_code == "repertoire_signature_mismatch"
        assert world_character.autonomous_enabled is False


def test_routes_expose_preflight_generate_and_approve_without_enabling_autonomy(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    engine = _engine()
    with Session(engine, expire_on_commit=False) as db:
        owner, _world_character = _seed(db)
    principal: dict[str, models.User | None] = {"user": owner}
    app = _app(engine, principal)
    provider = FakeProvider()
    monkeypatch.setattr(
        world_character_provider,
        "DirectLlmWorldCharacterSetupProvider",
        lambda: provider,
    )

    initial = _request(
        app,
        "GET",
        "/api/v1/world-characters/world-character-a/autonomy-setup",
    )
    assert initial.status_code == 200
    assert initial.json()["state"] == "needs_profile"

    preflight = _request(
        app,
        "POST",
        "/api/v1/world-characters/world-character-a/autonomy-setup/preflight",
    )
    assert preflight.status_code == 200
    assert preflight.json()["credential_ready"] is True
    assert preflight.json()["logical_call_count"] == 2
    assert preflight.json()["physical_request_count"] == 3

    generated = _request(
        app,
        "POST",
        "/api/v1/world-characters/world-character-a/autonomy-setup/generate",
        json={
            "idempotency_key": "route-generate-world-character-a",
            "consent_policy_version": "p2-consent-v1",
            "consented": True,
        },
    )
    assert generated.status_code == 200
    assert len(generated.json()["repertoire"]["candidates"]) == 40
    assert generated.json()["autonomous_enabled"] is False

    approved = _request(
        app,
        "POST",
        "/api/v1/world-characters/world-character-a/autonomy-setup/approve",
        json={
            "idempotency_key": "route-approve-world-character-a",
            "profile_id": generated.json()["profile"]["id"],
            "repertoire_id": generated.json()["repertoire"]["id"],
        },
    )
    assert approved.status_code == 200
    assert approved.json()["autonomy_ready"] is True
    assert approved.json()["autonomous_enabled"] is False

    reentered = _request(
        app,
        "GET",
        "/api/v1/worlds/world-a/characters/character-a",
    )
    restored = _request(
        app,
        "GET",
        "/api/v1/world-characters/world-character-a/autonomy-setup",
    )
    feed_status = _request(
        app,
        "GET",
        "/api/v1/world-characters/world-character-a/feed-status",
    )

    assert reentered.status_code == 200
    assert reentered.json()["id"] == "world-character-a"
    assert reentered.json()["status"] == "active"
    assert reentered.json()["reused"] is True
    assert restored.status_code == 200
    assert restored.json()["autonomy_ready"] is True
    assert restored.json()["autonomous_enabled"] is False
    assert feed_status.status_code == 200
    assert feed_status.json()["world_character_id"] == "world-character-a"
    assert feed_status.json()["feed_runtime_mode"] == "keyword_search_v1"
    assert feed_status.json()["runtime_state"] == "autonomy_disabled"
    assert feed_status.json()["profile_keyword_count"] == 8
    assert feed_status.json()["profile_keywords_ready"] is True
    assert feed_status.json()["recent_observations"] == []


def test_routes_hide_missing_and_foreign_world_characters() -> None:
    engine = _engine()
    with Session(engine, expire_on_commit=False) as db:
        owner, _world_character = _seed(db)
        outsider = models.User(
            id="outsider",
            email="outsider@example.test",
            display_name="outsider",
            display_name_normalized="outsider",
            privacy_policy_version="test",
            terms_version="test",
            profile_setup_completed=True,
        )
        db.add(outsider)
        db.commit()
    principal: dict[str, models.User | None] = {"user": outsider}
    app = _app(engine, principal)

    forbidden = _request(
        app,
        "GET",
        "/api/v1/world-characters/world-character-a/autonomy-setup",
    )
    missing = _request(
        app,
        "GET",
        "/api/v1/world-characters/missing/autonomy-setup",
    )
    feed_forbidden = _request(
        app,
        "GET",
        "/api/v1/world-characters/world-character-a/feed-status",
    )
    feed_missing = _request(
        app,
        "GET",
        "/api/v1/world-characters/missing/feed-status",
    )

    assert forbidden.status_code == 403
    assert forbidden.json() == {"detail": "character_not_owned"}
    assert missing.status_code == 404
    assert missing.json() == {"detail": "world_character_not_found"}
    assert feed_forbidden.status_code == 403
    assert feed_forbidden.json() == {"detail": "world_character_forbidden"}
    assert feed_missing.status_code == 404
    assert feed_missing.json() == {"detail": "world_character_not_found"}


def test_feed_status_distinguishes_runtime_lane_states() -> None:
    engine = _engine()
    with Session(engine, expire_on_commit=False) as db:
        owner, world_character = _seed(db)
        world_character.status = "active"
        db.commit()
    principal: dict[str, models.User | None] = {"user": owner}
    app = _app(engine, principal)

    def status_payload() -> dict:
        response = _request(
            app,
            "GET",
            "/api/v1/world-characters/world-character-a/feed-status",
        )
        assert response.status_code == 200
        return response.json()

    assert status_payload()["runtime_state"] == "autonomy_disabled"

    with Session(engine) as db:
        stored = db.get(models.WorldCharacter, world_character.id)
        assert stored is not None
        stored.feed_runtime_mode = "legacy_latest_v1"
        db.commit()
    assert status_payload()["runtime_state"] == "routine_only_legacy_feed"

    with Session(engine) as db:
        stored = db.get(models.WorldCharacter, world_character.id)
        assert stored is not None
        stored.feed_runtime_mode = "keyword_search_v1"
        stored.autonomous_enabled = True
        db.add(
            models.WorldCharacterFeedCursor(
                world_character_id=stored.id,
                world_id=stored.world_id,
                next_keyword_offset=0,
                last_cycle_key="cycle-degraded",
                last_run_id="run-degraded",
                last_cycle_summary={"reason_code": "search_unavailable"},
                version=1,
            )
        )
        db.commit()
    assert status_payload()["runtime_state"] == "feed_search_degraded"

    with Session(engine) as db:
        cursor = db.get(models.WorldCharacterFeedCursor, world_character.id)
        assert cursor is not None
        cursor.last_cycle_summary = {"reason_code": "no_candidate"}
        db.commit()
    assert status_payload()["runtime_state"] == "three_lane_ready"


def test_world_entry_creates_pending_world_character_without_provider_or_autonomy() -> None:
    engine = _engine()
    with Session(engine, expire_on_commit=False) as db:
        owner, _world_character = _seed(db)
        db.add(
            models.Character(
                id="character-b",
                owner_id=owner.id,
                name="Nia",
                handle="nia",
                one_liner="A new academy visitor",
                personality="Cheerful and methodical.",
                speech_style="Bright and concise.",
                worldview="New places are learned through observation.",
                topic_preferences="Maps and plants",
                safety_rules="Ask before entering restricted rooms.",
                persona_summary="A visiting student exploring Arcana Academy.",
                moderation_status="active",
            )
        )
        db.commit()
    principal: dict[str, models.User | None] = {"user": owner}
    app = _app(engine, principal)

    missing_entry = _request(
        app,
        "GET",
        "/api/v1/worlds/world-a/characters/character-b",
    )

    entered = _request(
        app,
        "POST",
        "/api/v1/worlds/world-a/characters",
        json={
            "character_id": "character-b",
            "role_key": "student",
            "local_background": "A first-day exchange student",
            "idempotency_key": "enter-character-b-world-a",
        },
    )
    replayed = _request(
        app,
        "POST",
        "/api/v1/worlds/world-a/characters",
        json={
            "character_id": "character-b",
            "role_key": "student",
            "local_background": "A first-day exchange student",
            "idempotency_key": "enter-character-b-world-a",
        },
    )

    assert missing_entry.status_code == 404
    assert missing_entry.json() == {"detail": "world_character_not_found"}
    assert entered.status_code == 201
    assert entered.json()["status"] == "pending"
    assert entered.json()["autonomous_enabled"] is False
    assert entered.json()["reused"] is False
    assert replayed.status_code == 201
    assert replayed.json()["id"] == entered.json()["id"]
    assert replayed.json()["reused"] is True
    with Session(engine) as db:
        stored = db.get(models.WorldCharacter, entered.json()["id"])
        assert stored is not None
        assert stored.control_mode == "autonomous"
        assert stored.owner_user_id is None
        assert stored.activity_runtime_mode == "routine_resident_v1"
        assert stored.feed_runtime_mode == "keyword_search_v1"
        assert stored.local_profile == {
            "entry_idempotency_key": "enter-character-b-world-a",
            "background": "A first-day exchange student",
        }
        assert db.scalar(select(models.WorldCharacterSetupAttempt)) is None
        assert db.scalar(select(func.count(models.AgentRun.id))) == 0
        assert db.scalar(select(func.count(models.Post.id))) == 0
        assert db.scalar(select(func.count(models.SocialEvent.id))) == 0
        assert db.scalar(select(func.count(models.RelationshipStateChange.id))) == 0
        assert db.scalar(select(func.count(models.GraphProjectionOutbox.id))) == 0


def test_world_entry_requires_explicit_no_specific_role_selection() -> None:
    engine = _engine()
    with Session(engine, expire_on_commit=False) as db:
        owner, _world_character = _seed(db)
        role = db.get(models.WorldRole, "role-a")
        assert role is not None
        role.status = "disabled"
        db.add(
            models.Character(
                id="character-no-role",
                owner_id=owner.id,
                name="Miro",
                handle="miro",
                one_liner="A traveler without a fixed academy role",
                personality="Curious and considerate.",
                speech_style="Calm and observant.",
                worldview="A place is understood by living alongside its people.",
                topic_preferences="Daily rituals and local stories",
                safety_rules="Respect local boundaries.",
                persona_summary="A traveler beginning ordinary life in Arcana Academy.",
                moderation_status="active",
            )
        )
        db.commit()
    principal: dict[str, models.User | None] = {"user": owner}
    app = _app(engine, principal)

    missing_role = _request(
        app,
        "POST",
        "/api/v1/worlds/world-a/characters",
        json={
            "character_id": "character-no-role",
            "role_key": None,
            "local_background": "A visitor learning the academy's everyday customs",
            "idempotency_key": "enter-character-no-role-world-a",
        },
    )

    assert missing_role.status_code == 422
    assert missing_role.json() == {"detail": "role_required"}

    entered = _request(
        app,
        "POST",
        "/api/v1/worlds/world-a/characters",
        json={
            "character_id": "character-no-role",
            "role_key": NO_SPECIFIC_ROLE_KEY,
            "local_background": "A visitor learning the academy's everyday customs",
            "idempotency_key": "enter-character-no-role-world-a-explicit",
        },
    )

    assert entered.status_code == 201
    assert entered.json()["role_key"] == NO_SPECIFIC_ROLE_KEY
    assert entered.json()["status"] == "pending"
    assert entered.json()["autonomous_enabled"] is False
    with Session(engine) as db:
        stored = db.get(models.WorldCharacter, entered.json()["id"])
        reserved = db.scalar(
            select(models.WorldRole).where(
                models.WorldRole.world_id == "world-a",
                models.WorldRole.role_key == NO_SPECIFIC_ROLE_KEY,
            )
        )
        assert stored is not None
        assert stored.activity_runtime_mode == "routine_resident_v1"
        assert stored.feed_runtime_mode == "keyword_search_v1"
        assert reserved is not None
        assert reserved.name == NO_SPECIFIC_ROLE_NAME
        assert reserved.description == NO_SPECIFIC_ROLE_DESCRIPTION
        assert reserved.autonomous_allowed is True
        assert reserved.status == "enabled"


def test_v2_to_v3_normalizes_existing_autonomous_null_role_idempotently() -> None:
    engine = _engine()
    with Session(engine, expire_on_commit=False) as db:
        owner, world_character = _seed(db)
        original_owner_id = owner.id
        original_character_id = world_character.character_id
        original_world_id = world_character.world_id
        world_character.role_key = None
        db.commit()

    with engine.begin() as connection:
        upgrade_v2_to_v3(connection)
    with engine.begin() as connection:
        upgrade_v2_to_v3(connection)

    with Session(engine) as db:
        migrated = db.get(models.WorldCharacter, "world-character-a")
        assert migrated is not None
        assert migrated.world_id == original_world_id
        assert migrated.character_id == original_character_id
        assert migrated.role_key == NO_SPECIFIC_ROLE_KEY
        assert db.get(models.User, original_owner_id) is not None
        assert db.get(models.Character, original_character_id) is not None
        reserved = db.scalar(
            select(models.WorldRole).where(
                models.WorldRole.world_id == original_world_id,
                models.WorldRole.role_key == NO_SPECIFIC_ROLE_KEY,
            )
        )
        assert reserved is not None
        assert reserved.name == NO_SPECIFIC_ROLE_NAME
        assert db.scalar(
            select(func.count())
            .select_from(models.WorldRole)
            .where(
                models.WorldRole.world_id == original_world_id,
                models.WorldRole.role_key == NO_SPECIFIC_ROLE_KEY,
            )
        ) == 1


def test_existing_world_character_role_can_be_changed_to_explicit_no_role() -> None:
    engine = _engine()
    with Session(engine, expire_on_commit=False) as db:
        owner, world_character = _seed(db)
        initial_version = world_character.version
    principal: dict[str, models.User | None] = {"user": owner}
    app = _app(engine, principal)

    changed = _request(
        app,
        "PATCH",
        "/api/v1/worlds/world-a/characters/character-a/role",
        json={
            "role_key": NO_SPECIFIC_ROLE_KEY,
            "version": initial_version,
        },
    )

    assert changed.status_code == 200
    assert changed.json()["role_key"] == NO_SPECIFIC_ROLE_KEY
    assert changed.json()["version"] == initial_version + 1
    stale = _request(
        app,
        "PATCH",
        "/api/v1/worlds/world-a/characters/character-a/role",
        json={"role_key": "student", "version": initial_version},
    )
    assert stale.status_code == 409
    assert stale.json() == {"detail": "row_version_conflict"}
