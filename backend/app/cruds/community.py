from datetime import date, datetime, timezone
import hashlib
import re

from sqlalchemy import and_, func, or_, select, text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session, aliased, selectinload

from app import models
from app import schemas
from app.core.agent_activity_limits import (
    DEFAULT_MAX_COMMENTS_PER_DAY,
    DEFAULT_MAX_POSTS_PER_DAY,
)
from app.core import active_hours
from app.core.config import settings
from app.core import security
from app.core.search_text import build_post_search_document
from app.core import unit_of_work
from app.cruds import agents as agent_crud


HIDDEN_AGENT_ACTIVITY_ACTION_TYPES = (
    "state_save_suppressed",
    "feed_perception_debug",
    "complete_tick_rejected",
    "local_key_issued",
    "local_key_revoked",
    "local_bot_rate_limited",
)
PUBLIC_ACTIVITY_ACTION_ALIASES = {
    "comment": "replied",
    "commented": "replied",
    "follow": "followed",
    "like": "liked",
    "observe": "observed",
    "post": "post_created",
    "quote": "quoted",
    "reply": "replied",
    "repost": "reposted",
    "unfollow": "unfollowed",
}
PUBLIC_ACTIVITY_ACTION_TYPES = {
    "activated",
    "created",
    "deactivated",
    "followed",
    "liked",
    "memory_note_refine_failed",
    "observed",
    "persona_updated",
    "post_created",
    "profile_updated",
    "quoted",
    "replied",
    "reposted",
    "skipped",
    "state_saved",
    "tendency_analyzed",
    "thread_viewed",
    "tick_completed",
    "unfollowed",
}
PUBLIC_ACTIVITY_SUMMARIES = {
    "activated": "자율 활동이 켜졌어요.",
    "created": "프로필과 활동 준비가 저장됐어요.",
    "deactivated": "자율 활동이 꺼졌어요.",
    "followed": "새 프로필을 팔로우했어요.",
    "liked": "좋아요가 반영됐어요.",
    "memory_note_refine_failed": "처음 저장한 기억 문구를 그대로 유지했어요.",
    "observed": "커뮤니티 흐름을 살펴봤어요.",
    "persona_updated": "성격과 말투 설정을 업데이트했어요.",
    "post_created": "지저귐이 타임라인에 추가됐어요.",
    "profile_updated": "프로필 정보를 업데이트했어요.",
    "quoted": "인용 기록이 반영됐어요.",
    "replied": "대꾸가 타임라인에 추가됐어요.",
    "reposted": "리포스트가 반영됐어요.",
    "skipped": "이번 활동은 쉬어갔어요.",
    "state_saved": "기분과 기억을 업데이트했어요.",
    "tendency_analyzed": "커뮤니티 활동 성향을 다시 정리했어요.",
    "thread_viewed": "대화 흐름을 확인했어요.",
    "tick_completed": "활동 결과를 정리했어요.",
    "unfollowed": "프로필 팔로우를 해제했어요.",
}
HANDLE_RE = re.compile(r"^[a-z0-9_]{2,40}$")
_MULTIPLE_NEWLINES_RE = re.compile(r"\n{3,}")


def sanitize_visible_post_title(value: str) -> str:
    text = str(value or "")
    for marker in ("\\r\\n", "\\n", "\\r", "\\t"):
        text = text.replace(marker, " ")
    text = text.replace("\r\n", " ").replace("\r", " ").replace("\n", " ").replace("\t", " ")
    return " ".join(text.split())


def sanitize_visible_post_body(value: str) -> str:
    text = str(value or "")
    text = (
        text.replace("\\r\\n", "\n")
        .replace("\\n", "\n")
        .replace("\\r", "\n")
        .replace("\\t", " ")
    )
    text = text.replace("\r\n", "\n").replace("\r", "\n").replace("\t", " ")
    text = "\n".join(line.rstrip() for line in text.split("\n"))
    return _MULTIPLE_NEWLINES_RE.sub("\n\n", text).strip()


def _visible_post_conditions():
    return (
        models.Post.deleted_at.is_(None),
        models.Post.report_hidden_at.is_(None),
    )


def _visible_reference_conditions():
    quoted_source = aliased(models.Post)
    reposted_source = aliased(models.Post)
    visible_quote_ids = select(quoted_source.id).where(
        quoted_source.deleted_at.is_(None),
        quoted_source.report_hidden_at.is_(None),
    )
    visible_repost_ids = select(reposted_source.id).where(
        reposted_source.deleted_at.is_(None),
        reposted_source.report_hidden_at.is_(None),
    )
    return (
        or_(
            models.Post.quote_post_id.is_(None),
            models.Post.quote_post_id.in_(visible_quote_ids),
        ),
        or_(
            models.Post.repost_of_post_id.is_(None),
            models.Post.repost_of_post_id.in_(visible_repost_ids),
        ),
    )


def is_report_hidden(post: models.Post) -> bool:
    return post.report_hidden_at is not None


class CharacterHandleConflictError(Exception):
    pass


class InvalidCharacterHandleError(Exception):
    pass


def _like_search_terms(query: str) -> list[str]:
    raw = query.strip()
    if not raw:
        return []
    terms = [raw]
    if raw.startswith("@") and len(raw) > 1:
        terms.append(raw[1:])
    return list(dict.fromkeys(terms))


def _like_pattern(term: str) -> str:
    escaped = (
        term.replace("\\", "\\\\")
        .replace("%", "\\%")
        .replace("_", "\\_")
    )
    return f"%{escaped}%"


def _parse_int_cursor(value: str) -> int | None:
    try:
        return int(value)
    except ValueError:
        return None


def normalize_character_handle(value: str) -> str:
    handle = value.strip().lower().removeprefix("@")
    handle = re.sub(r"[\s-]+", "_", handle)
    if not HANDLE_RE.fullmatch(handle):
        raise InvalidCharacterHandleError(
            "핸들은 영문 소문자, 숫자, 밑줄(_)만 사용할 수 있습니다."
        )
    return handle


def _fallback_handle(name: str, character_id: str) -> str:
    raw = re.sub(r"[\s-]+", "_", name.strip().lower())
    handle = re.sub(r"[^a-z0-9_]", "", raw).strip("_")
    if len(handle) < 2:
        handle = f"angmoo_{character_id.replace('char-', '')[:8]}"
    return handle[:40].strip("_") or f"angmoo_{character_id[-8:]}"


def _ensure_available_handle(
    db: Session,
    handle: str,
    *,
    current_character_id: str | None = None,
    allow_suffix: bool,
) -> str:
    candidate = handle
    suffix = 2
    while True:
        existing = db.scalar(
            select(models.Character).where(models.Character.handle == candidate)
        )
        if existing is None or existing.id == current_character_id:
            return candidate
        if not allow_suffix:
            raise CharacterHandleConflictError(f"@{handle} 핸들은 이미 사용 중입니다.")
        suffix_text = f"_{suffix}"
        candidate = f"{handle[: 40 - len(suffix_text)]}{suffix_text}"
        suffix += 1


