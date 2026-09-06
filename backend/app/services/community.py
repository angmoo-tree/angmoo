from app.runtime.social.agent_tool_reads import agent_tool_reads
list_agent_tool_feed = agent_tool_reads.list_agent_tool_feed
_list_resident_feed_scan_page = agent_tool_reads._list_resident_feed_scan_page
list_agent_tool_following_feed = agent_tool_reads.list_agent_tool_following_feed
_agent_feed_post_summary = agent_tool_reads._agent_feed_post_summary
get_agent_tool_post_thread = agent_tool_reads.get_agent_tool_post_thread
get_agent_tool_profile = agent_tool_reads.get_agent_tool_profile
_log_inbox_notifications_provided = agent_tool_reads._log_inbox_notifications_provided
_latest_inbox_delivery_notification_ids = agent_tool_reads._latest_inbox_delivery_notification_ids
_mark_provided_inbox_notifications_read = agent_tool_reads._mark_provided_inbox_notifications_read
list_agent_tool_notifications = agent_tool_reads.list_agent_tool_notifications
mark_agent_tool_notification_read = agent_tool_reads.mark_agent_tool_notification_read
_single_post_id_hint = agent_tool_reads._single_post_id_hint
_resolve_inbox_review_target_post_id = agent_tool_reads._resolve_inbox_review_target_post_id
note_agent_tool_inbox_review = agent_tool_reads.note_agent_tool_inbox_review
observe_agent_tool_community = agent_tool_reads.observe_agent_tool_community
from app.runtime.social.agent_tools import agent_tool_actions
create_agent_tool_comment = agent_tool_actions.create_agent_tool_comment
create_agent_tool_post = agent_tool_actions.create_agent_tool_post
like_agent_tool_post = agent_tool_actions.like_agent_tool_post
reply_agent_tool_post = agent_tool_actions.reply_agent_tool_post
quote_agent_tool_post = agent_tool_actions.quote_agent_tool_post
unlike_agent_tool_post = agent_tool_actions.unlike_agent_tool_post
repost_agent_tool_post = agent_tool_actions.repost_agent_tool_post
unrepost_agent_tool_post = agent_tool_actions.unrepost_agent_tool_post
follow_agent_tool_profile = agent_tool_actions.follow_agent_tool_profile
unfollow_agent_tool_profile = agent_tool_actions.unfollow_agent_tool_profile
from app.domains.social.service.agent_tool_authorization import (
    _session_fingerprint, _agent_tool_lookup_session_key,
    _is_daypart_memory_session_key, _agent_tool_scratch_lane,
    _raise_agent_tool_authorization_error, _agent_tool_character_id,
)
from app.runtime.social.agent_tool_authorization import (
    _get_agent_tool_run, _agent_tool_user, _ensure_tick_action_allowed,
)
from app.runtime.social.feed_history import recent_own_root_topic_exists
from app.core.json_objects import _json_object
from app.domains.routines.constants import FEED_SEED_CONSUMED_ACTION_TYPE, FEED_HISTORY_SANITIZED_ACTION_TYPE, FEED_SEED_CONSUMED_LOOKBACK_DAYS, FEED_SEED_CONSUMED_LIMIT, RECENT_FEED_INTEREST_LOG_SCAN_LIMIT, RECENT_OWN_ROOT_TOPIC_HISTORY_HOURS, RECENT_OWN_ROOT_TOPIC_SCAN_LIMIT
from app.domains.routines.service.feed_history import feed_seed_source_already_consumed
from app.domains.routines.service.feed_history_values import activity_result_text_for_prompt
from app.domains.social.service.topic_metadata import _topic_metadata_from_result, _topic_metadata_from_post_columns, _store_post_topic_metadata, _recent_feed_interest_post_is_eligible
from app.runtime.social.topic_metadata import _latest_post_created_topic_metadata, _topic_metadata_for_post, post_topic_signature_for_prompt
from app.runtime.social.feed_history import format_feed_seed_consumed_sources_for_prompt, format_recent_feed_interest_history_for_prompt, format_recent_own_root_topic_history_for_prompt, build_feed_history_sanitize_skeleton, format_feed_history_metadata_fallback_for_prompt, maybe_log_feed_seed_consumed_for_created_post
from app.domains.routines.service.feed_history_values import (
    _safe_feed_history_post_id,
    _feed_history_sanitize_skeleton_item,
    _format_feed_history_sanitize_task_items,
    format_feed_history_sanitize_skeleton_for_prompt,
    _clean_feed_history_summary,
    _safe_feed_history_warnings,
    _sanitize_feed_history_item,
    _feed_history_items_by_post_id,
    _feed_history_metadata_only_summary,
    _merge_feed_history_sanitize_group,
    _feed_history_sanitize_skeleton_has_items,
    _merge_feed_history_sanitize_payload,
    _format_sanitized_feed_history_items,
    _feed_history_payload_json,
    format_feed_history_sanitize_payload_for_prompt,
)
from app.domains.routines.constants import FEED_HISTORY_SANITIZED_CONSUMED_LIMIT, RECENT_FEED_INTEREST_HISTORY_LIMIT, RECENT_OWN_ROOT_TOPIC_HISTORY_LIMIT, FEED_HISTORY_STYLE_MARKER_RE
from app.domains.social.repository.resident_affordances import (
    _character_already_liked_post,
    _character_already_reposted_post,
    _thread_reply_post_ids,
)
from app.domains.social.service.resident_affordances import (
    _character_already_following_profile,
    _character_can_follow_profile_for_resident_scan,
    _character_can_reply_to_post_for_resident_scan,
    _post_has_resident_feed_action,
    resident_feed_action_affordance,
    resident_inbox_action_affordance,
    _notification_has_resident_inbox_action,
    _notification_source_is_public_context_visible,
    list_resident_actionable_inbox_notifications,
    _ensure_agent_can_reply_to_thread,
    _is_direct_reply_to_character_post,
    _thread_root_post_id,
    _candidate_target_parts,
)
from app.domains.social.service.agent_presentation import (
    _neutralize_post_reference_for_agent,
    _neutralize_post_summary_for_agent,
    _neutralize_post_detail_for_agent,
    _neutralize_post_thread_for_agent,
    _neutralize_feed_page_for_agent,
    _clip_agent_context_text,
    _compact_agent_notification_read,
)
from app.runtime.social.profile_activity import profile_activity_service
get_character_activity = profile_activity_service.get_character_activity
from app.domains.social.service.feed import list_today_popular_posts, _today_start_utc, _post_reaction_score
from app.runtime.social.discovery import discovery_service
list_today_activity = discovery_service.list_today_activity
search_nest = discovery_service.search_nest
from app.domains.social.service.feed import list_posts, list_feed, list_following_feed, list_character_following_feed
from app.domains.social.service.inbox import list_notifications_for_character, mark_character_notification_read
from app.runtime.social.inbox import inbox_service
list_notifications = inbox_service.list_notifications
mark_notification_read = inbox_service.mark_notification_read
from app.domains.social.service.profiles import (
    follow_profile,
    get_follow_status,
    unfollow_profile,
    get_user_profile,
    get_character_profile,
    get_user_profile_feed,
    get_character_profile_feed,
    get_user_profile_connections,
    get_character_profile_connections,
    _profile_ref,
    _profile_connections_page,
    _profile_list_item,
    _viewer_follows_character,
    _character_search_result,
    _resolve_follower,
    _resolve_target_profile,
    _ensure_not_self_follow,
)
from app.domains.social.utils.limits import _safe_limit
from app.domains.social.service.activity_results import _clip_text, _safe_topic_text, _body_preview, _fallback_topic_signature, build_post_created_activity_result
from app.domains.social.service.notifications import _notify_post_owner, _notify_mentioned_characters
from app.domains.social.service.timeline import _resolve_author_character, _can_delete_post, _reply_title, _quote_title, _timeline_world_scope, create_comment
from app.runtime.social.timeline import timeline_service
report_post = timeline_service.report_post
delete_post = timeline_service.delete_post
create_post = timeline_service.create_post
create_reply = timeline_service.create_reply
create_quote = timeline_service.create_quote
like_post = timeline_service.like_post
unlike_post = timeline_service.unlike_post
repost_post = timeline_service.repost_post
unrepost_post = timeline_service.unrepost_post

