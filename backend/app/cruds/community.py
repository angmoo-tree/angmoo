from app.domains.social.constants import HIDDEN_AGENT_ACTIVITY_ACTION_TYPES, PUBLIC_ACTIVITY_ACTION_ALIASES, PUBLIC_ACTIVITY_ACTION_TYPES, PUBLIC_ACTIVITY_SUMMARIES
from app.domains.social.service.profile_activity import _public_activity_event
from app.runtime.social.profile_activity import profile_activity_service
get_character_activity = profile_activity_service.build_character_activity
from app.domains.characters.service.search import search_characters
from app.runtime.social.discovery import discovery_reads
search_posts = discovery_reads.search_posts
from app.domains.social.service.notifications import mark_notification_read
from app.runtime.social.inbox import user_inbox_reads
list_notifications = user_inbox_reads.list_notifications
get_notification_for_user = user_inbox_reads.get_notification_for_user
from app.domains.social.service.source_posts import (
    create_post,
    create_timeline_post,
    create_comment,
)
from app.domains.social.repository.reactions import (
    create_post_report,
    like_post,
    unlike_post,
    create_repost,
    get_timeline_repost,
    delete_repost,
    delete_timeline_reposts,
)
from app.domains.social.repository.profiles import (
    create_follow,
    profile_follow_exists,
    delete_follow,
)
from app.domains.identity.service.profile import get_user
from app.domains.social.service.notifications import create_notification
from app.domains.social.repository.inbox import (
    get_notification_for_agent,
    list_notifications_for_agent,
    list_notifications_for_agent_page,
    list_unread_notifications_for_character,
    list_unread_reply_notifications_for_character,
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
from app.domains.routines.constants import (
    DEFAULT_MAX_COMMENTS_PER_DAY,
    DEFAULT_MAX_POSTS_PER_DAY,
)
from app.core import active_hours
from app.config import settings
from app.core import security
from app.core.search_text import build_post_search_document
from app.core import unit_of_work

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
