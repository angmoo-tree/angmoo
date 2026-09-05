"""Social image queue selection; claim/state transitions remain in the service."""
from datetime import datetime
from sqlalchemy import select
from sqlalchemy.orm import Session
from app.domains.social.models import posts as models

def next_queued_image_job(db: Session) -> models.PostImageGenerationJob | None:
    statement = (
        select(models.PostImageGenerationJob)
        .where(models.PostImageGenerationJob.status == "queued")
        .order_by(models.PostImageGenerationJob.created_at.asc())
        .limit(1)
    )
    if db.bind is not None and db.bind.dialect.name == "postgresql":
        statement = statement.with_for_update(skip_locked=True)
    return db.scalar(statement)


def stale_processing_image_jobs(
    db: Session, *, stale_before: datetime,
) -> list[models.PostImageGenerationJob]:
    return list(
        db.scalars(
            select(models.PostImageGenerationJob)
            .where(models.PostImageGenerationJob.status == "processing")
            .where(models.PostImageGenerationJob.started_at < stale_before)
        )
    )