from app.domains.social.exceptions import (
    AgentRunAuthorizationError,
    CharacterNotFoundError,
    CharacterOwnershipError,
    CharacterSuspendedError,
    CommunityRateLimitedError,
    CommunityServiceError,
    FollowSelfError,
    LegacyCommentsDisabledError,
    NotificationNotFoundError,
    PostNotFoundError,
    PostReportNotAllowedError,
    PostWorldScopeError,
    ProfileNotFoundError,
)
from app.domains.social.service.posts import (
    get_post,
    get_post_thread,
)
from app.domains.social.service.presentation import (
    _hidden_post_detail,
    _mentioned_characters_for_texts,
    _notification_actor_identity,
    _notification_post_preview,
    _notification_read,
    _notification_recipient_identity,
    _post_author_identity,
    _post_detail,
    _post_media_reads,
    _post_reference,
    _post_summary,
)
from app.domains.social.service.visibility import (
    _is_post_public_context_visible,
    is_post_public_context_visible,
)
from app.domains.social.constants import DELETED_CHARACTER_NAME, MENTION_HANDLE_RE, REPORT_HIDDEN_MESSAGE, REPORT_HIDDEN_TITLE

from app.domains.characters.service import state as character_state
from app.domains.characters.exceptions import CharacterStateNotFoundError
import hashlib
import json
import logging
import re
import time as time_module
from datetime import UTC, datetime, time, timedelta
from typing import Any, Iterable
from uuid import uuid4

from sqlalchemy import case, func, select
from sqlalchemy.orm import Session

from app.domains.routines.models.resident import AgentActivityLog as _model_AgentActivityLog
from app.domains.routines.models.resident import AgentRun as _model_AgentRun
from app.domains.characters.models import CharacterState as _model_CharacterState
from app.domains.social.models.posts import Notification as _model_Notification
from app.domains.social.models.posts import Post as _model_Post
from app.domains.identity.models import User as _model_User
from app.runtime.persistence.model_registration import register_models
register_models()
from app import schemas
from app.core import unit_of_work
from app.core.search_text import build_post_search_document
from app.cruds import agent_runs as agent_run_crud
from app.cruds import agents as agent_crud
from app.cruds import community as community_crud
from app.services import agent_activity_policy
from app.services import community_abuse_quota
from app.services.agent_briefs import (
    is_feed_scan_community_theme_brief,
    normalize_post_seed_intent,
)
from app.core.context_text import neutralize_context_text

logger = logging.getLogger(__name__)

COMPLETE_TICK_POLICY_ACTIONS = {
    "create_post": "post",
    "reply": "reply",
    "like": "like",
    "repost": "repost",
    "follow": "follow",
    "unfollow": "unfollow",
    "observe": "observe",
}
COMPLETE_TICK_CANDIDATE_ACTION_TYPES = {"like", "repost", "follow"}
COMPLETE_TICK_DECISION_TYPES = {
    "existing_post_interaction",
    "create_post",
    "observe",
    "relationship_review",
}
NOOP_COMPLETE_TICK_ACTION_PREFIXES = ("like_skipped_",)
from app.domains.social.constants import FEED_SCAN_BODY_PREVIEW_CHARS


def _diagnostic_hash(value: str | None) -> str | None:
    if value is None:
        return None
    trimmed = value.strip()
    if not trimmed:
        return None
    return hashlib.sha256(trimmed.encode("utf-8")).hexdigest()[:16]


def _json_byte_length(value: Any) -> int | None:
    try:
        return len(json.dumps(value, ensure_ascii=False, default=str).encode("utf-8"))
    except (TypeError, ValueError):
        return None


def _feed_history_sanitize_payload_bytes(
    data: schemas.AgentFeedHistorySanitizeCreate,
) -> int | None:
    return _json_byte_length(data.model_dump())


def _elapsed_ms(started_at: float) -> int:
    return int((time_module.monotonic() - started_at) * 1000)












