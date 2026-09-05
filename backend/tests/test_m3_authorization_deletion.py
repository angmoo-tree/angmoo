from __future__ import annotations
from app.runtime import account_deletion

from datetime import UTC, date, datetime, timedelta
import json
from pathlib import Path

import pytest
from sqlalchemy import create_engine, event, func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app import models, schemas
from app.core.config import settings
from app.core.db import Base
from app.credentials import (
    CredentialPurpose,
    CredentialResolutionError,
    CredentialResolver,
)
from app.runtime.characters import creator as draft_service
from app.runtime.characters import management as agent_service
from app.domains.identity.service import auth as auth_service
from app.services import character_lore as lore_service
from app.services import community as community_service
from app.services import messages as message_service


PRIVACY_INVENTORY = (
    Path(__file__).resolve().parents[1]
    / "security"
    / "privacy_deletion_inventory.json"
)


def _engine():
    engine = create_engine("sqlite:///:memory:")

    @event.listens_for(engine, "connect")
    def _enable_foreign_keys(dbapi_connection, _connection_record) -> None:
        cursor = dbapi_connection.cursor()
        cursor.execute("PRAGMA foreign_keys=ON")
        cursor.close()

    Base.metadata.create_all(engine)
    return engine


def _user(user_id: str, *, is_admin: bool = False) -> models.User:
    return models.User(
        id=user_id,
        email=f"{user_id}@example.test",
        google_sub=f"google-{user_id}",
        password_hash=f"hash-{user_id}",
        display_name=user_id,
        display_name_normalized=user_id,
        is_admin=is_admin,
        privacy_policy_version="test",
        terms_version="test",
    )


def _character(character_id: str, owner_id: str) -> models.Character:
    return models.Character(
        id=character_id,
        owner_id=owner_id,
        name=character_id,
        handle=character_id,
        avatar_url=f"/media/characters/{character_id}/avatar.webp",
        banner_url=f"/media/characters/{character_id}/banner.webp",
        one_liner="one",
        personality="private personality",
        speech_style="private speech",
        worldview="private worldview",
        topic_preferences="private topics",
        safety_rules="private safety",
        status="inactive",
        persona_summary="private summary",
    )


