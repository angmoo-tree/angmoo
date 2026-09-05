"""Relationships-owned canonical queries in the caller Session."""
from datetime import datetime
from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session
from app.domains.relationships import models


def find_outbox_by_dedupe(db: Session, *, dedupe_key: str) -> models.GraphProjectionOutbox | None:
    return db.scalar(
        select(models.GraphProjectionOutbox).where(
            models.GraphProjectionOutbox.dedupe_key == dedupe_key
        )
    )


def source_event_ids(db: Session, *, unique_post_ids: list[str]) -> list[str]:
    return list(
        db.scalars(
            select(models.SocialEventEvidence.social_event_id)
            .where(
                or_(
                    models.SocialEventEvidence.root_post_id.in_(unique_post_ids),
                    models.SocialEventEvidence.source_post_id.in_(unique_post_ids),
                    models.SocialEventEvidence.target_post_id.in_(unique_post_ids),
                    (
                        (models.SocialEventEvidence.source_object_type == "post")
                        & (
                            models.SocialEventEvidence.source_object_id.in_(
                                unique_post_ids
                            )
                        )
                    ),
                )
            )
            .distinct()
        )
    )


def find_event_for_update(db: Session, *, event_id: str) -> models.SocialEvent | None:
    return db.scalar(
            select(models.SocialEvent)
            .where(models.SocialEvent.id == event_id)
            .with_for_update()
        )