def _reject_complete_tick(
    db: Session,
    *,
    run: _model_AgentRun,
    message: str,
    target_post_id: str | None = None,
) -> None:
    try:
        agent_crud.log_activity(
            db,
            user_id=run.user_id,
            character_id=run.character_id,
            action_type="complete_tick_rejected",
            target_post_id=target_post_id or run.post_id,
            reason="agent_tool_complete_tick_rejected",
            result=message[:1000],
        )
    except Exception:
        logger.exception(
            "complete_tick_rejection_log_failed character_id=%s run_id=%s",
            run.character_id,
            run.id,
        )
    raise AgentRunAuthorizationError(message)


































































































def _complete_tick_representative_target(
    current: str | None, candidate: str | None
) -> str | None:
    return current or candidate






















































































































































































def note_agent_tool_feed_interests(
    db: Session, session_key: str, data: schemas.AgentFeedInterestsCreate
) -> schemas.AgentToolNoteRead:
    run = _get_agent_tool_run(db, session_key=session_key, action="note_feed_interests")
    interests: list[schemas.AgentFeedInterestItem] = []
    hidden_interest_count = 0
    warnings: list[str] = []
    for item in data.interests[:1]:
        post = community_crud.get_post(db, item.post_id)
        if post is None or not _is_post_public_context_visible(db, post):
            hidden_interest_count += 1
            continue
        interests.append(item)
    post_seed = data.post_seed or ""
    post_seed_intent = normalize_post_seed_intent(
        data.post_seed_intent, post_seed=data.post_seed
    )
    if not interests:
        if post_seed.strip() or post_seed_intent:
            warnings.append("post_seed_dropped_without_feed_interest")
        post_seed = ""
        post_seed_intent = ""
    if (
        interests
        and (post_seed.strip() or post_seed_intent)
        and post_seed_intent == "public_reaction"
    ):
        warnings.append("legacy_reaction_seed_not_writable")
    if (
        interests
        and (post_seed.strip() or post_seed_intent)
        and feed_seed_source_already_consumed(
            db,
            character_id=run.character_id,
            source_post_id=interests[0].post_id,
        )
    ):
        post_seed = ""
        post_seed_intent = ""
        warnings.append("seed_source_already_consumed")
    if (
        interests
        and (post_seed.strip() or post_seed_intent)
        and recent_own_root_topic_exists(
            db,
            character_id=run.character_id,
            topic_signature=data.topic_signature,
        )
    ):
        post_seed = ""
        post_seed_intent = ""
        warnings.append("post_seed_topic_repeated_recent_own_root")
    payload = {
        "interests": [item.model_dump() for item in interests],
        "post_seed": post_seed,
        "post_seed_intent": post_seed_intent,
        "topic_signature": _safe_topic_text(data.topic_signature, 300),
        "novelty_basis": _safe_topic_text(data.novelty_basis, 500),
        "no_relevant_signal": not interests,
        "review_reason": data.review_reason or "",
    }
    if hidden_interest_count:
        warnings.append("hidden_or_unavailable_interest_post_ignored")
    if warnings:
        payload["warnings"] = warnings
    result = json.dumps(payload, ensure_ascii=False)
    agent_crud.log_activity(
        db,
        user_id=run.user_id,
        character_id=run.character_id,
        action_type="feed_interests_noted",
        target_post_id=interests[0].post_id if interests else run.post_id,
        reason="agent_tool_note_feed_interests",
        result=result[:4000],
    )
    return schemas.AgentToolNoteRead(
        status="ok", action_type="feed_interests_noted", result=result
    )


def note_agent_tool_feed_history_sanitize(
    db: Session, session_key: str, data: schemas.AgentFeedHistorySanitizeCreate
) -> schemas.AgentToolNoteRead:
    started_at = time_module.monotonic()
    session_key_hash = _diagnostic_hash(session_key)
    payload_bytes = _feed_history_sanitize_payload_bytes(data)
    logger.info(
        "feed_history_sanitize_tool_endpoint_started "
        "sessionKeyHash=%s consumedSourcesCount=%s recentFeedInterestsCount=%s "
        "recentOwnRootTopicsCount=%s requestPayloadBytes=%s",
        session_key_hash,
        len(data.consumed_sources),
        len(data.recent_feed_interests),
        len(data.recent_own_root_topics),
        payload_bytes,
    )
    run: Any | None = None
    try:
        run = _get_agent_tool_run(
            db, session_key=session_key, action="note_feed_history_sanitize"
        )
        skeleton = (
            build_feed_history_sanitize_skeleton(db, character_id=run.character_id)
            if db is not None
            else {}
        )
        if _feed_history_sanitize_skeleton_has_items(skeleton):
            payload = _merge_feed_history_sanitize_payload(
                skeleton=skeleton,
                data=data,
            )
        else:
            payload = {
                "consumed_sources": [
                    _sanitize_feed_history_item(item)
                    for item in data.consumed_sources[
                        :FEED_HISTORY_SANITIZED_CONSUMED_LIMIT
                    ]
                ],
                "recent_feed_interests": [
                    _sanitize_feed_history_item(item)
                    for item in data.recent_feed_interests[
                        :RECENT_FEED_INTEREST_HISTORY_LIMIT
                    ]
                ],
                "recent_own_root_topics": [
                    _sanitize_feed_history_item(item)
                    for item in data.recent_own_root_topics[
                        :RECENT_OWN_ROOT_TOPIC_HISTORY_LIMIT
                    ]
                ],
            }
        result = _feed_history_payload_json(payload)
        agent_crud.log_activity(
            db,
            user_id=run.user_id,
            character_id=run.character_id,
            action_type=FEED_HISTORY_SANITIZED_ACTION_TYPE,
            target_post_id=run.post_id,
            reason="agent_tool_note_feed_history_sanitize",
            result=result[:4000],
        )
        logger.info(
            "feed_history_sanitize_tool_endpoint_finished "
            "sessionKeyHash=%s agentRunId=%s characterId=%s status=ok "
            "durationMs=%s resultBytes=%s",
            session_key_hash,
            getattr(run, "id", None),
            getattr(run, "character_id", None),
            _elapsed_ms(started_at),
            _json_byte_length(result),
        )
        return schemas.AgentToolNoteRead(
            status="ok", action_type=FEED_HISTORY_SANITIZED_ACTION_TYPE, result=result
        )
    except Exception as exc:
        failure_kind = (
            "authorization_error"
            if isinstance(exc, AgentRunAuthorizationError)
            else "backend_exception"
        )
        logger.warning(
            "feed_history_sanitize_tool_endpoint_error "
            "sessionKeyHash=%s agentRunId=%s characterId=%s status=error "
            "durationMs=%s errorCategory=%s failureKind=%s",
            session_key_hash,
            getattr(run, "id", None),
            getattr(run, "character_id", None),
            _elapsed_ms(started_at),
            type(exc).__name__,
            failure_kind,
        )
        raise










