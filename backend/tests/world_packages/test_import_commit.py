from __future__ import annotations

import asyncio
from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime, timedelta
import hashlib
from io import BytesIO
import json
from pathlib import Path
from types import SimpleNamespace

from fastapi import FastAPI
from fastapi.testclient import TestClient
from PIL import Image
import pytest
from sqlalchemy import create_engine, event, func, select
from sqlalchemy.orm import Session, sessionmaker

from app import models, schemas
from app.domains.identity.dependencies import get_current_user
from app.core import security
from app.core.db import Base, get_db
from app.core.search_text import build_post_search_document
from app.domains.device_home.repository import (
    SqlAlchemyWorldSurfaceRepository,
)
from app.domains.runtime.public import SearchIndexHit
from app.domains.social.public import SocialSearchState
from app.domains.world_packages.router import router
from app.domains.world_packages.schemas.content import (
    AssetIndexDocument,
    CharactersDocument,
    ManagedImageAsset,
    PortableWorldDefinition,
    WorldCharactersDocument,
)
from app.domains.world_packages.exceptions import (
    WorldPackageContractError,
    WorldPackageReasonCode,
)
from app.domains.world_packages.contracts.export import (
    WorldPackageResolvedAsset,
    WorldPackageResolvedAssets,
    WorldPackageSourceIdentity,
)
from app.domains.world_packages.schemas.manifest import WorldPackageLicense
from app.domains.world_packages.contracts.preview import (
    WorldPackageNormalizedAsset,
    WorldPackageNormalizedAssetPayload,
)
from app.domains.world_packages.storage.import_media import (
    FilesystemWorldPackageImportMedia,
)
from app.runtime.world_packages.import_commit import (
    SqlAlchemyWorldPackageImportCommitter,
)
from app.runtime.world_packages.seed import (
    SqlAlchemyWorldPackageDestinationSeed,
)
from app.domains.world_packages.archive.export import (
    DeterministicWorldPackageZipArchive,
)
from app.runtime.routine_posts.sqlalchemy_runtime import run_routine_post_runtime
from app.runtime.relationships import (
    sqlalchemy_social_event as social_event_runtime,
)
from app.runtime.search import CallbackSearchIndexAdapter
from app.domains.routines.contracts import activity_policy as agent_activity_policy
from app.runtime.characters import management as agent_service
from app.services import langgraph_resident
from app.services import (
    world_character_contracts,
    world_character_provider,
)
from app.domains.world_characters.service import autonomous_setup as world_character_setup
from app.runtime.resident.context import LangGraphResidentContext
from app.services.world_feed_runtime import run_world_keyword_feed


FIXTURE_ROOT = (
    Path(__file__).parents[1] / "fixtures" / "world_packages" / "v1" / "valid"
)
FRONTEND_HEADERS = {"Origin": "http://127.0.0.1:3000"}
OWNER_ID = "package-import-owner"
DAYPARTS = ("dawn", "morning", "afternoon", "evening")
IMPORTED_ACTIVITIES = (
    "catalog lantern supplies",
    "map tide markings",
    "practice welcome signals",
    "repair an old compass",
    "compare market aromas",
    "translate a traveler note",
    "organize harbor records",
    "sketch medicinal sea herbs",
    "review dock etiquette",
    "prepare lighthouse notes",
)
IMPORTED_OUTCOMES = (
    "produce a labeled supply drawer for the next guide shift",
    "leave a verified tide card beside the central pier notice board",
    "complete a safe signal diagram with three corrected lantern points",
    "restore the compass so tomorrow's ferry crew can use it",
    "write a sensory comparison table without tasting unknown goods",
    "prepare a glossary note that residents can review at the market",
    "find one missing patrol interval and update the shared harbor ledger",
    "identify two useful leaves and mark their drying schedule",
    "summarize a respectful greeting and farewell sequence for visitors",
    "assemble a concise weather log for the harbor archive",
)


class _DeterministicImportedSetupProvider:
    """Exercise the production setup path without an external provider call."""

    async def generate_community_profile(self, **_kwargs):
        return world_character_provider.WorldCharacterProviderResult(
            payload={
                "visible_summary": "A welcoming guide who notices small harbor changes.",
                "core_interests": ["harbor", "weather", "neighbors"],
                "adjacent_interests": ["lanterns", "travelers"],
                "avoid_topics": ["private memories"],
                "discovery_openness": 70,
                "search_keywords": [
                    "harbor",
                    "weather",
                    "lantern",
                    "pier",
                    "travelers",
                    "neighbors",
                    "market",
                    "evening news",
                ],
                "action_profile": {
                    key: {"weight": 50, "note": f"Use {key} when appropriate."}
                    for key in schemas.WORLD_COMMUNITY_ACTION_KEYS
                },
            },
            physical_request_count=1,
            prompt_token_count=100,
            output_token_count=50,
            total_token_count=150,
            latency_ms=25,
        )

    async def generate_repertoire(self, *, validator, **_kwargs):
        kinds = (
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
        )
        candidates = []
        for daypart in DAYPARTS:
            for index, (kind, activity, outcome) in enumerate(
                zip(kinds, IMPORTED_ACTIVITIES, IMPORTED_OUTCOMES, strict=True),
                start=1,
            ):
                candidates.append(
                    {
                        "daypart": daypart,
                        "activity_kind": kind,
                        "title": f"{daypart} {activity}",
                        "activity_seed": (
                            f"During {daypart}, Mango will {activity}, then {outcome}. "
                            f"This is distinct harbor scenario {daypart}-{index}."
                        ),
                        "place_key": None,
                        "social_mode": "open_to_interaction",
                    }
                )
        validated = validator({"candidates": candidates})
        return world_character_provider.WorldCharacterProviderResult(
            payload=validated,
            physical_request_count=2,
            prompt_token_count=200,
            output_token_count=500,
            total_token_count=700,
            latency_ms=50,
        )


class _DeterministicNoActionFeedProvider:
    """Keep P5-P7 on production code without making an external LLM call."""

    def __init__(self) -> None:
        self.plan_calls = 0

    async def plan(self, **_kwargs) -> schemas.FeedReactionDecision:
        self.plan_calls += 1
        return schemas.FeedReactionDecision(
            selected_candidate_index=None,
            selected_action=None,
            interaction_intent=None,
            comment_purpose=None,
            reason_code="model_abstained",
            brief=None,
        )


def _fixture(relative: str) -> dict:
    return json.loads((FIXTURE_ROOT / relative).read_text(encoding="utf-8"))


