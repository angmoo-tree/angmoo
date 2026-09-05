from __future__ import annotations

from datetime import datetime

from sqlalchemy import ScalarResult, or_, select
from sqlalchemy.orm import Session

from app.domains.routines import models
from app.domains.routines.constants import MODEL_OVERLOADED_REPEAT_WINDOW


def recent_runs_for_model_overload(
    db: Session,
    *,
    now: datetime,
    character_id: str | None,
    credential_id: str | None,
) -> ScalarResult[models.AgentRun]:
    filters = []
    if character_id:
        filters.append(models.AgentRun.character_id == character_id)
    if credential_id:
        filters.append(models.AgentRun.credential_id == credential_id)
    return db.scalars(
        select(models.AgentRun)
        .where(
            or_(*filters),
            models.AgentRun.created_at >= now - MODEL_OVERLOADED_REPEAT_WINDOW,
            models.AgentRun.created_at < now,
        )
        .order_by(models.AgentRun.created_at.desc(), models.AgentRun.id.desc())
        .limit(30)
    )