def _complete_tick_target_post(
    db: Session,
    *,
    run: _model_AgentRun,
    action_type: str,
    post_id: str | None,
) -> _model_Post:
    if not post_id:
        _reject_complete_tick(
            db,
            run=run,
            message=f"{action_type} requires post_id.",
            target_post_id=post_id,
        )
    post = community_crud.get_post(db, post_id)
    if (
        post is None
        or post.deleted_at is not None
        or not _is_post_public_context_visible(db, post)
    ):
        _reject_complete_tick(
            db,
            run=run,
            message=f"{action_type} target post was not found.",
            target_post_id=post_id,
        )
    return post


def _ensure_complete_tick_reply_target_is_not_self(
    db: Session, *, run: _model_AgentRun, post: _model_Post
) -> None:
    if post.author_character_id == run.character_id:
        _reject_complete_tick(
            db,
            run=run,
            message=(
                "reply target is self-authored. Reply to another character's "
                "post in the viewed thread instead."
            ),
            target_post_id=post.id,
        )


def _complete_tick_follow_status(
    db: Session,
    *,
    run: _model_AgentRun,
    target_type: str | None,
    target_id: str | None,
    action_type: str,
) -> bool:
    if not target_type or not target_id:
        _reject_complete_tick(
            db,
            run=run,
            message=(
                f"{action_type} requires target_type and target_id. Use the exact "
                f"{action_type}_payload target_type/target_id shown in actionable_feed_candidates."
            ),
        )
    follower_character = community_crud.get_character(db, run.character_id)
    if follower_character is None or follower_character.deleted_at is not None:
        _reject_complete_tick(
            db,
            run=run,
            message=f"{action_type} follower character was not found.",
        )
    try:
        target_user, target_character = _resolve_target_profile(db, target_type, target_id)
        _ensure_not_self_follow(None, follower_character, target_user, target_character)
    except ProfileNotFoundError:
        _reject_complete_tick(
            db,
            run=run,
            message=(
                f"{action_type} target was not found. Use the exact "
                f"{action_type}_payload target_type/target_id shown in actionable_feed_candidates; "
                "do not mix user and character ids."
            ),
        )
    except FollowSelfError as exc:
        _reject_complete_tick(db, run=run, message=str(exc))
    return community_crud.profile_follow_exists(
        db,
        follower_user=None,
        follower_character=follower_character,
        target_user=target_user,
        target_character=target_character,
    )


def _resident_action_candidate_id(
    *,
    run_id: str,
    character_id: str,
    action_type: str,
    target_key: str,
) -> str:
    digest = hashlib.sha256(
        f"{run_id}:{character_id}:{action_type}:{target_key}".encode("utf-8")
    ).hexdigest()[:12]
    return f"cand_{action_type}_{digest}"




def _put_candidate_action(
    candidate_actions: dict[str, schemas.AgentCompleteTickAction],
    *,
    run: _model_AgentRun,
    action_type: str,
    target_key: str,
    action: schemas.AgentCompleteTickAction,
) -> None:
    candidate_id = _resident_action_candidate_id(
        run_id=run.id,
        character_id=run.character_id,
        action_type=action_type,
        target_key=target_key,
    )
    candidate_actions.setdefault(candidate_id, action)


def _build_complete_tick_candidate_actions(
    db: Session,
    *,
    run: _model_AgentRun,
    policy: agent_activity_policy.ActivityPolicy | None,
) -> dict[str, schemas.AgentCompleteTickAction]:
    allowed_actions = (
        policy.allowed_actions
        if policy is not None
        else ("like", "repost", "follow")
    )
    allowed = set(allowed_actions)
    candidate_actions: dict[str, schemas.AgentCompleteTickAction] = {}

    feed = list_feed(db, limit=50)
    for post in feed.items:
        self_authored = post.author_character_id == run.character_id
        if "like" in allowed and not _character_already_liked_post(
            db, character_id=run.character_id, post_id=post.id
        ):
            _put_candidate_action(
                candidate_actions,
                run=run,
                action_type="like",
                target_key=f"post:{post.id}",
                action=schemas.AgentCompleteTickAction(
                    action_type="like", post_id=post.id
                ),
            )
        if "repost" in allowed and not _character_already_reposted_post(
            db, character_id=run.character_id, post_id=post.id
        ):
            _put_candidate_action(
                candidate_actions,
                run=run,
                action_type="repost",
                target_key=f"post:{post.id}",
                action=schemas.AgentCompleteTickAction(
                    action_type="repost", post_id=post.id
                ),
            )
        target_type, target_id = _candidate_target_parts(
            user_id=post.author_user_id, character_id=post.author_character_id
        )
        if (
            "follow" in allowed
            and not self_authored
            and target_type is not None
            and target_id is not None
        ):
            try:
                already_following = _character_already_following_profile(
                    db,
                    character_id=run.character_id,
                    target_type=target_type,
                    target_id=target_id,
                )
            except ProfileNotFoundError:
                already_following = True
            if not already_following:
                _put_candidate_action(
                    candidate_actions,
                    run=run,
                    action_type="follow",
                    target_key=f"{target_type}:{target_id}",
                    action=schemas.AgentCompleteTickAction(
                        action_type="follow",
                        target_type=target_type,
                        target_id=target_id,
                    ),
                )

    if "follow" in allowed:
        notifications = list(
            db.scalars(
                select(_model_Notification)
                .where(
                    _model_Notification.recipient_character_id == run.character_id,
                    _model_Notification.notification_type == "reply",
                    _model_Notification.read_at.is_(None),
                )
                .order_by(
                    _model_Notification.created_at.desc(),
                    _model_Notification.id.desc(),
                )
                .limit(30)
            )
        )
        for notification in notifications:
            target_type, target_id = _candidate_target_parts(
                user_id=notification.actor_user_id,
                character_id=notification.actor_character_id,
            )
            if target_type is None or target_id is None:
                continue
            if target_type == "character" and target_id == run.character_id:
                continue
            try:
                already_following = _character_already_following_profile(
                    db,
                    character_id=run.character_id,
                    target_type=target_type,
                    target_id=target_id,
                )
            except ProfileNotFoundError:
                already_following = True
            if already_following:
                continue
            _put_candidate_action(
                candidate_actions,
                run=run,
                action_type="follow",
                target_key=f"{target_type}:{target_id}",
                action=schemas.AgentCompleteTickAction(
                    action_type="follow",
                    target_type=target_type,
                    target_id=target_id,
                ),
            )

    return candidate_actions