def _archive(*, with_image: bool = False, no_specific_role: bool = False) -> bytes:
    world_payload = _fixture("content/world.json")
    world_characters_payload = _fixture("content/world-characters.json")
    if no_specific_role:
        world_payload["roles"].append(
            {
                "allowed_activity_scope": [],
                "autonomous_allowed": True,
                "description": "별도의 World 역할을 지정하지 않은 캐릭터",
                "name": "역할 없음",
                "ref": "roles/no-specific-role",
                "responsibilities": [],
            }
        )
        world_characters_payload["characters"][0]["role_ref"] = (
            "roles/no-specific-role"
        )
    world = PortableWorldDefinition.model_validate(world_payload)
    world = world.model_copy(
        update={
            "setting_description": (
                "달빛과 비늘등이 물결에 비치는 항구에서 주민들은 "
                "푸른 부두와 시장을 오가며 서로의 소식을 나눕니다. "
            )
            * 5,
            "daily_life_description": (
                "아침에는 상인들이 물건을 정리하고 안내인은 방문객의 "
                "질문에 답하며, 저녁에는 비늘등을 밝히고 하루의 작은 "
                "사건과 관계의 변화를 함께 돌아봅니다. "
            )
            * 5,
        }
    )
    characters = CharactersDocument.model_validate(
        _fixture("content/characters.json")
    )
    world_characters = WorldCharactersDocument.model_validate(
        world_characters_payload
    )
    assets = AssetIndexDocument(schema_version="assets-index-v1", assets=[])
    resolved = WorldPackageResolvedAssets(assets=())
    if with_image:
        source = Image.new("RGB", (12, 8), (12, 34, 56))
        exif = Image.Exif()
        exif[0x010E] = "private metadata must be stripped"
        stream = BytesIO()
        source.save(stream, format="WEBP", lossless=True, exif=exif)
        content = stream.getvalue()
        digest = hashlib.sha256(content).hexdigest()
        reference = f"assets/sha256-{digest}.webp"
        asset = ManagedImageAsset(
            ref=reference,
            sha256=digest,
            bytes=len(content),
            media_type="image/webp",
            width=12,
            height=8,
            alt_text="fixture banner",
        )
        world = world.model_copy(update={"banner_asset_ref": reference})
        assets = AssetIndexDocument(
            schema_version="assets-index-v1",
            assets=[asset],
        )
        resolved = WorldPackageResolvedAssets(
            assets=(
                WorldPackageResolvedAsset(
                    candidate_key="world:banner",
                    asset=asset,
                    content=content,
                ),
            )
        )
    return DeterministicWorldPackageZipArchive().build(
        identity=WorldPackageSourceIdentity(
            package_id="019ff9d5-559d-7452-b0f5-68f4964a2d46",
            next_version=1,
            created_at=datetime(2026, 8, 25, tzinfo=UTC),
        ),
        package_version=1,
        world=world,
        characters=characters,
        world_characters=world_characters,
        asset_index=assets,
        resolved_assets=resolved,
        license=WorldPackageLicense(
            expression="CC-BY-4.0",
            attribution="fixture creator",
        ),
        license_text=None,
    ).content


@pytest.fixture
def import_runtime(tmp_path: Path):
    engine = create_engine(
        f"sqlite:///{tmp_path / 'package-import.sqlite3'}",
        connect_args={"check_same_thread": False},
    )

    @event.listens_for(engine, "connect")
    def _sqlite_contract(dbapi_connection, _connection_record) -> None:
        dbapi_connection.execute("PRAGMA foreign_keys=ON")
        dbapi_connection.execute("PRAGMA busy_timeout=5000")
        dbapi_connection.execute("PRAGMA journal_mode=WAL")

    Base.metadata.create_all(engine)
    factory = sessionmaker(bind=engine, expire_on_commit=False)
    owner = models.User(
        id=OWNER_ID,
        email="package-import-owner@example.test",
        display_name="Package Import Owner",
        display_name_normalized="package import owner",
        privacy_policy_version="test",
        terms_version="test",
        profile_setup_completed=True,
    )
    with factory() as db:
        db.add(owner)
        db.commit()

    media_root = tmp_path / "media"
    runtime_root = tmp_path / "runtime"
    media_root.mkdir()
    runtime_root.mkdir()
    media = FilesystemWorldPackageImportMedia(
        media_root=media_root,
        runtime_root=runtime_root,
        media_url_path="/media",
    )
    committer = SqlAlchemyWorldPackageImportCommitter(
        factory,
        media=media,
    )
    app = FastAPI()
    from app.runtime.world_packages.composition import configure_world_package_runtime
    configure_world_package_runtime(app)
    app.include_router(router, prefix="/api/v1")
    app.state.runtime_settings = SimpleNamespace(
        media_root_path=media_root,
        media_url_path="/media",
    )
    app.state.runtime_config = None
    app.state.runtime_composition = None
    app.state.world_package_import_committer = committer

    def db_dependency():
        with factory() as db:
            yield db

    app.dependency_overrides[get_db] = db_dependency
    app.dependency_overrides[get_current_user] = lambda: owner
    client = TestClient(app, base_url="http://127.0.0.1:3000")
    yield SimpleNamespace(
        app=app,
        client=client,
        committer=committer,
        engine=engine,
        factory=factory,
        media=media,
        media_root=media_root,
        runtime_root=runtime_root,
    )
    engine.dispose()


def _stage(client: TestClient, content: bytes) -> dict:
    response = client.post(
        "/api/v1/world-package-imports/stage",
        headers=FRONTEND_HEADERS,
        files={
            "package": (
                "world.angmoo-world",
                content,
                "application/vnd.angmoo.world+zip",
            )
        },
    )
    assert response.status_code == 201, response.text
    return response.json()


def _commit(
    client: TestClient,
    prepared: dict,
    *,
    idempotency_key: str,
    strategy: str = "reject",
    digest: str | None = None,
):
    preview = prepared["preview"]
    return client.post(
        f"/api/v1/world-package-imports/{preview['operation_id']}/commit",
        headers={
            **FRONTEND_HEADERS,
            "X-World-Package-Preview-Token": prepared["preview_token"],
            "Idempotency-Key": idempotency_key,
        },
        json={
            "expected_content_digest": digest or preview["content_digest"],
            "duplicate_strategy": strategy,
        },
    )


def _count(db: Session, model) -> int:
    return int(db.scalar(select(func.count()).select_from(model)) or 0)


def _database_digest(engine) -> str:
    with engine.connect() as connection:
        dbapi_connection = connection.connection.driver_connection
        payload = "\n".join(dbapi_connection.iterdump()).encode("utf-8")
    return hashlib.sha256(payload).hexdigest()