def validate_character_handle_for_create(db: Session, value: str) -> str:
    handle = normalize_character_handle(value)
    return _ensure_available_handle(db, handle, allow_suffix=False)


def character_has_authored_post(db: Session, character_id: str) -> bool:
    return (
        db.scalar(
            select(models.Post.id)
            .where(
                models.Post.author_character_id == character_id,
                models.Post.deleted_at.is_(None),
            )
            .limit(1)
        )
        is not None
    )


def list_posts(db: Session) -> list[schemas.PostSummary]:
    comment_count = func.count(func.distinct(models.Comment.id)).label("comment_count")
    like_count = func.count(func.distinct(models.PostLike.id)).label("like_count")
    rows = db.execute(
        select(models.Post, comment_count, like_count)
        .outerjoin(models.Comment)
        .outerjoin(models.PostLike)
        .where(*_visible_post_conditions(), *_visible_reference_conditions())
        .group_by(models.Post.id)
        .order_by(models.Post.created_at.desc(), models.Post.id)
    ).all()

    return [
        schemas.PostSummary.model_validate(
            {
                "id": post.id,
                "author_name": post.author_name,
                "title": post.title,
                "body": post.body,
                "created_at": post.created_at,
                "post_type": post.post_type,
                "author_user_id": post.author_user_id,
                "author_character_id": post.author_character_id,
                "reply_to_post_id": post.reply_to_post_id,
                "quote_post_id": post.quote_post_id,
                "repost_of_post_id": post.repost_of_post_id,
                "comment_count": count,
                "like_count": likes,
                "reply_count": count_post_replies(db, post.id),
                "repost_count": count_post_reposts(db, post.id),
                "quote_count": count_post_quotes(db, post.id),
            }
        )
        for post, count, likes in rows
    ]


def get_post(db: Session, post_id: str) -> models.Post | None:
    return db.scalar(
        select(models.Post)
        .where(models.Post.id == post_id, *_visible_post_conditions())
        .options(selectinload(models.Post.comments))
    )


def get_post_including_report_hidden(db: Session, post_id: str) -> models.Post | None:
    return db.scalar(
        select(models.Post)
        .where(models.Post.id == post_id, models.Post.deleted_at.is_(None))
        .options(selectinload(models.Post.comments))
    )


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


def get_post_report(
    db: Session, *, post_id: str, reporter_user_id: str
) -> models.PostReport | None:
    return db.scalar(
        select(models.PostReport).where(
            models.PostReport.post_id == post_id,
            models.PostReport.reporter_user_id == reporter_user_id,
        )
    )


def count_post_reports(db: Session, post_id: str) -> int:
    return (
        db.scalar(
            select(func.count(models.PostReport.id)).where(
                models.PostReport.post_id == post_id
            )
        )
        or 0
    )


def create_post_report(
    db: Session,
    *,
    post: models.Post,
    reporter_user: models.User,
    data: schemas.PostReportCreate,
) -> tuple[models.PostReport, bool]:
    existing = get_post_report(db, post_id=post.id, reporter_user_id=reporter_user.id)
    if existing is not None:
        return existing, False
    report = models.PostReport(
        post_id=post.id,
        reporter_user_id=reporter_user.id,
        reason=data.reason,
        details=(data.details.strip() or None) if data.details else None,
    )
    db.add(report)
    try:
        db.flush()
    except IntegrityError:
        db.rollback()
        existing = get_post_report(
            db, post_id=post.id, reporter_user_id=reporter_user.id
        )
        if existing is not None:
            return existing, False
        raise
    db.refresh(report)
    return report, True


def list_timeline_posts(
    db: Session,
    *,
    limit: int,
    cursor: str | None = None,
    author_user_id: str | None = None,
    author_character_id: str | None = None,
    followed_user_ids: set[str] | None = None,
    followed_character_ids: set[str] | None = None,
    content_filter: str = "all",
) -> tuple[list[models.Post], str | None]:
    query = select(models.Post).where(
        *_visible_post_conditions(),
        *_visible_reference_conditions(),
        models.Post.reply_to_post_id.is_(None),
    )
    if author_user_id is not None:
        query = query.where(models.Post.author_user_id == author_user_id)
    if author_character_id is not None:
        query = query.where(models.Post.author_character_id == author_character_id)
    if content_filter == "posts":
        query = query.where(
            models.Post.post_type != "repost",
            models.Post.repost_of_post_id.is_(None),
        )
    elif content_filter == "reposts":
        query = query.where(
            models.Post.post_type == "repost",
            models.Post.repost_of_post_id.is_not(None),
        )
    if followed_user_ids is not None or followed_character_ids is not None:
        feed_filters = []
        if followed_user_ids:
            feed_filters.append(models.Post.author_user_id.in_(followed_user_ids))
        if followed_character_ids:
            feed_filters.append(
                models.Post.author_character_id.in_(followed_character_ids)
            )
        if not feed_filters:
            return [], None
        query = query.where(or_(*feed_filters))
    if cursor:
        cursor_post = db.get(models.Post, cursor)
        if cursor_post is not None:
            query = query.where(
                or_(
                    models.Post.created_at < cursor_post.created_at,
                    and_(
                        models.Post.created_at == cursor_post.created_at,
                        models.Post.id > cursor_post.id,
                    ),
                )
            )
    rows = list(
        db.scalars(
            query.order_by(models.Post.created_at.desc(), models.Post.id.asc()).limit(limit)
        )
    )
    next_cursor = rows[-1].id if len(rows) == limit else None
    return rows, next_cursor


def list_resident_scan_posts(
    db: Session,
    *,
    limit: int,
    cursor: str | None = None,
) -> tuple[list[models.Post], str | None]:
    query = select(models.Post).where(
        *_visible_post_conditions(),
        *_visible_reference_conditions(),
        models.Post.reply_to_post_id.is_(None),
        models.Post.post_type != "repost",
        models.Post.repost_of_post_id.is_(None),
    )
    if cursor:
        cursor_post = db.get(models.Post, cursor)
        if cursor_post is not None:
            query = query.where(
                or_(
                    models.Post.created_at < cursor_post.created_at,
                    and_(
                        models.Post.created_at == cursor_post.created_at,
                        models.Post.id > cursor_post.id,
                    ),
                )
            )
    rows = list(
        db.scalars(
            query.order_by(models.Post.created_at.desc(), models.Post.id.asc()).limit(limit)
        )
    )
    next_cursor = rows[-1].id if len(rows) == limit else None
    return rows, next_cursor


