"""Activity summary and log target presentation; profile SQL stays with its owner."""
from datetime import datetime
import re
from typing import Iterable
from sqlalchemy.orm import Session
from app.domains.routines import models, schemas
from app.domains.routines.contracts.activity_management import ActivityCharacter
from app.domains.routines.contracts.activity_policy import ActivityPolicy
from app.domains.routines.contracts.activity_presentation import ActivityPresentationReads

def _visible_activity_actions(actions: Iterable[str]) -> list[str]:
    return [action for action in actions if action != "observe"]


def _activity_log_read(
    db: Session, log: models.AgentActivityLog, *, reads: ActivityPresentationReads
) -> schemas.AgentActivityLogRead:
    data = schemas.AgentActivityLogRead.model_validate(log).model_dump()
    target = _activity_log_target_profile(db, log, reads=reads)
    if target is not None:
        data.update(target)
    return schemas.AgentActivityLogRead.model_validate(data)


def _activity_log_target_profile(
    db: Session, log: models.AgentActivityLog, *, reads: ActivityPresentationReads
) -> dict[str, str | None] | None:
    if log.action_type not in {"followed", "unfollowed"}:
        return None
    match = re.search(r"\b(user|character):([A-Za-z0-9_-]+)", log.result)
    if match is None:
        return None
    profile_type, profile_id = match.group(1), match.group(2)
    if profile_type == "character":
        character = reads.get_character(db, profile_id)
        if character is None:
            return None
        return {
            "target_profile_type": "character",
            "target_profile_id": character.id,
            "target_profile_name": character.name,
            "target_profile_handle": character.handle,
            "target_profile_avatar_url": character.avatar_url,
        }
    user = reads.get_user(db, profile_id)
    if user is None:
        return None
    return {
        "target_profile_type": "user",
        "target_profile_id": user.id,
        "target_profile_name": user.display_name,
        "target_profile_handle": None,
        "target_profile_avatar_url": None,
    }


def build_activity_summary(
    db: Session, *, character: ActivityCharacter,
    setting: models.AgentActivitySetting, slot: models.AgentSlot | None,
    policy: ActivityPolicy, last_activity_at: datetime | None,
    manual_run_available_at: datetime | None,
    first_greeting_available_at: datetime | None,
    reads: ActivityPresentationReads,
) -> schemas.AgentActivitySummaryRead:
    return schemas.AgentActivitySummaryRead(
        within_active_hours=policy.within_active_hours,
        timezone=reads.activity_timezone_name(
            db, character_id=character.id
        ),
        allowed_actions=_visible_activity_actions(policy.allowed_actions),
        blocked_reasons=policy.blocked_reasons,
        last_activity_at=last_activity_at,
        next_activity_at=(
            slot.next_tick_at if slot is not None and setting.auto_enabled else None
        ),
        manual_run_available_at=manual_run_available_at,
        first_greeting_available_at=first_greeting_available_at,
        today_comment_count=reads.count_action_today(
            db, character_id=character.id, action="comment"
        ),
        max_comments_per_day=setting.max_comments_per_day,
        today_post_count=reads.count_action_today(
            db, character_id=character.id, action="post"
        ),
        max_posts_per_day=setting.max_posts_per_day,
        today_like_count=reads.count_action_today(
            db, character_id=character.id, action="like"
        ),
    )
