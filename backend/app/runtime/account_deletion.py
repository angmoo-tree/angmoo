from uuid import uuid4


from sqlalchemy import delete, false, or_, select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session
from app import models

from app.core.config import settings
from app.core.redaction import redact_secret_text
from app.cruds import agent_runs as agent_run_crud


from app.services import profile_media
from app.services.runtime_boundary import (
    OpenClawGatewayClient,
    OpenClawGatewayError,
    openclaw_auth_profiles,
)
from app.domains.identity.service import auth as auth_service
from app.domains.identity.constants import (
    DELETED_USER_DISPLAY_NAME,
    DELETED_CHARACTER_NAME,
    DELETED_CHARACTER_PLACEHOLDER,
)
from app.domains.identity.exceptions import (
    AuthError,
    AccountDeletionBusyError,
    AccountDeletionCredentialSyncError,
    AccountDeletionMediaCleanupError,
)


def delete_current_user_account(
    db: Session, user: models.User
) -> None:
    characters = list(
        db.scalars(
            select(models.Character)
            .where(models.Character.owner_id == user.id)
            .order_by(models.Character.id.asc())
        )
    )
    character_ids = [character.id for character in characters]

    _ensure_account_deletion_not_busy(db, user.id, character_ids)
    media_quarantine = _quarantine_account_private_media(db, user.id, character_ids)
    try:
        _release_openclaw_profiles_for_account(db, user.id, character_ids)
        _clear_resident_slots_for_account(db, user.id, character_ids)
        db.flush()
        _scrub_account_data(db, user, characters, character_ids)
        db.commit()
    except Exception as exc:
        db.rollback()
        try:
            media_quarantine.restore()
        except profile_media.PrivateMediaCleanupError as restore_exc:
            raise AccountDeletionMediaCleanupError(
                "private_media_restore_failed"
            ) from restore_exc
        if isinstance(exc, IntegrityError):
            raise AuthError("Account deletion failed") from exc
        raise
    try:
        media_quarantine.purge()
    except profile_media.PrivateMediaCleanupError as exc:
        raise AccountDeletionMediaCleanupError("private_media_purge_failed") from exc


def _quarantine_account_private_media(
    db: Session, user_id: str, character_ids: list[str]
) -> profile_media.PrivateMediaQuarantine:
    draft_ids = list(
        db.scalars(
            select(models.AgentCreationDraft.id).where(
                models.AgentCreationDraft.user_id == user_id
            )
        )
    )
    media_root = settings.media_root_path
    paths = [media_root / "characters" / character_id for character_id in character_ids]
    paths.extend(media_root / "drafts" / draft_id for draft_id in draft_ids)
    paths.append(media_root / "profile-candidates" / user_id)
    return profile_media.quarantine_private_media(paths)


def _ensure_account_deletion_not_busy(
    db: Session, user_id: str, character_ids: list[str]
) -> None:
    active_run_id = db.scalar(
        select(models.AgentRun.id)
        .where(
            _owned_agent_run_condition(user_id, character_ids),
            models.AgentRun.status.in_(agent_run_crud.ACTIVE_RUN_STATUSES),
        )
        .limit(1)
    )
    if active_run_id is not None:
        raise AccountDeletionBusyError("Agent run is running")

    running_slot_id = db.scalar(
        select(models.AgentSlot.agent_id)
        .where(
            _owned_agent_slot_condition(user_id, character_ids),
            models.AgentSlot.status == agent_run_crud.SLOT_STATUS_RUNNING,
        )
        .limit(1)
    )
    if running_slot_id is not None:
        raise AccountDeletionBusyError("Resident slot is running")