def _seed_private_graph(db: Session, *, user: models.User, character: models.Character):
    now = datetime.now(UTC)
    post = models.Post(
        id=f"post-{character.id}",
        author_character_id=character.id,
        author_name=character.name,
        title="public title",
        body="public body",
    )
    tree_post = models.TreePost(
        id=f"tree-{character.id}",
        category="free",
        title="public tree title",
        body="public tree body",
        author_user_id=user.id,
        related_character_id=character.id,
    )
    credential = models.LlmCredential(
        id=f"credential-{character.id}",
        owner_id=user.id,
        character_id=character.id,
        provider="google",
        purpose="agent",
        model="gemini-test",
        auth_profile_id=f"profile-{character.id}",
        label="private key",
        encrypted_api_key="dev-v1:private-envelope",
        key_fingerprint="private-fingerprint",
    )
    db.add_all([post, tree_post, credential])
    db.flush()

    profile_quota = models.ProfileImageQuotaReservation(
        user_id=user.id,
        quota_date=date.today(),
        bucket="profile",
        scope="profile",
        media_type="avatar",
        status="generated",
        candidate_id=f"candidate-{character.id}",
    )
    post_quota = models.PostImageQuotaReservation(
        user_id=user.id,
        character_id=character.id,
        quota_date=date.today(),
        source="resident",
        status="generated",
        post_id=post.id,
    )
    db.add_all([profile_quota, post_quota])
    db.flush()

    draft = models.AgentCreationDraft(
        id=f"draft-{character.id}",
        user_id=user.id,
        provider="google",
        model="gemini-test",
        encrypted_api_key="dev-v1:draft-envelope",
        key_fingerprint="draft-fingerprint",
        name="private draft",
        avatar_temp_url=f"/media/drafts/draft-{character.id}/avatar.webp",
        expires_at=now + timedelta(hours=1),
    )
    candidate = models.ProfileImageCandidate(
        id=f"candidate-{character.id}",
        user_id=user.id,
        character_id=character.id,
        quota_reservation_id=profile_quota.id,
        scope="profile",
        bucket="profile",
        media_type="avatar",
        url=f"/media/profile-candidates/{user.id}/candidate-{character.id}/avatar.webp",
        model="image-test",
        route_mode="direct",
        expires_at=now + timedelta(hours=1),
    )
    lore = models.CharacterLoreSource(
        id=f"lore-{character.id}",
        owner_id=user.id,
        character_id=character.id,
        filename="private.txt",
        extension="txt",
        content_type="text/plain",
        file_size_bytes=7,
        raw_text="private lore",
        raw_text_hash=f"hash-{character.id}",
        extracted_char_count=12,
        chunk_count=1,
    )
    thread = models.MessageThread(
        id=f"thread-{character.id}",
        requester_id=user.id,
        character_id=character.id,
    )
    run = models.AgentRun(
        id=f"run-{character.id}",
        user_id=user.id,
        character_id=character.id,
        post_id=post.id,
        credential_id=credential.id,
        agent_id=f"agent-{character.id}",
        session_key=f"private-session-{character.id}",
        tool_auth_key=f"private-tool-{character.id}",
        status="completed",
        gateway_result={"private": "trace"},
        completed_at=now,
    )
    notification = models.Notification(
        recipient_user_id=user.id,
        actor_character_id=character.id,
        notification_type="reply",
        post_id=post.id,
        data="private notification",
    )
    db.add_all([draft, candidate, lore, thread, run, notification])
    db.flush()

    db.add_all(
        [
            models.PostMedia(
                post_id=post.id,
                url=f"/media/posts/{post.id}/image.webp",
                alt_text="public image",
                model="image-test",
                prompt_hash="public-prompt-hash",
                byte_size=4,
                width=1,
                height=1,
            ),
            models.Comment(
                post_id=post.id,
                author_character_id=character.id,
                content="public reply",
            ),
            models.TreeComment(
                post_id=tree_post.id,
                author_user_id=user.id,
                content="public tree comment",
            ),
            models.AuthSession(
                token_hash=f"session-hash-{user.id}",
                user_id=user.id,
            ),
            models.CharacterState(
                character_id=character.id,
                mood="private",
                summary="private state",
                memory_note="private memory",
            ),
            models.AgentActivitySetting(
                character_id=character.id,
                tendency_summary="private tendency",
                tendency_action_ranges={"post": {"min": 1}},
                planner_tendency_profile={"private": True},
            ),
            models.AgentImageGenerationSetting(
                character_id=character.id,
                encrypted_pollinations_api_key="dev-v1:image-envelope",
                key_fingerprint="image-fingerprint",
                seed_image_url=f"/media/characters/{character.id}/seed.webp",
                visual_identity_prompt="private visual identity",
            ),
            models.AgentLocalKey(
                id=f"local-{character.id}",
                owner_id=user.id,
                character_id=character.id,
                token_hash=f"local-hash-{character.id}",
                token_prefix="angmoo_local_test",
            ),
            models.CharacterMessageSetting(character_id=character.id, enabled=True),
            models.UserMessagePreference(
                user_id=user.id,
                credential_source="agent_key",
                source_character_id=character.id,
            ),
            models.MessageMessage(
                thread_id=thread.id,
                role="user",
                content="private message",
            ),
            models.CharacterLoreChunk(
                id=f"chunk-{character.id}",
                source_id=lore.id,
                owner_id=user.id,
                character_id=character.id,
                chunk_index=0,
                text="private lore",
                content_hash=f"chunk-hash-{character.id}",
            ),
            models.PostImageGenerationJob(
                post_id=post.id,
                character_id=character.id,
                user_id=user.id,
                quota_reservation_id=post_quota.id,
                image_model="image-test",
                image_prompt="private image prompt",
                media_url=f"/media/posts/{post.id}/image.webp",
            ),
            models.AgentFeedCue(
                user_id=user.id,
                character_id=character.id,
                topic="private feed cue",
                consumed_run_id=run.id,
                consumed_post_id=post.id,
            ),
            models.AgentActivityLog(
                user_id=user.id,
                character_id=character.id,
                action_type="private",
                target_post_id=post.id,
                reason="private reason",
                result="private result",
            ),
            models.AgentPublicActionExecution(
                run_id=run.id,
                character_id=character.id,
                signature=f"action-{character.id}",
                scope="community",
                action_type="post",
                target_post_id=post.id,
                result={"private": "result"},
            ),
            models.AgentDaypartMemoryEvent(
                character_id=character.id,
                memory_session_key=f"private-memory-{character.id}",
                daypart_start_date=date.today(),
                activity_daypart="day",
                event_type="observed",
                source_post_id=post.id,
                notification_id=notification.id,
                run_id=run.id,
                summary="private memory",
                payload={"private": True},
            ),
            models.AgentRelationshipPoint(
                recipient_character_id=character.id,
                source_character_id=character.id,
                kind="reply",
                source_post_id=post.id,
                source_run_id=run.id,
                topic_brief="private relationship",
                source_signature=f"relationship-{character.id}",
                chain_id=f"chain-{character.id}",
                pair_key=f"pair-{character.id}",
                expires_at=now + timedelta(days=1),
            ),
            models.PostLike(
                post_id=post.id,
                user_id=user.id,
                character_id=character.id,
            ),
            models.PostRepost(
                post_id=post.id,
                character_id=character.id,
            ),
            models.PostReport(
                post_id=post.id,
                reporter_user_id=user.id,
                reason="private",
                details="private report",
            ),
            models.ProfileFollow(
                follower_character_id=character.id,
                target_user_id=user.id,
            ),
            models.AgentSlot(
                agent_id=f"slot-{character.id}",
                status="assigned_idle",
                assigned_user_id=user.id,
                assigned_character_id=character.id,
                assigned_credential_id=credential.id,
                locked_by_run_id=run.id,
            ),
            models.AdminAuditLog(
                admin_user_id=user.id,
                action="private_action",
                target_type="character",
                target_id=character.id,
                note="private audit note",
                metadata_json={"private": True},
                request_ip="192.0.2.10",
                user_agent="private user agent",
            ),
            models.SiteOperationBanner(
                key=f"banner-{character.id}",
                title="test",
                message="test",
                updated_by_user_id=user.id,
            ),
            models.SiteOperationSetting(
                key=f"setting-{character.id}",
                value="test",
                updated_by_user_id=user.id,
            ),
        ]
    )
    db.commit()
    return post, tree_post


