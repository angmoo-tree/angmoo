"""Social image queue claims, stale failure, job validation and completion policy."""
from __future__ import annotations
from datetime import UTC, datetime, timezone
from collections.abc import Callable
from sqlalchemy.orm import Session
from app.domains.social.models import posts as models
from app.domains.social.contracts.image_generation import ImageCharacter
from app.domains.social.contracts.image_jobs import LocalImagePreparer, PreparedImageAttacher
from app.domains.social.repository import image_jobs as queries
from app.domains.social.repository.event_evidence import get_post
from app.domains.social.repository.media import get_post_image_quota_reservation, update_post_image_quota_reservation


def claim_next_post_image_generation_job(
    db: Session,
) -> models.PostImageGenerationJob | None:
    job = queries.next_queued_image_job(db)
    if job is None:
        return None
    now = datetime.now(timezone.utc)
    job.status = "processing"
    job.started_at = now
    job.updated_at = now
    job.attempt_count = (job.attempt_count or 0) + 1
    reservation = get_post_image_quota_reservation(db, job.quota_reservation_id)
    if reservation is not None and reservation.status == "queued":
        update_post_image_quota_reservation(db, reservation, status="processing", job_id=job.id)
    db.commit()
    db.refresh(job)
    return job


def mark_stale_post_image_generation_jobs_failed(
    db: Session,
    *,
    stale_before: datetime,
) -> int:
    rows = queries.stale_processing_image_jobs(db, stale_before=stale_before)
    now = datetime.now(timezone.utc)
    for job in rows:
        job.status = "failed"
        job.failure_class = "stale_processing"
        job.finished_at = now
        job.updated_at = now
        reservation = get_post_image_quota_reservation(db, job.quota_reservation_id)
        if reservation is not None:
            update_post_image_quota_reservation(db, reservation, status="failed", job_id=job.id)
    if rows:
        db.commit()
    return len(rows)


def finish_post_image_generation_job(
    db: Session,
    job: models.PostImageGenerationJob,
    *,
    status: str,
    prompt_hash: str | None = None,
    reference_source: str | None = None,
    skip_reason: str | None = None,
    failure_class: str | None = None,
    media_url: str | None = None,
    byte_size: int | None = None,
) -> models.PostImageGenerationJob:
    job.status = status
    job.prompt_hash = prompt_hash or job.prompt_hash
    job.reference_source = reference_source or job.reference_source
    job.skip_reason = skip_reason
    job.failure_class = failure_class
    job.media_url = media_url
    job.byte_size = byte_size
    job.finished_at = datetime.now(timezone.utc)
    reservation = get_post_image_quota_reservation(db, job.quota_reservation_id)
    if reservation is not None:
        reservation_status = (
            "attached"
            if status == "attached"
            else "released"
            if status == "skipped"
            else "failed"
        )
        update_post_image_quota_reservation(
            db,
            reservation,
            status=reservation_status,
            post_id=job.post_id,
            job_id=job.id,
        )
    db.commit()
    db.refresh(job)
    return job


async def process_one_post_image_job(
    db: Session, *, stale_before: datetime,
    get_character: Callable[[str], ImageCharacter | None],
    prepare_image: LocalImagePreparer, attach_image: PreparedImageAttacher,
) -> bool:
    mark_stale_post_image_generation_jobs_failed(
        db,
        stale_before=stale_before,
    )
    job = claim_next_post_image_generation_job(db)
    if job is None:
        return False
    character = get_character(job.character_id)
    if character is None or character.deleted_at is not None:
        finish_post_image_generation_job(
            db,
            job,
            status="failed",
            failure_class="character_missing",
        )
        return True
    post = get_post(db, job.post_id)
    if post is None or post.deleted_at is not None:
        finish_post_image_generation_job(
            db,
            job,
            status="failed",
            failure_class="post_missing",
        )
        return True
    prepared = await prepare_image(
        db=db,
        character=character,
        image_prompt=job.image_prompt,
        run_started_at=job.started_at or datetime.now(UTC),
        key_source=job.key_source,
        quota_reservation_id=job.quota_reservation_id,
        post_id=job.post_id,
        job_id=job.id,
    )
    attached = attach_image(
        db=db,
        post_id=job.post_id,
        prepared=prepared,
    )
    finish_post_image_generation_job(
        db,
        job,
        status=attached.get("status", "failed"),
        prompt_hash=attached.get("prompt_hash"),
        reference_source=attached.get("reference_source"),
        skip_reason=attached.get("skip_reason"),
        failure_class=attached.get("failure_class"),
        media_url=attached.get("media_url"),
        byte_size=attached.get("byte_size"),
    )
    return True