def _release_openclaw_profiles_for_account(
    db: Session, user_id: str, character_ids: list[str]
) -> None:
    if settings.agent_activity_engine != "openclaw":
        return
    released = False
    slots = list(
        db.scalars(
            select(models.AgentSlot)
            .where(_owned_agent_slot_condition(user_id, character_ids))
            .order_by(models.AgentSlot.agent_id.asc())
        )
    )
    for slot in slots:
        if slot.status == agent_run_crud.SLOT_STATUS_RUNNING:
            raise AccountDeletionBusyError("Resident slot is running")
        if (
            slot.assigned_user_id is None
            or slot.assigned_character_id is None
            or slot.assigned_credential_id is None
        ):
            continue
        credential = db.get(models.LlmCredential, slot.assigned_credential_id)
        if credential is None:
            continue
        try:
            openclaw_auth_profiles.release_credential_from_slot(
                agent_id=slot.agent_id,
                user_id=slot.assigned_user_id,
                character_id=slot.assigned_character_id,
                credential=credential,
            )
        except openclaw_auth_profiles.OpenClawAuthProfileSyncError as exc:
            raise AccountDeletionCredentialSyncError(
                redact_secret_text(str(exc))
            ) from exc
        released = True
    if released:
        _reload_openclaw_secrets_sync()


def _reload_openclaw_secrets_sync() -> None:
    token = settings.openclaw_gateway_token
    if token is None:
        return
    try:
        OpenClawGatewayClient(
            url=settings.openclaw_gateway_url,
            token=token,
            timeout_seconds=settings.openclaw_timeout_seconds,
        ).reload_secrets_sync()
    except OpenClawGatewayError as exc:
        raise AccountDeletionCredentialSyncError(redact_secret_text(str(exc))) from exc


def _clear_resident_slots_for_account(
    db: Session, user_id: str, character_ids: list[str]
) -> None:
    slots = list(
        db.scalars(
            select(models.AgentSlot)
            .where(_owned_agent_slot_condition(user_id, character_ids))
            .order_by(models.AgentSlot.agent_id.asc())
        )
    )
    for slot in slots:
        if slot.status == agent_run_crud.SLOT_STATUS_RUNNING:
            raise AccountDeletionBusyError("Resident slot is running")
        slot.status = agent_run_crud.SLOT_STATUS_EMPTY
        slot.assigned_user_id = None
        slot.assigned_character_id = None
        slot.assigned_credential_id = None
        slot.next_tick_at = None
        slot.last_run_at = None
        slot.heartbeat_interval_seconds = None
        slot.locked_by_run_id = None
        slot.lease_expires_at = None
        slot.last_error = None


