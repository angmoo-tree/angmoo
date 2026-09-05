"""Social-owned SQL; original caller transaction/flush/finish_write behavior is preserved."""

from datetime import date, datetime, timezone
from sqlalchemy import and_, func, or_, select, text
from sqlalchemy.orm import Session, aliased, selectinload
from app.domains.social.models import posts as models



def list_post_media(db: Session, post_id: str) -> list[models.PostMedia]:
    return list(
        db.scalars(
            select(models.PostMedia)
            .where(models.PostMedia.post_id == post_id)
            .order_by(models.PostMedia.created_at.asc(), models.PostMedia.id.asc())
        )
    )

def create_post_media(
    db: Session,
    *,
    post_id: str,
    url: str,
    alt_text: str,
    model: str,
    prompt_hash: str,
    byte_size: int,
    width: int,
    height: int,
    key_source: str = "user",
) -> models.PostMedia:
    media = models.PostMedia(
        post_id=post_id,
        media_type="image",
        url=url,
        alt_text=alt_text,
        model=model,
        prompt_hash=prompt_hash,
        byte_size=byte_size,
        width=width,
        height=height,
        key_source=key_source,
    )
    db.add(media)
    db.commit()
    db.refresh(media)
    return media

def create_post_image_generation_job(
    db: Session,
    *,
    post_id: str,
    user_id: str,
    character_id: str,
    source: str,
    status: str,
    image_model: str,
    image_prompt: str,
    key_source: str = "user",
    quota_reservation_id: int | None = None,
    prompt_hash: str | None = None,
    reference_source: str | None = None,
    skip_reason: str | None = None,
    failure_class: str | None = None,
) -> models.PostImageGenerationJob:
    job = models.PostImageGenerationJob(
        post_id=post_id,
        user_id=user_id,
        character_id=character_id,
        source=source,
        status=status,
        key_source=key_source,
        quota_reservation_id=quota_reservation_id,
        image_model=image_model,
        image_prompt=image_prompt,
        prompt_hash=prompt_hash,
        reference_source=reference_source,
        skip_reason=skip_reason,
        failure_class=failure_class,
        attempt_count=0,
    )
    db.add(job)
    db.commit()
    db.refresh(job)
    return job

def lock_service_image_quota(
    db: Session, *, user_id: str, quota_date: date
) -> None:
    if db.bind is None or db.bind.dialect.name != "postgresql":
        return
    lock_key = f"post_image_quota:service:{user_id}:{quota_date.isoformat()}"
    db.execute(select(func.pg_advisory_xact_lock(func.hashtext(lock_key))))

def count_service_image_quota_used(
    db: Session, *, user_id: str, quota_date: date
) -> int:
    return int(
        db.scalar(
            select(func.count(models.PostImageQuotaReservation.id)).where(
                models.PostImageQuotaReservation.user_id == user_id,
                models.PostImageQuotaReservation.quota_date == quota_date,
                models.PostImageQuotaReservation.key_source == "service",
                models.PostImageQuotaReservation.status.in_(
                    ("reserved", "queued", "processing", "attached")
                ),
            )
        )
        or 0
    )

def count_service_image_global_used(db: Session, *, quota_date: date) -> int:
    return int(
        db.scalar(
            select(func.count(models.PostImageQuotaReservation.id)).where(
                models.PostImageQuotaReservation.quota_date == quota_date,
                models.PostImageQuotaReservation.key_source == "service",
                models.PostImageQuotaReservation.status.in_(
                    ("reserved", "queued", "processing", "attached")
                ),
            )
        )
        or 0
    )

def create_post_image_quota_reservation(
    db: Session,
    *,
    user_id: str,
    character_id: str,
    quota_date: date,
    source: str,
    status: str = "reserved",
    post_id: str | None = None,
    job_id: int | None = None,
) -> models.PostImageQuotaReservation:
    reservation = models.PostImageQuotaReservation(
        user_id=user_id,
        character_id=character_id,
        quota_date=quota_date,
        key_source="service",
        source=source,
        status=status,
        post_id=post_id,
        job_id=job_id,
    )
    db.add(reservation)
    db.flush()
    return reservation

def update_post_image_quota_reservation(
    db: Session,
    reservation: models.PostImageQuotaReservation,
    *,
    status: str,
    post_id: str | None = None,
    job_id: int | None = None,
) -> models.PostImageQuotaReservation:
    reservation.status = status
    if post_id is not None:
        reservation.post_id = post_id
    if job_id is not None:
        reservation.job_id = job_id
    if status in {"attached", "released", "failed"}:
        reservation.finalized_at = datetime.now(timezone.utc)
    db.flush()
    return reservation

def get_post_image_quota_reservation(
    db: Session, reservation_id: int | None
) -> models.PostImageQuotaReservation | None:
    if reservation_id is None:
        return None
    return db.get(models.PostImageQuotaReservation, reservation_id)

def count_active_post_image_jobs_for_character_between(
    db: Session,
    *,
    character_id: str,
    start_at: datetime,
    end_at: datetime,
) -> int:
    return int(
        db.scalar(
            select(func.count(models.PostImageGenerationJob.id))
            .where(models.PostImageGenerationJob.character_id == character_id)
            .where(models.PostImageGenerationJob.status.in_(("queued", "processing")))
            .where(models.PostImageGenerationJob.created_at >= start_at)
            .where(models.PostImageGenerationJob.created_at < end_at)
        )
        or 0
    )

def claim_next_post_image_generation_job(
    db: Session,
) -> models.PostImageGenerationJob | None:
    statement = (
        select(models.PostImageGenerationJob)
        .where(models.PostImageGenerationJob.status == "queued")
        .order_by(models.PostImageGenerationJob.created_at.asc())
        .limit(1)
    )
    if db.bind is not None and db.bind.dialect.name == "postgresql":
        statement = statement.with_for_update(skip_locked=True)
    job = db.scalar(statement)
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
    rows = list(
        db.scalars(
            select(models.PostImageGenerationJob)
            .where(models.PostImageGenerationJob.status == "processing")
            .where(models.PostImageGenerationJob.started_at < stale_before)
        )
    )
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

def count_post_media_for_character_between(
    db: Session,
    *,
    character_id: str,
    start_at: datetime,
    end_at: datetime,
) -> int:
    return int(
        db.scalar(
            select(func.count(models.PostMedia.id))
            .join(models.Post, models.Post.id == models.PostMedia.post_id)
            .where(
                models.Post.author_character_id == character_id,
                models.Post.deleted_at.is_(None),
                models.PostMedia.created_at >= start_at,
                models.PostMedia.created_at < end_at,
            )
        )
        or 0
    )