def _resolve_complete_tick_candidate_actions(
    db: Session,
    *,
    run: _model_AgentRun,
    data: schemas.AgentCompleteTickCreate,
    policy: agent_activity_policy.ActivityPolicy | None,
) -> list[schemas.AgentCompleteTickAction]:
    candidate_ids = data.selected_candidate_ids
    if not candidate_ids:
        return []
    if len(set(candidate_ids)) != len(candidate_ids):
        _reject_complete_tick(
            db,
            run=run,
            message="selected_candidate_ids contains a duplicate candidate_id.",
        )
    candidate_actions = _build_complete_tick_candidate_actions(
        db, run=run, policy=policy
    )
    resolved: list[schemas.AgentCompleteTickAction] = []
    for candidate_id in candidate_ids:
        action = candidate_actions.get(candidate_id)
        if action is None:
            _reject_complete_tick(
                db,
                run=run,
                message=(
                    "selected_candidate_ids contains an unknown or no-longer-valid "
                    f"candidate_id: {candidate_id}"
                ),
            )
        resolved.append(action)
    return resolved


def _validate_complete_tick_decision_type(
    db: Session, *, run: _model_AgentRun, data: schemas.AgentCompleteTickCreate
) -> None:
    decision_type = data.decision_type
    if decision_type is None:
        return
    if decision_type not in COMPLETE_TICK_DECISION_TYPES:
        _reject_complete_tick(
            db,
            run=run,
            message=f"Unknown resident tick decision_type: {decision_type}",
        )
    action_types = [action.action_type for action in data.actions]
    if decision_type == "existing_post_interaction":
        if any(action_type in {"create_post", "observe", "unfollow"} for action_type in action_types):
            _reject_complete_tick(
                db,
                run=run,
                message=(
                    "existing_post_interaction can only use selected_candidate_ids "
                    "and optional reply actions."
                ),
            )
        return
    if data.selected_candidate_ids:
        _reject_complete_tick(
            db,
            run=run,
            message=f"{decision_type} cannot include selected_candidate_ids.",
        )
    if decision_type == "create_post" and action_types != ["create_post"]:
        _reject_complete_tick(
            db,
            run=run,
            message="create_post decision_type requires exactly one create_post action.",
        )
    if decision_type == "observe" and action_types != ["observe"]:
        _reject_complete_tick(
            db,
            run=run,
            message="observe decision_type requires exactly one observe action.",
        )
    if decision_type == "relationship_review":
        data.relationship_review = True
        if any(action_type not in {"observe", "unfollow"} for action_type in action_types):
            _reject_complete_tick(
                db,
                run=run,
                message="relationship_review decision_type can only observe or unfollow.",
            )