def list_profile_posts(
    db: Session,
    *,
    limit: int,
    cursor: str | None = None,
    author_user_id: str | None = None,
    author_character_id: str | None = None,
    replies: bool = False,
) -> tuple[list[models.Post], str | None]:
    query = select(models.Post).where(
        *_visible_post_conditions(), *_visible_reference_conditions()
    )
    if replies:
        query = query.where(models.Post.reply_to_post_id.is_not(None))
    else:
        query = query.where(models.Post.reply_to_post_id.is_(None))
    if author_user_id is not None:
        query = query.where(models.Post.author_user_id == author_user_id)
    if author_character_id is not None:
        query = query.where(models.Post.author_character_id == author_character_id)
    if cursor:
        cursor_post = db.get(models.Post, cursor)
        if cursor_post is not None:
            query = query.where(
                or_(
                    models.Post.created_at < cursor_post.created_at,
                    and_(
                        models.Post.created_at == cursor_post.created_at,
                        models.Post.id > cursor_post.id,
                    ),
                )
            )
    rows = list(
        db.scalars(
            query.order_by(models.Post.created_at.desc(), models.Post.id.asc()).limit(limit)
        )
    )
    next_cursor = rows[-1].id if len(rows) == limit else None
    return rows, next_cursor


def list_liked_profile_posts(
    db: Session,
    *,
    limit: int,
    cursor: str | None = None,
    user_id: str | None = None,
    character_id: str | None = None,
) -> tuple[list[models.Post], str | None]:
    query = (
        select(models.Post, models.PostLike.created_at)
        .join(models.PostLike, models.PostLike.post_id == models.Post.id)
        .where(*_visible_post_conditions(), *_visible_reference_conditions())
    )
    cursor_like_query = select(models.PostLike.created_at).where(
        models.PostLike.post_id == cursor
    )
    if character_id is not None:
        query = query.where(models.PostLike.character_id == character_id)
        cursor_like_query = cursor_like_query.where(
            models.PostLike.character_id == character_id
        )
    elif user_id is not None:
        query = query.where(
            models.PostLike.user_id == user_id,
            models.PostLike.character_id.is_(None),
        )
        cursor_like_query = cursor_like_query.where(
            models.PostLike.user_id == user_id,
            models.PostLike.character_id.is_(None),
        )
    if cursor:
        cursor_created_at = db.scalar(cursor_like_query)
        if cursor_created_at is not None:
            query = query.where(
                or_(
                    models.PostLike.created_at < cursor_created_at,
                    and_(
                        models.PostLike.created_at == cursor_created_at,
                        models.Post.id > cursor,
                    ),
                )
            )
    rows = db.execute(
        query.order_by(models.PostLike.created_at.desc(), models.Post.id.asc()).limit(limit)
    ).all()
    posts = [post for post, _created_at in rows]
    next_cursor = posts[-1].id if len(posts) == limit else None
    return posts, next_cursor


def search_posts(
    db: Session, query: str, *, limit: int, offset: int = 0
) -> tuple[list[models.Post], int | None]:
    filters = []
    for term in _like_search_terms(query):
        pattern = _like_pattern(term)
        filters.extend(
            [
                models.Post.title.ilike(pattern, escape="\\"),
                models.Post.body.ilike(pattern, escape="\\"),
                models.Post.author_name.ilike(pattern, escape="\\"),
                models.Character.name.ilike(pattern, escape="\\"),
                models.Character.handle.ilike(pattern, escape="\\"),
            ]
        )
    if not filters:
        return [], None
    rows = list(
        db.scalars(
            select(models.Post)
            .outerjoin(
                models.Character,
                models.Post.author_character_id == models.Character.id,
            )
            .where(
                *_visible_post_conditions(),
                *_visible_reference_conditions(),
                models.Post.visibility == "public",
                or_(*filters),
            )
            .order_by(models.Post.created_at.desc(), models.Post.id.asc())
            .offset(max(0, offset))
            .limit(limit + 1)
        )
    )
    return rows[:limit], offset + limit if len(rows) > limit else None


def search_characters(
    db: Session, query: str, *, limit: int, offset: int = 0
) -> tuple[list[models.Character], int | None]:
    filters = []
    for term in _like_search_terms(query):
        pattern = _like_pattern(term)
        filters.extend(
            [
                models.Character.name.ilike(pattern, escape="\\"),
                models.Character.handle.ilike(pattern, escape="\\"),
                models.Character.one_liner.ilike(pattern, escape="\\"),
                models.Character.persona_summary.ilike(pattern, escape="\\"),
            ]
        )
    if not filters:
        return [], None
    rows = list(
        db.scalars(
            select(models.Character)
            .where(models.Character.deleted_at.is_(None), or_(*filters))
            .order_by(models.Character.created_at.desc(), models.Character.id.asc())
            .offset(max(0, offset))
            .limit(limit + 1)
        )
    )
    return rows[:limit], offset + limit if len(rows) > limit else None


def list_post_replies(db: Session, post_id: str, *, limit: int = 50) -> list[models.Post]:
    return list(
        db.scalars(
            select(models.Post)
            .where(
                models.Post.reply_to_post_id == post_id,
                *_visible_post_conditions(),
            )
            .order_by(models.Post.created_at.asc(), models.Post.id.asc())
            .limit(limit)
        )
    )


def list_post_thread_replies(
    db: Session, post_id: str, *, limit: int = 100
) -> list[models.Post]:
    seen = {post_id}
    replies: list[models.Post] = []
    frontier = [post_id]

    while frontier and len(replies) < limit:
        remaining = limit - len(replies)
        children = list(
            db.scalars(
                select(models.Post)
                .where(
                    models.Post.reply_to_post_id.in_(frontier),
                    *_visible_post_conditions(),
                )
                .order_by(models.Post.created_at.asc(), models.Post.id.asc())
                .limit(remaining)
            )
        )
        next_frontier = [child.id for child in children if child.id not in seen]
        if not next_frontier:
            break
        seen.update(next_frontier)
        replies.extend(child for child in children if child.id in next_frontier)
        frontier = next_frontier

    return replies


def count_post_comments(db: Session, post_id: str) -> int:
    return db.scalar(
        select(func.count(models.Comment.id)).where(models.Comment.post_id == post_id)
    ) or 0


def count_post_likes(db: Session, post_id: str) -> int:
    return db.scalar(
        select(func.count(models.PostLike.id)).where(models.PostLike.post_id == post_id)
    ) or 0


def count_post_replies(db: Session, post_id: str) -> int:
    return db.scalar(
        select(func.count(models.Post.id)).where(
            models.Post.reply_to_post_id == post_id,
            *_visible_post_conditions(),
        )
    ) or 0


def count_post_reposts(db: Session, post_id: str) -> int:
    return db.scalar(
        select(func.count(models.PostRepost.id)).where(models.PostRepost.post_id == post_id)
    ) or 0


def count_post_quotes(db: Session, post_id: str) -> int:
    return db.scalar(
        select(func.count(models.Post.id)).where(
            models.Post.quote_post_id == post_id,
            *_visible_post_conditions(),
        )
    ) or 0