def _scrub_account_data(
    db: Session,
    user: models.User,
    characters: list[models.Character],
    character_ids: list[str],
) -> None:
    now = auth_service._utcnow()
    character_condition = _character_id_condition

    from app.services import world_character_setup

    from app.runtime.memory_privacy import scrub_memory_data

    scrub_memory_data(db, owner_id=user.id)
    db.execute(
        delete(models.SocialActionSubjectiveContext).where(
            models.SocialActionSubjectiveContext.owner_id == user.id
        )
    )
    world_character_setup.delete_setup_data_for_characters(
        db, character_ids=character_ids
    )

    db.execute(
        delete(models.ProfileImageCandidate).where(
            or_(
                models.ProfileImageCandidate.user_id == user.id,
                character_condition(
                    models.ProfileImageCandidate.character_id, character_ids
                ),
            )
        )
    )
    db.execute(
        delete(models.ProfileImageQuotaReservation).where(
            models.ProfileImageQuotaReservation.user_id == user.id
        )
    )
    db.execute(
        delete(models.AgentCreationDraft).where(
            models.AgentCreationDraft.user_id == user.id
        )
    )

    message_thread_ids = select(models.MessageThread.id).where(
        or_(
            models.MessageThread.requester_id == user.id,
            character_condition(models.MessageThread.character_id, character_ids),
        )
    )
    db.execute(
        delete(models.MessageMessage).where(
            models.MessageMessage.thread_id.in_(message_thread_ids)
        )
    )
    db.execute(
        delete(models.MessageThread).where(
            or_(
                models.MessageThread.requester_id == user.id,
                character_condition(models.MessageThread.character_id, character_ids),
            )
        )
    )
    db.execute(
        delete(models.UserMessagePreference).where(
            models.UserMessagePreference.user_id == user.id
        )
    )
    db.execute(
        delete(models.CharacterMessageSetting).where(
            character_condition(
                models.CharacterMessageSetting.character_id, character_ids
            )
        )
    )

    lore_source_ids = select(models.CharacterLoreSource.id).where(
        or_(
            models.CharacterLoreSource.owner_id == user.id,
            character_condition(models.CharacterLoreSource.character_id, character_ids),
        )
    )
    db.execute(
        delete(models.CharacterLoreChunk).where(
            or_(
                models.CharacterLoreChunk.owner_id == user.id,
                character_condition(
                    models.CharacterLoreChunk.character_id, character_ids
                ),
                models.CharacterLoreChunk.source_id.in_(lore_source_ids),
            )
        )
    )
    db.execute(
        delete(models.CharacterLoreSource).where(
            or_(
                models.CharacterLoreSource.owner_id == user.id,
                character_condition(
                    models.CharacterLoreSource.character_id, character_ids
                ),
            )
        )
    )

    db.execute(
        delete(models.PostImageGenerationJob).where(
            or_(
                models.PostImageGenerationJob.user_id == user.id,
                character_condition(
                    models.PostImageGenerationJob.character_id, character_ids
                ),
            )
        )
    )
    db.execute(
        delete(models.PostImageQuotaReservation).where(
            or_(
                models.PostImageQuotaReservation.user_id == user.id,
                character_condition(
                    models.PostImageQuotaReservation.character_id, character_ids
                ),
            )
        )
    )
    db.execute(
        delete(models.AgentPublicActionExecution).where(
            character_condition(
                models.AgentPublicActionExecution.character_id, character_ids
            )
        )
    )
    db.execute(
        delete(models.AgentDaypartMemoryEvent).where(
            character_condition(
                models.AgentDaypartMemoryEvent.character_id, character_ids
            )
        )
    )
    db.execute(
        delete(models.AgentRelationshipPoint).where(
            or_(
                character_condition(
                    models.AgentRelationshipPoint.recipient_character_id,
                    character_ids,
                ),
                character_condition(
                    models.AgentRelationshipPoint.source_character_id,
                    character_ids,
                ),
            )
        )
    )

    db.execute(delete(models.AuthSession).where(models.AuthSession.user_id == user.id))
    db.execute(
        delete(models.AgentFeedCue).where(
            or_(
                models.AgentFeedCue.user_id == user.id,
                character_condition(models.AgentFeedCue.character_id, character_ids),
            )
        )
    )
    db.execute(
        delete(models.AgentActivityLog).where(
            or_(
                models.AgentActivityLog.user_id == user.id,
                character_condition(
                    models.AgentActivityLog.character_id, character_ids
                ),
            )
        )
    )
    db.execute(
        delete(models.AgentRun).where(
            _owned_agent_run_condition(user.id, character_ids)
        )
    )
    db.execute(
        delete(models.PostReport).where(models.PostReport.reporter_user_id == user.id)
    )
    db.execute(
        delete(models.PostLike).where(
            or_(
                models.PostLike.user_id == user.id,
                character_condition(models.PostLike.character_id, character_ids),
            )
        )
    )
    db.execute(
        delete(models.PostRepost).where(
            or_(
                models.PostRepost.user_id == user.id,
                character_condition(models.PostRepost.character_id, character_ids),
            )
        )
    )
    db.execute(
        delete(models.ProfileFollow).where(
            or_(
                models.ProfileFollow.follower_user_id == user.id,
                models.ProfileFollow.target_user_id == user.id,
                character_condition(
                    models.ProfileFollow.follower_character_id, character_ids
                ),
                character_condition(
                    models.ProfileFollow.target_character_id, character_ids
                ),
            )
        )
    )
    db.execute(
        delete(models.Notification).where(
            or_(
                models.Notification.recipient_user_id == user.id,
                models.Notification.actor_user_id == user.id,
                character_condition(
                    models.Notification.recipient_character_id, character_ids
                ),
                character_condition(
                    models.Notification.actor_character_id, character_ids
                ),
            )
        )
    )
    db.execute(
        update(models.Post)
        .where(models.Post.author_user_id == user.id)
        .values(author_name=DELETED_USER_DISPLAY_NAME)
    )
    if character_ids:
        db.execute(
            update(models.Post)
            .where(models.Post.author_character_id.in_(character_ids))
            .values(author_name=DELETED_CHARACTER_NAME)
        )
        db.execute(
            delete(models.CharacterState).where(
                models.CharacterState.character_id.in_(character_ids)
            )
        )
        db.execute(
            delete(models.AgentImageGenerationSetting).where(
                models.AgentImageGenerationSetting.character_id.in_(character_ids)
            )
        )

    db.execute(
        delete(models.AgentActivitySetting).where(
            character_condition(models.AgentActivitySetting.character_id, character_ids)
        )
    )

    db.execute(
        delete(models.LlmCredential).where(
            or_(
                models.LlmCredential.owner_id == user.id,
                character_condition(models.LlmCredential.character_id, character_ids),
            )
        )
    )
    db.execute(
        delete(models.AgentLocalKey).where(
            or_(
                models.AgentLocalKey.owner_id == user.id,
                character_condition(models.AgentLocalKey.character_id, character_ids),
            )
        )
    )
    db.execute(
        update(models.AdminAuditLog)
        .where(models.AdminAuditLog.admin_user_id == user.id)
        .values(note=None, metadata_json=None, request_ip=None, user_agent=None)
    )
    db.execute(
        update(models.SiteOperationBanner)
        .where(models.SiteOperationBanner.updated_by_user_id == user.id)
        .values(updated_by_user_id=None)
    )
    db.execute(
        update(models.SiteOperationSetting)
        .where(models.SiteOperationSetting.updated_by_user_id == user.id)
        .values(updated_by_user_id=None)
    )
    db.execute(
        update(models.Character)
        .where(models.Character.moderation_updated_by_user_id == user.id)
        .values(moderation_updated_by_user_id=None)
    )

    for character in characters:
        character.name = DELETED_CHARACTER_NAME
        character.handle = _deleted_character_handle(db, character.id)
        character.avatar_url = None
        character.banner_url = None
        character.one_liner = DELETED_CHARACTER_PLACEHOLDER
        character.personality = ""
        character.speech_style = ""
        character.worldview = ""
        character.topic_preferences = ""
        character.safety_rules = ""
        character.status = "inactive"
        character.persona_summary = DELETED_CHARACTER_PLACEHOLDER
        character.deleted_at = now

    user.email = None
    user.google_sub = None
    user.password_hash = None
    user.display_name = DELETED_USER_DISPLAY_NAME
    user.display_name_normalized = None
    user.display_name_updated_at = None
    user.is_admin = False
    user.privacy_policy_agreed_at = None
    user.terms_agreed_at = None
    user.privacy_policy_version = None
    user.terms_version = None
    user.profile_setup_completed = False
    user.feed_content_filter = "all"
    user.deleted_at = now


def _owned_agent_run_condition(user_id: str, character_ids: list[str]):
    return or_(
        models.AgentRun.user_id == user_id,
        _character_id_condition(models.AgentRun.character_id, character_ids),
    )


def _owned_agent_slot_condition(user_id: str, character_ids: list[str]):
    return or_(
        models.AgentSlot.assigned_user_id == user_id,
        _character_id_condition(models.AgentSlot.assigned_character_id, character_ids),
    )


def _character_id_condition(column, character_ids: list[str]):
    if not character_ids:
        return false()
    return column.in_(character_ids)


def _deleted_character_handle(db: Session, character_id: str) -> str:
    suffix = "".join(
        char.lower() for char in character_id if char.isalnum() or char in {"-", "_"}
    )
    suffix = suffix[-31:] or uuid4().hex[:12]
    base = f"deleted-{suffix}"[:40]
    candidate = base
    index = 2
    while db.scalar(
        select(models.Character.id).where(
            models.Character.handle == candidate,
            models.Character.id != character_id,
        )
    ):
        suffix_text = f"_{index}"
        candidate = f"{base[: 40 - len(suffix_text)]}{suffix_text}"
        index += 1
    return candidate