def _write_private_media(media_root: Path, *, user_id: str, character_id: str) -> None:
    files = {
        media_root / "characters" / character_id / "avatar.webp": b"private-avatar",
        media_root / "characters" / character_id / "seed.webp": b"private-seed",
        media_root / "drafts" / f"draft-{character_id}" / "avatar.webp": b"private-draft",
        media_root
        / "profile-candidates"
        / user_id
        / f"candidate-{character_id}"
        / "avatar.webp": b"private-candidate",
        media_root / "posts" / f"post-{character_id}" / "image.webp": b"public-post",
    }
    for path, content in files.items():
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(content)


PRIVATE_MODELS = (
    models.AuthSession,
    models.AgentCreationDraft,
    models.ProfileImageCandidate,
    models.ProfileImageQuotaReservation,
    models.CharacterLoreChunk,
    models.CharacterLoreSource,
    models.MessageMessage,
    models.MessageThread,
    models.UserMessagePreference,
    models.CharacterMessageSetting,
    models.PostImageGenerationJob,
    models.PostImageQuotaReservation,
    models.AgentPublicActionExecution,
    models.AgentDaypartMemoryEvent,
    models.AgentRelationshipPoint,
    models.AgentFeedCue,
    models.AgentActivityLog,
    models.AgentRun,
    models.PostLike,
    models.PostRepost,
    models.PostReport,
    models.ProfileFollow,
    models.CharacterState,
    models.AgentActivitySetting,
    models.AgentImageGenerationSetting,
    models.LlmCredential,
    models.AgentLocalKey,
    models.Notification,
)