def _runtime_rows_are_zero(db: Session) -> None:
    for model in (
        models.CharacterState,
        models.CharacterActiveWorld,
        models.LlmCredential,
        models.AgentActivitySetting,
        models.AgentImageGenerationSetting,
        models.WorldActivityCandidate,
        models.WorldActivityRepertoire,
        models.WorldCharacterSetupAttempt,
        models.WorldCommunityProfile,
        models.DailyActivityPlan,
        models.DailyActivityPlanItem,
        models.Post,
        models.Comment,
        models.SocialEvent,
        models.SocialEventEvidence,
        models.RelationshipState,
        models.RelationshipStateChange,
        models.GraphProjectionOutbox,
    ):
        assert _count(db, model) == 0, model.__name__


def _seed_owner_social_source(
    db: Session,
    *,
    world: models.World,
    suffix: str,
    occurred_at: datetime,
) -> tuple[models.WorldCharacter, models.Post, models.SocialEvent]:
    """Create a canonical owner post that a resident may later observe."""

    owner = models.User(
        id=f"package-parity-source-owner-{suffix}",
        email=f"package-parity-source-{suffix}@example.test",
        display_name=f"Package parity source {suffix}",
        display_name_normalized=f"package parity source {suffix}",
        privacy_policy_version="test",
        terms_version="test",
        profile_setup_completed=True,
    )
    character = models.Character(
        id=f"package-parity-source-character-{suffix}",
        owner_id=owner.id,
        name=f"Harbor reporter {suffix}",
        handle=f"harbor-reporter-{suffix}",
        one_liner="Records small changes around the harbor.",
        personality="Observant and considerate.",
        speech_style="Friendly and concise.",
        worldview="Shared observations help a community understand itself.",
        topic_preferences="Harbor weather and neighbors.",
        safety_rules="Do not invent private memories.",
        persona_summary="A resident who writes public harbor reports.",
        moderation_status="active",
    )
    db.add_all([owner, character])
    db.flush()
    membership = models.WorldMembership(
        id=f"package-parity-source-membership-{suffix}",
        world_id=world.id,
        user_id=owner.id,
        role="member",
        status="active",
        joined_at=occurred_at,
    )
    db.add(membership)
    db.flush()
    world_character = models.WorldCharacter(
        id=f"package-parity-source-world-character-{suffix}",
        world_id=world.id,
        character_id=character.id,
        membership_id=membership.id,
        role_key=None,
        status="active",
        control_mode="owner_controlled",
        owner_user_id=owner.id,
        autonomous_enabled=False,
        activity_runtime_mode="legacy_resident_v1",
        feed_runtime_mode="legacy_latest_v1",
        character_contract_hash=(
            world_character_contracts.character_contract_hash(character)
        ),
        world_contract_hash=world.contract_hash,
    )
    db.add(world_character)
    db.flush()
    title = "Harbor weather log"
    body = "The harbor weather cleared while neighbors relit the pier lanterns."
    topic_signature = "harbor weather neighbors lantern"
    post = models.Post(
        id=f"package-parity-source-post-{suffix}",
        author_user_id=owner.id,
        author_character_id=character.id,
        world_id=world.id,
        author_world_character_id=world_character.id,
        author_name=character.name,
        title=title,
        body=body,
        topic_signature=topic_signature,
        visibility="public",
        search_document=build_post_search_document(
            title=title,
            body=body,
            topic_signature=topic_signature,
        ),
        created_at=occurred_at,
    )
    db.add(post)
    db.flush()
    source_event = social_event_runtime.record_successful_social_event(
        db,
        world_id=world.id,
        actor_world_character_id=world_character.id,
        target_world_character_id=None,
        event_type="post_published",
        occurred_at=occurred_at,
        idempotency_key=f"package-parity-source-event-{suffix}",
        evidence=social_event_runtime.EvidenceInput(
            evidence_kind="post",
            source_object_type="post",
            source_object_id=post.id,
            root_post_id=post.id,
            source_post_id=post.id,
            source_text=post.body,
            source_visibility_at_event="public",
            source_author_id_at_event=world_character.id,
        ),
    ).event
    db.commit()
    return world_character, post, source_event


def _parity_search_adapter(db: Session) -> CallbackSearchIndexAdapter:
    def search(
        world_id: str,
        query: str,
        limit: int,
    ) -> tuple[SearchIndexHit, ...]:
        normalized = query.casefold()
        posts = db.scalars(
            select(models.Post).where(models.Post.world_id == world_id)
        ).all()
        return tuple(
            SearchIndexHit(
                document_id=post.id,
                score=1.0,
                world_id=post.world_id,
                kind="world_post",
            )
            for post in posts
            if normalized in post.search_document.casefold()
        )[:limit]

    return CallbackSearchIndexAdapter(
        upsert=lambda _document: None,
        remove=lambda _document_id: None,
        search=search,
    )


def _feed_context(
    db: Session,
    *,
    owner: models.User,
    character: models.Character,
    credential: models.LlmCredential,
    run_id: str,
    occurred_at: datetime,
) -> LangGraphResidentContext:
    return LangGraphResidentContext(
        db=db,
        run_id=run_id,
        user_id=owner.id,
        agent_id=f"agent-{run_id}",
        session_key=f"agent:{run_id}:resident-scheduled",
        character=character,
        credential=credential,
        state=None,
        activity_policy=agent_activity_policy.ActivityPolicy(
            within_active_hours=True,
            allowed_actions=(
                "post",
                "reply",
                "like",
                "repost",
                "follow",
                "observe",
            ),
            blocked_reasons={},
            next_tick_at=occurred_at + timedelta(hours=1),
            summary="deterministic imported/direct P5-P7 parity",
        ),
        selected_post_id=None,
        run_started_at=occurred_at,
        run_mode="scheduled",
        social_search_index=_parity_search_adapter(db),
        social_search_state=SocialSearchState.READY,
    )


