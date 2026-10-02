"""Short installation-wide lock makes cross-character attempt admission atomic."""
from uuid import uuid4
from sqlalchemy import select, update, func
from app.domains.social.models.image_intents import ImageGenerationPolicy, ImageGenerationAttempt
from app.domains.media.contracts import ImagePreparationError


def read_installation_limit(db):
    row = db.get(ImageGenerationPolicy, 1)
    return row.daily_limit if row else None


def set_installation_limit(db, value, *, expected_revision=None):
    if not isinstance(value, int) or isinstance(value, bool) or not 1 <= value <= 10000:
        raise ImagePreparationError("installation_limit_invalid")
    row = db.get(ImageGenerationPolicy, 1)
    if expected_revision is not None and expected_revision != (row.revision if row else 0):
        raise ImagePreparationError("installation_limit_revision_conflict")
    if row is None:
        db.add(ImageGenerationPolicy(id=1, daily_limit=value, revision=1))
    else:
        previous = row.revision
        changed = db.execute(update(ImageGenerationPolicy).where(ImageGenerationPolicy.id == 1,
            ImageGenerationPolicy.revision == previous).values(daily_limit=value, revision=previous + 1))
        if changed.rowcount != 1:
            raise ImagePreparationError("installation_limit_revision_conflict")
        db.refresh(row)
    db.flush()


def read_usage(db, quota_day):
    row = db.get(ImageGenerationPolicy, 1)
    count = db.scalar(select(func.count()).select_from(ImageGenerationAttempt).where(
        ImageGenerationAttempt.quota_day == quota_day, ImageGenerationAttempt.status != "released"))
    return {"revision": row.revision if row else 0, "daily_limit": row.daily_limit if row else None,
        "quota_day": quota_day, "generation_reserved_or_used": count}


def reserve_attempt(db, *, job_id, owner_id, character_id, character_limit, quota_day):
    # A SQLite write lock or PostgreSQL row lock is acquired before both counts.
    if db.execute(update(ImageGenerationPolicy).where(ImageGenerationPolicy.id == 1).values(
        revision=ImageGenerationPolicy.revision)).rowcount != 1:
        raise ImagePreparationError("generation_limits_required")
    cap = read_installation_limit(db)
    if not cap or not character_limit:
        raise ImagePreparationError("generation_limits_required")
    conditions = (ImageGenerationAttempt.quota_day == quota_day, ImageGenerationAttempt.status != "released")
    total = db.scalar(select(func.count()).select_from(ImageGenerationAttempt).where(*conditions))
    own = db.scalar(select(func.count()).select_from(ImageGenerationAttempt).where(*conditions, ImageGenerationAttempt.character_id == character_id))
    if total >= cap or own >= character_limit:
        raise ImagePreparationError("generation_daily_limit_reached")
    row = ImageGenerationAttempt(id=uuid4().hex, job_id=job_id, owner_id=owner_id, character_id=character_id,
        quota_day=quota_day, status="reserved")
    db.add(row)
    db.flush()
    return row