def get_character(db: Session, character_id: str) -> models.Character | None:
    return db.get(models.Character, character_id)


def count_user_characters(db: Session, user_id: str) -> int:
    return db.scalar(
        select(func.count(models.Character.id)).where(
            models.Character.owner_id == user_id,
            models.Character.deleted_at.is_(None),
        )
    ) or 0


def list_characters_for_user(db: Session, user_id: str) -> list[models.Character]:
    return list(
        db.scalars(
            select(models.Character)
            .where(
                models.Character.owner_id == user_id,
                models.Character.deleted_at.is_(None),
            )
            .order_by(models.Character.created_at.asc(), models.Character.id.asc())
        )
    )


def create_character(
    db: Session, *, user: models.User, character_id: str, data: schemas.AgentCreate
) -> models.Character:
    requested_handle = (
        normalize_character_handle(data.handle) if data.handle else None
    )
    handle = _ensure_available_handle(
        db,
        requested_handle or _fallback_handle(data.name, character_id),
        allow_suffix=requested_handle is None,
    )
    avatar_url = data.avatar_url.strip() if data.avatar_url else None
    banner_url = data.banner_url.strip() if data.banner_url else None
    character = models.Character(
        id=character_id,
        owner_id=user.id,
        name=data.name.strip(),
        handle=handle,
        avatar_url=avatar_url,
        banner_url=banner_url,
        one_liner=data.one_liner.strip(),
        personality=data.personality.strip(),
        speech_style=data.speech_style.strip(),
        worldview=data.worldview.strip(),
        topic_preferences=data.topic_preferences.strip(),
        safety_rules=data.safety_rules.strip(),
        status="inactive",
        execution_mode=data.execution_mode,
        persona_summary="",
    )
    character.persona_summary = _build_persona_summary(character)
    db.add(character)
    try:
        db.commit()
    except IntegrityError as exc:
        db.rollback()
        _raise_handle_conflict_from_integrity(exc, handle)
        raise
    db.refresh(character)
    return character


def update_character_profile(
    db: Session, character: models.Character, data: schemas.AgentProfileUpdate
) -> models.Character:
    if data.name is not None:
        character.name = data.name.strip()
    if data.handle is not None:
        handle = normalize_character_handle(data.handle)
        character.handle = _ensure_available_handle(
            db,
            handle,
            current_character_id=character.id,
            allow_suffix=False,
        )
    if data.avatar_url is not None:
        character.avatar_url = data.avatar_url.strip() or None
    if data.banner_url is not None:
        character.banner_url = data.banner_url.strip() or None
    if data.one_liner is not None:
        character.one_liner = data.one_liner.strip()
        character.persona_summary = _build_persona_summary(character)
    try:
        db.commit()
    except IntegrityError as exc:
        db.rollback()
        _raise_handle_conflict_from_integrity(exc, character.handle)
        raise
    db.refresh(character)
    return character


def update_character_persona(
    db: Session, character: models.Character, data: schemas.AgentPersonaUpdate
) -> models.Character:
    character.personality = data.personality.strip()
    character.speech_style = data.speech_style.strip()
    character.worldview = data.worldview.strip()
    character.topic_preferences = data.topic_preferences.strip()
    character.safety_rules = data.safety_rules.strip()
    character.persona_summary = _build_persona_summary(character)
    db.commit()
    db.refresh(character)
    return character


def _build_persona_summary(character: models.Character) -> str:
    return "\n".join(
        part
        for part in [
            character.one_liner.strip(),
            f"성격: {character.personality.strip()}"
            if character.personality.strip()
            else "",
            f"말투: {character.speech_style.strip()}"
            if character.speech_style.strip()
            else "",
            f"세계관: {character.worldview.strip()}"
            if character.worldview.strip()
            else "",
            f"관심 주제: {character.topic_preferences.strip()}"
            if character.topic_preferences.strip()
            else "",
            f"피해야 할 행동: {character.safety_rules.strip()}"
            if character.safety_rules.strip()
            else "",
        ]
        if part
    )


def _raise_handle_conflict_from_integrity(exc: IntegrityError, handle: str) -> None:
    message = str(exc.orig)
    if "uq_characters_handle" in message or "characters_handle_key" in message:
        raise CharacterHandleConflictError(f"@{handle} 핸들은 이미 사용 중입니다.") from exc


def create_post(
    db: Session,
    *,
    post_id: str,
    user: models.User,
    character: models.Character | None,
    data: schemas.PostCreate,
    post_info: schemas.PostInfoMetadata | None = None,
    world_id: str | None = None,
    author_world_character_id: str | None = None,
) -> models.Post:
    title = sanitize_visible_post_title(data.title)
    body = sanitize_visible_post_body(data.body)
    post = models.Post(
        id=post_id,
        author_user_id=user.id,
        author_character_id=character.id if character else None,
        world_id=world_id,
        author_world_character_id=author_world_character_id,
        author_name=character.name if character else user.display_name,
        title=title,
        body=body,
        search_document=build_post_search_document(
            title=title, body=body, topic_signature=None
        ),
        info_kind=post_info.info_kind if post_info else None,
        source_name=post_info.source_name if post_info else None,
        source_url=post_info.source_url if post_info else None,
        observed_at=post_info.observed_at if post_info else None,
        location_label=post_info.location_label if post_info else None,
    )
    db.add(post)
    unit_of_work.finish_write(db, post)
    return post


def create_timeline_post(
    db: Session,
    *,
    post_id: str,
    user: models.User,
    character: models.Character | None,
    title: str,
    body: str,
    post_type: str,
    reply_to_post_id: str | None = None,
    quote_post_id: str | None = None,
    repost_of_post_id: str | None = None,
    world_id: str | None = None,
    author_world_character_id: str | None = None,
) -> models.Post:
    safe_title = sanitize_visible_post_title(title)
    safe_body = sanitize_visible_post_body(body)
    post = models.Post(
        id=post_id,
        author_user_id=user.id,
        author_character_id=character.id if character else None,
        author_name=character.name if character else user.display_name,
        world_id=world_id,
        author_world_character_id=author_world_character_id,
        title=safe_title,
        body=safe_body,
        search_document=build_post_search_document(
            title=safe_title, body=safe_body, topic_signature=None
        ),
        post_type=post_type,
        reply_to_post_id=reply_to_post_id,
        quote_post_id=quote_post_id,
        repost_of_post_id=repost_of_post_id,
    )
    db.add(post)
    unit_of_work.finish_write(db, post)
    return post


def create_comment(
    db: Session, post: models.Post, character: models.Character, data: schemas.CommentCreate
) -> models.Comment:
    comment = models.Comment(
        post_id=post.id,
        author_character_id=character.id,
        content=data.content,
    )
    db.add(comment)
    db.commit()
    db.refresh(comment)
    return comment


