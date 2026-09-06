from uuid import uuid4

from app.domains.operations import repository as operation_repository

from sqlalchemy import delete

from sqlalchemy import false

from sqlalchemy import or_

from sqlalchemy import select

from sqlalchemy import update

from sqlalchemy.exc import IntegrityError

from sqlalchemy.orm import Session

from app.domains.routines.models.resident import AgentActivityLog as _model_AgentActivityLog

from app.domains.routines.models.resident import AgentActivitySetting as _model_AgentActivitySetting

from app.domains.characters.models import AgentCreationDraft as _model_AgentCreationDraft

from app.domains.memory.models.daypart import AgentDaypartMemoryEvent as _model_AgentDaypartMemoryEvent

from app.domains.routines.models.resident import AgentFeedCue as _model_AgentFeedCue

from app.domains.characters.models import AgentImageGenerationSetting as _model_AgentImageGenerationSetting

from app.domains.local_bot.models import AgentLocalKey as _model_AgentLocalKey

from app.domains.routines.models.resident import AgentPublicActionExecution as _model_AgentPublicActionExecution

from app.domains.relationships.models.points import AgentRelationshipPoint as _model_AgentRelationshipPoint

from app.domains.routines.models.resident import AgentRun as _model_AgentRun

from app.domains.routines.models.resident import AgentSlot as _model_AgentSlot

from app.domains.identity.models import AuthSession as _model_AuthSession

from app.domains.characters.models import Character as _model_Character

from app.domains.character_lore.models import CharacterLoreChunk as _model_CharacterLoreChunk

from app.domains.character_lore.models import CharacterLoreSource as _model_CharacterLoreSource

from app.domains.chat.models import CharacterMessageSetting as _model_CharacterMessageSetting

from app.domains.characters.models import CharacterState as _model_CharacterState

from app.domains.identity.models import LlmCredential as _model_LlmCredential

from app.domains.chat.models import MessageMessage as _model_MessageMessage

from app.domains.chat.models import MessageThread as _model_MessageThread

from app.domains.social.models.posts import Notification as _model_Notification

from app.domains.social.models.posts import Post as _model_Post

from app.domains.social.models.posts import PostImageGenerationJob as _model_PostImageGenerationJob

from app.domains.social.models.posts import PostImageQuotaReservation as _model_PostImageQuotaReservation

from app.domains.social.models.posts import PostLike as _model_PostLike

from app.domains.social.models.posts import PostReport as _model_PostReport

from app.domains.social.models.posts import PostRepost as _model_PostRepost

from app.domains.social.models.posts import ProfileFollow as _model_ProfileFollow

from app.domains.characters.models import ProfileImageCandidate as _model_ProfileImageCandidate

from app.domains.characters.models import ProfileImageQuotaReservation as _model_ProfileImageQuotaReservation

from app.domains.social.models.subjective_context import SocialActionSubjectiveContext as _model_SocialActionSubjectiveContext

from app.domains.identity.models import User as _model_User

from app.domains.chat.models import UserMessagePreference as _model_UserMessagePreference

from app.runtime.persistence.model_registration import register_models

from app.config import settings

from app.core.redaction import redact_secret_text

from app.integrations.media import files as profile_media

from app.services.runtime_boundary import OpenClawGatewayClient

from app.services.runtime_boundary import OpenClawGatewayError

from app.services.runtime_boundary import openclaw_auth_profiles

from app.domains.identity.service import auth as auth_service

from app.domains.identity.constants import DELETED_USER_DISPLAY_NAME

from app.domains.identity.constants import DELETED_CHARACTER_NAME

from app.domains.identity.constants import DELETED_CHARACTER_PLACEHOLDER

from app.domains.identity.exceptions import AuthError

from app.domains.identity.exceptions import AccountDeletionBusyError

from app.domains.identity.exceptions import AccountDeletionCredentialSyncError

from app.domains.identity.exceptions import AccountDeletionMediaCleanupError

from app.domains.routines import constants as routine_constants

register_models()