def test_account_deletion_removes_private_graph_and_keeps_public_content(
    tmp_path, monkeypatch
) -> None:
    monkeypatch.setattr(settings, "MEDIA_ROOT", str(tmp_path / "media"))
    monkeypatch.setattr(settings, "AGENT_ACTIVITY_ENGINE", "langgraph")
    engine = _engine()
    with Session(engine) as db:
        user = _user("owner", is_admin=True)
        character = _character("char-owner", user.id)
        db.add_all([user, character])
        db.commit()
        post, tree_post = _seed_private_graph(db, user=user, character=character)
        _write_private_media(
            settings.media_root_path, user_id=user.id, character_id=character.id
        )

        auth_service.delete_current_user_account(
            db,
            user,
            schemas.AccountDeletionCreate(
                confirmation=auth_service.ACCOUNT_DELETE_CONFIRMATION
            ),
            workflow=account_deletion.delete_current_user_account,
        )

        for model in PRIVATE_MODELS:
            assert db.scalar(select(func.count()).select_from(model)) == 0, model.__name__
        assert db.get(models.Post, post.id) is not None
        assert db.get(models.Comment, 1) is not None
        assert db.get(models.PostMedia, 1) is not None
        assert db.get(models.TreePost, tree_post.id) is not None
        assert db.get(models.TreeComment, 1) is not None
        assert db.get(models.Post, post.id).author_name == auth_service.DELETED_CHARACTER_NAME
        assert db.get(models.User, user.id).email is None
        assert db.get(models.User, user.id).google_sub is None
        assert db.get(models.User, user.id).password_hash is None
        assert db.get(models.User, user.id).is_admin is False
        assert db.get(models.Character, character.id).deleted_at is not None
        slot = db.get(models.AgentSlot, f"slot-{character.id}")
        assert slot.status == "empty"
        assert slot.assigned_user_id is None
        assert slot.assigned_character_id is None
        assert slot.assigned_credential_id is None
        audit = db.scalar(select(models.AdminAuditLog))
        assert audit.note is None
        assert audit.metadata_json is None
        assert audit.request_ip is None
        assert audit.user_agent is None
        assert db.scalar(select(models.SiteOperationBanner)).updated_by_user_id is None
        assert db.scalar(select(models.SiteOperationSetting)).updated_by_user_id is None

        media_root = settings.media_root_path
        assert not (media_root / "characters" / character.id).exists()
        assert not (media_root / "drafts" / f"draft-{character.id}").exists()
        assert not (media_root / "profile-candidates" / user.id).exists()
        assert (media_root / "posts" / post.id / "image.webp").read_bytes() == b"public-post"


def test_account_deletion_flushes_active_slot_before_credential_delete(
    tmp_path, monkeypatch
) -> None:
    monkeypatch.setattr(settings, "MEDIA_ROOT", str(tmp_path / "media"))
    monkeypatch.setattr(settings, "AGENT_ACTIVITY_ENGINE", "langgraph")
    engine = _engine()
    with Session(engine, autoflush=False) as db:
        user = _user("active-owner")
        character = _character("char-active-owner", user.id)
        credential = models.LlmCredential(
            id="credential-active-owner",
            owner_id=user.id,
            character_id=character.id,
            provider="google",
            purpose="agent",
            model="gemini-test",
            auth_profile_id="profile-active-owner",
            label="private key",
            encrypted_api_key="dev-v1:private-envelope",
            key_fingerprint="private-fingerprint",
        )
        slot = models.AgentSlot(
            agent_id="slot-active-owner",
            status="assigned_idle",
            assigned_user_id=user.id,
            assigned_character_id=character.id,
            assigned_credential_id=credential.id,
        )
        db.add_all([user, character, credential])
        db.flush()
        db.add(slot)
        db.commit()

        auth_service.delete_current_user_account(
            db,
            user,
            schemas.AccountDeletionCreate(
                confirmation=auth_service.ACCOUNT_DELETE_CONFIRMATION
            ),
            workflow=account_deletion.delete_current_user_account,
        )

        assert db.get(models.LlmCredential, "credential-active-owner") is None
        assert db.get(models.User, "active-owner").deleted_at is not None
        assert db.get(models.Character, "char-active-owner").deleted_at is not None
        assert slot.status == "empty"
        assert slot.assigned_user_id is None
        assert slot.assigned_character_id is None
        assert slot.assigned_credential_id is None