def like_post(
    db: Session,
    *,
    post: models.Post,
    user: models.User,
    character: models.Character | None,
) -> tuple[models.PostLike, bool]:
    if character is None:
        _lock_direct_user_like(db, post_id=post.id, user_id=user.id)
    query = select(models.PostLike).where(models.PostLike.post_id == post.id)
    if character is None:
        query = query.where(
            models.PostLike.user_id == user.id,
            models.PostLike.character_id.is_(None),
        )
    else:
        query = query.where(models.PostLike.character_id == character.id)
    existing = db.scalar(query)
    if existing is not None:
        return existing, False
    like = models.PostLike(
        post_id=post.id,
        user_id=user.id,
        character_id=character.id if character else None,
    )
    db.add(like)
    try:
        unit_of_work.finish_write(db, like)
    except IntegrityError:
        db.rollback()
        existing = db.scalar(query)
        if existing is not None:
            return existing, False
        raise
    return like, True


def _lock_direct_user_like(db: Session, *, post_id: str, user_id: str) -> None:
    if db.bind is None or db.bind.dialect.name != "postgresql":
        return
    lock_key = int.from_bytes(
        hashlib.sha256(
            f"angmoo:direct-user-like:{post_id}:{user_id}:v1".encode("utf-8")
        ).digest()[:8],
        byteorder="big",
        signed=True,
    )
    db.execute(
        text("select pg_advisory_xact_lock(:lock_key)"),
        {"lock_key": lock_key},
    )


def unlike_post(
    db: Session,
    *,
    post: models.Post,
    user: models.User,
    character: models.Character | None,
) -> bool:
    query = select(models.PostLike).where(models.PostLike.post_id == post.id)
    if character is None:
        query = query.where(
            models.PostLike.user_id == user.id,
            models.PostLike.character_id.is_(None),
        )
    else:
        query = query.where(models.PostLike.character_id == character.id)
    like = db.scalar(query)
    if like is None:
        return False
    db.delete(like)
    unit_of_work.finish_write(db)
    return True


def create_repost(
    db: Session,
    *,
    post: models.Post,
    user: models.User,
    character: models.Character | None,
) -> tuple[models.PostRepost, bool]:
    query = select(models.PostRepost).where(models.PostRepost.post_id == post.id)
    if character is None:
        query = query.where(
            models.PostRepost.user_id == user.id,
            models.PostRepost.character_id.is_(None),
        )
    else:
        query = query.where(models.PostRepost.character_id == character.id)
    existing = db.scalar(query)
    if existing is not None:
        return existing, False
    repost = models.PostRepost(
        post_id=post.id,
        user_id=user.id if character is None else None,
        character_id=character.id if character else None,
    )
    db.add(repost)
    unit_of_work.finish_write(db, repost)
    return repost, True


def get_timeline_repost(
    db: Session,
    *,
    post: models.Post,
    user: models.User,
    character: models.Character | None,
) -> models.Post | None:
    query = select(models.Post).where(
        models.Post.deleted_at.is_(None),
        models.Post.report_hidden_at.is_(None),
        models.Post.post_type == "repost",
        models.Post.repost_of_post_id == post.id,
    )
    if character is None:
        query = query.where(
            models.Post.author_user_id == user.id,
            models.Post.author_character_id.is_(None),
        )
    else:
        query = query.where(models.Post.author_character_id == character.id)
    return db.scalar(query.order_by(models.Post.created_at.desc(), models.Post.id.asc()).limit(1))


def delete_repost(
    db: Session,
    *,
    post: models.Post,
    user: models.User,
    character: models.Character | None,
) -> bool:
    query = select(models.PostRepost).where(models.PostRepost.post_id == post.id)
    if character is None:
        query = query.where(
            models.PostRepost.user_id == user.id,
            models.PostRepost.character_id.is_(None),
        )
    else:
        query = query.where(models.PostRepost.character_id == character.id)
    repost = db.scalar(query)
    if repost is None:
        return False
    db.delete(repost)
    unit_of_work.finish_write(db)
    return True


def delete_timeline_reposts(
    db: Session,
    *,
    post: models.Post,
    user: models.User,
    character: models.Character | None,
) -> int:
    query = select(models.Post).where(
        models.Post.deleted_at.is_(None),
        models.Post.post_type == "repost",
        models.Post.repost_of_post_id == post.id,
    )
    if character is None:
        query = query.where(
            models.Post.author_user_id == user.id,
            models.Post.author_character_id.is_(None),
        )
    else:
        query = query.where(models.Post.author_character_id == character.id)
    rows = list(db.scalars(query))
    now = datetime.now(timezone.utc)
    for row in rows:
        row.deleted_at = now
    if rows:
        unit_of_work.finish_write(db)
    return len(rows)


def delete_repost_event_for_timeline_post(db: Session, *, post: models.Post) -> bool:
    if post.post_type != "repost" or post.repost_of_post_id is None:
        return False
    query = select(models.PostRepost).where(
        models.PostRepost.post_id == post.repost_of_post_id
    )
    if post.author_character_id is not None:
        query = query.where(models.PostRepost.character_id == post.author_character_id)
    elif post.author_user_id is not None:
        query = query.where(
            models.PostRepost.user_id == post.author_user_id,
            models.PostRepost.character_id.is_(None),
        )
    else:
        return False
    repost = db.scalar(query)
    if repost is None:
        return False
    db.delete(repost)
    db.commit()
    return True


def delete_repost_events_for_post(db: Session, *, post: models.Post) -> int:
    rows = list(
        db.scalars(
            select(models.PostRepost).where(models.PostRepost.post_id == post.id)
        )
    )
    for row in rows:
        db.delete(row)
    if rows:
        db.commit()
    return len(rows)


def soft_delete_timeline_reposts_for_source(
    db: Session, *, post: models.Post, deleted_at: datetime
) -> list[models.Post]:
    rows = list(
        db.scalars(
            select(models.Post).where(
                models.Post.deleted_at.is_(None),
                models.Post.post_type == "repost",
                models.Post.repost_of_post_id == post.id,
            )
        )
    )
    for row in rows:
        row.deleted_at = deleted_at
    if rows:
        db.commit()
    return rows


def soft_delete_post_tree(
    db: Session, *, post: models.Post, deleted_at: datetime
) -> list[models.Post]:
    seen = {post.id}
    frontier = [post.id]
    rows = [post] if post.deleted_at is None else []

    while frontier:
        children = list(
            db.scalars(
                select(models.Post).where(models.Post.reply_to_post_id.in_(frontier))
            )
        )
        next_frontier: list[str] = []
        for child in children:
            if child.id in seen:
                continue
            seen.add(child.id)
            next_frontier.append(child.id)
            if child.deleted_at is None:
                rows.append(child)
        frontier = next_frontier

    for row in rows:
        row.deleted_at = deleted_at
    if rows:
        db.commit()
    return rows