def _validate_complete_tick_actions_before_execution(
    db: Session, *, run: _model_AgentRun, data: schemas.AgentCompleteTickCreate
) -> None:
    seen_likes: set[str] = set()
    seen_reposts: set[str] = set()
    seen_follows: set[tuple[str, str]] = set()
    seen_unfollows: set[tuple[str, str]] = set()
    for action in data.actions:
        if action.action_type == "observe":
            continue
        if action.action_type == "create_post":
            if not action.title or not action.body:
                _reject_complete_tick(
                    db,
                    run=run,
                    message="create_post requires title and body.",
                )
            continue
        if action.action_type == "reply":
            post = _complete_tick_target_post(
                db, run=run, action_type="reply", post_id=action.post_id
            )
            _ensure_complete_tick_reply_target_is_not_self(db, run=run, post=post)
            if not action.body:
                _reject_complete_tick(
                    db,
                    run=run,
                    message="reply requires body.",
                    target_post_id=action.post_id,
                )
            if len(action.body) > 1000:
                _reject_complete_tick(
                    db,
                    run=run,
                    message="reply body must be 1000 chars or less.",
                    target_post_id=action.post_id,
                )
            root_post_id = _thread_root_post_id(db, post.id)
            thread_viewed = db.scalar(
                select(_model_AgentActivityLog.id)
                .where(
                    _model_AgentActivityLog.character_id == run.character_id,
                    _model_AgentActivityLog.action_type == "thread_viewed",
                    _model_AgentActivityLog.target_post_id == root_post_id,
                    _model_AgentActivityLog.created_at >= run.created_at,
                )
                .limit(1)
            )
            if thread_viewed is None:
                _reject_complete_tick(
                    db,
                    run=run,
                    message=(
                        "reply requires angmoo_get_post_thread before complete_tick. "
                        f"Call angmoo_get_post_thread({root_post_id}) first, then retry reply."
                    ),
                    target_post_id=root_post_id,
                )
            try:
                _ensure_agent_can_reply_to_thread(
                    db, post_id=action.post_id, character_id=run.character_id
                )
            except AgentRunAuthorizationError as exc:
                _reject_complete_tick(
                    db,
                    run=run,
                    message=str(exc),
                    target_post_id=root_post_id,
                )
            continue
        if action.action_type == "like":
            post = _complete_tick_target_post(
                db, run=run, action_type="like", post_id=action.post_id
            )
            if post.id in seen_likes:
                _reject_complete_tick(
                    db,
                    run=run,
                    message="like is duplicated for this post in the same complete_tick payload.",
                    target_post_id=post.id,
                )
            seen_likes.add(post.id)
            if _character_already_liked_post(
                db, character_id=run.character_id, post_id=post.id
            ):
                _reject_complete_tick(
                    db,
                    run=run,
                    message=(
                        "like is blocked for this post: already_liked. "
                        "Do not retry like for this same post_id in this tick."
                    ),
                    target_post_id=post.id,
                )
            continue
        if action.action_type == "repost":
            post = _complete_tick_target_post(
                db, run=run, action_type="repost", post_id=action.post_id
            )
            if post.id in seen_reposts:
                _reject_complete_tick(
                    db,
                    run=run,
                    message="repost is duplicated for this post in the same complete_tick payload.",
                    target_post_id=post.id,
                )
            seen_reposts.add(post.id)
            if _character_already_reposted_post(
                db, character_id=run.character_id, post_id=post.id
            ):
                _reject_complete_tick(
                    db,
                    run=run,
                    message=(
                        "repost is blocked for this post: already_reposted. "
                        "Do not retry repost for this same post_id in this tick."
                    ),
                    target_post_id=post.id,
                )
            continue
        if action.action_type == "follow":
            key = (action.target_type or "", action.target_id or "")
            if key in seen_follows:
                _reject_complete_tick(
                    db,
                    run=run,
                    message="follow is duplicated for this target in the same complete_tick payload.",
                )
            seen_follows.add(key)
            already_following = _complete_tick_follow_status(
                db,
                run=run,
                target_type=action.target_type,
                target_id=action.target_id,
                action_type="follow",
            )
            if already_following:
                _reject_complete_tick(
                    db,
                    run=run,
                    message=(
                        "follow is blocked for this profile: already_following. "
                        "Do not retry follow for this same target_type/target_id in this tick."
                    ),
                )
            continue
        if action.action_type == "unfollow":
            key = (action.target_type or "", action.target_id or "")
            if key in seen_unfollows:
                _reject_complete_tick(
                    db,
                    run=run,
                    message="unfollow is duplicated for this target in the same complete_tick payload.",
                )
            seen_unfollows.add(key)
            already_following = _complete_tick_follow_status(
                db,
                run=run,
                target_type=action.target_type,
                target_id=action.target_id,
                action_type="unfollow",
            )
            if not already_following:
                _reject_complete_tick(
                    db,
                    run=run,
                    message="unfollow is blocked for this profile: not_following.",
                )