def test_character_deletion_resets_cross_user_preference_and_removes_private_data(
    tmp_path, monkeypatch
) -> None:
    monkeypatch.setattr(settings, "MEDIA_ROOT", str(tmp_path / "media"))
    monkeypatch.setattr(settings, "AGENT_ACTIVITY_ENGINE", "langgraph")
    engine = _engine()
    with Session(engine) as db:
        owner = _user("owner")
        requester = _user("requester")
        character = _character("char-owner", owner.id)
        db.add_all([owner, requester, character])
        db.commit()
        post, _tree_post = _seed_private_graph(db, user=owner, character=character)
        preference = db.get(models.UserMessagePreference, owner.id)
        preference.user_id = requester.id
        db.commit()
        _write_private_media(
            settings.media_root_path, user_id=owner.id, character_id=character.id
        )

        agent_service.delete_agent(
            db,
            owner,
            character.id,
            schemas.AgentDeleteCreate(confirmation=character.name),
        )

        assert db.get(models.User, owner.id).deleted_at is None
        assert db.get(models.UserMessagePreference, requester.id).credential_source == "message_key"
        assert db.get(models.UserMessagePreference, requester.id).source_character_id is None
        assert db.scalar(select(func.count()).select_from(models.MessageThread)) == 0
        assert db.scalar(select(func.count()).select_from(models.CharacterLoreSource)) == 0
        assert db.scalar(select(func.count()).select_from(models.AgentRun)) == 0
        assert db.scalar(select(func.count()).select_from(models.PostImageGenerationJob)) == 0
        assert db.get(models.Post, post.id) is not None
        assert db.get(models.PostMedia, 1) is not None
        assert db.get(models.Character, character.id).deleted_at is not None
        assert not (settings.media_root_path / "characters" / character.id).exists()
        assert (settings.media_root_path / "posts" / post.id / "image.webp").exists()


def test_account_deletion_restores_private_media_when_database_commit_fails(
    tmp_path, monkeypatch
) -> None:
    monkeypatch.setattr(settings, "MEDIA_ROOT", str(tmp_path / "media"))
    monkeypatch.setattr(settings, "AGENT_ACTIVITY_ENGINE", "langgraph")
    engine = _engine()
    with Session(engine) as db:
        user = _user("owner")
        character = _character("char-owner", user.id)
        db.add_all([user, character])
        db.commit()
        private_file = settings.media_root_path / "characters" / character.id / "avatar.webp"
        private_file.parent.mkdir(parents=True)
        private_file.write_bytes(b"private-avatar")

        original_commit = db.commit

        def _fail_commit() -> None:
            raise IntegrityError("forced", {}, RuntimeError("forced"))

        monkeypatch.setattr(db, "commit", _fail_commit)
        with pytest.raises(auth_service.AuthError, match="Account deletion failed"):
            auth_service.delete_current_user_account(
                db,
                user,
                schemas.AccountDeletionCreate(
                    confirmation=auth_service.ACCOUNT_DELETE_CONFIRMATION
                ),
                workflow=account_deletion.delete_current_user_account,
            )
        monkeypatch.setattr(db, "commit", original_commit)

        assert private_file.read_bytes() == b"private-avatar"
        assert db.get(models.User, user.id).deleted_at is None
        assert db.get(models.Character, character.id).deleted_at is None


