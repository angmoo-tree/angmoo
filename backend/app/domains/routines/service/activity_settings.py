"""Activity-setting defaults and explicit commit/flush update modes."""
from sqlalchemy.orm import Session
from app.core import active_hours
from app.domains.routines import models, schemas
from app.domains.routines.constants import DEFAULT_MAX_COMMENTS_PER_DAY, DEFAULT_MAX_POSTS_PER_DAY


def get_setting(db: Session, character_id: str) -> models.AgentActivitySetting | None:
    return db.get(models.AgentActivitySetting, character_id)


def ensure_setting(
    db: Session,
    character_id: str,
    *,
    commit: bool = True,
) -> models.AgentActivitySetting:
    setting = get_setting(db, character_id)
    if setting is not None:
        return setting
    setting = models.AgentActivitySetting(
        character_id=character_id,
        auto_enabled=False,
        activity_level="normal",
        activity_interval_minutes=60,
        comment_cooldown_minutes=180,
        max_comments_per_day=DEFAULT_MAX_COMMENTS_PER_DAY,
        post_cooldown_hours=24,
        max_posts_per_day=DEFAULT_MAX_POSTS_PER_DAY,
        like_policy="normal",
        allow_post=True,
        allow_reply=True,
        allow_like=True,
        allow_repost=True,
        allow_follow=True,
        allow_unfollow=True,
        allow_observe=True,
        tendency_summary="",
        tendency_action_ranges={},
        planner_tendency_profile={},
        tendency_error=None,
        active_hours_start=active_hours.DEFAULT_ACTIVE_HOURS_START,
        active_hours_end=active_hours.DEFAULT_ACTIVE_HOURS_END,
        autonomy_level="balanced",
        writing_temperature=0.6,
        writing_presence_penalty=0.3,
        writing_repetition_level="light",
    )
    db.add(setting)
    if commit:
        db.commit()
        db.refresh(setting)
    else:
        db.flush()
    return setting


def update_setting(
    db: Session,
    setting: models.AgentActivitySetting,
    data: schemas.AgentActivitySettingUpdate,
    *,
    commit: bool = True,
) -> models.AgentActivitySetting:
    for field, value in data.model_dump(exclude_unset=True).items():
        if value is not None:
            setattr(setting, field, value)
    if commit:
        db.commit()
        db.refresh(setting)
    else:
        db.flush()
    return setting