def _world_feed_runtime_snapshot(
    db: Session,
    *,
    world: models.World,
    observer_world_character: models.WorldCharacter,
    source_world_character: models.WorldCharacter,
    source_post: models.Post,
    source_event: models.SocialEvent,
) -> tuple[dict[str, object], frozenset[str]]:
    cursor = db.scalar(
        select(models.WorldCharacterFeedCursor).where(
            models.WorldCharacterFeedCursor.world_id == world.id
        )
    )
    observation = db.scalar(
        select(models.WorldCharacterFeedObservation).where(
            models.WorldCharacterFeedObservation.world_id == world.id
        )
    )
    events = list(
        db.scalars(
            select(models.SocialEvent).where(models.SocialEvent.world_id == world.id)
        )
    )
    evidence = list(
        db.scalars(
            select(models.SocialEventEvidence).where(
                models.SocialEventEvidence.social_event_id == source_event.id
            )
        )
    )
    relationships = list(
        db.scalars(
            select(models.RelationshipState).where(
                models.RelationshipState.world_id == world.id
            )
        )
    )
    changes = list(
        db.scalars(
            select(models.RelationshipStateChange).where(
                models.RelationshipStateChange.world_id == world.id
            )
        )
    )
    outbox = list(
        db.scalars(
            select(models.GraphProjectionOutbox).where(
                models.GraphProjectionOutbox.world_id == world.id
            )
        )
    )
    assert cursor is not None and observation is not None
    assert events == [source_event]
    assert len(evidence) == len(relationships) == len(changes) == 1
    assert len(outbox) == 2
    relationship = relationships[0]
    change = changes[0]
    event_evidence = evidence[0]
    assert cursor.world_character_id == observer_world_character.id
    assert observation.observer_world_character_id == observer_world_character.id
    assert observation.post_id == source_post.id
    assert source_event.actor_world_character_id == source_world_character.id
    assert event_evidence.source_post_id == source_post.id
    assert relationship.actor_world_character_id == observer_world_character.id
    assert relationship.target_world_character_id == source_world_character.id
    assert change.social_event_id == source_event.id
    assert change.relationship_state_id == relationship.id
    assert all(row.source_event_id == source_event.id for row in outbox)
    assert all(row.payload["world_id"] == world.id for row in outbox)

    def participant(value: str | None) -> str | None:
        if value == observer_world_character.id:
            return "observer"
        if value == source_world_character.id:
            return "source"
        return value

    snapshot = {
        "cursor": (cursor.next_keyword_offset, cursor.version),
        "observation": (
            observation.status,
            observation.decision_outcome,
            observation.reason_code,
            observation.selected_action,
            tuple(observation.matched_keywords),
        ),
        "event": (
            source_event.event_type,
            source_event.result,
            source_event.retrieval_status,
        ),
        "evidence": (
            event_evidence.evidence_kind,
            event_evidence.source_object_type,
            event_evidence.source_visibility_at_event,
        ),
        "relationship": (
            relationship.familiarity,
            relationship.affinity,
            relationship.trust,
            relationship.tension,
            relationship.interaction_count,
            relationship.version,
        ),
        "change": (
            change.delta_familiarity,
            change.delta_affinity,
            change.delta_trust,
            change.delta_tension,
            change.applied,
            change.not_applied_reason,
        ),
        "outbox": tuple(
            sorted(
                (
                    row.projection_type,
                    row.payload_version,
                    participant(row.payload["actor_world_character_id"]),
                    participant(row.payload["target_world_character_id"]),
                    row.status,
                )
                for row in outbox
            )
        ),
    }
    ids = frozenset(
        {
            world.id,
            observer_world_character.id,
            source_world_character.id,
            source_post.id,
            source_event.id,
            observation.id,
            relationship.id,
            change.id,
            *(row.id for row in outbox),
        }
    )
    return snapshot, ids


def test_commit_is_atomic_registers_one_home_world_and_replays_without_writes(
    import_runtime,
) -> None:
    prepared = _stage(import_runtime.client, _archive(with_image=True))
    with import_runtime.factory() as db:
        owner_before = (
            db.get(models.User, OWNER_ID).display_name,
            db.get(models.User, OWNER_ID).email,
        )

    first = _commit(
        import_runtime.client,
        prepared,
        idempotency_key="package-import-success",
    )
    assert first.status_code == 201, first.text
    result = first.json()
    assert result["replayed"] is False
    assert result["device_home_world_id"] == result["imported_world_id"]

    with import_runtime.factory() as db:
        assert _count(db, models.World) == 1
        assert _count(db, models.WorldMembership) == 1
        assert _count(db, models.Character) == 1
        assert _count(db, models.WorldCharacter) == 1
        assert _count(db, models.WorldPackageImport) == 1
        assert _count(db, models.WorldPackageImportIdMap) == 4
        membership = db.scalar(select(models.WorldMembership))
        assert membership is not None and membership.role == "owner"
        owner = db.get(models.User, OWNER_ID)
        character = db.scalar(select(models.Character))
        world_character = db.scalar(select(models.WorldCharacter))
        assert owner is not None
        assert character is not None and character.owner_id == OWNER_ID
        assert world_character is not None
        assert world_character.control_mode == "autonomous"
        assert world_character.owner_user_id is None
        assert world_character.autonomous_enabled is False
        with pytest.raises(
            agent_service.AgentExecutionModeError,
            match="자율활동을 먼저 켠 뒤",
        ):
            asyncio.run(agent_service.run_agent_now(db, owner, character.id))
        _runtime_rows_are_zero(db)
        home = SqlAlchemyWorldSurfaceRepository(db).list_worlds(
            owner_user_id=OWNER_ID,
            surface="device_home",
            limit=20,
            cursor=None,
        )
        assert [item.world_id for item in home.items] == [
            result["imported_world_id"]
        ]
        owner_after = (
            db.get(models.User, OWNER_ID).display_name,
            db.get(models.User, OWNER_ID).email,
        )
        assert owner_after == owner_before

    final_root = (
        import_runtime.media_root
        / "world-package-imports"
        / result["import_id"]
    )
    imported_files = tuple(final_root.glob("sha256-*.webp"))
    assert len(imported_files) == 1
    with Image.open(imported_files[0]) as image:
        assert image.format == "WEBP"
        assert not image.getexif()

    replay = _commit(
        import_runtime.client,
        prepared,
        idempotency_key="package-import-success",
    )
    assert replay.status_code == 201, replay.text
    assert replay.json() == {**result, "replayed": True}
    with import_runtime.factory() as db:
        assert _count(db, models.World) == 1
        assert _count(db, models.WorldPackageImport) == 1
        assert _count(db, models.WorldPackageImportIdMap) == 4


def test_commit_maps_portable_no_role_to_canonical_reserved_role(
    import_runtime,
) -> None:
    prepared = _stage(
        import_runtime.client,
        _archive(no_specific_role=True),
    )
    committed = _commit(
        import_runtime.client,
        prepared,
        idempotency_key="package-import-no-specific-role",
    )
    assert committed.status_code == 201, committed.text

    with import_runtime.factory() as db:
        world_character = db.scalar(select(models.WorldCharacter))
        reserved = db.scalar(
            select(models.WorldRole).where(
                models.WorldRole.role_key == "no_specific_role"
            )
        )
        assert world_character is not None
        assert world_character.role_key == "no_specific_role"
        assert reserved is not None
        assert reserved.name == "역할 없음"
        assert reserved.description == "별도의 World 역할을 지정하지 않은 캐릭터"
        assert reserved.responsibilities == []
        assert reserved.allowed_activity_scope == []
        assert reserved.autonomous_allowed is True


