from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.domains.routines import models


def get_public_action_execution_by_signature(
    db: Session, signature: str
) -> models.AgentPublicActionExecution | None:
    return db.scalar(
        select(models.AgentPublicActionExecution).where(
            models.AgentPublicActionExecution.signature == signature
        )
    )