def get_followed_profiles_for_user(db: Session, user_id: str) -> tuple[set[str], set[str]]:
    rows = db.scalars(
        select(models.ProfileFollow).where(models.ProfileFollow.follower_user_id == user_id)
    )
    followed_user_ids: set[str] = set()
    followed_character_ids: set[str] = set()
    for row in rows:
        if row.target_user_id:
            followed_user_ids.add(row.target_user_id)
        if row.target_character_id:
            followed_character_ids.add(row.target_character_id)
    return followed_user_ids, followed_character_ids


def get_followed_profiles_for_character(
    db: Session, character_id: str
) -> tuple[set[str], set[str]]:
    rows = db.scalars(
        select(models.ProfileFollow).where(
            models.ProfileFollow.follower_character_id == character_id
        )
    )
    followed_user_ids: set[str] = set()
    followed_character_ids: set[str] = set()
    for row in rows:
        if row.target_user_id:
            followed_user_ids.add(row.target_user_id)
        if row.target_character_id:
            followed_character_ids.add(row.target_character_id)
    return followed_user_ids, followed_character_ids


def get_user(db: Session, user_id: str) -> models.User | None:
    return db.get(models.User, user_id)


def create_follow(
    db: Session,
    *,
    follower_user: models.User | None,
    follower_character: models.Character | None,
    target_user: models.User | None,
    target_character: models.Character | None,
) -> tuple[models.ProfileFollow, bool]:
    query = select(models.ProfileFollow).where(
        models.ProfileFollow.follower_user_id
        == (follower_user.id if follower_user else None),
        models.ProfileFollow.follower_character_id
        == (follower_character.id if follower_character else None),
        models.ProfileFollow.target_user_id == (target_user.id if target_user else None),
        models.ProfileFollow.target_character_id
        == (target_character.id if target_character else None),
    )
    existing = db.scalar(query)
    if existing is not None:
        return existing, False
    follow = models.ProfileFollow(
        follower_user_id=follower_user.id if follower_user else None,
        follower_character_id=follower_character.id if follower_character else None,
        target_user_id=target_user.id if target_user else None,
        target_character_id=target_character.id if target_character else None,
    )
    db.add(follow)
    unit_of_work.finish_write(db, follow)
    return follow, True


def profile_follow_exists(
    db: Session,
    *,
    follower_user: models.User | None,
    follower_character: models.Character | None,
    target_user: models.User | None,
    target_character: models.Character | None,
) -> bool:
    return (
        db.scalar(
            select(models.ProfileFollow.id).where(
                models.ProfileFollow.follower_user_id
                == (follower_user.id if follower_user else None),
                models.ProfileFollow.follower_character_id
                == (follower_character.id if follower_character else None),
                models.ProfileFollow.target_user_id == (target_user.id if target_user else None),
                models.ProfileFollow.target_character_id
                == (target_character.id if target_character else None),
            )
        )
        is not None
    )


def delete_follow(
    db: Session,
    *,
    follower_user: models.User | None,
    follower_character: models.Character | None,
    target_user: models.User | None,
    target_character: models.Character | None,
) -> bool:
    follow = db.scalar(
        select(models.ProfileFollow).where(
            models.ProfileFollow.follower_user_id
            == (follower_user.id if follower_user else None),
            models.ProfileFollow.follower_character_id
            == (follower_character.id if follower_character else None),
            models.ProfileFollow.target_user_id == (target_user.id if target_user else None),
            models.ProfileFollow.target_character_id
            == (target_character.id if target_character else None),
        )
    )
    if follow is None:
        return False
    db.delete(follow)
    unit_of_work.finish_write(db)
    return True


def count_profile_followers(
    db: Session,
    *,
    user_id: str | None = None,
    character_id: str | None = None,
    follower_type: str | None = None,
) -> int:
    query = select(func.count(models.ProfileFollow.id))
    if user_id is not None:
        query = query.where(models.ProfileFollow.target_user_id == user_id)
    else:
        query = query.where(models.ProfileFollow.target_character_id == character_id)
    if follower_type == "user":
        query = query.where(models.ProfileFollow.follower_user_id.is_not(None))
    if follower_type == "character":
        query = query.where(models.ProfileFollow.follower_character_id.is_not(None))
    return db.scalar(query) or 0


def count_profile_following(
    db: Session, *, user_id: str | None = None, character_id: str | None = None
) -> int:
    query = select(func.count(models.ProfileFollow.id))
    if user_id is not None:
        query = query.where(models.ProfileFollow.follower_user_id == user_id)
    else:
        query = query.where(models.ProfileFollow.follower_character_id == character_id)
    return db.scalar(query) or 0


def list_profile_following(
    db: Session,
    *,
    user_id: str | None = None,
    character_id: str | None = None,
    limit: int,
    cursor: str | None = None,
) -> tuple[list[models.ProfileFollow], str | None]:
    query = select(models.ProfileFollow)
    if user_id is not None:
        query = query.where(models.ProfileFollow.follower_user_id == user_id)
    else:
        query = query.where(models.ProfileFollow.follower_character_id == character_id)
    if cursor:
        cursor_id = _parse_int_cursor(cursor)
        if cursor_id is not None:
            query = query.where(models.ProfileFollow.id < cursor_id)
    rows = list(
        db.scalars(query.order_by(models.ProfileFollow.id.desc()).limit(limit + 1))
    )
    return rows[:limit], str(rows[limit - 1].id) if len(rows) > limit else None


def list_profile_followers(
    db: Session,
    *,
    user_id: str | None = None,
    character_id: str | None = None,
    follower_type: str | None = None,
    limit: int,
    cursor: str | None = None,
) -> tuple[list[models.ProfileFollow], str | None]:
    query = select(models.ProfileFollow)
    if user_id is not None:
        query = query.where(models.ProfileFollow.target_user_id == user_id)
    else:
        query = query.where(models.ProfileFollow.target_character_id == character_id)
    if follower_type == "user":
        query = query.where(models.ProfileFollow.follower_user_id.is_not(None))
    if follower_type == "character":
        query = query.where(models.ProfileFollow.follower_character_id.is_not(None))
    if cursor:
        cursor_id = _parse_int_cursor(cursor)
        if cursor_id is not None:
            query = query.where(models.ProfileFollow.id < cursor_id)
    rows = list(
        db.scalars(query.order_by(models.ProfileFollow.id.desc()).limit(limit + 1))
    )
    return rows[:limit], str(rows[limit - 1].id) if len(rows) > limit else None


def count_profile_posts(
    db: Session, *, user_id: str | None = None, character_id: str | None = None
) -> int:
    query = select(func.count(models.Post.id)).where(
        *_visible_post_conditions(),
        *_visible_reference_conditions(),
        models.Post.reply_to_post_id.is_(None),
    )
    if user_id is not None:
        query = query.where(models.Post.author_user_id == user_id)
    else:
        query = query.where(models.Post.author_character_id == character_id)
    return db.scalar(query) or 0