def test_two_user_object_authorization_matrix_denies_cross_owner_access(
    tmp_path, monkeypatch
) -> None:
    monkeypatch.setattr(settings, "MEDIA_ROOT", str(tmp_path / "media"))
    monkeypatch.setattr(settings, "AGENT_ACTIVITY_ENGINE", "langgraph")
    engine = _engine()
    with Session(engine) as db:
        owner = _user("owner")
        intruder = _user("intruder")
        character = _character("char-owner", owner.id)
        db.add_all([owner, intruder, character])
        db.commit()
        post, _tree_post = _seed_private_graph(db, user=owner, character=character)
        _write_private_media(
            settings.media_root_path, user_id=owner.id, character_id=character.id
        )

        with pytest.raises(agent_service.AgentNotFoundError):
            agent_service.get_agent(db, intruder, character.id)
        with pytest.raises(agent_service.AgentNotFoundError):
            agent_service.get_local_connection(db, intruder, character.id)
        with pytest.raises(draft_service.AgentCreationDraftNotFoundError):
            draft_service.get_draft(db, intruder, f"draft-{character.id}")
        with pytest.raises(agent_service.AgentNotFoundError):
            draft_service.discard_profile_media_candidate(
                db, intruder, character.id, f"candidate-{character.id}"
            )
        with pytest.raises(lore_service.CharacterLoreNotFoundError):
            lore_service.delete_lore_source(
                db, intruder, character.id, f"lore-{character.id}"
            )
        with pytest.raises(message_service.MessageNotFoundError):
            message_service.get_thread(db, intruder, f"thread-{character.id}")
        with pytest.raises(community_service.CharacterNotFoundError):
            community_service.save_character_state_for_user(
                db,
                intruder,
                character.id,
                schemas.CharacterStateWrite(mood="safe", summary="unchanged"),
            )
        notification_id = db.scalar(select(models.Notification.id))
        with pytest.raises(community_service.NotificationNotFoundError):
            community_service.mark_notification_read(db, intruder, notification_id)
        with pytest.raises(community_service.CharacterOwnershipError):
            community_service.delete_post(db, intruder, post.id)
        with pytest.raises(CredentialResolutionError, match="owner does not match"):
            CredentialResolver.resolve_llm_credential(
                db.get(models.LlmCredential, f"credential-{character.id}"),
                purpose=CredentialPurpose.RESIDENT_LLM,
                owner_id=intruder.id,
                character_id=character.id,
            )

        db.expire_all()
        assert db.get(models.Post, post.id).deleted_at is None
        assert db.get(models.CharacterState, character.id).summary == "private state"
        assert db.get(models.Notification, notification_id).read_at is None
        assert db.get(models.ProfileImageCandidate, f"candidate-{character.id}") is not None
        assert db.get(models.CharacterLoreSource, f"lore-{character.id}") is not None
        assert db.get(models.MessageThread, f"thread-{character.id}") is not None


def test_sensitive_update_schemas_ignore_ownership_and_secret_mass_assignment() -> None:
    attempts = {
        "owner_id": "intruder",
        "user_id": "intruder",
        "character_id": "other-character",
        "is_admin": True,
        "encrypted_api_key": "forbidden-envelope",
        "key_fingerprint": "forbidden-fingerprint",
    }
    profile = schemas.AgentProfileUpdate.model_validate(
        {"name": "Safe name", **attempts}
    ).model_dump(exclude_unset=True)
    persona = schemas.AgentPersonaUpdate.model_validate(
        {"personality": "Safe persona", **attempts}
    ).model_dump(exclude_unset=True)
    user = schemas.UserDisplayNameUpdate.model_validate(
        {"display_name": "Safe user", **attempts}
    ).model_dump(exclude_unset=True)

    for payload in (profile, persona, user):
        assert not set(attempts).intersection(payload)


def test_privacy_deletion_inventory_classifies_every_model_table_once() -> None:
    inventory = json.loads(PRIVACY_INVENTORY.read_text(encoding="utf-8"))
    assert inventory["schema_version"] == 1
    expected = set(Base.metadata.tables)

    for scenario in ("account_deletion", "character_deletion"):
        groups = inventory[scenario]
        classified: set[str] = set()
        for table_names in groups.values():
            current = set(table_names)
            assert not classified.intersection(current), scenario
            classified.update(current)
        assert classified == expected, scenario
