from __future__ import annotations

from datetime import datetime
from sqlalchemy.orm import Session
from app.domains.routines import models
from app.domains.routines.contracts.activity_policy import ActivityTimezoneReader
from app.domains.routines.service import activity_settings as agent_crud
from app.domains.routines.service import tick_schedule as agent_activity_policy


def _scheduled_retry_next_tick_at(
    db: Session,
    *,
    setting: models.AgentActivitySetting | None,
    character_id: str,
    retry_at: datetime,
    manual_next_tick_at: datetime | None,
    timezone_reader: ActivityTimezoneReader,
) -> datetime:
    if manual_next_tick_at is not None:
        return manual_next_tick_at
    if not character_id:
        return retry_at
    effective_setting = setting or agent_crud.ensure_setting(db, character_id)
    return agent_activity_policy.retry_tick_schedule(
        effective_setting,
        character_id=character_id,
        retry_at=retry_at,
        timezone=timezone_reader(
            db, character_id=character_id
        ),
    ).next_tick_at
