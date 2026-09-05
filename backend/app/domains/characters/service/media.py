"""Character media ownership, private previews and candidate application.

File operations keep their original order relative to database commits. Runtime
callbacks participate in the same Session for activity and visual-identity work.
"""
from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.domains.characters import models as character_models, schemas, exceptions as errors
from app.domains.characters.contracts import CharacterOwner, CreatorWorkflows, CharacterMediaWorkflows
from app.domains.characters.exceptions import (
    AgentCreationDraftNotFoundError,
    AgentProfileImageCandidateNotFoundError,
    AgentProfileImageCandidateExpiredError,
    AgentPrivateMediaNotFoundError,
    InvalidProfileMediaError,
)
from app.domains.characters.service import drafts as draft_lifecycle
from app.domains.characters.service import profile as character_profile
from app.domains.characters.service import media_storage as profile_media
from app.domains.characters.service.access import _get_owned_character
from app.domains.characters.service.creator import _draft_read
from app.domains.characters.service.image_quota import _profile_image_usage_read, _finalize_profile_image_quota
from app.domains.identity.service import demo_access as demo_lock
from app.integrations.media import files as media_files


def get_draft_media_content(
    db: Session,
    user: CharacterOwner,
    draft_id: str,
    media_type: str,
    *, workflows: CreatorWorkflows,
):
    if media_type not in {"avatar", "banner"}:
        raise AgentPrivateMediaNotFoundError(media_type)
    draft = draft_lifecycle._get_owned_draft(db, user, draft_id, workflows=workflows)
    media_url = (
        draft.avatar_temp_url if media_type == "avatar" else draft.banner_temp_url
    )
    if media_url is None:
        raise AgentPrivateMediaNotFoundError(media_type)
    try:
        return media_files.resolve_private_media_file(
            media_url,
            expected_directory="drafts",
        )
    except profile_media.InvalidProfileMediaError as exc:
        raise AgentPrivateMediaNotFoundError(media_type) from exc


def get_draft_candidate_content(
    db: Session,
    user: CharacterOwner,
    draft_id: str,
    candidate_id: str,
    *, workflows: CreatorWorkflows,
):
    draft = draft_lifecycle._get_owned_draft(db, user, draft_id, workflows=workflows)
    candidate = _get_owned_profile_image_candidate(
        db,
        user=user,
        candidate_id=candidate_id,
        scope="create",
        draft_id=draft.id,
        character_id=None,
    )
    try:
        return media_files.resolve_private_media_file(
            candidate.url,
            expected_directory="profile-candidates",
        )
    except profile_media.InvalidProfileMediaError as exc:
        raise AgentProfileImageCandidateNotFoundError(candidate_id) from exc


def get_profile_candidate_content(
    db: Session,
    user: CharacterOwner,
    character_id: str,
    candidate_id: str,
):
    character = character_profile.get_character(db, character_id)
    if (
        character is None
        or character.owner_id != user.id
        or character.deleted_at is not None
    ):
        raise errors.AgentNotFoundError(character_id)
    candidate = _get_owned_profile_image_candidate(
        db,
        user=user,
        candidate_id=candidate_id,
        scope="profile",
        draft_id=None,
        character_id=character.id,
    )
    try:
        return media_files.resolve_private_media_file(
            candidate.url,
            expected_directory="profile-candidates",
        )
    except profile_media.InvalidProfileMediaError as exc:
        raise AgentProfileImageCandidateNotFoundError(candidate_id) from exc


def upload_draft_media(
    db: Session,
    user: CharacterOwner,
    draft_id: str,
    data: schemas.AgentCreationDraftMediaUpload,
    *, workflows: CreatorWorkflows,
) -> schemas.AgentCreationDraftRead:
    draft = draft_lifecycle._get_owned_draft(db, user, draft_id, workflows=workflows)
    url = profile_media.save_draft_profile_media(
        draft_id=draft.id,
        media_type=data.media_type,
        content_type=data.content_type,
        data_base64=data.data_base64,
    )
    if data.media_type == "avatar":
        draft.avatar_temp_url = url
    else:
        draft.banner_temp_url = url
    db.commit()
    db.refresh(draft)
    return _draft_read(draft)


