"""Foreign Identity/World/Relationship/Routines facts for privacy-safe diagnostics."""

from __future__ import annotations
from datetime import datetime
from typing import Any
from sqlalchemy import text
from sqlalchemy.orm import Session

LOCAL_INSTALLATION_KEY = "local-installation"


def owner_state(db: Session) -> Any:
    return (
        db.execute(
            text(
                """
                SELECT bootstrap_state, owner_user_id
                FROM installation_identities
                WHERE singleton_key = :singleton_key
                """
            ),
            {"singleton_key": LOCAL_INSTALLATION_KEY},
        )
        .mappings()
        .first()
    )


def registered_world_count(db: Session, owner_user_id: str) -> Any:
    return db.execute(
        text(
            """
                    SELECT COUNT(*) FROM worlds
                    WHERE owner_user_id = :owner_user_id AND status <> 'archived'
                    """
        ),
        {"owner_user_id": owner_user_id},
    ).scalar_one()


def active_world_count(db: Session, owner_user_id: str) -> Any:
    return db.execute(
        text(
            """
                    SELECT COUNT(DISTINCT wc.world_id)
                    FROM character_active_worlds caw
                    JOIN world_characters wc ON wc.id = caw.world_character_id
                    JOIN characters c ON c.id = caw.character_id
                    WHERE c.owner_id = :owner_user_id
                    """
        ),
        {"owner_user_id": owner_user_id},
    ).scalar_one()


def active_world_character_count(db: Session, owner_user_id: str) -> Any:
    return db.execute(
        text(
            """
                    SELECT COUNT(*)
                    FROM world_characters wc
                    JOIN characters c ON c.id = wc.character_id
                    WHERE c.owner_id = :owner_user_id AND wc.status = 'active'
                    """
        ),
        {"owner_user_id": owner_user_id},
    ).scalar_one()


def projection_counts(db: Session) -> Any:
    return (
        db.execute(
            text(
                """
                SELECT
                    SUM(CASE WHEN status IN ('pending','processing') THEN 1 ELSE 0 END) AS pending_count,
                    SUM(CASE WHEN status = 'pending' AND attempt_count > 0 THEN 1 ELSE 0 END) AS retry_count,
                    SUM(CASE WHEN status = 'pending' AND last_error_class IS NOT NULL THEN 1 ELSE 0 END) AS failed_count,
                    SUM(CASE WHEN status = 'dead' THEN 1 ELSE 0 END) AS dead_letter_count,
                    MIN(CASE WHEN status IN ('pending','processing') THEN created_at END) AS oldest_pending_at,
                    MAX(updated_at) AS last_projection_at
                FROM graph_projection_outbox
                """
            )
        )
        .mappings()
        .one()
    )


def recent_runs(db: Session, owner_user_id: str, since: datetime) -> Any:
    return (
        db.execute(
            text(
                """
                SELECT id, post_id, status, gateway_result, created_at, completed_at
                FROM agent_runs
                WHERE user_id = :owner_user_id AND created_at >= :since
                ORDER BY COALESCE(completed_at, created_at) DESC
                LIMIT 200
                """
            ),
            {
                "owner_user_id": owner_user_id,
                "since": since,
            },
        )
        .mappings()
        .all()
    )