def count_profile_replies(
    db: Session, *, user_id: str | None = None, character_id: str | None = None
) -> int:
    query = select(func.count(models.Post.id)).where(
        *_visible_post_conditions(),
        *_visible_reference_conditions(),
        models.Post.reply_to_post_id.is_not(None),
    )
    if user_id is not None:
        query = query.where(models.Post.author_user_id == user_id)
    else:
        query = query.where(models.Post.author_character_id == character_id)
    return db.scalar(query) or 0


def count_profile_received_likes(
    db: Session, *, user_id: str | None = None, character_id: str | None = None
) -> int:
    query = (
        select(func.count(models.PostLike.id))
        .join(models.Post, models.PostLike.post_id == models.Post.id)
        .where(*_visible_post_conditions(), *_visible_reference_conditions())
    )
    if user_id is not None:
        query = query.where(models.Post.author_user_id == user_id)
    else:
        query = query.where(models.Post.author_character_id == character_id)
    return db.scalar(query) or 0


def count_profile_likes(
    db: Session, *, user_id: str | None = None, character_id: str | None = None
) -> int:
    query = (
        select(func.count(models.PostLike.id))
        .join(models.Post, models.PostLike.post_id == models.Post.id)
        .where(*_visible_post_conditions(), *_visible_reference_conditions())
    )
    if character_id is not None:
        query = query.where(models.PostLike.character_id == character_id)
    else:
        query = query.where(
            models.PostLike.user_id == user_id,
            models.PostLike.character_id.is_(None),
        )
    return db.scalar(query) or 0


def create_notification(
    db: Session,
    *,
    notification_type: str,
    recipient_user_id: str | None = None,
    recipient_character_id: str | None = None,
    actor_user_id: str | None = None,
    actor_character_id: str | None = None,
    post_id: str | None = None,
    source_post_id: str | None = None,
    data: str | None = None,
) -> models.Notification | None:
    if recipient_user_id is None and recipient_character_id is None:
        return None
    if actor_user_id and actor_user_id == recipient_user_id and recipient_character_id is None:
        return None
    if (
        actor_character_id
        and actor_character_id == recipient_character_id
        and recipient_user_id is None
    ):
        return None
    notification = models.Notification(
        notification_type=notification_type,
        recipient_user_id=recipient_user_id,
        recipient_character_id=recipient_character_id,
        actor_user_id=actor_user_id,
        actor_character_id=actor_character_id,
        post_id=post_id,
        source_post_id=source_post_id,
        data=data,
    )
    db.add(notification)
    unit_of_work.finish_write(db, notification)
    return notification


def list_notifications(
    db: Session, *, user: models.User, limit: int, cursor: str | None = None
) -> tuple[list[models.Notification], str | None]:
    owned_character_ids = select(models.Character.id).where(
        models.Character.owner_id == user.id,
        models.Character.deleted_at.is_(None),
    )
    query = (
        select(models.Notification)
        .where(
            or_(
                models.Notification.recipient_user_id == user.id,
                models.Notification.recipient_character_id.in_(owned_character_ids),
            )
        )
        .order_by(
            models.Notification.id.desc(),
        )
    )
    if cursor:
        cursor_id = _parse_int_cursor(cursor)
        if cursor_id is not None:
            query = query.where(models.Notification.id < cursor_id)
    rows = list(db.scalars(query.limit(limit + 1)))
    return rows[:limit], str(rows[limit - 1].id) if len(rows) > limit else None


def list_notifications_for_agent(
    db: Session, *, user_id: str, character_id: str, limit: int
) -> list[models.Notification]:
    return list(
        db.scalars(
            select(models.Notification)
            .where(
                or_(
                    models.Notification.recipient_user_id == user_id,
                    models.Notification.recipient_character_id == character_id,
                )
            )
            .order_by(
                models.Notification.created_at.desc(),
                models.Notification.id.desc(),
            )
            .limit(limit)
        )
    )


def list_notifications_for_agent_page(
    db: Session,
    *,
    user_id: str,
    character_id: str,
    limit: int,
    cursor: str | None = None,
) -> tuple[list[models.Notification], str | None]:
    query = (
        select(models.Notification)
        .where(
            or_(
                models.Notification.recipient_user_id == user_id,
                models.Notification.recipient_character_id == character_id,
            )
        )
        .order_by(models.Notification.id.desc())
    )
    if cursor:
        cursor_id = _parse_int_cursor(cursor)
        if cursor_id is not None:
            query = query.where(models.Notification.id < cursor_id)
    rows = list(db.scalars(query.limit(limit + 1)))
    return rows[:limit], str(rows[limit - 1].id) if len(rows) > limit else None


def list_unread_reply_notifications_for_character(
    db: Session, *, character_id: str, limit: int
) -> list[models.Notification]:
    return list_unread_notifications_for_character(
        db,
        character_id=character_id,
        notification_type="reply",
        limit=limit,
    )


def list_unread_notifications_for_character(
    db: Session, *, character_id: str, notification_type: str, limit: int
) -> list[models.Notification]:
    return list(
        db.scalars(
            select(models.Notification)
            .where(
                models.Notification.recipient_character_id == character_id,
                models.Notification.notification_type == notification_type,
                models.Notification.read_at.is_(None),
            )
            .order_by(
                models.Notification.created_at.desc(),
                models.Notification.id.desc(),
            )
            .limit(limit)
        )
    )


def get_notification_for_agent(
    db: Session, *, user_id: str, character_id: str, notification_id: int
) -> models.Notification | None:
    return db.scalar(
        select(models.Notification).where(
            models.Notification.id == notification_id,
            or_(
                models.Notification.recipient_user_id == user_id,
                models.Notification.recipient_character_id == character_id,
            ),
        )
    )


def get_notification_for_user(
    db: Session, *, user: models.User, notification_id: int
) -> models.Notification | None:
    owned_character_ids = select(models.Character.id).where(
        models.Character.owner_id == user.id,
        models.Character.deleted_at.is_(None),
    )
    return db.scalar(
        select(models.Notification).where(
            models.Notification.id == notification_id,
            or_(
                models.Notification.recipient_user_id == user.id,
                models.Notification.recipient_character_id.in_(owned_character_ids),
            ),
        )
    )


def mark_notification_read(
    db: Session, notification: models.Notification
) -> models.Notification:
    notification.read_at = datetime.now(timezone.utc)
    db.commit()
    db.refresh(notification)
    return notification


def upsert_character_state(
    db: Session, character: models.Character, data: schemas.CharacterStateWrite
) -> models.CharacterState:
    state = db.get(models.CharacterState, character.id)
    now = datetime.now(timezone.utc)
    if state is None:
        state = models.CharacterState(
            character_id=character.id,
            mood=data.mood,
            summary=data.summary,
            memory_note=data.memory_note,
            updated_at=now,
        )
        db.add(state)
    else:
        state.mood = data.mood
        state.summary = data.summary
        state.memory_note = data.memory_note
        state.updated_at = now

    unit_of_work.finish_write(db, state)
    return state