def get_draft_profile_image_usage(
    db: Session, user: CharacterOwner, draft_id: str,
    *, workflows: CreatorWorkflows,
) -> schemas.AgentProfileImageUsageRead:
    _ = draft_lifecycle._get_owned_draft(db, user, draft_id, workflows=workflows)
    return _profile_image_usage_read(db, user=user, scope="create")


def get_agent_profile_image_usage(
    db: Session, user: CharacterOwner, character_id: str
) -> schemas.AgentProfileImageUsageRead:
    character = character_profile.get_character(db, character_id)
    if (
        character is None
        or character.owner_id != user.id
        or character.deleted_at is not None
    ):
        raise errors.AgentNotFoundError(character_id)
    return _profile_image_usage_read(db, user=user, scope="profile")


def apply_draft_media_candidate(
    db: Session,
    user: CharacterOwner,
    draft_id: str,
    candidate_id: str,
    *, workflows: CreatorWorkflows,
) -> schemas.AgentCreationDraftRead:
    draft = draft_lifecycle._get_owned_draft(db, user, draft_id, workflows=workflows)
    candidate = _get_owned_profile_image_candidate(
        db,
        user=user,
        candidate_id=candidate_id,
        scope="create",
        draft_id=draft.id,
        character_id=None,
    )
    source_path = media_files.media_url_to_path(candidate.url)
    content = source_path.read_bytes()
    url = profile_media.save_draft_profile_media_bytes(
        draft_id=draft.id,
        media_type=candidate.media_type,
        content_type="image/webp",
        content=content,
    )
    if candidate.media_type == "avatar":
        draft.avatar_temp_url = url
    else:
        draft.banner_temp_url = url
    candidate_id = candidate.id
    _finalize_profile_image_quota(
        db,
        reservation_id=candidate.quota_reservation_id,
        status="applied",
        candidate_id=candidate_id,
    )
    db.delete(candidate)
    db.commit()
    db.refresh(draft)
    profile_media.delete_profile_image_candidate(candidate_id, user.id)
    return _draft_read(draft)


def apply_profile_media_candidate(
    db: Session,
    user: CharacterOwner,
    character_id: str,
    candidate_id: str,
    *, workflows: CharacterMediaWorkflows,
) -> schemas.AgentDetailRead:
    character = character_profile.get_character(db, character_id)
    if (
        character is None
        or character.owner_id != user.id
        or character.deleted_at is not None
    ):
        raise errors.AgentNotFoundError(character_id)
    demo_lock.ensure_demo_user_mutable(user)
    candidate = _get_owned_profile_image_candidate(
        db,
        user=user,
        candidate_id=candidate_id,
        scope="profile",
        draft_id=None,
        character_id=character.id,
    )
    url = profile_media.promote_profile_image_candidate(
        character_id=character.id,
        media_type=candidate.media_type,
        candidate_media_url=candidate.url,
    )
    if candidate.media_type == "avatar":
        character.avatar_url = url
    else:
        character.banner_url = url
    workflows.invalidate_visual_identity(db, character.id)
    candidate_id = candidate.id
    _finalize_profile_image_quota(
        db,
        reservation_id=candidate.quota_reservation_id,
        status="applied",
        candidate_id=candidate_id,
    )
    db.delete(candidate)
    workflows.log_activity(
        db,
        user_id=user.id,
        character_id=character.id,
        action_type="profile_updated",
        target_post_id=None,
        reason=f"user_applied_generated_{candidate.media_type}",
        result=f"Agent {candidate.media_type} image candidate was applied.",
    )
    db.commit()
    db.refresh(character)
    profile_media.delete_profile_image_candidate(candidate_id, user.id)
    return workflows.build_detail(db, character)


