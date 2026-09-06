"""Chat-owned thread/message queries and transaction-scoped advisory locks.

These operations do not commit, roll back or reinterpret Chat admission errors.
Services keep permission/state decisions and use the caller's Session.
"""

from __future__ import annotations

import hashlib
from sqlalchemy import func, select, text
from sqlalchemy.orm import Session, joinedload

from app.domains.chat import models


def _find_active_world_thread(
    db: Session,
    owner_id: str,
    world_id: str,
    requester_world_character_id: str,
    responding_world_character_id: str,
) -> models.MessageThread | None:
    return db.scalar(
        select(models.MessageThread).where(
            models.MessageThread.requester_id == owner_id,
            models.MessageThread.world_id == world_id,
            models.MessageThread.requester_world_character_id
            == requester_world_character_id,
            models.MessageThread.responding_world_character_id
            == responding_world_character_id,
            models.MessageThread.world_scope_status == "resolved",
            models.MessageThread.deleted_at.is_(None),
        )
    )


def _lock_world_thread_tuple(
    db: Session,
    owner_id: str,
    world_id: str,
    requester_world_character_id: str,
    responding_world_character_id: str,
) -> None:
    if not _is_postgresql_session(db):
        return
    material = ":".join(
        (
            "angmoo-world-chat-thread-v1",
            owner_id,
            world_id,
            requester_world_character_id,
            responding_world_character_id,
        )
    )
    lock_key = int.from_bytes(
        hashlib.sha256(material.encode("utf-8")).digest()[:8],
        byteorder="big",
        signed=True,
    )
    db.execute(text("select pg_advisory_xact_lock(:lock_key)"), {"lock_key": lock_key})


def _lock_message_thread_quota(db: Session, requester_id: str) -> None:
    if not _is_postgresql_session(db):
        return
    lock_key = int.from_bytes(
        hashlib.sha256(
            f"angmoo:message-thread-quota:{requester_id}:v1".encode("utf-8")
        ).digest()[:8],
        byteorder="big",
        signed=True,
    )
    db.execute(
        text("select pg_advisory_xact_lock(:lock_key)"),
        {"lock_key": lock_key},
    )


def _is_postgresql_session(db: Session) -> bool:
    bind = db.get_bind()
    return bind.dialect.name == "postgresql"


def list_world_threads(
    db: Session, requester_id: str, world_id: str
) -> list[models.MessageThread]:
    return db.scalars(
        select(models.MessageThread)
        .where(
            models.MessageThread.requester_id == requester_id,
            models.MessageThread.world_id == world_id,
            models.MessageThread.world_scope_status == "resolved",
            models.MessageThread.deleted_at.is_(None),
        )
        .order_by(
            models.MessageThread.last_message_at.desc().nullslast(),
            models.MessageThread.created_at.desc(),
        )
    ).all()


def count_ambiguous_threads(db: Session, requester_id: str) -> int:
    return (
        db.scalar(
            select(func.count(models.MessageThread.id)).where(
                models.MessageThread.requester_id == requester_id,
                models.MessageThread.world_scope_status.in_(
                    ("ambiguous", "quarantined")
                ),
                models.MessageThread.deleted_at.is_(None),
            )
        )
        or 0
    )


def list_threads(db: Session, requester_id: str) -> list[models.MessageThread]:
    return (
        db.scalars(
            select(models.MessageThread)
            .options(joinedload(models.MessageThread.character))
            .where(models.MessageThread.requester_id == requester_id)
            .where(models.MessageThread.deleted_at.is_(None))
            .order_by(
                models.MessageThread.last_message_at.desc().nullslast(),
                models.MessageThread.created_at.desc(),
            )
        )
        .unique()
        .all()
    )


def find_legacy_thread_candidates(
    db: Session, requester_id: str, character_id: str
) -> list[models.MessageThread]:
    return list(
        db.scalars(
            select(models.MessageThread)
            .where(models.MessageThread.requester_id == requester_id)
            .where(models.MessageThread.character_id == character_id)
            .where(models.MessageThread.deleted_at.is_(None))
            .order_by(models.MessageThread.created_at, models.MessageThread.id)
            .limit(2)
        )
    )


def count_active_threads(db: Session, requester_id: str) -> int:
    return (
        db.scalar(
            select(func.count(models.MessageThread.id))
            .where(models.MessageThread.requester_id == requester_id)
            .where(models.MessageThread.deleted_at.is_(None))
        )
        or 0
    )


def list_thread_messages(db: Session, thread_id: str) -> list[models.MessageMessage]:
    return db.scalars(
        select(models.MessageMessage)
        .where(models.MessageMessage.thread_id == thread_id)
        .order_by(models.MessageMessage.created_at, models.MessageMessage.id)
    ).all()


def latest_thread_message(db: Session, thread_id: str) -> models.MessageMessage | None:
    return db.scalar(
        select(models.MessageMessage)
        .where(models.MessageMessage.thread_id == thread_id)
        .order_by(
            models.MessageMessage.created_at.desc(), models.MessageMessage.id.desc()
        )
        .limit(1)
    )


def get_owned_thread(
    db: Session, requester_id: str, thread_id: str
) -> models.MessageThread | None:
    return db.scalar(
        select(models.MessageThread)
        .options(
            joinedload(models.MessageThread.requester),
            joinedload(models.MessageThread.character),
        )
        .where(models.MessageThread.id == thread_id)
        .where(models.MessageThread.requester_id == requester_id)
        .where(models.MessageThread.deleted_at.is_(None))
    )


def list_committed_response_requests(
    db: Session, thread_id: str
) -> list[models.ChatResponseRequest]:
    return list(
        db.scalars(
            select(models.ChatResponseRequest).where(
                models.ChatResponseRequest.thread_id == thread_id,
                models.ChatResponseRequest.state == "committed",
                models.ChatResponseRequest.committed_assistant_message_id.is_not(None),
            )
        )
    )
