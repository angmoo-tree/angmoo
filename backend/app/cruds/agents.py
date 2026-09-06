from app.domains.routines.repository.slots import get_assigned_slot
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



from app.domains.routines.constants import HIDDEN_ACTIVITY_ACTION_TYPES, STATE_SAVE_DEDUPE_WINDOW
from app.domains.routines.service.activity_logs import filter_visible_activity_logs, list_recent_activity, log_activity
from app.domains.routines.service.activity_settings import get_setting, ensure_setting, update_setting