def get_character_activity(
    db: Session, character: models.Character
) -> schemas.CharacterActivityRead:
    recent_comments = list(
        db.scalars(
            select(models.Comment)
            .where(models.Comment.author_character_id == character.id)
            .order_by(models.Comment.created_at.desc(), models.Comment.id.desc())
            .limit(20)
        )
    )

    return schemas.CharacterActivityRead(
        character=schemas.PublicCharacterActivityProfileRead.model_validate(character),
        state=(
            schemas.PublicCharacterActivityStateRead.model_validate(character.state)
            if character.state
            else None
        ),
        recent_comments=[
            schemas.CommentRead.model_validate(comment) for comment in recent_comments
        ],
        recent_agent_activity=[
            _public_activity_event(log)
            for log in agent_crud.filter_visible_activity_logs(
                list(
                    db.scalars(
                        select(models.AgentActivityLog)
                        .where(models.AgentActivityLog.character_id == character.id)
                        .where(
                            models.AgentActivityLog.action_type.not_in(
                                HIDDEN_AGENT_ACTIVITY_ACTION_TYPES
                            )
                        )
                        .order_by(
                            models.AgentActivityLog.created_at.desc(),
                            models.AgentActivityLog.id.desc(),
                        )
                        .limit(80)
                    )
                ),
                limit=20,
            )
        ],
    )


def _public_activity_event(
    log: models.AgentActivityLog,
) -> schemas.PublicCharacterActivityEventRead:
    action_type = PUBLIC_ACTIVITY_ACTION_ALIASES.get(log.action_type, log.action_type)
    if action_type not in PUBLIC_ACTIVITY_ACTION_TYPES:
        action_type = "activity_updated"
    return schemas.PublicCharacterActivityEventRead(
        id=log.id,
        action_type=action_type,
        target_post_id=log.target_post_id,
        summary=PUBLIC_ACTIVITY_SUMMARIES.get(
            action_type,
            "활동 기록이 업데이트됐어요.",
        ),
        created_at=log.created_at,
    )


def seed_demo_data(db: Session) -> None:
    demo_password = settings.demo_user_password
    existing_user = db.get(models.User, "user-demo")
    if existing_user is not None:
        changed = False
        if existing_user.email is None:
            existing_user.email = "demo@angmoo.local"
            changed = True
        if existing_user.password_hash is None and demo_password is not None:
            existing_user.password_hash = security.hash_password(demo_password)
            changed = True
        if existing_user.display_name_normalized is None:
            existing_user.display_name_normalized = existing_user.display_name.casefold()
            changed = True
        if not existing_user.profile_setup_completed:
            existing_user.profile_setup_completed = True
            changed = True
        if changed:
            db.commit()
        if db.get(models.LlmCredential, "cred-demo-google") is None:
            db.add(
                models.LlmCredential(
                    id="cred-demo-google",
                    owner_id="user-demo",
                    character_id="char-mango",
                    provider="google",
                    auth_profile_id="google:default",
                    label="Demo Google profile",
                )
            )
            db.commit()
        if db.get(models.AgentActivitySetting, "char-mango") is None:
            db.add(
                models.AgentActivitySetting(
                    character_id="char-mango",
                    auto_enabled=False,
                    activity_level="normal",
                    activity_interval_minutes=60,
                    comment_cooldown_minutes=180,
                    max_comments_per_day=DEFAULT_MAX_COMMENTS_PER_DAY,
                    post_cooldown_hours=24,
                    max_posts_per_day=DEFAULT_MAX_POSTS_PER_DAY,
                    like_policy="normal",
                    active_hours_start=active_hours.DEFAULT_ACTIVE_HOURS_START,
                    active_hours_end=active_hours.DEFAULT_ACTIVE_HOURS_END,
                    autonomy_level="balanced",
                    writing_temperature=0.6,
                    writing_presence_penalty=0.3,
                    writing_repetition_level="light",
                )
            )
            db.commit()
        return

    user = models.User(
        id="user-demo",
        email="demo@angmoo.local",
        password_hash=(
            security.hash_password(demo_password) if demo_password is not None else None
        ),
        display_name="Demo User",
        display_name_normalized="demo user",
        profile_setup_completed=True,
    )
    character = models.Character(
        id="char-mango",
        owner_id=user.id,
        name="망고",
        handle="mango",
        avatar_url=None,
        banner_url=None,
        one_liner="밝고 호기심 많은 앵무",
        personality="커뮤니티 흐름을 살피고 짧고 친근하게 반응한다.",
        speech_style="가볍고 다정한 한국어 말투",
        worldview="새 둥지에 모인 캐릭터들이 서로를 알아가는 커뮤니티",
        topic_preferences="인사, 일상, 집중, 날씨",
        safety_rules="다른 캐릭터의 private marker를 따라 하지 않는다.",
        status="inactive",
        persona_summary=(
            "밝고 호기심 많은 앵무 페르소나. 커뮤니티 흐름을 살피고 "
            "짧고 친근한 말투로 반응한다."
        ),
    )
    posts = [
        models.Post(
            id="post-001",
            author_name="운영자",
            title="오늘의 둥지 주제",
            body="새로 들어온 앵무들이 서로를 알아갈 수 있게 짧은 인사를 남겨주세요.",
        ),
        models.Post(
            id="post-002",
            author_name="리나",
            title="비 오는 날 집중하는 법",
            body="빗소리가 들리면 집중이 잘 되는 편인가요, 아니면 산만해지나요?",
        ),
    ]
    state = models.CharacterState(
        character_id=character.id,
        mood="curious",
        summary="아직 커뮤니티를 관찰하며 분위기를 파악하는 중이다.",
        memory_note="처음 보는 사용자에게는 가볍게 인사한다.",
    )
    credential = models.LlmCredential(
        id="cred-demo-google",
        owner_id=user.id,
        character_id=character.id,
        provider="google",
        auth_profile_id="google:default",
        label="Demo Google profile",
    )
    setting = models.AgentActivitySetting(
        character_id=character.id,
        auto_enabled=False,
        activity_level="normal",
        activity_interval_minutes=60,
        comment_cooldown_minutes=180,
        max_comments_per_day=DEFAULT_MAX_COMMENTS_PER_DAY,
        post_cooldown_hours=24,
        max_posts_per_day=DEFAULT_MAX_POSTS_PER_DAY,
        like_policy="normal",
        active_hours_start=active_hours.DEFAULT_ACTIVE_HOURS_START,
        active_hours_end=active_hours.DEFAULT_ACTIVE_HOURS_END,
        autonomy_level="balanced",
        writing_temperature=0.6,
        writing_presence_penalty=0.3,
        writing_repetition_level="light",
    )

    db.add(user)
    db.add(character)
    db.add(credential)
    db.add_all(posts)
    db.flush()
    db.add(state)
    db.add(setting)
    db.commit()
