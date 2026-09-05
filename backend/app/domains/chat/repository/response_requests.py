"""Read the active or latest durable request in the caller's transaction."""

from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.domains.chat import models
from app.domains.chat.contracts.generation_lifecycle import TERMINAL_STATES


def _active_request(db: Session, thread_id: str) -> models.ChatResponseRequest | None:
    return db.scalar(
        select(models.ChatResponseRequest)
        .where(
            models.ChatResponseRequest.thread_id == thread_id,
            models.ChatResponseRequest.state.not_in(
                tuple(state.value for state in TERMINAL_STATES)
            ),
        )
        .order_by(models.ChatResponseRequest.created_at.desc())
        .limit(1)
    )


def _latest_request_row(
    db: Session,
    thread_id: str,
) -> models.ChatResponseRequest | None:
    return db.scalar(
        select(models.ChatResponseRequest)
        .where(models.ChatResponseRequest.thread_id == thread_id)
        .order_by(
            models.ChatResponseRequest.created_at.desc(),
            models.ChatResponseRequest.attempt_number.desc(),
        )
        .limit(1)
    )