def complete_agent_tool_tick(
    db: Session, session_key: str, data: schemas.AgentCompleteTickCreate
) -> schemas.AgentCompleteTickRead:
    run = _get_agent_tool_run(db, session_key=session_key, action="complete_tick")
    _agent_tool_user(db, run, action="complete_tick", session_key=session_key)
    policy: agent_activity_policy.ActivityPolicy | None = None
    policy_enforced = agent_activity_policy.is_policy_enforced_session(run.session_key)
    if policy_enforced:
        policy = agent_activity_policy.build_activity_policy(
            db,
            character_id=run.character_id,
            ignore_active_hours=agent_activity_policy.is_manual_policy_session(
                run.session_key
            ),
        )
        raw_candidate_actions = [
            action.action_type
            for action in data.actions
            if action.action_type in COMPLETE_TICK_CANDIDATE_ACTION_TYPES
        ]
        if raw_candidate_actions:
            _reject_complete_tick(
                db,
                run=run,
                message=(
                    "Resident ticks must submit like/repost/follow through "
                    "selected_candidate_ids, not raw action objects."
                ),
            )
        resolved_candidate_actions = _resolve_complete_tick_candidate_actions(
            db, run=run, data=data, policy=policy
        )
        if resolved_candidate_actions:
            data.actions = [*resolved_candidate_actions, *data.actions]
        if len(data.actions) > 4:
            _reject_complete_tick(
                db,
                run=run,
                message="A resident tick can execute at most 4 actions total.",
            )
        _validate_complete_tick_decision_type(db, run=run, data=data)

    action_types = [action.action_type for action in data.actions]
    writing_actions = [
        action_type
        for action_type in action_types
        if action_type in {"create_post", "reply"}
    ]
    if len(writing_actions) > 1:
        _reject_complete_tick(
            db,
            run=run,
            message="A resident tick can write at most one create_post or reply action.",
        )
    if "create_post" in action_types and len(action_types) > 1:
        _reject_complete_tick(
            db,
            run=run,
            message="create_post must be the only action in a resident tick.",
        )
    if "observe" in action_types and len(action_types) > 1:
        _reject_complete_tick(
            db,
            run=run,
            message="observe cannot be combined with public actions.",
        )
    if "unfollow" in action_types and not data.relationship_review:
        _reject_complete_tick(
            db,
            run=run,
            message="unfollow is only allowed in a relationship review tick.",
        )
    if data.relationship_review and any(
        action_type not in {"observe", "unfollow"} for action_type in action_types
    ):
        _reject_complete_tick(
            db,
            run=run,
            message="relationship review ticks can only observe or unfollow.",
        )
    pending_cue = agent_crud.get_pending_feed_cue(db, run.character_id)
    if pending_cue is not None and action_types != ["create_post"]:
        _reject_complete_tick(
            db,
            run=run,
            message="A pending feed cue requires exactly one create_post action.",
        )
    if policy_enforced and policy is not None:
        for action_type in action_types:
            policy_action = COMPLETE_TICK_POLICY_ACTIONS.get(action_type)
            if policy_action is None:
                _reject_complete_tick(
                    db,
                    run=run,
                    message=(
                        f"{action_type} is not a valid complete_tick action_type. "
                        "For a new post, use action_type=create_post; post is only an activity policy name."
                    ),
                )
            if policy_action in policy.allowed_actions:
                continue
            reason = policy.blocked_reasons.get(
                policy_action, "action is not allowed for this tick"
            )
            _reject_complete_tick(
                db,
                run=run,
                message=f"{action_type} is not allowed in this resident tick: {reason}",
            )
        if (
            not action_types
            and "observe" not in policy.allowed_actions
            and "post" in policy.allowed_actions
        ):
            _reject_complete_tick(
                db,
                run=run,
                message=(
                    "A resident tick with observe disabled and policy action post allowed "
                    "cannot finish without actions. If no existing-post reaction fits, "
                    "submit action_type=create_post as self_update_post or community_theme_post."
                ),
            )

    _validate_complete_tick_actions_before_execution(db, run=run, data=data)

    executed_actions: list[str] = []
    representative_target_post_id: str | None = None
    for action in data.actions:
        if action.action_type == "observe":
            executed_actions.append("observe")
            continue
        if action.action_type == "create_post":
            if not action.title or not action.body:
                _reject_complete_tick(
                    db,
                    run=run,
                    message="create_post requires title and body.",
                )
            created = create_agent_tool_post(
                db,
                session_key,
                schemas.PostCreate(
                    title=action.title,
                    body=action.body,
                    author_character_id=run.character_id,
                ),
                consume_pending_feed_cue=pending_cue is not None,
                feed_cue_id=pending_cue.id if pending_cue is not None else None,
            )
            executed_actions.append(f"create_post:{created.id}")
            representative_target_post_id = _complete_tick_representative_target(
                representative_target_post_id, created.id
            )
            continue
        if action.action_type == "reply":
            if not action.post_id or not action.body:
                _reject_complete_tick(
                    db,
                    run=run,
                    message="reply requires post_id and body.",
                    target_post_id=action.post_id,
                )
            if len(action.body) > 1000:
                _reject_complete_tick(
                    db,
                    run=run,
                    message="reply body must be 1000 chars or less.",
                    target_post_id=action.post_id,
                )
            post = _complete_tick_target_post(
                db, run=run, action_type="reply", post_id=action.post_id
            )
            _ensure_complete_tick_reply_target_is_not_self(db, run=run, post=post)
            root_post_id = _thread_root_post_id(db, post.id)
            thread_viewed = db.scalar(
                select(_model_AgentActivityLog.id)
                .where(
                    _model_AgentActivityLog.character_id == run.character_id,
                    _model_AgentActivityLog.action_type == "thread_viewed",
                    _model_AgentActivityLog.target_post_id == root_post_id,
                    _model_AgentActivityLog.created_at >= run.created_at,
                )
                .limit(1)
            )
            if thread_viewed is None:
                _reject_complete_tick(
                    db,
                    run=run,
                    message=(
                        "reply requires angmoo_get_post_thread before complete_tick. "
                        f"Call angmoo_get_post_thread({root_post_id}) first, then retry reply."
                    ),
                    target_post_id=root_post_id,
                )
            reply = reply_agent_tool_post(
                db,
                session_key,
                action.post_id,
                schemas.TimelineReplyCreate(
                    body=action.body,
                    author_character_id=run.character_id,
                ),
            )
            executed_actions.append(f"reply:{reply.id}")
            representative_target_post_id = _complete_tick_representative_target(
                representative_target_post_id, action.post_id
            )
            continue
        if action.action_type == "like":
            if not action.post_id:
                _reject_complete_tick(
                    db,
                    run=run,
                    message="like requires post_id.",
                )
            already_liked = _character_already_liked_post(
                db, character_id=run.character_id, post_id=action.post_id
            )
            if already_liked:
                _reject_complete_tick(
                    db,
                    run=run,
                    message=(
                        "like is blocked for this post: already_liked. "
                        "Do not retry like for this same post_id in this tick."
                    ),
                    target_post_id=action.post_id,
                )
            like_agent_tool_post(
                db,
                session_key,
                action.post_id,
                schemas.PostLikeCreate(character_id=run.character_id),
            )
            executed_actions.append(f"like:{action.post_id}")
            representative_target_post_id = _complete_tick_representative_target(
                representative_target_post_id, action.post_id
            )
            continue
        if action.action_type == "repost":
            if not action.post_id:
                _reject_complete_tick(
                    db,
                    run=run,
                    message="repost requires post_id.",
                )
            if _character_already_reposted_post(
                db, character_id=run.character_id, post_id=action.post_id
            ):
                _reject_complete_tick(
                    db,
                    run=run,
                    message=(
                        "repost is blocked for this post: already_reposted. "
                        "Do not retry repost for this same post_id in this tick."
                    ),
                    target_post_id=action.post_id,
                )
            repost_agent_tool_post(
                db,
                session_key,
                action.post_id,
                schemas.PostLikeCreate(character_id=run.character_id),
            )
            executed_actions.append(f"repost:{action.post_id}")
            representative_target_post_id = _complete_tick_representative_target(
                representative_target_post_id, action.post_id
            )
            continue
        if action.action_type == "follow":
            if not action.target_type or not action.target_id:
                _reject_complete_tick(
                    db,
                    run=run,
                    message=(
                        "follow requires target_type and target_id. Resident ticks must "
                        "use selected_candidate_ids for follow; direct follow payloads are "
                        "only accepted outside resident candidate mode."
                    ),
                )
            already_following = False
            try:
                already_following = _character_already_following_profile(
                    db,
                    character_id=run.character_id,
                    target_type=action.target_type,
                    target_id=action.target_id,
                )
            except ProfileNotFoundError:
                _reject_complete_tick(
                    db,
                    run=run,
                    message=(
                        "follow target was not found. Use a backend candidate_id when "
                        "following during resident ticks; do not mix user and character ids."
                    ),
                )
            if already_following:
                _reject_complete_tick(
                    db,
                    run=run,
                    message=(
                        "follow is blocked for this profile: already_following. "
                        "Do not retry follow for this same target_type/target_id in this tick."
                    ),
                )
            follow_agent_tool_profile(
                db,
                session_key,
                schemas.FollowCreate(
                    target_type=action.target_type,
                    target_id=action.target_id,
                    follower_character_id=run.character_id,
                ),
            )
            executed_actions.append(f"follow:{action.target_type}:{action.target_id}")
            continue
        if action.action_type == "unfollow":
            if not action.target_type or not action.target_id:
                _reject_complete_tick(
                    db,
                    run=run,
                    message="unfollow requires target_type and target_id.",
                )
            unfollow_agent_tool_profile(
                db,
                session_key,
                schemas.FollowCreate(
                    target_type=action.target_type,
                    target_id=action.target_id,
                    follower_character_id=run.character_id,
                ),
            )
            executed_actions.append(f"unfollow:{action.target_type}:{action.target_id}")

    if (
        policy is not None
        and action_types
        and "observe" not in policy.allowed_actions
        and "post" in policy.allowed_actions
        and not _has_effective_complete_tick_action(executed_actions)
    ):
        _reject_complete_tick(
            db,
            run=run,
            message=(
                "A resident tick with observe disabled and policy action post allowed "
                "cannot finish with only skipped/no-op actions. Choose an available "
                "existing-post action or submit action_type=create_post."
            ),
        )

    handled_ids: list[int] = []
    for notification_id in dict.fromkeys(data.handled_notification_ids):
        notification = community_crud.get_notification_for_agent(
            db,
            user_id=run.user_id,
            character_id=run.character_id,
            notification_id=notification_id,
        )
        if notification is None:
            raise NotificationNotFoundError(notification_id)
        if not _notification_source_is_public_context_visible(db, notification):
            raise NotificationNotFoundError(notification_id)
        community_crud.mark_notification_read(db, notification)
        handled_ids.append(notification_id)

    state = save_agent_tool_character_state(
        db,
        session_key,
        run.character_id,
        schemas.CharacterStateWrite(
            mood=data.state.mood,
            summary=data.state.summary,
            memory_note=data.state.memory_note,
        ),
    )
    if data.relationship_review:
        agent_crud.log_activity(
            db,
            user_id=run.user_id,
            character_id=run.character_id,
            action_type="relationship_reviewed",
            target_post_id=None,
            reason="agent_tool_complete_tick",
            result=data.selection_reason[:1000],
        )
    tick_target_post_id = representative_target_post_id
    if not executed_actions or executed_actions == ["observe"]:
        tick_target_post_id = run.post_id
    agent_crud.log_activity(
        db,
        user_id=run.user_id,
        character_id=run.character_id,
        action_type="tick_completed",
        target_post_id=tick_target_post_id,
        reason="agent_tool_complete_tick",
        result=(
            f"actions={','.join(executed_actions) or 'none'}; "
            f"handled_notifications={','.join(str(item) for item in handled_ids) or 'none'}; "
            f"selection_reason={data.selection_reason[:700]}"
        ),
    )
    return schemas.AgentCompleteTickRead(
        status="ok",
        executed_actions=executed_actions,
        handled_notification_ids=handled_ids,
        selection_reason=data.selection_reason,
        state=schemas.AgentTickStateRead.model_validate(state),
    )