def test_imported_world_is_inert_until_enable_then_matches_direct_p5_p7_runtime(
    import_runtime,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Imported actors stay inert, then use the same World-scoped social UoW."""

    prepared = _stage(import_runtime.client, _archive(no_specific_role=True))
    committed = _commit(
        import_runtime.client,
        prepared,
        idempotency_key="package-import-setup-lifecycle",
    )
    assert committed.status_code == 201, committed.text
    imported_world_id = committed.json()["imported_world_id"]

    with import_runtime.factory() as db:
        owner = db.get(models.User, OWNER_ID)
        world_character = db.scalar(
            select(models.WorldCharacter).where(
                models.WorldCharacter.world_id == imported_world_id
            )
        )
        assert owner is not None and world_character is not None
        character = db.get(models.Character, world_character.character_id)
        assert character is not None
        assert world_character.status == "pending"
        assert world_character.autonomous_enabled is False
        _runtime_rows_are_zero(db)

        db.add(
            models.LlmCredential(
                id="package-import-setup-credential",
                owner_id=owner.id,
                character_id=character.id,
                provider="google",
                purpose="agent",
                model="gemini-3.1-flash-lite",
                auth_profile_id="package-import-setup-profile",
                label="deterministic fixture key",
                encrypted_api_key=security.encrypt_secret(
                    "synthetic-package-import-api-key",
                    scope=security.SecretScope(
                        owner_id=owner.id,
                        character_id=character.id,
                        provider="google",
                        purpose="agent",
                    ),
                ),
                enabled=True,
            )
        )
        db.commit()

        generated = asyncio.run(
            world_character_setup.generate_setup(
                db,
                world_character_id=world_character.id,
                user=owner,
                data=schemas.WorldCharacterSetupGenerateCreate(
                    idempotency_key="generate-imported-world-character",
                    consent_policy_version="p2-consent-v1",
                    consented=True,
                ),
                provider=_DeterministicImportedSetupProvider(),
            )
        )
        assert generated.state == "ready"
        assert generated.profile is not None
        assert generated.repertoire is not None
        assert len(generated.repertoire.candidates) == 40

        approved = world_character_setup.approve_setup(
            db,
            world_character_id=world_character.id,
            user=owner,
            data=schemas.WorldCharacterSetupApproveCreate(
                idempotency_key="approve-imported-world-character",
                profile_id=generated.profile.id,
                repertoire_id=generated.repertoire.id,
            ),
        )
        assert approved.autonomy_ready is True
        assert approved.autonomous_enabled is False
        assert world_character.status == "active"
        assert world_character.role_key == "no_specific_role"
        active_world = db.get(models.CharacterActiveWorld, character.id)
        assert active_world is not None
        assert active_world.world_character_id == world_character.id

        runner_calls = 0
        runner_allowed = False

        async def guarded_runner(*_args, **_kwargs):
            nonlocal runner_calls
            runner_calls += 1
            if not runner_allowed:
                raise AssertionError("imported World ran before explicit autonomy enable")
            return schemas.OpenClawAgentRunRead(
                run_id="imported-world-enabled-run",
                status="completed",
                summary="enabled runtime entered",
                agent_id="angmoo-1",
                session_key="agent:angmoo-1:resident-manual:imported-enabled",
                character_id=character.id,
                post_id=None,
                gateway_result={"status": "completed"},
            )

        monkeypatch.setattr(
            agent_service.agent_run_service,
            "run_claimed_temporary_resident_slot_once",
            guarded_runner,
        )
        with pytest.raises(
            agent_service.AgentExecutionModeError,
            match="자율활동을 먼저 켠 뒤",
        ):
            asyncio.run(agent_service.run_agent_now(db, owner, character.id))
        with pytest.raises(agent_service.AgentExecutionModeError):
            agent_service.give_feed_cue(
                db,
                owner,
                character.id,
                schemas.AgentFeedCueCreate(
                    topic="가져온 World의 다음 활동",
                    manual_run=True,
                ),
            )
        with pytest.raises(agent_service.AgentExecutionModeError):
            asyncio.run(
                agent_service.run_first_greeting(
                    db,
                    owner,
                    character.id,
                    schemas.AgentFirstGreetingCreate(topic="가져온 World 첫인사"),
                )
            )
        with pytest.raises(agent_service.AgentExecutionModeError):
            asyncio.run(agent_service.analyze_tendency(db, owner, character.id))
        assert runner_calls == 0
        assert _count(db, models.AgentActivitySetting) == 0

        credential = db.get(
            models.LlmCredential, "package-import-setup-credential"
        )
        assert credential is not None
        pre_enable_context = LangGraphResidentContext(
            db=db,
            run_id="imported-world-pre-enable",
            user_id=owner.id,
            agent_id="angmoo-1",
            session_key=(
                "agent:angmoo-1:resident-manual:"
                "package-import-owner:imported-world-pre-enable"
            ),
            character=character,
            credential=credential,
            state=None,
            activity_policy=agent_activity_policy.ActivityPolicy(
                within_active_hours=True,
                allowed_actions=("post", "reply", "observe"),
                blocked_reasons={},
                next_tick_at=datetime(2026, 8, 28, 12, 0, tzinfo=UTC),
                summary="imported World pre-enable contract",
            ),
            selected_post_id=None,
            run_started_at=datetime(2026, 8, 28, 11, 0, tzinfo=UTC),
            run_mode="manual",
        )
        routine_result = asyncio.run(
            run_routine_post_runtime(
                pre_enable_context,
                provider=SimpleNamespace(),
            )
        )
        feed_result = asyncio.run(
            run_world_keyword_feed(
                pre_enable_context,
                provider=SimpleNamespace(),
            )
        )
        combined_result = asyncio.run(
            langgraph_resident.run_resident_langgraph(pre_enable_context)
        )
        assert routine_result["routine_outcome"] == "AUTONOMY_DISABLED"
        assert feed_result["feed_outcome"] == "AUTONOMY_DISABLED"
        assert combined_result["outcome"] == "AUTONOMY_DISABLED"
        assert routine_result["llm_usage_summary"]["provider_call_count"] == 0
        assert feed_result["llm_usage_summary"]["provider_call_count"] == 0
        assert combined_result["llm_usage_summary"]["provider_call_count"] == 0
        for model in (
            models.WorldCharacterFeedCursor,
            models.WorldCharacterFeedObservation,
            models.AgentRun,
            models.ActivityBeat,
            models.ActivityEpisode,
            models.ActivityEventConsumption,
            models.OwnerManualInboxCandidate,
            models.SocialEvent,
            models.SocialEventEvidence,
            models.RelationshipState,
            models.RelationshipStateChange,
            models.GraphProjectionOutbox,
        ):
            assert _count(db, model) == 0, model.__name__

        monkeypatch.setattr(
            agent_service.settings,
            "AGENT_ACTIVITY_ENGINE",
            "langgraph",
        )
        activated = agent_service.activate_agent(db, owner, character.id)
        db.refresh(world_character)
        assert activated.settings.auto_enabled is True
        assert world_character.autonomous_enabled is True
        assert world_character.role_key == "no_specific_role"

        # This test proves the imported actor enters the shared runtime after
        # explicit enable. Keep the run-now step deterministic instead of
        # depending on whether activation jitter lands inside the imminent
        # scheduler guard window.
        assigned_slot = db.scalar(
            select(models.AgentSlot).where(
                models.AgentSlot.assigned_character_id == character.id
            )
        )
        assert assigned_slot is not None
        assigned_slot.next_tick_at = datetime.now(UTC) - timedelta(seconds=1)
        db.commit()

        runner_allowed = True
        monkeypatch.setattr(
            agent_service.agent_run_service,
            "run_assigned_resident_slot_once",
            guarded_runner,
        )
        run_result = asyncio.run(agent_service.run_agent_now(db, owner, character.id))
        assert run_result.status == "completed"
        assert runner_calls == 1

        # Dispatch success alone is not P5-P7 evidence. Keep the fake runner
        # side-effect-free, then enter the actual keyword-feed observation UoW.
        for model in (
            models.Post,
            models.Comment,
            models.SocialEvent,
            models.SocialEventEvidence,
            models.RelationshipState,
            models.RelationshipStateChange,
            models.GraphProjectionOutbox,
        ):
            assert _count(db, model) == 0, model.__name__

        imported_profile = db.scalar(
            select(models.WorldCommunityProfile).where(
                models.WorldCommunityProfile.world_character_id
                == world_character.id,
                models.WorldCommunityProfile.status == "ready",
            )
        )
        imported_world = db.get(models.World, imported_world_id)
        assert imported_profile is not None and imported_world is not None

        direct_owner = models.User(
            id="package-parity-direct-owner",
            email="package-parity-direct-owner@example.test",
            display_name="Package parity direct owner",
            display_name_normalized="package parity direct owner",
            privacy_policy_version="test",
            terms_version="test",
            profile_setup_completed=True,
        )
        direct_character = models.Character(
            id="package-parity-direct-character",
            owner_id=direct_owner.id,
            name="Direct harbor guide",
            handle="direct-harbor-guide",
            one_liner="A directly created harbor guide.",
            personality="Welcoming and observant.",
            speech_style="Friendly and concise.",
            worldview="Small public events shape community relationships.",
            topic_preferences="Harbor weather and neighbors.",
            safety_rules="Do not invent private memories.",
            persona_summary="A directly created resident of the harbor.",
            moderation_status="active",
        )
        direct_world = models.World(
            id="package-parity-direct-world",
            slug="package-parity-direct-harbor",
            owner_user_id=direct_owner.id,
            name="Direct Harbor",
            tagline="A directly created comparison World",
            setting_description="Neighbors share small harbor observations.",
            daily_life_description="Residents maintain the pier and exchange news.",
            genre_tags=["fantasy", "community"],
            tone_tags=["warm", "calm"],
            timezone="Asia/Seoul",
            language="ko",
            visibility="public",
            join_policy="open",
            status="published",
            contract_version="world-v1",
            contract_hash="d" * 64,
            readiness_status="publish_ready",
            create_idempotency_key="package-parity-direct-world",
        )
        direct_credential = models.LlmCredential(
            id="package-parity-direct-credential",
            owner_id=direct_owner.id,
            character_id=direct_character.id,
            provider="google",
            purpose="agent",
            model="gemini-3.1-flash-lite",
            auth_profile_id="package-parity-direct-profile",
            label="deterministic direct fixture key",
            encrypted_api_key=security.encrypt_secret(
                "synthetic-direct-parity-api-key",
                scope=security.SecretScope(
                    owner_id=direct_owner.id,
                    character_id=direct_character.id,
                    provider="google",
                    purpose="agent",
                ),
            ),
            enabled=True,
        )
        db.add_all(
            [direct_owner, direct_character, direct_world, direct_credential]
        )
        db.flush()
        direct_membership = models.WorldMembership(
            id="package-parity-direct-membership",
            world_id=direct_world.id,
            user_id=direct_owner.id,
            role="owner",
            status="active",
            joined_at=datetime(2026, 8, 28, 12, 0, tzinfo=UTC),
        )
        db.add(direct_membership)
        db.flush()
        direct_character_hash = (
            world_character_contracts.character_contract_hash(direct_character)
        )
        direct_world_character = models.WorldCharacter(
            id="package-parity-direct-world-character",
            world_id=direct_world.id,
            character_id=direct_character.id,
            membership_id=direct_membership.id,
            role_key="guide",
            status="active",
            control_mode="autonomous",
            owner_user_id=None,
            autonomous_enabled=True,
            activity_runtime_mode="routine_resident_v1",
            feed_runtime_mode="keyword_search_v1",
            local_profile={"background": "direct harbor guide"},
            character_contract_hash=direct_character_hash,
            world_contract_hash=direct_world.contract_hash,
        )
        db.add(direct_world_character)
        db.flush()
        db.add_all(
            [
                models.CharacterActiveWorld(
                    character_id=direct_character.id,
                    world_character_id=direct_world_character.id,
                    selected_at=datetime(2026, 8, 28, 12, 0, tzinfo=UTC),
                    idempotency_key="package-parity-direct-active-world",
                    version=1,
                ),
                models.WorldCommunityProfile(
                    id="package-parity-direct-community-profile",
                    world_character_id=direct_world_character.id,
                    status="ready",
                    visible_summary=imported_profile.visible_summary,
                    core_interests=list(imported_profile.core_interests),
                    adjacent_interests=list(imported_profile.adjacent_interests),
                    avoid_topics=list(imported_profile.avoid_topics),
                    discovery_openness=imported_profile.discovery_openness,
                    search_keywords=list(imported_profile.search_keywords),
                    action_profile=dict(imported_profile.action_profile),
                    schema_version=1,
                    generator_version="deterministic-direct-parity-v1",
                    character_contract_hash=direct_character_hash,
                    world_contract_hash=direct_world.contract_hash,
                    provider="google",
                    model=direct_credential.model,
                    credential_id=direct_credential.id,
                    generated_at=datetime(2026, 8, 28, 12, 0, tzinfo=UTC),
                    approved_at=datetime(2026, 8, 28, 12, 0, tzinfo=UTC),
                ),
            ]
        )
        db.commit()

        source_at = datetime(2026, 8, 28, 12, 55, tzinfo=UTC)
        imported_source_wc, imported_post, imported_event = (
            _seed_owner_social_source(
                db,
                world=imported_world,
                suffix="imported",
                occurred_at=source_at,
            )
        )
        direct_source_wc, direct_post, direct_event = _seed_owner_social_source(
            db,
            world=direct_world,
            suffix="direct",
            occurred_at=source_at,
        )
        feed_at = source_at + timedelta(minutes=5)
        imported_provider = _DeterministicNoActionFeedProvider()
        direct_provider = _DeterministicNoActionFeedProvider()
        imported_result = asyncio.run(
            run_world_keyword_feed(
                _feed_context(
                    db,
                    owner=owner,
                    character=character,
                    credential=credential,
                    run_id="package-parity-imported-feed",
                    occurred_at=feed_at,
                ),
                provider=imported_provider,
            )
        )
        direct_result = asyncio.run(
            run_world_keyword_feed(
                _feed_context(
                    db,
                    owner=direct_owner,
                    character=direct_character,
                    credential=direct_credential,
                    run_id="package-parity-direct-feed",
                    occurred_at=feed_at,
                ),
                provider=direct_provider,
            )
        )

        assert imported_world.id != direct_world.id
        assert imported_result["world_id"] == imported_world.id
        assert direct_result["world_id"] == direct_world.id
        assert imported_result["feed_outcome"] == "model_abstained"
        assert direct_result["feed_outcome"] == "model_abstained"
        assert imported_provider.plan_calls == direct_provider.plan_calls == 1
        assert (
            imported_result["llm_usage_summary"]["provider_call_count"]
            == direct_result["llm_usage_summary"]["provider_call_count"]
            == 0
        )
        assert (
            imported_result["feed_cycle_summary"]["observation_receipt_count"]
            == direct_result["feed_cycle_summary"]["observation_receipt_count"]
            == 1
        )
        assert (
            imported_result["feed_cycle_summary"]["keyword_offset"]
            == direct_result["feed_cycle_summary"]["keyword_offset"]
            == 0
        )

        imported_snapshot, imported_runtime_ids = _world_feed_runtime_snapshot(
            db,
            world=imported_world,
            observer_world_character=world_character,
            source_world_character=imported_source_wc,
            source_post=imported_post,
            source_event=imported_event,
        )
        direct_snapshot, direct_runtime_ids = _world_feed_runtime_snapshot(
            db,
            world=direct_world,
            observer_world_character=direct_world_character,
            source_world_character=direct_source_wc,
            source_post=direct_post,
            source_event=direct_event,
        )
        assert imported_snapshot == direct_snapshot
        assert imported_runtime_ids.isdisjoint(direct_runtime_ids)


def test_media_promotion_failure_rolls_back_all_rows_and_is_retryable(
    import_runtime,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    sentinel = import_runtime.media_root / "existing-user-media.bin"
    sentinel.write_bytes(b"preserve-existing-user-media")
    sentinel_digest = hashlib.sha256(sentinel.read_bytes()).hexdigest()
    prepared = _stage(import_runtime.client, _archive(with_image=True))
    database_digest = _database_digest(import_runtime.engine)
    original_promote = import_runtime.media.promote

    def fail_promotion(*, import_id: str) -> None:
        del import_id
        raise WorldPackageContractError(WorldPackageReasonCode.COMMIT_FAILED)

    monkeypatch.setattr(import_runtime.media, "promote", fail_promotion)
    failed = _commit(
        import_runtime.client,
        prepared,
        idempotency_key="package-import-retry",
    )
    assert failed.status_code == 409
    assert failed.json()["detail"] == "world_package_commit_failed"
    with import_runtime.factory() as db:
        for model in (
            models.World,
            models.WorldMembership,
            models.Character,
            models.WorldCharacter,
            models.WorldPackageImport,
            models.WorldPackageImportIdMap,
        ):
            assert _count(db, model) == 0
    assert hashlib.sha256(sentinel.read_bytes()).hexdigest() == sentinel_digest
    assert _database_digest(import_runtime.engine) == database_digest
    assert not any(
        (import_runtime.media_root / "world-package-imports").iterdir()
    )

    monkeypatch.setattr(import_runtime.media, "promote", original_promote)
    retried = _commit(
        import_runtime.client,
        prepared,
        idempotency_key="package-import-retry",
    )
    assert retried.status_code == 201, retried.text


def test_seed_failure_after_partial_flush_preserves_existing_data(
    import_runtime,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    prepared = _stage(import_runtime.client, _archive(with_image=True))
    database_digest = _database_digest(import_runtime.engine)
    original_seed = SqlAlchemyWorldPackageDestinationSeed.seed

    def fail_after_seed(self, request):
        original_seed(self, request)
        raise WorldPackageContractError(WorldPackageReasonCode.COMMIT_FAILED)

    monkeypatch.setattr(
        SqlAlchemyWorldPackageDestinationSeed,
        "seed",
        fail_after_seed,
    )
    failed = _commit(
        import_runtime.client,
        prepared,
        idempotency_key="package-import-seed-failure",
    )
    assert failed.status_code == 409
    assert failed.json()["detail"] == "world_package_commit_failed"
    assert _database_digest(import_runtime.engine) == database_digest
    assert not any(
        (import_runtime.media_root / "world-package-imports").iterdir()
    )
    assert not any(
        (
            import_runtime.runtime_root
            / "world-packages"
            / "import-media-journal"
        ).iterdir()
    )

    monkeypatch.setattr(
        SqlAlchemyWorldPackageDestinationSeed,
        "seed",
        original_seed,
    )
    retried = _commit(
        import_runtime.client,
        prepared,
        idempotency_key="package-import-seed-failure",
    )
    assert retried.status_code == 201, retried.text


def test_commit_revalidates_owner_digest_and_collision_preview(
    import_runtime,
) -> None:
    stale = _stage(import_runtime.client, _archive())

    import_runtime.app.dependency_overrides[get_current_user] = lambda: (
        SimpleNamespace(id="different-local-owner")
    )
    forbidden = _commit(
        import_runtime.client,
        stale,
        idempotency_key="package-import-owner-check",
    )
    assert forbidden.status_code == 403
    assert forbidden.json()["detail"] == "world_package_stage_forbidden"
    import_runtime.app.dependency_overrides[get_current_user] = lambda: (
        SimpleNamespace(id=OWNER_ID)
    )

    changed_digest = _commit(
        import_runtime.client,
        stale,
        idempotency_key="package-import-digest-check",
        digest="0" * 64,
    )
    assert changed_digest.status_code == 409
    assert changed_digest.json()["detail"] == "world_package_preview_changed"

    winner = _stage(import_runtime.client, _archive())
    committed = _commit(
        import_runtime.client,
        winner,
        idempotency_key="package-import-preview-winner",
    )
    assert committed.status_code == 201, committed.text
    database_digest = _database_digest(import_runtime.engine)

    stale_commit = _commit(
        import_runtime.client,
        stale,
        idempotency_key="package-import-stale-preview",
    )
    assert stale_commit.status_code == 409
    assert stale_commit.json()["detail"] == "world_package_preview_changed"
    assert _database_digest(import_runtime.engine) == database_digest

    refreshed = _stage(import_runtime.client, _archive())
    copied = _commit(
        import_runtime.client,
        refreshed,
        idempotency_key="package-import-refreshed-copy",
        strategy="independent_copy",
    )
    assert copied.status_code == 201, copied.text
    assert copied.json()["imported_world_id"] != committed.json()[
        "imported_world_id"
    ]


def test_duplicate_requires_explicit_independent_copy(import_runtime) -> None:
    first = _stage(import_runtime.client, _archive())
    committed = _commit(
        import_runtime.client,
        first,
        idempotency_key="package-import-original",
    )
    assert committed.status_code == 201, committed.text

    duplicate = _stage(import_runtime.client, _archive())
    assert duplicate["preview"]["collision_plan"]["duplicate_state"] == (
        "already_imported"
    )
    rejected = _commit(
        import_runtime.client,
        duplicate,
        idempotency_key="package-import-copy",
    )
    assert rejected.status_code == 409
    assert rejected.json()["detail"] == "world_package_duplicate"

    copied = _commit(
        import_runtime.client,
        duplicate,
        idempotency_key="package-import-copy",
        strategy="independent_copy",
    )
    assert copied.status_code == 201, copied.text
    assert copied.json()["imported_world_id"] != committed.json()[
        "imported_world_id"
    ]
    with import_runtime.factory() as db:
        assert _count(db, models.World) == 2
        assert _count(db, models.WorldPackageImport) == 2


def test_concurrent_idempotency_commits_once(import_runtime) -> None:
    prepared = [
        _stage(import_runtime.client, _archive()),
        _stage(import_runtime.client, _archive()),
    ]

    def commit(index: int):
        return _commit(
            import_runtime.client,
            prepared[index],
            idempotency_key="package-import-concurrent",
        )

    with ThreadPoolExecutor(max_workers=2) as executor:
        responses = list(executor.map(commit, range(2)))
    assert [item.status_code for item in responses] == [201, 201]
    payloads = [item.json() for item in responses]
    assert len({item["import_id"] for item in payloads}) == 1
    assert len({item["imported_world_id"] for item in payloads}) == 1
    assert sorted(item["replayed"] for item in payloads) == [False, True]
    with import_runtime.factory() as db:
        assert _count(db, models.World) == 1
        assert _count(db, models.WorldPackageImport) == 1


def test_ambiguous_commit_result_recovers_promoted_media(
    import_runtime,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    prepared = _stage(import_runtime.client, _archive(with_image=True))
    session_type = import_runtime.factory.class_
    original_commit = session_type.commit
    raised = False

    def commit_then_report_transport_failure(self) -> None:
        nonlocal raised
        original_commit(self)
        if not raised:
            raised = True
            raise RuntimeError("synthetic post-commit transport failure")

    monkeypatch.setattr(
        session_type,
        "commit",
        commit_then_report_transport_failure,
    )
    response = _commit(
        import_runtime.client,
        prepared,
        idempotency_key="package-import-ambiguous-commit",
    )
    assert response.status_code == 201, response.text
    result = response.json()
    assert result["replayed"] is False
    assert (
        import_runtime.media_root
        / "world-package-imports"
        / result["import_id"]
    ).is_dir()
    assert not any(
        (
            import_runtime.runtime_root
            / "world-packages"
            / "import-media-journal"
        ).iterdir()
    )
    with import_runtime.factory() as db:
        assert _count(db, models.World) == 1
        assert _count(db, models.WorldPackageImport) == 1


def test_media_journal_recovery_keeps_only_canonical_commits(
    tmp_path: Path,
) -> None:
    media = FilesystemWorldPackageImportMedia(
        media_root=tmp_path / "media",
        runtime_root=tmp_path / "runtime",
        media_url_path="/media",
    )
    content = b"verified-normalized-payload"
    digest = hashlib.sha256(content).hexdigest()
    source_ref = f"assets/sha256-{digest}.webp"
    metadata = (
        WorldPackageNormalizedAsset(
            source_ref=source_ref,
            normalized_ref=source_ref,
            normalized_sha256=digest,
            normalized_bytes=len(content),
            width=1,
            height=1,
            alt_text="fixture",
        ),
    )
    payloads = (
        WorldPackageNormalizedAssetPayload(
            source_ref=source_ref,
            normalized_ref=source_ref,
            normalized_sha256=digest,
            content=content,
        ),
    )
    orphan_id = "019ff9d5-559d-7452-b0f5-68f4964a2d80"
    media.prepare(import_id=orphan_id, metadata=metadata, payloads=payloads)
    media.promote(import_id=orphan_id)
    media.recover(import_exists=lambda _import_id: False)
    assert not (tmp_path / "media" / "world-package-imports" / orphan_id).exists()

    committed_id = "019ff9d5-559d-7452-b0f5-68f4964a2d81"
    media.prepare(import_id=committed_id, metadata=metadata, payloads=payloads)
    media.promote(import_id=committed_id)
    media.recover(import_exists=lambda value: value == committed_id)
    assert (tmp_path / "media" / "world-package-imports" / committed_id).is_dir()
    assert not (
        tmp_path
        / "runtime"
        / "world-packages"
        / "import-media-journal"
        / f"{committed_id}.json"
    ).exists()
