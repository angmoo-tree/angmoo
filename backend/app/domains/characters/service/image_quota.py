"""Creator image quotas for create/profile and avatar/banner buckets."""
from datetime import UTC, date, datetime, timedelta
from sqlalchemy import func, select
from sqlalchemy.orm import Session
from app.domains.routines.service import tick_schedule as agent_activity_policy
from app.domains.characters import models, schemas
from app.domains.characters.contracts import CharacterOwner
from app.domains.characters.exceptions import AgentProfileImageQuotaExceededError, AgentCreationDraftMediaError


PROFILE_IMAGE_DAILY_LIMIT = 1

PROFILE_IMAGE_USED_STATUSES = ("reserved", "generated", "applied")

def _profile_image_usage_read(
    db: Session, *, user: CharacterOwner, scope: str
) -> schemas.AgentProfileImageUsageRead:
    media_types = ("avatar", "banner")
    return schemas.AgentProfileImageUsageRead(
        items=[
            _profile_image_usage_status(
                db,
                user=user,
                scope=scope,
                media_type=media_type,
            )
            for media_type in media_types
        ]
    )

def _profile_image_usage_status(
    db: Session,
    *,
    user: CharacterOwner,
    scope: str,
    media_type: str,
    at: datetime | None = None,
) -> schemas.AgentProfileImageUsageStatusRead:
    current = at or datetime.now(UTC)
    quota_date = _profile_image_quota_date(current)
    bucket = _profile_image_bucket(scope, media_type)
    used = int(
        db.scalar(
            select(func.count(models.ProfileImageQuotaReservation.id)).where(
                models.ProfileImageQuotaReservation.user_id == user.id,
                models.ProfileImageQuotaReservation.quota_date == quota_date,
                models.ProfileImageQuotaReservation.bucket == bucket,
                models.ProfileImageQuotaReservation.status.in_(
                    PROFILE_IMAGE_USED_STATUSES
                ),
            )
        )
        or 0
    )
    remaining = max(0, PROFILE_IMAGE_DAILY_LIMIT - used)
    reset_at = _profile_image_reset_at(current)
    return schemas.AgentProfileImageUsageStatusRead(
        bucket=bucket,  # type: ignore[arg-type]
        scope=scope,  # type: ignore[arg-type]
        media_type=media_type,  # type: ignore[arg-type]
        used_today=used,
        remaining=remaining,
        limit=PROFILE_IMAGE_DAILY_LIMIT,
        reset_at=reset_at,
        next_available_at=reset_at if remaining <= 0 else None,
    )

def _reserve_profile_image_quota(
    db: Session,
    *,
    user: CharacterOwner,
    scope: str,
    media_type: str,
    model: str,
    route_mode: str,
) -> models.ProfileImageQuotaReservation:
    now = datetime.now(UTC)
    status = _profile_image_usage_status(
        db,
        user=user,
        scope=scope,
        media_type=media_type,
        at=now,
    )
    if status.remaining <= 0:
        raise AgentProfileImageQuotaExceededError(status)
    quota_date = _profile_image_quota_date(now)
    _lock_profile_image_quota(db, user_id=user.id, quota_date=quota_date, bucket=status.bucket)
    status = _profile_image_usage_status(
        db,
        user=user,
        scope=scope,
        media_type=media_type,
        at=now,
    )
    if status.remaining <= 0:
        raise AgentProfileImageQuotaExceededError(status)
    reservation = models.ProfileImageQuotaReservation(
        user_id=user.id,
        quota_date=quota_date,
        bucket=status.bucket,
        scope=scope,
        media_type=media_type,
        status="reserved",
        model=model,
        route_mode=route_mode,
    )
    db.add(reservation)
    db.commit()
    db.refresh(reservation)
    return reservation

def _finalize_profile_image_quota(
    db: Session,
    *,
    reservation_id: int | None,
    status: str,
    candidate_id: str | None,
) -> None:
    if reservation_id is None:
        return
    reservation = db.get(models.ProfileImageQuotaReservation, reservation_id)
    if reservation is None:
        return
    reservation.status = status
    if candidate_id is not None:
        reservation.candidate_id = candidate_id
    reservation.finalized_at = datetime.now(UTC)
    db.flush()

def _profile_image_bucket(scope: str, media_type: str) -> str:
    if scope not in {"create", "profile"}:
        raise AgentCreationDraftMediaError("invalid_profile_image_scope")
    if media_type not in {"avatar", "banner"}:
        raise AgentCreationDraftMediaError("invalid_profile_image_media_type")
    return f"{scope}_{media_type}"

def _profile_image_quota_date(at: datetime) -> date:
    local_at = (
        at.astimezone(agent_activity_policy.APP_TIMEZONE)
        if at.tzinfo
        else at.replace(tzinfo=UTC).astimezone(agent_activity_policy.APP_TIMEZONE)
    )
    return local_at.date()

def _profile_image_reset_at(at: datetime) -> datetime:
    local_at = (
        at.astimezone(agent_activity_policy.APP_TIMEZONE)
        if at.tzinfo
        else at.replace(tzinfo=UTC).astimezone(agent_activity_policy.APP_TIMEZONE)
    )
    return local_at.replace(hour=0, minute=0, second=0, microsecond=0) + timedelta(days=1)

def _lock_profile_image_quota(
    db: Session, *, user_id: str, quota_date: date, bucket: str
) -> None:
    if db.bind is None or db.bind.dialect.name != "postgresql":
        return
    lock_key = f"profile_image_quota:{user_id}:{quota_date.isoformat()}:{bucket}"
    db.execute(select(func.pg_advisory_xact_lock(func.hashtext(lock_key))))