def discard_draft_media_candidate(
    db: Session,
    user: CharacterOwner,
    draft_id: str,
    candidate_id: str,
    *, workflows: CreatorWorkflows,
) -> None:
    draft = draft_lifecycle._get_owned_draft(db, user, draft_id, workflows=workflows)
    candidate = _get_owned_profile_image_candidate(
        db,
        user=user,
        candidate_id=candidate_id,
        scope="create",
        draft_id=draft.id,
        character_id=None,
    )
    profile_media.delete_profile_image_candidate(candidate.id, user.id)
    db.delete(candidate)
    db.commit()


def discard_profile_media_candidate(
    db: Session,
    user: CharacterOwner,
    character_id: str,
    candidate_id: str,
) -> None:
    character = character_profile.get_character(db, character_id)
    if (
        character is None
        or character.owner_id != user.id
        or character.deleted_at is not None
    ):
        raise errors.AgentNotFoundError(character_id)
    candidate = _get_owned_profile_image_candidate(
        db,
        user=user,
        candidate_id=candidate_id,
        scope="profile",
        draft_id=None,
        character_id=character.id,
    )
    profile_media.delete_profile_image_candidate(candidate.id, user.id)
    db.delete(candidate)
    db.commit()


def _get_owned_profile_image_candidate(
    db: Session,
    *,
    user: CharacterOwner,
    candidate_id: str,
    scope: str,
    draft_id: str | None,
    character_id: str | None,
) -> character_models.ProfileImageCandidate:
    candidate = db.get(character_models.ProfileImageCandidate, candidate_id)
    if (
        candidate is None
        or candidate.user_id != user.id
        or candidate.scope != scope
        or candidate.applied_at is not None
    ):
        raise AgentProfileImageCandidateNotFoundError(candidate_id)
    if draft_id is not None and candidate.draft_id != draft_id:
        raise AgentProfileImageCandidateNotFoundError(candidate_id)
    if character_id is not None and candidate.character_id != character_id:
        raise AgentProfileImageCandidateNotFoundError(candidate_id)
    expires_at = candidate.expires_at
    if expires_at.tzinfo is None:
        expires_at = expires_at.replace(tzinfo=UTC)
    if expires_at < datetime.now(UTC):
        profile_media.delete_profile_image_candidate(candidate.id, user.id)
        raise AgentProfileImageCandidateExpiredError(candidate_id)
    if not media_files.media_url_to_path(candidate.url).is_file():
        raise AgentProfileImageCandidateNotFoundError(candidate_id)
    return candidate


def _cleanup_expired_profile_image_candidates(db: Session, user_id: str) -> None:
    now = datetime.now(UTC)
    candidates = list(
        db.scalars(
            select(character_models.ProfileImageCandidate)
            .where(character_models.ProfileImageCandidate.user_id == user_id)
            .where(character_models.ProfileImageCandidate.expires_at < now)
            .limit(50)
        )
    )
    if not candidates:
        return
    for candidate in candidates:
        profile_media.delete_profile_image_candidate(candidate.id, user_id)
        db.delete(candidate)
    db.commit()


def upload_profile_media(
    db: Session,
    user: CharacterOwner,
    character_id: str,
    data: schemas.AgentProfileMediaUpload,
    *, workflows: CharacterMediaWorkflows,
) -> schemas.AgentDetailRead:
    character = _get_owned_character(db, user, character_id)
    demo_lock.ensure_demo_user_mutable(user)
    try:
        url = profile_media.save_profile_media(
            character_id=character.id,
            media_type=data.media_type,
            content_type=data.content_type,
            data_base64=data.data_base64,
        )
    except profile_media.InvalidProfileMediaError as exc:
        raise InvalidProfileMediaError(str(exc)) from exc

    if data.media_type == "avatar":
        character.avatar_url = url
    else:
        character.banner_url = url
    workflows.invalidate_visual_identity(db, character.id)
    db.commit()
    workflows.log_activity(
        db,
        user_id=user.id,
        character_id=character.id,
        action_type="profile_updated",
        target_post_id=None,
        reason=f"user_uploaded_{data.media_type}",
        result=f"Agent {data.media_type} image was uploaded.",
    )
    db.refresh(character)
    return workflows.build_detail(db, character)
