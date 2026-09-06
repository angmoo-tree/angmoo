from app.runtime.social.complete_tick import agent_tool_tick
_reject_complete_tick = agent_tool_tick._reject_complete_tick
_complete_tick_target_post = agent_tool_tick._complete_tick_target_post
_ensure_complete_tick_reply_target_is_not_self = agent_tool_tick._ensure_complete_tick_reply_target_is_not_self
_complete_tick_follow_status = agent_tool_tick._complete_tick_follow_status
_build_complete_tick_candidate_actions = agent_tool_tick._build_complete_tick_candidate_actions
_resolve_complete_tick_candidate_actions = agent_tool_tick._resolve_complete_tick_candidate_actions
_validate_complete_tick_decision_type = agent_tool_tick._validate_complete_tick_decision_type
_validate_complete_tick_actions_before_execution = agent_tool_tick._validate_complete_tick_actions_before_execution
complete_agent_tool_tick = agent_tool_tick.complete_agent_tool_tick
from app.domains.social.policies.complete_tick import COMPLETE_TICK_POLICY_ACTIONS, COMPLETE_TICK_CANDIDATE_ACTION_TYPES, COMPLETE_TICK_DECISION_TYPES, NOOP_COMPLETE_TICK_ACTION_PREFIXES, _complete_tick_representative_target, _has_effective_complete_tick_action, _put_candidate_action, _resident_action_candidate_id
from app.runtime.social.agent_tool_state import agent_tool_state
save_agent_tool_character_state = agent_tool_state.save_agent_tool_character_state
from app.runtime.social.agent_tool_state import save_character_state, save_character_state_for_user
from app.domains.characters.service.state_notes import _normalize_state_memory_note, _is_duplicate_memory_note, _state_observation_note
from app.runtime.social.feed_history_notes import note_agent_tool_feed_interests, note_agent_tool_feed_history_sanitize
from app.domains.routines.service.feed_history_notes import _diagnostic_hash, _json_byte_length, _feed_history_sanitize_payload_bytes, _elapsed_ms
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

from app.runtime.persistence.model_registration import register_models
register_models()
from app import schemas
from app.core import unit_of_work
from app.core.search_text import build_post_search_document
from app.cruds import agent_runs as agent_run_crud
from app.cruds import agents as agent_crud
from app.cruds import community as community_crud
from app.runtime.resident import activity_policy as agent_activity_policy
from app.domains.routines.service.action_briefs import (
    is_feed_scan_community_theme_brief,
    normalize_post_seed_intent,
)
from app.core.context_text import neutralize_context_text

logger = logging.getLogger(__name__)

from app.domains.social.constants import FEED_SCAN_BODY_PREVIEW_CHARS