def _has_effective_complete_tick_action(executed_actions: list[str]) -> bool:
    return any(
        not action.startswith(NOOP_COMPLETE_TICK_ACTION_PREFIXES)
        for action in executed_actions
    )


def save_character_state(
    db: Session, character_id: str, data: schemas.CharacterStateWrite
) -> schemas.CharacterStateRead:
    try:
        return character_state.save_character_state(db, character_id, data)
    except CharacterStateNotFoundError as exc:
        raise CharacterNotFoundError(str(exc)) from exc


def save_character_state_for_user(
    db: Session,
    user: _model_User,
    character_id: str,
    data: schemas.CharacterStateWrite,
) -> schemas.CharacterStateRead:
    try:
        return character_state.save_character_state_for_user(db, user, character_id, data)
    except CharacterStateNotFoundError as exc:
        raise CharacterNotFoundError(str(exc)) from exc


def _normalize_state_memory_note(value: str) -> str:
    return " ".join(value.split()).casefold()


def _is_duplicate_memory_note(
    state: _model_CharacterState | None, data: schemas.CharacterStateWrite
) -> bool:
    if state is None:
        return False
    incoming_note = _normalize_state_memory_note(data.memory_note)
    saved_note = _normalize_state_memory_note(state.memory_note)
    return bool(incoming_note and incoming_note == saved_note)


def _state_observation_note(data: schemas.CharacterStateWrite) -> str:
    note = getattr(data, "observation_note", None)
    return note.strip() if isinstance(note, str) else ""


def save_agent_tool_character_state(
    db: Session, session_key: str, character_id: str, data: schemas.CharacterStateWrite
) -> schemas.CharacterStateRead:
    run = _get_agent_tool_run(
        db,
        session_key=session_key,
        action="state",
        requested_character_id=character_id,
    )
    if run.character_id != character_id:
        _raise_agent_tool_authorization_error(
            action="state",
            reason="character_mismatch",
            session_key=session_key,
            run=run,
            requested_character_id=character_id,
        )
    existing_state = db.get(_model_CharacterState, character_id)
    observation_note = _state_observation_note(data)
    if observation_note:
        agent_crud.log_activity(
            db,
            user_id=run.user_id,
            character_id=run.character_id,
            action_type="observation_note_saved",
            target_post_id=run.post_id,
            reason="agent_tool_state_observation_note",
            result=observation_note[:1000],
        )
    if _is_duplicate_memory_note(existing_state, data):
        agent_crud.log_activity(
            db,
            user_id=run.user_id,
            character_id=run.character_id,
            action_type="state_save_suppressed",
            target_post_id=run.post_id,
            reason="agent_tool_state_duplicate_memory_note",
            result="Suppressed duplicate memory_note state save.",
        )
        logger.info(
            "duplicate_state_save_suppressed character_id=%s run_id=%s session_key=%s",
            character_id,
            run.id,
            session_key,
        )
        return schemas.CharacterStateRead.model_validate(existing_state)
    state = save_character_state(db, character_id, data)
    agent_crud.log_activity(
        db,
        user_id=run.user_id,
        character_id=run.character_id,
        action_type="state_saved",
        target_post_id=run.post_id,
        reason="agent_tool_state",
        result=(
            f"Saved state mood={state.mood}; "
            f"summary={state.summary[:300]}; memory_note={state.memory_note[:700]}"
        ),
    )
    return state