def delete_current_user_account(
    db: Session, user: _model_User
) -> None:
    characters = list(
        db.scalars(
            select(_model_Character)
            .where(_model_Character.owner_id == user.id)
            .order_by(_model_Character.id.asc())
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
            select(_model_AgentCreationDraft.id).where(
                _model_AgentCreationDraft.user_id == user_id
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
        select(_model_AgentRun.id)
        .where(
            _owned_agent_run_condition(user_id, character_ids),
            _model_AgentRun.status.in_(routine_constants.ACTIVE_RUN_STATUSES),
        )
        .limit(1)
    )
    if active_run_id is not None:
        raise AccountDeletionBusyError("Agent run is running")

    running_slot_id = db.scalar(
        select(_model_AgentSlot.agent_id)
        .where(
            _owned_agent_slot_condition(user_id, character_ids),
            _model_AgentSlot.status == routine_constants.SLOT_STATUS_RUNNING,
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
            select(_model_AgentSlot)
            .where(_owned_agent_slot_condition(user_id, character_ids))
            .order_by(_model_AgentSlot.agent_id.asc())
        )
    )
    for slot in slots:
        if slot.status == routine_constants.SLOT_STATUS_RUNNING:
            raise AccountDeletionBusyError("Resident slot is running")
        if (
            slot.assigned_user_id is None
            or slot.assigned_character_id is None
            or slot.assigned_credential_id is None
        ):
            continue
        credential = db.get(_model_LlmCredential, slot.assigned_credential_id)
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
            select(_model_AgentSlot)
            .where(_owned_agent_slot_condition(user_id, character_ids))
            .order_by(_model_AgentSlot.agent_id.asc())
        )
    )
    for slot in slots:
        if slot.status == routine_constants.SLOT_STATUS_RUNNING:
            raise AccountDeletionBusyError("Resident slot is running")
        slot.status = routine_constants.SLOT_STATUS_EMPTY
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
    user: _model_User,
    characters: list[_model_Character],
    character_ids: list[str],
) -> None:
    now = auth_service._utcnow()
    character_condition = _character_id_condition

    from app.runtime.world_characters import cleanup as world_character_setup

    from app.runtime.memory_privacy import scrub_memory_data

    scrub_memory_data(db, owner_id=user.id)
    db.execute(
        delete(_model_SocialActionSubjectiveContext).where(
            _model_SocialActionSubjectiveContext.owner_id == user.id
        )
    )
    world_character_setup.delete_setup_data_for_characters(
        db, character_ids=character_ids
    )

    db.execute(
        delete(_model_ProfileImageCandidate).where(
            or_(
                _model_ProfileImageCandidate.user_id == user.id,
                character_condition(
                    _model_ProfileImageCandidate.character_id, character_ids
                ),
            )
        )
    )
    db.execute(
        delete(_model_ProfileImageQuotaReservation).where(
            _model_ProfileImageQuotaReservation.user_id == user.id
        )
    )
    db.execute(
        delete(_model_AgentCreationDraft).where(
            _model_AgentCreationDraft.user_id == user.id
        )
    )

    message_thread_ids = select(_model_MessageThread.id).where(
        or_(
            _model_MessageThread.requester_id == user.id,
            character_condition(_model_MessageThread.character_id, character_ids),
        )
    )
    db.execute(
        delete(_model_MessageMessage).where(
            _model_MessageMessage.thread_id.in_(message_thread_ids)
        )
    )
    db.execute(
        delete(_model_MessageThread).where(
            or_(
                _model_MessageThread.requester_id == user.id,
                character_condition(_model_MessageThread.character_id, character_ids),
            )
        )
    )
    db.execute(
        delete(_model_UserMessagePreference).where(
            _model_UserMessagePreference.user_id == user.id
        )
    )
    db.execute(
        delete(_model_CharacterMessageSetting).where(
            character_condition(
                _model_CharacterMessageSetting.character_id, character_ids
            )
        )
    )

    lore_source_ids = select(_model_CharacterLoreSource.id).where(
        or_(
            _model_CharacterLoreSource.owner_id == user.id,
            character_condition(_model_CharacterLoreSource.character_id, character_ids),
        )
    )
    db.execute(
        delete(_model_CharacterLoreChunk).where(
            or_(
                _model_CharacterLoreChunk.owner_id == user.id,
                character_condition(
                    _model_CharacterLoreChunk.character_id, character_ids
                ),
                _model_CharacterLoreChunk.source_id.in_(lore_source_ids),
            )
        )
    )
    db.execute(
        delete(_model_CharacterLoreSource).where(
            or_(
                _model_CharacterLoreSource.owner_id == user.id,
                character_condition(
                    _model_CharacterLoreSource.character_id, character_ids
                ),
            )
        )
    )

    db.execute(
        delete(_model_PostImageGenerationJob).where(
            or_(
                _model_PostImageGenerationJob.user_id == user.id,
                character_condition(
                    _model_PostImageGenerationJob.character_id, character_ids
                ),
            )
        )
    )
    db.execute(
        delete(_model_PostImageQuotaReservation).where(
            or_(
                _model_PostImageQuotaReservation.user_id == user.id,
                character_condition(
                    _model_PostImageQuotaReservation.character_id, character_ids
                ),
            )
        )
    )
    db.execute(
        delete(_model_AgentPublicActionExecution).where(
            character_condition(
                _model_AgentPublicActionExecution.character_id, character_ids
            )
        )
    )
    db.execute(
        delete(_model_AgentDaypartMemoryEvent).where(
            character_condition(
                _model_AgentDaypartMemoryEvent.character_id, character_ids
            )
        )
    )
    db.execute(
        delete(_model_AgentRelationshipPoint).where(
            or_(
                character_condition(
                    _model_AgentRelationshipPoint.recipient_character_id,
                    character_ids,
                ),
                character_condition(
                    _model_AgentRelationshipPoint.source_character_id,
                    character_ids,
                ),
            )
        )
    )

    db.execute(delete(_model_AuthSession).where(_model_AuthSession.user_id == user.id))
    db.execute(
        delete(_model_AgentFeedCue).where(
            or_(
                _model_AgentFeedCue.user_id == user.id,
                character_condition(_model_AgentFeedCue.character_id, character_ids),
            )
        )
    )
    db.execute(
        delete(_model_AgentActivityLog).where(
            or_(
                _model_AgentActivityLog.user_id == user.id,
                character_condition(
                    _model_AgentActivityLog.character_id, character_ids
                ),
            )
        )
    )
    db.execute(
        delete(_model_AgentRun).where(
            _owned_agent_run_condition(user.id, character_ids)
        )
    )
    db.execute(
        delete(_model_PostReport).where(_model_PostReport.reporter_user_id == user.id)
    )
    db.execute(
        delete(_model_PostLike).where(
            or_(
                _model_PostLike.user_id == user.id,
                character_condition(_model_PostLike.character_id, character_ids),
            )
        )
    )
    db.execute(
        delete(_model_PostRepost).where(
            or_(
                _model_PostRepost.user_id == user.id,
                character_condition(_model_PostRepost.character_id, character_ids),
            )
        )
    )
    db.execute(
        delete(_model_ProfileFollow).where(
            or_(
                _model_ProfileFollow.follower_user_id == user.id,
                _model_ProfileFollow.target_user_id == user.id,
                character_condition(
                    _model_ProfileFollow.follower_character_id, character_ids
                ),
                character_condition(
                    _model_ProfileFollow.target_character_id, character_ids
                ),
            )
        )
    )
    db.execute(
        delete(_model_Notification).where(
            or_(
                _model_Notification.recipient_user_id == user.id,
                _model_Notification.actor_user_id == user.id,
                character_condition(
                    _model_Notification.recipient_character_id, character_ids
                ),
                character_condition(
                    _model_Notification.actor_character_id, character_ids
                ),
            )
        )
    )
    db.execute(
        update(_model_Post)
        .where(_model_Post.author_user_id == user.id)
        .values(author_name=DELETED_USER_DISPLAY_NAME)
    )
    if character_ids:
        db.execute(
            update(_model_Post)
            .where(_model_Post.author_character_id.in_(character_ids))
            .values(author_name=DELETED_CHARACTER_NAME)
        )
        db.execute(
            delete(_model_CharacterState).where(
                _model_CharacterState.character_id.in_(character_ids)
            )
        )
        db.execute(
            delete(_model_AgentImageGenerationSetting).where(
                _model_AgentImageGenerationSetting.character_id.in_(character_ids)
            )
        )

    db.execute(
        delete(_model_AgentActivitySetting).where(
            character_condition(_model_AgentActivitySetting.character_id, character_ids)
        )
    )

    db.execute(
        delete(_model_LlmCredential).where(
            or_(
                _model_LlmCredential.owner_id == user.id,
                character_condition(_model_LlmCredential.character_id, character_ids),
            )
        )
    )
    db.execute(
        delete(_model_AgentLocalKey).where(
            or_(
                _model_AgentLocalKey.owner_id == user.id,
                character_condition(_model_AgentLocalKey.character_id, character_ids),
            )
        )
    )
    operation_repository.scrub_user_attribution(db, user.id)
    db.execute(
        update(_model_Character)
        .where(_model_Character.moderation_updated_by_user_id == user.id)
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
        _model_AgentRun.user_id == user_id,
        _character_id_condition(_model_AgentRun.character_id, character_ids),
    )

def _owned_agent_slot_condition(user_id: str, character_ids: list[str]):
    return or_(
        _model_AgentSlot.assigned_user_id == user_id,
        _character_id_condition(_model_AgentSlot.assigned_character_id, character_ids),
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
        select(_model_Character.id).where(
            _model_Character.handle == candidate,
            _model_Character.id != character_id,
        )
    ):
        suffix_text = f"_{index}"
        candidate = f"{base[: 40 - len(suffix_text)]}{suffix_text}"
        index += 1
    return candidate
