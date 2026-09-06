from __future__ import annotations

from datetime import UTC, datetime
from typing import Any
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.domains.routines import models
from app.domains.routines.exceptions import AgentRunConflictError


def create_agent_run(
    db: Session,
    *,
    run_id: str,
    user_id: str,
    character_id: str,
    post_id: str | None,
    credential_id: str | None,
    agent_id: str,
    session_key: str,
    tool_auth_key: str | None = None,
) -> models.AgentRun:
    run = models.AgentRun(
        id=run_id,
        user_id=user_id,
        character_id=character_id,
        post_id=post_id,
        credential_id=credential_id,
        agent_id=agent_id,
        session_key=session_key,
        tool_auth_key=tool_auth_key,
        status="running",
    )
    db.add(run)
    try:
        db.commit()
    except IntegrityError as exc:
        db.rollback()
        raise AgentRunConflictError("An active agent run already exists") from exc
    db.refresh(run)
    return run


def mark_agent_run_finished(
    db: Session,
    run_id: str,
    status: str,
    gateway_result: dict[str, Any] | None = None,
) -> None:
    run = db.get(models.AgentRun, run_id)
    if run is None:
        return
    run.status = status
    run.completed_at = datetime.now(UTC)
    if gateway_result is not None:
        run.gateway_result = gateway_result
    db.commit()


def set_agent_run_post_id(db: Session, run_id: str, post_id: str | None) -> None:
    run = db.get(models.AgentRun, run_id)
    if run is None:
        return
    run.post_id = post_id
    db.commit()
