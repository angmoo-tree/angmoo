from app.domains.local_bot.repository.keys import get_active_local_key, get_active_local_key_by_hash, get_latest_local_key
from app.domains.local_bot.service.key_records import create_local_key, mark_local_key_used, revoke_active_local_key
from app.domains.identity.repository.credentials import get_character_credential
from app.domains.identity.service.character_credentials import default_auth_profile_id, default_credential_model, upsert_credential
from datetime import UTC, datetime, timedelta
from uuid import uuid4

from sqlalchemy import select
from sqlalchemy.orm import Session

from app import models, schemas
from app.core.image_generation import (
    DEFAULT_USER_IMAGE_MODEL,
    DEFAULT_MAX_IMAGES_PER_DAY,
)
from app.core import security
from app.core import active_hours
from app.core import unit_of_work












































def get_pending_feed_cue(db: Session, character_id: str) -> models.AgentFeedCue | None:
    return db.scalar(
        select(models.AgentFeedCue)
        .where(
            models.AgentFeedCue.character_id == character_id,
            models.AgentFeedCue.status == "pending",
        )
        .order_by(models.AgentFeedCue.created_at.asc(), models.AgentFeedCue.id.asc())
        .limit(1)
    )


def create_feed_cue(
    db: Session, *, user: models.User, character: models.Character, topic: str
) -> models.AgentFeedCue:
    cue = models.AgentFeedCue(
        user_id=user.id,
        character_id=character.id,
        topic=topic.strip(),
        status="pending",
    )
    db.add(cue)
    db.commit()
    db.refresh(cue)
    return cue


def mark_pending_feed_cue_used(
    db: Session, *, character_id: str, run_id: str | None, post_id: str
) -> models.AgentFeedCue | None:
    cue = get_pending_feed_cue(db, character_id)
    if cue is None:
        return None
    cue.status = "used"
    cue.consumed_run_id = run_id
    cue.consumed_post_id = post_id
    cue.consumed_at = datetime.now(UTC)
    db.commit()
    db.refresh(cue)
    return cue




def get_assigned_slot(
    db: Session, character_id: str
) -> models.AgentSlot | None:
    return db.scalar(
        select(models.AgentSlot)
        .where(models.AgentSlot.assigned_character_id == character_id)
        .order_by(
            (models.AgentSlot.status == "running").desc(),
            models.AgentSlot.last_run_at.desc().nullslast(),
            models.AgentSlot.updated_at.desc(),
            models.AgentSlot.agent_id.asc(),
        )
    )


def set_character_status(db: Session, character: models.Character, status: str) -> None:
    character.status = status
    db.commit()


def disable_other_active_settings(
    db: Session,
    *,
    user_id: str,
    keep_character_id: str,
    commit: bool = True,
) -> list[models.AgentActivitySetting]:
    settings = list_other_active_settings(
        db, user_id=user_id, keep_character_id=keep_character_id
    )
    now = datetime.now(UTC)
    for setting in settings:
        setting.auto_enabled = False
        setting.updated_at = now
    if settings and commit:
        db.commit()
    elif settings:
        db.flush()
    return settings


def list_other_active_settings(
    db: Session, *, user_id: str, keep_character_id: str
) -> list[models.AgentActivitySetting]:
    settings = list(
        db.scalars(
            select(models.AgentActivitySetting)
            .join(models.Character)
            .where(
                models.Character.owner_id == user_id,
                models.Character.deleted_at.is_(None),
                models.Character.id != keep_character_id,
                models.AgentActivitySetting.auto_enabled.is_(True),
            )
        )
    )
    return settings


def count_effective_active_server_llm_autonomy_agents(
    db: Session, *, exclude_character_ids: set[str] | None = None
) -> int:
    excluded = exclude_character_ids or set()
    auto_enabled_ids = set(
        db.scalars(
            select(models.Character.id)
            .join(models.AgentActivitySetting)
            .where(
                models.Character.execution_mode == "llm",
                models.Character.deleted_at.is_(None),
                models.Character.moderation_status != "suspended",
                models.AgentActivitySetting.auto_enabled.is_(True),
            )
        )
    )
    assigned_slot_ids = set(
        db.scalars(
            select(models.AgentSlot.assigned_character_id)
            .join(
                models.Character,
                models.Character.id == models.AgentSlot.assigned_character_id,
            )
            .where(
                models.AgentSlot.assigned_character_id.is_not(None),
                models.Character.execution_mode == "llm",
                models.Character.deleted_at.is_(None),
                models.Character.moderation_status != "suspended",
            )
        )
    )
    return len((auto_enabled_ids | assigned_slot_ids) - excluded)

from app.domains.routines.constants import HIDDEN_ACTIVITY_ACTION_TYPES, STATE_SAVE_DEDUPE_WINDOW
from app.domains.routines.service.activity_logs import filter_visible_activity_logs, list_recent_activity, log_activity
from app.domains.routines.service.activity_settings import get_setting, ensure_setting, update_setting
