"""Social image daily windows, quota reservation and finalization policy."""
from __future__ import annotations
from datetime import UTC, date, datetime, time, timedelta
from sqlalchemy.orm import Session
from app.config import settings
from app.domains.social.exceptions import ServiceImageQuotaError
from app.domains.social.models import posts as models
from app.domains.social.repository import media as community_crud
from app.domains.routines.service import tick_schedule as agent_activity_policy






def _daily_image_count(db: Session, *, character_id: str, at: datetime) -> int:
    return _daily_image_window_count(db, character_id=character_id, at=at)



def _daily_image_usage(db: Session, *, character_id: str, at: datetime) -> int:
    start_at, end_at = _daily_image_window(at)
    return community_crud.count_post_media_for_character_between(
        db,
        character_id=character_id,
        start_at=start_at,
        end_at=end_at,
    ) + community_crud.count_active_post_image_jobs_for_character_between(
        db,
        character_id=character_id,
        start_at=start_at,
        end_at=end_at,
    )



def _daily_image_window_count(db: Session, *, character_id: str, at: datetime) -> int:
    start_at, end_at = _daily_image_window(at)
    return community_crud.count_post_media_for_character_between(
        db,
        character_id=character_id,
        start_at=start_at,
        end_at=end_at,
    )



def _daily_image_window(at: datetime) -> tuple[datetime, datetime]:
    tz = agent_activity_policy.APP_TIMEZONE
    local_at = at.astimezone(tz) if at.tzinfo else at.replace(tzinfo=UTC).astimezone(tz)
    local_start = datetime.combine(local_at.date(), time.min, tzinfo=tz)
    local_end = local_start + timedelta(days=1)
    return local_start.astimezone(UTC), local_end.astimezone(UTC)



def _service_quota_date(at: datetime) -> date:
    local_at = (
        at.astimezone(agent_activity_policy.APP_TIMEZONE)
        if at.tzinfo
        else at.replace(tzinfo=UTC).astimezone(agent_activity_policy.APP_TIMEZONE)
    )
    return local_at.date()



def _reserve_service_image_quota(
    db: Session,
    *,
    user_id: str,
    character_id: str,
    source: str,
    at: datetime,
    status: str = "reserved",
    post_id: str | None = None,
) -> models.PostImageQuotaReservation:
    limit = settings.pollinations_service_free_images_per_user_day
    quota_date = _service_quota_date(at)
    if limit <= 0:
        raise ServiceImageQuotaError("free_quota_exceeded")
    community_crud.lock_service_image_quota(
        db,
        user_id=user_id,
        quota_date=quota_date,
    )
    used = community_crud.count_service_image_quota_used(
        db,
        user_id=user_id,
        quota_date=quota_date,
    )
    if used >= limit:
        raise ServiceImageQuotaError("free_quota_exceeded")
    global_cap = settings.pollinations_service_max_images_per_day
    if global_cap > 0:
        global_used = community_crud.count_service_image_global_used(
            db, quota_date=quota_date
        )
        if global_used >= global_cap:
            raise ServiceImageQuotaError("service_limit_exceeded")
    reservation = community_crud.create_post_image_quota_reservation(
        db,
        user_id=user_id,
        character_id=character_id,
        quota_date=quota_date,
        source=source,
        status=status,
        post_id=post_id,
    )
    db.commit()
    db.refresh(reservation)
    return reservation



def _finalize_service_image_quota(
    db: Session,
    reservation: models.PostImageQuotaReservation | None,
    *,
    status: str,
    post_id: str | None = None,
) -> None:
    if reservation is None:
        return
    community_crud.update_post_image_quota_reservation(
        db,
        reservation,
        status=status,
        post_id=post_id,
    )
    db.commit()
