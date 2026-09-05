from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.domains.routines import models
from app.domains.routines.constants import ACTIVE_RUN_STATUSES


def get_active_run_for_session(
    db: Session, session_key: str
) -> models.AgentRun | None:
    return db.scalar(
        select(models.AgentRun)
        .where(
            models.AgentRun.session_key == session_key,
            models.AgentRun.status.in_(ACTIVE_RUN_STATUSES),
        )
        .order_by(models.AgentRun.created_at.desc(), models.AgentRun.id.desc())
    )


def get_active_run_for_tool_auth_key(
    db: Session, tool_auth_key: str
) -> models.AgentRun | None:
    return db.scalar(
        select(models.AgentRun)
        .where(
            models.AgentRun.tool_auth_key == tool_auth_key,
            models.AgentRun.status.in_(ACTIVE_RUN_STATUSES),
        )
        .order_by(models.AgentRun.created_at.desc(), models.AgentRun.id.desc())
    )


def get_latest_run_for_session(
    db: Session, session_key: str
) -> models.AgentRun | None:
    return db.scalar(
        select(models.AgentRun)
        .where(models.AgentRun.session_key == session_key)
        .order_by(models.AgentRun.created_at.desc(), models.AgentRun.id.desc())
    )


def get_latest_run_for_tool_auth_key(
    db: Session, tool_auth_key: str
) -> models.AgentRun | None:
    return db.scalar(
        select(models.AgentRun)
        .where(models.AgentRun.tool_auth_key == tool_auth_key)
        .order_by(models.AgentRun.created_at.desc(), models.AgentRun.id.desc())
    )


def get_latest_manual_run_for_user(
    db: Session, user_id: str
) -> models.AgentRun | None:
    return db.scalar(
        select(models.AgentRun)
        .where(
            models.AgentRun.user_id == user_id,
            models.AgentRun.session_key.contains(":resident-manual:"),
        )
        .order_by(models.AgentRun.created_at.desc(), models.AgentRun.id.desc())
    )


def get_latest_first_greeting_run_for_user(
    db: Session, user_id: str
) -> models.AgentRun | None:
    return db.scalar(
        select(models.AgentRun)
        .where(
            models.AgentRun.user_id == user_id,
            models.AgentRun.session_key.contains(":first-greeting:"),
        )
        .order_by(models.AgentRun.created_at.desc(), models.AgentRun.id.desc())
    )
