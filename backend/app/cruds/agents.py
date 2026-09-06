from app.domains.local_bot.repository.keys import get_active_local_key, get_active_local_key_by_hash, get_latest_local_key
from app.domains.local_bot.service.key_records import create_local_key, mark_local_key_used, revoke_active_local_key
from app.domains.identity.repository.credentials import get_character_credential
from app.domains.identity.service.character_credentials import default_auth_profile_id, default_credential_model, upsert_credential
from datetime import UTC, datetime, timedelta
from uuid import uuid4

from sqlalchemy import select
from sqlalchemy.orm import Session

from app import schemas
from app.domains.routines.models.resident import AgentActivitySetting as _model_AgentActivitySetting
from app.domains.routines.models.resident import AgentFeedCue as _model_AgentFeedCue
from app.domains.routines.models.resident import AgentSlot as _model_AgentSlot
from app.domains.characters.models import Character as _model_Character
from app.domains.identity.models import User as _model_User
from app.runtime.persistence.model_registration import register_models
register_models()
from app.core.image_generation import (
    DEFAULT_USER_IMAGE_MODEL,
    DEFAULT_MAX_IMAGES_PER_DAY,
)
from app.core import security
from app.core import active_hours
from app.core import unit_of_work












































def get_pending_feed_cue(db: Session, character_id: str) -> _model_AgentFeedCue | None:
    return db.scalar(
        select(_model_AgentFeedCue)
        .where(
            _model_AgentFeedCue.character_id == character_id,
            _model_AgentFeedCue.status == "pending",
        )
        .order_by(_model_AgentFeedCue.created_at.asc(), _model_AgentFeedCue.id.asc())
        .limit(1)
    )


def create_feed_cue(
    db: Session, *, user: _model_User, character: _model_Character, topic: str
) -> _model_AgentFeedCue:
    cue = _model_AgentFeedCue(
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
) -> _model_AgentFeedCue | None:
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
) -> _model_AgentSlot | None:
    return db.scalar(
        select(_model_AgentSlot)
        .where(_model_AgentSlot.assigned_character_id == character_id)
        .order_by(
            (_model_AgentSlot.status == "running").desc(),
            _model_AgentSlot.last_run_at.desc().nullslast(),
            _model_AgentSlot.updated_at.desc(),
            _model_AgentSlot.agent_id.asc(),
        )
    )


def set_character_status(db: Session, character: _model_Character, status: str) -> None:
    character.status = status
    db.commit()


def disable_other_active_settings(
    db: Session,
    *,
    user_id: str,
    keep_character_id: str,
    commit: bool = True,
) -> list[_model_AgentActivitySetting]:
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
) -> list[_model_AgentActivitySetting]:
    settings = list(
        db.scalars(
            select(_model_AgentActivitySetting)
            .join(_model_Character)
            .where(
                _model_Character.owner_id == user_id,
                _model_Character.deleted_at.is_(None),
                _model_Character.id != keep_character_id,
                _model_AgentActivitySetting.auto_enabled.is_(True),
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
            select(_model_Character.id)
            .join(_model_AgentActivitySetting)
            .where(
                _model_Character.execution_mode == "llm",
                _model_Character.deleted_at.is_(None),
                _model_Character.moderation_status != "suspended",
                _model_AgentActivitySetting.auto_enabled.is_(True),
            )
        )
    )
    assigned_slot_ids = set(
        db.scalars(
            select(_model_AgentSlot.assigned_character_id)
            .join(
                _model_Character,
                _model_Character.id == _model_AgentSlot.assigned_character_id,
            )
            .where(
                _model_AgentSlot.assigned_character_id.is_not(None),
                _model_Character.execution_mode == "llm",
                _model_Character.deleted_at.is_(None),
                _model_Character.moderation_status != "suspended",
            )
        )
    )
    return len((auto_enabled_ids | assigned_slot_ids) - excluded)

from app.domains.routines.constants import HIDDEN_ACTIVITY_ACTION_TYPES, STATE_SAVE_DEDUPE_WINDOW
from app.domains.routines.service.activity_logs import filter_visible_activity_logs, list_recent_activity, log_activity
from app.domains.routines.service.activity_settings import get_setting, ensure_setting, update_setting
