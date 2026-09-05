from app.domains.social.service.notifications import create_notification
from app.domains.social.repository.inbox import (
    get_notification_for_agent,
    list_notifications_for_agent,
    list_notifications_for_agent_page,
    list_unread_notifications_for_character,
    list_unread_reply_notifications_for_character,
    mark_notification_read,
)
from app.domains.social.repository.media import (
    claim_next_post_image_generation_job,
    count_active_post_image_jobs_for_character_between,
    count_post_media_for_character_between,
    count_service_image_global_used,
    count_service_image_quota_used,
    create_post_image_generation_job,
    create_post_image_quota_reservation,
    create_post_media,
    finish_post_image_generation_job,
    get_post_image_quota_reservation,
    list_post_media,
    lock_service_image_quota,
    mark_stale_post_image_generation_jobs_failed,
    update_post_image_quota_reservation,
)
from app.domains.social.repository.posts import (
    _like_pattern,
    _like_search_terms,
    _lock_direct_user_like,
    _visible_post_conditions,
    _visible_reference_conditions,
    character_has_authored_post,
    count_post_comments,
    count_post_likes,
    count_post_quotes,
    count_post_replies,
    count_post_reports,
    count_post_reposts,
    delete_repost_event_for_timeline_post,
    delete_repost_events_for_post,
    get_post,
    get_post_including_report_hidden,
    get_post_report,
    is_report_hidden,
    list_post_replies,
    list_post_thread_replies,
    list_posts,
    list_resident_scan_posts,
    list_timeline_posts,
    soft_delete_post_tree,
    soft_delete_timeline_reposts_for_source,
)
from app.domains.social.repository.profiles import (
    count_profile_followers,
    count_profile_following,
    count_profile_likes,
    count_profile_posts,
    count_profile_received_likes,
    count_profile_replies,
    get_followed_profiles_for_character,
    get_followed_profiles_for_user,
    list_liked_profile_posts,
    list_profile_followers,
    list_profile_following,
    list_profile_posts,
)
from app.domains.social.utils.cursors import (
    _parse_int_cursor,
)
from app.domains.social.utils.text import (
    sanitize_visible_post_body,
    sanitize_visible_post_title,
)

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
from app.config import settings
from app.core import security
from app.core.search_text import build_post_search_document
from app.core import unit_of_work
from app.cruds import agents as agent_crud

from app.domains.characters.exceptions import CharacterHandleConflictError, InvalidCharacterHandleError
from app.domains.characters.service.profile import (
    HANDLE_RE,
    normalize_character_handle,
    _fallback_handle,
    _ensure_available_handle,
    validate_character_handle_for_create,
    get_character,
    count_user_characters,
    list_characters_for_user,
    create_character,
    update_character_profile,
    update_character_persona,
    _build_persona_summary,
    _raise_handle_conflict_from_integrity,
)
from app.domains.characters.service.state import upsert_character_state


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
