from __future__ import annotations
from app.domains.routines.service import activity_logs as agent_crud
import app.domains.characters.schemas as character_schemas
import app.domains.social.schemas.community as social_schemas
import app.domains.characters.service.profile as characters_profile_service
import app.domains.social.repository.inbox as social_inbox_repository
import app.domains.social.repository.posts as social_posts_repository
import app.domains.social.service.resident_affordances as social_resident_affordances_service
import app.runtime.social.agent_tool_reads as social_agent_tool_reads_runtime
import app.runtime.social.agent_tools as social_agent_tools_runtime
from app.runtime.social.agent_tool_state import agent_tool_state
from app.runtime.resident import langgraph_queries
from app.domains.routines.policies import execution_results
from app.domains.routines.contracts.context_reads import RelationshipContextWorkflows, WritingContextWorkflows, ConversationWorkflows
from app.domains.routines.service import relationship_context as relationship_context_service
from app.domains.routines.service import writing_context as writing_context_service
from app.domains.routines.service import conversation_context as conversation_context_service
from app.domains.routines.service.relationship_context import _RELATIONSHIP_MEMORY_EVENT_TYPES, _REPLY_TARGET_ALREADY_ANSWERED
from app.domains.routines.service.conversation_context import _INBOX_CONVERSATION_TURN_LIMIT, _INBOX_DIRECT_EXCHANGE_TURN_LIMIT
from app.domains.routines.service import resident_prompts as resident_prompts_service
from app.domains.routines.service import planner_results as planner_results_service
from app.domains.routines.service import writing_tasks as writing_tasks_service
from app.domains.routines.policies import writer_tasks as writer_tasks_service
from app.domains.routines.service import post_writer_results as post_writer_results_service
from app.domains.routines.service import state_outputs as state_outputs_service
from app.domains.routines.service.post_writer_results import _POST_WRITER_PLAN_CONSTRAINTS
from app.domains.routines.service.state_outputs import _STATE_WRITE_STRING_LIMITS
from app.domains.routines.contracts.action_planning import ActionPlanningWorkflows, ActionBudgetWorkflows
from app.domains.routines.service import activity_settings
from app.domains.routines.service import action_plans as action_plans_service
from app.domains.routines.service import writing_plans as writing_plans_service
from app.domains.routines.service import action_budgets as action_budgets_service
from app.domains.routines.service.action_plans import _INBOX_CONVERSATION_JUDGMENTS
from app.domains.routines.service.action_budgets import _REPLY_WRITER_MAX_TASKS_PER_RUN, _REPLY_WRITER_BUCKET_MAX_TASKS
from app.domains.routines.service import independent_topics as independent_topic_service
from app.domains.routines.repository import independent_topics as independent_topic_queries
from app.domains.routines.policies.resident_clock import _today_kst_window, _yesterday_kst_window
from app.domains.routines.service.independent_topics import _INDEPENDENT_TOPIC_PROMPT_COUNT, _INDEPENDENT_TOPIC_SELECTION_SALT
from functools import partial
from app.domains.routines.contracts.topic_arcs import TopicArcWorkflows
from app.domains.routines.service import topic_arcs as topic_arc_service
from app.domains.routines.policies.resident_clock import (
    _current_kst_date,
    _event_kst_date,
    _korean_daypart_label,
    _format_current_time_reference,
    _aware_datetime,
    _KOREAN_WEEKDAYS,
)
from app.domains.routines.policies.topic_dates import (
    _CARRYOVER_ACTIVE,
    _CARRYOVER_COMPLETED,
    _CARRYOVER_EXPIRED,
    _CARRYOVER_DUE_TODAY,
    _CARRYOVER_FUTURE,
    _CARRYOVER_NONE,
    _normalize_iso_date,
    _normalized_relative_text,
    _detect_relative_date_anchor,
    _attach_step_date_anchors,
    _parse_target_date,
    _carryover_phase,
    _carryover_phase_label,
)
from app.domains.routines.policies.handoff_coverage import (
    _TOPIC_ARC_EVENT_TYPE,
    _normalize_coverage_text,
    _coverage_word_tokens,
    _coverage_char_ngrams,
    _handoff_covered_by_today_post,
    _handoff_coverage,
    _handoff_continuity_kind,
)
from app.domains.routines.policies.action_matching import (
    _action_name_for_policy,
    _relationship_allowed_actions,
    _strip_action_from_affordance,
    _dedupe_relationship_candidates,
    _coerce_item_index,
    _observation_items,
    _normalize_planned_action_for_item,
    _normalize_planned_action,
    _relationship_candidate_counts,
    _matching_relationship_candidate,
)
from app.domains.routines.policies.writing_contract import (
    _OWNER_FEED_CUE_MODE,
    _RELATIONSHIP_POINT_MODE,
    _POST_TEXT_WRITING_MODES,
    _PERSONA_WRITER_MISSING_POST_TEXT,
    _coerce_writing_form,
    _coerce_action_step_count,
    _subjective_plan_fields,
    _mandatory_post_required,
    _writing_plan_requires_post_text,
    _persona_writer_validation_meta,
    _persona_writer_has_required_post_text,
    _with_persona_writer_validation,
)
from app.domains.routines.policies.writer_outputs import (
    _reply_task_results_by_id,
    _reply_tasks_by_id,
    _missing_reply_task_ids,
    _required_handle_text,
    _post_body_missing_required_mention,
    _post_body_has_forbidden_structure_label,
    _source_copy_windows,
    _post_body_copies_source,
    _post_task_needs_repair,
    _write_task_summary,
    _mandatory_post_missing_reason,
    _apply_reply_writer_output,
)
from app.domains.routines.schemas.resident_planning import (
    _PlannedAction,
    _TopicArcStep,
    _TopicArcDraft,
    _TopicArcPayload,
    _WritingPlan,
    _ActionPlan,
    _FeedPlannerAction,
    _InboxPlannerAction,
    _InboxConversationDecision,
    _FeedPlannerWriting,
    _FeedActionPlan,
    _InboxActionPlan,
    _RelationshipActionPlan,
    _IndependentWritingChoice,
    _IndependentWritingPlan,
    _FeedSeedSelection,
    _IndependentTopicComposition,
    _ReplyText,
    _PersonaWriting,
    _ReplyTaskText,
    _ReplyWriterOutput,
    _PostWriterOutput,
    _PostWriterPlannerOutput,
    _LoreQueryRewriteOutput,
    _StateWrite,
    _TOPIC_ARC_SCHEMA_VERSION,
)
from app.domains.routines.policies.topic_arc_roles import _validate_topic_arc_step_roles
from app.domains.routines.repository import public_action_executions as public_action_queries
from app.domains.routines.service import public_action_executions as public_action_executions

import asyncio
import hashlib
import json
import logging
import re
import unicodedata
from collections.abc import Awaitable, Callable, Iterable
from datetime import UTC, date, datetime, timedelta
from typing import Any, Literal

from langgraph.errors import GraphRecursionError
from langgraph.graph import END, START, StateGraph
from pydantic import BaseModel, ValidationError
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session


from app.domains.memory.models.daypart import AgentDaypartMemoryEvent as _model_AgentDaypartMemoryEvent
from app.domains.routines.models.resident import AgentPublicActionExecution as _model_AgentPublicActionExecution
from app.domains.relationships.models.points import AgentRelationshipPoint as _model_AgentRelationshipPoint
from app.domains.identity.models import LlmCredential as _model_LlmCredential
from app.runtime.persistence.model_registration import register_models
register_models()
from app.runtime.social.observations import observe_source
from app.core import unit_of_work
from app.config import settings
from app.core.redaction import redact_secret_text
from app.credentials import (
    CredentialPurpose,
    CredentialResolutionError,
    CredentialResolver,
)
from app.domains.relationships import constants as relationship_point_constants
from app.domains.relationships.repository import points as relationship_point_queries
from app.domains.relationships.service import points as relationship_points
from app.domains.relationships.utils import points as relationship_point_values


from app.domains.world_characters.contracts.runtime_modes import (
    AUTONOMOUS_ACTIVITY_RUNTIME_MODE,
    AUTONOMOUS_FEED_RUNTIME_MODE,
    LEGACY_FEED_RUNTIME_MODE,
)
from app.domains.social.contracts.subjective_context import (
    ActionEmotionLabel,
    ActionMotivationKind,
    ActionSubjectiveContextV1,
)
from app.runtime.social.subjective_composition import record_declared_subjective_context
from app.runtime.routine_posts.sqlalchemy_runtime import (
    routine_world_character_for_character,
    run_routine_post_runtime,
)
from app.runtime.routines import activity_policy as agent_activity_policy
from app.domains.character_lore.service import documents as character_lore_service

from app.runtime.social import langgraph_actions as langgraph_social_apply
from app.runtime.social import image_generation as post_image_generation
from app.core import prompt_safety as prompt_safety
from app.integrations.direct_llm import DirectLlmCallContext
from app.integrations.direct_llm import DirectLlmDeferred
from app.integrations.direct_llm import DirectLlmError
from app.integrations.direct_llm import DirectLlmJsonError
from app.integrations.direct_llm import RunLlmTracker
from app.integrations.direct_llm import generate_json
from app.core.context_text import neutralize_context_text
from app.runtime.resident.context import LangGraphResidentContext
from app.domains.routines.contracts.resident import ResidentGraphState as _ResidentGraphState
from app.runtime.social.feed_cycle import run_world_keyword_feed
from app.domains.character_lore.service import presentation as lore_presentation
from app.domains.social.service import image_attachment
from app.runtime.character_lore import build_lore_workflows


logger = logging.getLogger("app.services.langgraph_resident")


_PUBLIC_ACTIONS = {"post", "reply", "like", "repost", "follow", "unfollow"}
_GRAPH_SEMAPHORE = asyncio.Semaphore(settings.langgraph_max_concurrent_graphs)
_MANDATORY_POST_ALLOWED_SKIP_REASONS = {
    "action_budget_trimmed",
    "feed_cue_pending_post_blocked",
}
_TOPIC_ARC_LOOKBACK = timedelta(hours=48)


def _langgraph_recursion_limit() -> int:
    return max(settings.langgraph_max_steps_per_run * 3, 48)


def _clip(value: Any, max_chars: int) -> str:
    text = neutralize_context_text(str(value or "")).strip()
    if len(text) <= max_chars:
        return text
    return text[: max(0, max_chars - 3)].rstrip() + "..."


_topic_arc_last_post_created_at = langgraph_queries._topic_arc_last_post_created_at
_target_character_following = langgraph_queries._target_character_following
_today_own_root_posts_for_coverage = partial(langgraph_queries._today_own_root_posts_for_coverage, clip=_clip)
_today_root_writing_memory_for_prompt = partial(langgraph_queries._today_root_writing_memory_for_prompt, clip=_clip)
_recent_own_root_posts = partial(langgraph_queries._recent_own_root_posts, clip=_clip)
_conversation_context_post = langgraph_queries._conversation_context_post
_character_handle_by_id = partial(langgraph_queries._character_handle_by_id, clip=_clip)
_character_for_handle = langgraph_queries._character_for_handle
_relationship_source_post_available = langgraph_queries._relationship_source_post_available
_character_already_replied_to_target = langgraph_queries._character_already_replied_to_target
_brief_hash = execution_results._brief_hash
_action_signature = execution_results._action_signature
_normalize_reply_body_for_duplicate = execution_results._normalize_reply_body_for_duplicate
_skipped_public_action = execution_results._skipped_public_action
_record_topic_arc_progress = partial(execution_results._record_topic_arc_progress, coerce_topic_arc=lambda value: _coerce_topic_arc_payload(value))
_reply_body = partial(execution_results._reply_body, reply_task_id=lambda **kwargs: _reply_task_id(**kwargs))
_successful_action_results = execution_results._successful_action_results
_writing_success_post_id = execution_results._writing_success_post_id
_inbox_lane_planner_invoked = execution_results._inbox_lane_planner_invoked
_inbox_lane_target_post_id = execution_results._inbox_lane_target_post_id


_relationship_context_workflows = RelationshipContextWorkflows(
    clip=_clip,
    history=lambda ctx: _daypart_history(ctx),
    history_prompt=lambda ctx: _daypart_history_for_prompt(ctx),
    following=lambda ctx, target_id: _target_character_following(ctx, target_id),
    already_replied=lambda db, **kwargs: _character_already_replied_to_target(db, **kwargs),
)
_writing_context_workflows = WritingContextWorkflows(
    clip=_clip,
    coerce_topic_arc=lambda value: _coerce_topic_arc_payload(value),
    topic_arc_for_prompt=lambda value, **kwargs: _topic_arc_for_prompt(value, **kwargs),
    previous_handoff=lambda ctx: _yesterday_handoff_context(ctx),
    history_prompt=lambda ctx: _daypart_history_for_prompt(ctx),
    recent_own_posts=lambda ctx: _recent_own_root_posts(ctx),
    latest_summary=lambda ctx: _latest_daypart_summary(ctx),
    seen_feed_posts=lambda ctx: _seen_daypart_feed_post_ids(ctx),
    seen_notifications=lambda ctx: _seen_daypart_notification_ids(ctx),
)
_conversation_workflows = ConversationWorkflows(
    clip=_clip,
    get_post=lambda db, post_id: _conversation_context_post(db, post_id),
    thread_replies=lambda db, post_id, **kwargs: social_posts_repository.list_post_thread_replies(db, post_id, **kwargs),
)
_tendency_action_note = partial(relationship_context_service._tendency_action_note, workflows=_relationship_context_workflows)
_relationship_daypart_memory = partial(relationship_context_service._relationship_daypart_memory, workflows=_relationship_context_workflows)
_relationship_candidate_from_item = partial(relationship_context_service._relationship_candidate_from_item, workflows=_relationship_context_workflows)
_relationship_candidates_from_daypart_memory = partial(relationship_context_service._relationship_candidates_from_daypart_memory, workflows=_relationship_context_workflows)
_has_unfollow_watch = partial(relationship_context_service._has_unfollow_watch, workflows=_relationship_context_workflows)
_inbox_lane_relationship_memory = partial(relationship_context_service._inbox_lane_relationship_memory, workflows=_relationship_context_workflows)
_suppress_already_answered_reply_affordance = partial(relationship_context_service._suppress_already_answered_reply_affordance, workflows=_relationship_context_workflows)
_coverage_text_from_payload = partial(writing_context_service._coverage_text_from_payload, workflows=_writing_context_workflows)
_compact_yesterday_handoff_event = partial(writing_context_service._compact_yesterday_handoff_event, workflows=_writing_context_workflows)
_feed_mood_for_prompt = partial(writing_context_service._feed_mood_for_prompt, workflows=_writing_context_workflows)
_independent_post_context_for_prompt = partial(writing_context_service._independent_post_context_for_prompt, workflows=_writing_context_workflows)
_current_daypart_context = partial(writing_context_service._current_daypart_context, workflows=_writing_context_workflows)
_mandatory_post_context = partial(writing_context_service._mandatory_post_context, workflows=_writing_context_workflows)
_conversation_turn_for_prompt = partial(conversation_context_service._conversation_turn_for_prompt, workflows=_conversation_workflows)
_thread_root_post_for_conversation_context = partial(conversation_context_service._thread_root_post_for_conversation_context, workflows=_conversation_workflows)
_inbox_conversation_context = partial(conversation_context_service._inbox_conversation_context, workflows=_conversation_workflows)


_task_id_part = partial(writer_tasks_service._task_id_part, clip=_clip)
_reply_task_id = partial(writer_tasks_service._reply_task_id, clip=_clip)
_post_task_id = partial(writer_tasks_service._post_task_id, clip=_clip, coerce_topic_arc=lambda value: _coerce_topic_arc_payload(value))
_clean_lore_chunk_ids = partial(post_writer_results_service._clean_lore_chunk_ids, clip=_clip)
_dedupe_clipped_items = partial(post_writer_results_service._dedupe_clipped_items, clip=_clip)
_post_writer_plan_defaults = partial(post_writer_results_service._post_writer_plan_defaults, clip=_clip)
_mandatory_post_writer_constraints = partial(post_writer_results_service._mandatory_post_writer_constraints, clip=_clip)
_post_writer_plan_result = post_writer_results_service._post_writer_plan_result
_fallback_post_writer_plan = partial(post_writer_results_service._fallback_post_writer_plan, clip=_clip)
_normalize_post_writer_plan = partial(post_writer_results_service._normalize_post_writer_plan, clip=_clip)
_post_identity_for_prompt = post_writer_results_service._post_identity_for_prompt
_apply_post_writer_output = partial(post_writer_results_service._apply_post_writer_output, clip=_clip)
_successful_publish_actions = state_outputs_service._successful_publish_actions
_state_publish_context = state_outputs_service._state_publish_context
_state_action_plan_context = partial(state_outputs_service._state_action_plan_context, clip=_clip, topic_arc_for_prompt=lambda value: _topic_arc_for_prompt(value))
_state_observation_context = partial(state_outputs_service._state_observation_context, clip=_clip)
_state_recorder_prompt_inputs = partial(state_outputs_service._state_recorder_prompt_inputs, clip=_clip, topic_arc_for_prompt=lambda value: _topic_arc_for_prompt(value))
_validation_summary_from_exception = partial(state_outputs_service._validation_summary_from_exception, clip=_clip)
_fallback_state_payload = partial(state_outputs_service._fallback_state_payload, clip=_clip)
_state_recorder_length_validation_fields = state_outputs_service._state_recorder_length_validation_fields
_state_recorder_should_retry_json_error = partial(state_outputs_service._state_recorder_should_retry_json_error, clip=_clip)
_state_recorder_sanitized_payload_from_failure = partial(state_outputs_service._state_recorder_sanitized_payload_from_failure, clip=_clip, length_summary=lambda exc: _state_recorder_length_validation_summary(exc))


_action_planning_workflows = ActionPlanningWorkflows(
    clip=_clip,
    target_following=lambda ctx, target_id: _target_character_following(ctx, target_id),
    has_unfollow_watch=lambda ctx, **kwargs: _has_unfollow_watch(ctx, **kwargs),
    yesterday_handoff=lambda ctx: _yesterday_handoff_context(ctx),
)
_action_budget_workflows = ActionBudgetWorkflows(
    ensure_setting=lambda db, character_id: activity_settings.ensure_setting(db, character_id),
    count_today=lambda db, **kwargs: agent_activity_policy.count_action_today(db, **kwargs),
    get_post=lambda db, post_id: social_posts_repository.get_post(db, post_id),
    reply_task_id=lambda **kwargs: _reply_task_id(**kwargs),
)
_filter_action_plan = partial(action_plans_service._filter_action_plan, workflows=_action_planning_workflows)
_normalize_feed_action_plan = partial(action_plans_service._normalize_feed_action_plan, workflows=_action_planning_workflows)
_normalized_inbox_conversation_decisions = partial(action_plans_service._normalized_inbox_conversation_decisions, workflows=_action_planning_workflows)
_inbox_actions_with_conversation_decisions = action_plans_service._inbox_actions_with_conversation_decisions
_normalize_inbox_action_plan = partial(action_plans_service._normalize_inbox_action_plan, workflows=_action_planning_workflows)
_normalize_relationship_action_plan = partial(action_plans_service._normalize_relationship_action_plan, workflows=_action_planning_workflows)
_normalize_independent_writing_plan = partial(action_plans_service._normalize_independent_writing_plan, workflows=_action_planning_workflows)
_empty_action_plan = action_plans_service._empty_action_plan
_empty_relationship_plan = action_plans_service._empty_relationship_plan
_independent_writing_skip_reason = action_plans_service._independent_writing_skip_reason
_owner_feed_cue_writing = partial(action_plans_service._owner_feed_cue_writing, workflows=_action_planning_workflows)
_compose_action_bundle = partial(action_plans_service._compose_action_bundle, workflows=_action_planning_workflows)
_independent_topic_prompt_text = partial(action_plans_service._independent_topic_prompt_text, workflows=_action_planning_workflows)
_covered_handoff_matches_independent_writing = partial(action_plans_service._covered_handoff_matches_independent_writing, workflows=_action_planning_workflows)
_feed_seed_candidates = writing_plans_service._feed_seed_candidates
_normalize_feed_seed_selection = partial(writing_plans_service._normalize_feed_seed_selection, clip=_clip)
_normalize_independent_topic_composition = partial(writing_plans_service._normalize_independent_topic_composition, clip=_clip)
_writing_from_topic_composition = partial(writing_plans_service._writing_from_topic_composition, clip=_clip)
_mandatory_root_writing_from_composition = partial(writing_plans_service._mandatory_root_writing_from_composition, clip=_clip)
_restore_mandatory_root_writing = partial(writing_plans_service._restore_mandatory_root_writing, clip=_clip)
_daily_action_budgets = partial(action_budgets_service._daily_action_budgets, workflows=_action_budget_workflows)
_post_author_character_id = partial(action_budgets_service._post_author_character_id, workflows=_action_budget_workflows)
_action_conflicts_with_unfollow_target = partial(action_budgets_service._action_conflicts_with_unfollow_target, workflows=_action_budget_workflows)
_apply_unfollow_conflict_suppression = partial(action_budgets_service._apply_unfollow_conflict_suppression, workflows=_action_budget_workflows)
_trim_action_plan_to_budget = partial(action_budgets_service._trim_action_plan_to_budget, workflows=_action_budget_workflows)


_planner_tendency_profile = independent_topic_service._planner_tendency_profile
_feed_seed_interest_criteria = partial(independent_topic_service._feed_seed_interest_criteria, clip=_clip)
_independent_post_topics = partial(independent_topic_service._independent_post_topics, clip=_clip)
_select_independent_post_topics_for_tick = independent_topic_service._select_independent_post_topics_for_tick
_independent_post_initiative = independent_topic_service._independent_post_initiative
_deterministic_independent_post_roll = independent_topic_service._deterministic_independent_post_roll
_build_independent_post_roll = partial(independent_topic_service._build_independent_post_roll, clip=_clip)
_base_independent_topic_candidates = partial(independent_topic_service._base_independent_topic_candidates, clip=_clip)
_recent_independent_topic_keys = independent_topic_queries._recent_independent_topic_keys
_today_independent_topic_keys = independent_topic_queries._today_independent_topic_keys


_topic_arc_workflows = TopicArcWorkflows(
    clip=_clip,
    last_post_created_at=lambda ctx, last_post_id: _topic_arc_last_post_created_at(ctx, last_post_id),
    latest_event=lambda ctx, arc_id: _latest_topic_arc_event(ctx, arc_id),
)
_topic_arc_step_dict = partial(topic_arc_service._topic_arc_step_dict, workflows=_topic_arc_workflows)
_carryover_time_context = partial(topic_arc_service._carryover_time_context, workflows=_topic_arc_workflows)
_coerce_topic_arc_draft = partial(topic_arc_service._coerce_topic_arc_draft, workflows=_topic_arc_workflows)
_coerce_topic_arc_payload = partial(topic_arc_service._coerce_topic_arc_payload, workflows=_topic_arc_workflows)
_topic_arc_active_step = partial(topic_arc_service._topic_arc_active_step, workflows=_topic_arc_workflows)
_topic_arc_completed_step_summaries = partial(topic_arc_service._topic_arc_completed_step_summaries, workflows=_topic_arc_workflows)
_topic_arc_for_prompt = partial(topic_arc_service._topic_arc_for_prompt, workflows=_topic_arc_workflows)
_make_topic_arc_id = topic_arc_service._make_topic_arc_id
_build_topic_arc_payload = partial(topic_arc_service._build_topic_arc_payload, workflows=_topic_arc_workflows)
_topic_arc_recovery_decision = partial(topic_arc_service._topic_arc_recovery_decision, workflows=_topic_arc_workflows)
_active_topic_arc = topic_arc_service._active_topic_arc
_writing_from_topic_arc = partial(topic_arc_service._writing_from_topic_arc, workflows=_topic_arc_workflows)
_attach_topic_arc_to_new_writing = partial(topic_arc_service._attach_topic_arc_to_new_writing, workflows=_topic_arc_workflows)
_topic_arc_continuity_context = partial(topic_arc_service._topic_arc_continuity_context, workflows=_topic_arc_workflows)


_persona_context = partial(resident_prompts_service._persona_context, clip=_clip)
_format_json_for_prompt = partial(resident_prompts_service._format_json_for_prompt, clip=_clip)
_build_system_prompt = partial(resident_prompts_service._build_system_prompt, clip=_clip)
_independent_topic_for_lore = partial(resident_prompts_service._independent_topic_for_lore, clip=_clip)
_deterministic_lore_query = partial(resident_prompts_service._deterministic_lore_query, clip=_clip)
_build_lore_query_rewriter_prompt = partial(resident_prompts_service._build_lore_query_rewriter_prompt, clip=_clip)
_build_reply_writer_user_prompt = partial(resident_prompts_service._build_reply_writer_user_prompt, clip=_clip)
_build_post_writer_planner_user_prompt = partial(resident_prompts_service._build_post_writer_planner_user_prompt, clip=_clip)
_build_post_writer_user_prompt = partial(resident_prompts_service._build_post_writer_user_prompt, clip=_clip)
_build_state_recorder_user_prompt = partial(resident_prompts_service._build_state_recorder_user_prompt, clip=_clip, topic_workflows=_topic_arc_workflows)
_planner_feed_observation_for_prompt = planner_results_service._planner_feed_observation_for_prompt
_planner_inbox_observation_for_prompt = planner_results_service._planner_inbox_observation_for_prompt
_empty_lore_query_result = planner_results_service._empty_lore_query_result
_langgraph_tick_payload = partial(planner_results_service._langgraph_tick_payload, topic_workflows=_topic_arc_workflows)
_independent_post_decision_meta = planner_results_service._independent_post_decision_meta
_planner_results_summary = partial(planner_results_service._planner_results_summary, clip=_clip, topic_workflows=_topic_arc_workflows)
_compile_write_tasks = partial(writing_tasks_service._compile_write_tasks, clip=_clip, topic_workflows=_topic_arc_workflows)


def _decrypt_api_key(credential: _model_LlmCredential) -> str:
    try:
        return CredentialResolver.resolve_llm_credential(
            credential,
            purpose=CredentialPurpose.RESIDENT_LLM,
        ).reveal()
    except CredentialResolutionError as exc:
        raise DirectLlmError("credential key cannot be decrypted") from exc


def _latest_topic_arc_event(
    ctx: LangGraphResidentContext, arc_id: str | None
) -> _model_AgentDaypartMemoryEvent | None:
    if not arc_id:
        return None
    db_scalars = getattr(getattr(ctx, "db", None), "scalars", None)
    if not callable(db_scalars):
        return None
    cutoff = ctx.run_started_at.astimezone(UTC) - _TOPIC_ARC_LOOKBACK
    try:
        events = list(
            db_scalars(
                select(_model_AgentDaypartMemoryEvent)
                .where(_model_AgentDaypartMemoryEvent.character_id == ctx.character.id)
                .where(_model_AgentDaypartMemoryEvent.event_type == _TOPIC_ARC_EVENT_TYPE)
                .where(_model_AgentDaypartMemoryEvent.provided_at >= cutoff)
                .order_by(
                    _model_AgentDaypartMemoryEvent.provided_at.desc(),
                    _model_AgentDaypartMemoryEvent.id.desc(),
                )
                .limit(20)
            )
        )
    except Exception:
        logger.debug(
            "Failed to load topic arc events for continuity context",
            exc_info=True,
            extra={"arc_id": arc_id, "character_id": ctx.character.id},
        )
        return None
    for event in events:
        payload = _coerce_topic_arc_payload(getattr(event, "payload", None) or {})
        if payload and payload.get("arc_id") == arc_id:
            return event
    return None


def _daypart_history(ctx: LangGraphResidentContext) -> list[dict[str, Any]]:
    if not ctx.memory_session_key:
        return []
    events = list(
        ctx.db.scalars(
            select(_model_AgentDaypartMemoryEvent)
            .where(
                _model_AgentDaypartMemoryEvent.character_id == ctx.character.id,
                _model_AgentDaypartMemoryEvent.memory_session_key
                == ctx.memory_session_key,
            )
            .order_by(
                _model_AgentDaypartMemoryEvent.provided_at.asc(),
                _model_AgentDaypartMemoryEvent.id.asc(),
            )
            .limit(64)
        )
    )
    return [
        {
            "event_type": event.event_type,
            "source_post_id": event.source_post_id,
            "notification_id": event.notification_id,
            "topic_signature": event.topic_signature,
            "summary": _clip(event.summary, 600),
            "payload": event.payload or {},
            "provided_at": event.provided_at.isoformat(),
        }
        for event in events
    ]


def _daypart_history_for_prompt(ctx: LangGraphResidentContext) -> list[dict[str, Any]]:
    return [
        {
            "event_type": event.get("event_type"),
            "source_post_id": event.get("source_post_id"),
            "notification_id": event.get("notification_id"),
            "topic_signature": event.get("topic_signature"),
            "summary": _clip(event.get("summary"), 600),
            "provided_at": event.get("provided_at"),
        }
        for event in _daypart_history(ctx)
    ]


def _yesterday_handoff_context(ctx: LangGraphResidentContext) -> list[dict[str, Any]]:
    db_scalars = getattr(getattr(ctx, "db", None), "scalars", None)
    if not callable(db_scalars):
        return []
    start_utc, end_utc = _yesterday_kst_window(ctx)
    coverage_posts = _today_own_root_posts_for_coverage(ctx)
    try:
        events = list(
            db_scalars(
                select(_model_AgentDaypartMemoryEvent)
                .where(_model_AgentDaypartMemoryEvent.character_id == ctx.character.id)
                .where(
                    _model_AgentDaypartMemoryEvent.event_type.in_(
                        [
                            _TOPIC_ARC_EVENT_TYPE,
                            "langgraph_tick",
                            "observation_feed",
                            "observation_inbox",
                            "relationship_review",
                        ]
                    )
                )
                .where(_model_AgentDaypartMemoryEvent.provided_at >= start_utc)
                .where(_model_AgentDaypartMemoryEvent.provided_at < end_utc)
                .order_by(
                    _model_AgentDaypartMemoryEvent.provided_at.desc(),
                    _model_AgentDaypartMemoryEvent.id.desc(),
                )
                .limit(12)
            )
        )
    except Exception:
        logger.debug(
            "Failed to load yesterday handoff context",
            exc_info=True,
            extra={"character_id": ctx.character.id},
        )
        return []
    items: list[dict[str, Any]] = []
    for event in events:
        item = _compact_yesterday_handoff_event(
            event, coverage_posts=coverage_posts
        )
        if item is not None:
            items.append(item)
        if len(items) >= 8:
            break
    return items


def _compact_daypart_summary_event(
    event: _model_AgentDaypartMemoryEvent,
) -> dict[str, Any]:
    return {
        "event_type": event.event_type,
        "memory_session_key": event.memory_session_key,
        "daypart_start_date": (
            event.daypart_start_date.isoformat()
            if event.daypart_start_date
            else None
        ),
        "activity_daypart": event.activity_daypart,
        "summary": _clip(event.summary, 600),
        "payload": event.payload or {},
        "provided_at": event.provided_at.isoformat() if event.provided_at else None,
    }


def _latest_daypart_summary(
    ctx: LangGraphResidentContext,
) -> dict[str, Any] | None:
    db_scalars = getattr(getattr(ctx, "db", None), "scalars", None)
    if not callable(db_scalars):
        return None
    try:
        query = (
            select(_model_AgentDaypartMemoryEvent)
            .where(_model_AgentDaypartMemoryEvent.character_id == ctx.character.id)
            .where(_model_AgentDaypartMemoryEvent.event_type == "daypart_summary")
            .where(_model_AgentDaypartMemoryEvent.provided_at <= ctx.run_started_at)
        )
        if ctx.memory_session_key:
            query = query.where(
                _model_AgentDaypartMemoryEvent.memory_session_key
                != ctx.memory_session_key
            )
        event = next(
            iter(
                db_scalars(
                    query.order_by(
                        _model_AgentDaypartMemoryEvent.provided_at.desc(),
                        _model_AgentDaypartMemoryEvent.id.desc(),
                    ).limit(1)
                )
            ),
            None,
        )
    except Exception:
        logger.debug(
            "Failed to load latest daypart summary",
            exc_info=True,
            extra={"character_id": ctx.character.id},
        )
        return None
    return _compact_daypart_summary_event(event) if event is not None else None


def _daypart_start_utc(
    daypart_start_date: date | None,
    activity_daypart: str | None,
) -> datetime | None:
    if daypart_start_date is None or not activity_daypart:
        return None
    hour_by_daypart = {"morning": 6, "afternoon": 14, "night": 22}
    hour = hour_by_daypart.get(activity_daypart)
    if hour is None:
        return None
    return datetime(
        daypart_start_date.year,
        daypart_start_date.month,
        daypart_start_date.day,
        hour,
        tzinfo=agent_activity_policy.APP_TIMEZONE,
    ).astimezone(UTC)


def _daypart_end_summary_payload(
    events: list[_model_AgentDaypartMemoryEvent],
) -> dict[str, Any]:
    seen_feed_post_ids: list[str] = []
    seen_notification_ids: list[int] = []
    root_posts: list[dict[str, Any]] = []
    public_action_counts: dict[str, int] = {}
    relationship_point_counts = {"created": 0, "consumed": 0, "skipped": 0}
    topic_keys: list[str] = []

    def _remember_topic_key(value: Any) -> None:
        topic_key = _clip(value, 80) or None
        if topic_key and topic_key not in topic_keys:
            topic_keys.append(topic_key)

    for event in events:
        if event.event_type == "observation_feed" and event.source_post_id:
            if event.source_post_id not in seen_feed_post_ids:
                seen_feed_post_ids.append(event.source_post_id)
        if event.event_type == "observation_inbox" and event.notification_id is not None:
            if event.notification_id not in seen_notification_ids:
                seen_notification_ids.append(event.notification_id)
        if event.topic_signature:
            _remember_topic_key(event.topic_signature)

        payload = event.payload if isinstance(event.payload, dict) else {}
        if event.event_type == "relationship_point_update":
            for key in ("created", "consumed", "skipped"):
                value = payload.get(key)
                if isinstance(value, list):
                    relationship_point_counts[key] += len(value)
            continue

        publish_result = payload.get("publish_result")
        if not isinstance(publish_result, dict):
            continue
        actions = publish_result.get("actions")
        if not isinstance(actions, list):
            continue
        for action in actions:
            if not isinstance(action, dict):
                continue
            if action.get("status") not in {"succeeded", "reused"}:
                continue
            action_type = str(action.get("action_type") or "").strip() or "unknown"
            public_action_counts[action_type] = public_action_counts.get(action_type, 0) + 1
            result = action.get("result") if isinstance(action.get("result"), dict) else {}
            if action_type == "post":
                post_id = _clip(result.get("post_id"), 64) or None
                topic_key = _clip(result.get("topic_key"), 80) or None
                if topic_key:
                    _remember_topic_key(topic_key)
                root_posts.append(
                    {
                        "post_id": post_id,
                        "topic_key": topic_key,
                        "title": _clip(result.get("title"), 160) or None,
                    }
                )

    return {
        "source_event_count": len(events),
        "seen_feed_post_ids": seen_feed_post_ids[:50],
        "seen_notification_ids": seen_notification_ids[:50],
        "public_action_counts": public_action_counts,
        "root_posts": root_posts[:20],
        "used_topic_keys": topic_keys[:50],
        "relationship_point_counts": relationship_point_counts,
        "repetition_prevention": {
            "seen_feed_post_count": len(seen_feed_post_ids),
            "seen_notification_count": len(seen_notification_ids),
            "used_topic_key_count": len(topic_keys),
        },
    }


def _daypart_end_summary_text(payload: dict[str, Any]) -> str:
    actions = payload.get("public_action_counts")
    action_text = (
        ", ".join(f"{key}={value}" for key, value in sorted(actions.items()))
        if isinstance(actions, dict) and actions
        else "none"
    )
    relationship_counts = payload.get("relationship_point_counts")
    created = consumed = 0
    if isinstance(relationship_counts, dict):
        created = int(relationship_counts.get("created") or 0)
        consumed = int(relationship_counts.get("consumed") or 0)
    return _clip(
        "daypart closed: "
        f"events={payload.get('source_event_count', 0)}; "
        f"actions={action_text}; "
        f"root_posts={len(payload.get('root_posts') or [])}; "
        f"relationship_points_created={created}; "
        f"relationship_points_consumed={consumed}",
        2000,
    )


def _finalize_closed_dayparts(ctx: LangGraphResidentContext) -> dict[str, Any]:
    current_start = _daypart_start_utc(ctx.daypart_start_date, ctx.activity_daypart)
    result: dict[str, Any] = {
        "status": "skipped" if current_start is None else "succeeded",
        "expired_relationship_points": 0,
        "summaries_created": 0,
        "summaries_skipped": 0,
    }
    try:
        result["expired_relationship_points"] = relationship_points.expire_relationship_points(
            ctx.db, now=ctx.run_started_at
        )
    except Exception as exc:
        ctx.db.rollback()
        result["relationship_point_expire_error"] = type(exc).__name__
    if current_start is None:
        return result
    db_scalars = getattr(getattr(ctx, "db", None), "scalars", None)
    if not callable(db_scalars):
        result["status"] = "skipped"
        result["reason"] = "db_scalars_unavailable"
        return result
    try:
        events = list(
            db_scalars(
                select(_model_AgentDaypartMemoryEvent)
                .where(_model_AgentDaypartMemoryEvent.character_id == ctx.character.id)
                .where(_model_AgentDaypartMemoryEvent.provided_at < current_start)
                .where(
                    _model_AgentDaypartMemoryEvent.provided_at
                    >= current_start - timedelta(days=3)
                )
                .order_by(
                    _model_AgentDaypartMemoryEvent.daypart_start_date.asc(),
                    _model_AgentDaypartMemoryEvent.activity_daypart.asc(),
                    _model_AgentDaypartMemoryEvent.provided_at.asc(),
                    _model_AgentDaypartMemoryEvent.id.asc(),
                )
            )
        )
    except Exception as exc:
        ctx.db.rollback()
        return {
            **result,
            "status": "failed",
            "failure_class": type(exc).__name__,
        }
    grouped: dict[tuple[str, date, str], list[_model_AgentDaypartMemoryEvent]] = {}
    for event in events:
        key = (
            event.memory_session_key,
            event.daypart_start_date,
            event.activity_daypart,
        )
        grouped.setdefault(key, []).append(event)
    for (memory_session_key, daypart_start_date, activity_daypart), group_events in grouped.items():
        if any(event.event_type == "daypart_summary" for event in group_events):
            result["summaries_skipped"] += 1
            continue
        source_events = [
            event for event in group_events if event.event_type != "daypart_summary"
        ]
        if not source_events:
            result["summaries_skipped"] += 1
            continue
        payload = _daypart_end_summary_payload(source_events)
        summary = _daypart_end_summary_text(payload)
        payload["finalized_by_run_id"] = ctx.run_id
        payload["finalized_at"] = ctx.run_started_at.isoformat()
        try:
            ctx.db.add(
                _model_AgentDaypartMemoryEvent(
                    character_id=ctx.character.id,
                    memory_session_key=memory_session_key,
                    daypart_start_date=daypart_start_date,
                    activity_daypart=activity_daypart,
                    event_type="daypart_summary",
                    run_id=ctx.run_id,
                    summary=summary,
                    payload=payload,
                    provided_at=current_start - timedelta(microseconds=1),
                )
            )
            ctx.db.commit()
            result["summaries_created"] += 1
        except Exception as exc:
            ctx.db.rollback()
            result.setdefault("summary_errors", []).append(
                {
                    "memory_session_key": memory_session_key,
                    "failure_class": type(exc).__name__,
                }
            )
    return result


def _relationship_point_to_state(
    ctx: LangGraphResidentContext,
    point: _model_AgentRelationshipPoint,
) -> dict[str, Any] | None:
    source_post = _relationship_source_post_available(ctx, point.source_post_id)
    if source_post is None:
        try:
            relationship_points.mark_relationship_point_failed(
                ctx.db, point, failure_class="source_post_unavailable"
            )
        except Exception:
            ctx.db.rollback()
        return None
    source_character = characters_profile_service.get_character(ctx.db, point.source_character_id)
    if (
        source_character is None
        or source_character.deleted_at is not None
        or source_character.moderation_status == "suspended"
    ):
        try:
            relationship_points.mark_relationship_point_failed(
                ctx.db, point, failure_class="source_character_unavailable"
            )
        except Exception:
            ctx.db.rollback()
        return None
    return {
        "id": point.id,
        "kind": point.kind,
        "status": point.status,
        "source_character_id": point.source_character_id,
        "source_handle": source_character.handle,
        "source_name": source_character.name,
        "source_post_id": point.source_post_id,
        "reply_post_id": point.reply_post_id,
        "topic_brief": _clip(point.topic_brief, 800),
        "source_post_title": _clip(source_post.title, 160),
        "source_post_body": _clip(source_post.body, 800),
        "chain_id": point.chain_id,
        "chain_depth": point.chain_depth,
        "pair_key": point.pair_key,
        "created_at": point.created_at.isoformat(),
        "expires_at": point.expires_at.isoformat(),
    }


def _pending_relationship_points_for_state(
    ctx: LangGraphResidentContext,
) -> list[dict[str, Any]]:
    if not getattr(ctx, "db", None):
        return []
    now = ctx.run_started_at.astimezone(UTC)
    try:
        points = relationship_points.list_pending_relationship_points(
            ctx.db,
            recipient_character_id=ctx.character.id,
            now=now,
            limit=10,
        )
    except Exception:
        ctx.db.rollback()
        return []
    result: list[dict[str, Any]] = []
    for point in points:
        if point.kind == "mention_received":
            continue
        item = _relationship_point_to_state(ctx, point)
        if item is not None:
            result.append(item)
    return result


def _record_feed_seed_selected(
    ctx: LangGraphResidentContext, selected_feed_seed: dict[str, Any]
) -> None:
    if selected_feed_seed.get("mode") != "use_seed":
        return
    _record_daypart_event(
        ctx,
        event_type="feed_seed_selected",
        source_post_id=str(selected_feed_seed.get("post_id") or "") or None,
        summary=_clip(selected_feed_seed.get("seed_brief"), 2000)
        or "feed seed selected",
        payload=selected_feed_seed,
    )


def _seen_daypart_feed_post_ids(ctx: LangGraphResidentContext) -> set[str]:
    if not ctx.memory_session_key:
        return set()
    return set(
        ctx.db.scalars(
            select(_model_AgentDaypartMemoryEvent.source_post_id).where(
                _model_AgentDaypartMemoryEvent.character_id == ctx.character.id,
                _model_AgentDaypartMemoryEvent.memory_session_key
                == ctx.memory_session_key,
                _model_AgentDaypartMemoryEvent.event_type == "observation_feed",
                _model_AgentDaypartMemoryEvent.source_post_id.is_not(None),
            )
        )
    )


def _seen_daypart_notification_ids(ctx: LangGraphResidentContext) -> set[int]:
    if not ctx.memory_session_key:
        return set()
    return set(
        ctx.db.scalars(
            select(_model_AgentDaypartMemoryEvent.notification_id).where(
                _model_AgentDaypartMemoryEvent.character_id == ctx.character.id,
                _model_AgentDaypartMemoryEvent.memory_session_key
                == ctx.memory_session_key,
                _model_AgentDaypartMemoryEvent.event_type == "observation_inbox",
                _model_AgentDaypartMemoryEvent.notification_id.is_not(None),
            )
        )
    )


def _record_daypart_event(
    ctx: LangGraphResidentContext,
    *,
    event_type: str,
    summary: str,
    payload: dict[str, Any] | None = None,
    source_post_id: str | None = None,
    notification_id: int | None = None,
    thread_id: str | None = None,
    topic_signature: str | None = None,
) -> None:
    if (
        ctx.memory_session_key is None
        or ctx.daypart_start_date is None
        or ctx.activity_daypart is None
    ):
        return
    event = _model_AgentDaypartMemoryEvent(
        character_id=ctx.character.id,
        memory_session_key=ctx.memory_session_key,
        daypart_start_date=ctx.daypart_start_date,
        activity_daypart=ctx.activity_daypart,
        event_type=event_type,
        source_post_id=source_post_id,
        notification_id=notification_id,
        thread_id=thread_id,
        topic_signature=topic_signature,
        run_id=ctx.run_id,
        summary=summary[:2000],
        payload=payload,
    )
    ctx.db.add(event)
    ctx.db.commit()


def _llm_context(
    ctx: LangGraphResidentContext, *, node: str, lane: str
) -> DirectLlmCallContext:
    return DirectLlmCallContext(
        credential_id=ctx.credential.id,
        character_id=ctx.character.id,
        agent_run_id=ctx.run_id,
        node=node,
        lane=lane,
        provider=ctx.credential.provider,
        model=ctx.credential.model,
        key_fingerprint=ctx.credential.key_fingerprint,
    )


_PLANNER_THINKING_LANES = {
    "feed_seed_selector",
    "feed_action_planner",
    "inbox_action_planner",
    "independent_writing_planner",
    "independent_topic_composer",
}
_RELATIONSHIP_THINKING_LANES = {"relationship_action_planner"}
_POST_WRITER_THINKING_LANES = {
    "post_writer",
    "post_writer_planner",
    "post_writer_repair",
}
LANGGRAPH_DEFAULT_OUTPUT_TOKENS = 2000
LANGGRAPH_PLANNER_OUTPUT_TOKENS = 4000
LANGGRAPH_RELATIONSHIP_OUTPUT_TOKENS = 4000
LANGGRAPH_POST_WRITER_PLANNER_OUTPUT_TOKENS = 4000
LANGGRAPH_POST_WRITER_OUTPUT_TOKENS = 4000
LANGGRAPH_REPLY_WRITER_OUTPUT_TOKENS = 5000
LANGGRAPH_REPLY_WRITER_REPAIR_OUTPUT_TOKENS = 4000
LANGGRAPH_STATE_RECORDER_OUTPUT_TOKENS = 3000


def _thinking_level_for_lane(lane: str) -> str | None:
    if lane == "supervisor":
        return None
    if lane == "state_recorder":
        return "low"
    if lane in _RELATIONSHIP_THINKING_LANES:
        return settings.langgraph_relationship_thinking_level or "medium"
    if lane in _PLANNER_THINKING_LANES:
        return settings.langgraph_planner_thinking_level or "medium"
    if lane in _POST_WRITER_THINKING_LANES:
        return (
            settings.langgraph_post_writer_thinking_level
            or settings.langgraph_writer_thinking_level
            or "medium"
        )
    if lane == "reply_writer":
        return "high"
    if lane == "reply_writer_repair":
        return "medium"
    return None


async def _call_json(
    ctx: LangGraphResidentContext,
    tracker: RunLlmTracker,
    *,
    node: str,
    lane: str,
    system_prompt: str,
    user_prompt: str,
    response_schema: type[BaseModel],
    max_output_tokens: int = 1200,
    should_retry_json_error: Callable[
        [BaseException, dict[str, Any] | None, dict[str, Any], int], bool
    ]
    | None = None,
) -> dict[str, Any]:
    api_key = _decrypt_api_key(ctx.credential)

    def _validator(payload: dict[str, Any]) -> dict[str, Any]:
        return response_schema.model_validate(payload).model_dump()

    try:
        return await generate_json(
            api_key=api_key,
            context=_llm_context(ctx, node=node, lane=lane),
            tracker=tracker,
            system_prompt=system_prompt,
            user_prompt=user_prompt,
            response_schema=response_schema,
            validator=_validator,
            max_output_tokens=max_output_tokens,
            thinking_level=_thinking_level_for_lane(lane),
            on_rate_limit_wait=ctx.on_rate_limit_wait,
            should_retry_json_error=should_retry_json_error,
        )
    except (DirectLlmJsonError, DirectLlmError, ValidationError) as exc:
        setattr(exc, "node", node)
        setattr(exc, "lane", lane)
        raise


async def _build_lore_query_result(
    ctx: LangGraphResidentContext,
    tracker: RunLlmTracker,
    state: _ResidentGraphState,
) -> dict[str, Any]:
    action_plan = state.get("action_plan", {})
    writing = action_plan.get("writing") if isinstance(action_plan, dict) else None
    if not isinstance(writing, dict) or writing.get("mode") != "independent":
        return _empty_lore_query_result("skipped_not_independent")
    if not str(writing.get("topic_key") or "").strip() or not str(
        writing.get("brief") or ""
    ).strip():
        return _empty_lore_query_result("skipped_missing_topic")
    try:
        if not character_lore_service.has_ready_lore_chunks(
            ctx.db, character_id=ctx.character.id
        ):
            return _empty_lore_query_result("skipped_no_lore")
    except Exception as exc:
        return {
            **_empty_lore_query_result("skipped_lore_check_failed"),
            "error_message": redact_secret_text(str(exc))[:500],
        }

    independent_post_roll = state.get("independent_post_roll", {})
    if not isinstance(independent_post_roll, dict):
        independent_post_roll = {}
    query = _deterministic_lore_query(
        ctx,
        action_plan=action_plan,
        independent_post_roll=independent_post_roll,
    )
    lore_query_mode = "deterministic_fallback"
    focus_terms: list[str] = []
    try:
        rewrite = await _call_json(
            ctx,
            tracker,
            node="LoreQueryRewriter",
            lane="lore_query_rewriter",
            system_prompt=_build_system_prompt(ctx),
            user_prompt=_build_lore_query_rewriter_prompt(
                ctx,
                action_plan=action_plan,
                independent_post_roll=independent_post_roll,
            ),
            response_schema=_LoreQueryRewriteOutput,
            max_output_tokens=400,
        )
        candidate = str(rewrite.get("query") or "").strip()
        if candidate:
            query = candidate
            lore_query_mode = "llm_rewrite"
        raw_focus_terms = rewrite.get("focus_terms")
        if isinstance(raw_focus_terms, list):
            focus_terms = [
                _clip(term, 40)
                for term in raw_focus_terms
                if str(term or "").strip()
            ][:8]
    except Exception as exc:
        logger.info(
            "lore_query_rewriter_fallback run_id=%s character_id=%s error=%s",
            ctx.run_id,
            ctx.character.id,
            redact_secret_text(str(exc))[:300],
        )

    retrieval = await character_lore_service.retrieve_lore_for_query_tracked(
        ctx.db,
        character=ctx.character,
        query=query,
        tracker=tracker,
        agent_run_id=ctx.run_id,
     workflows=build_lore_workflows())
    lore_context = lore_presentation.format_lore_prompt_context(
        retrieval,
        lore_query_mode=lore_query_mode,
        max_chunks=3,
        max_text_chars=500,
    )
    result: dict[str, Any] = {
        "lore_query_mode": lore_query_mode,
        "query": _clip(query, 700),
        "focus_terms": focus_terms,
        "retrieval_mode": retrieval.mode,
        "lore_chunk_ids": retrieval.chunk_ids,
    }
    if lore_context:
        result["lore_context"] = lore_context
    if retrieval.error_message:
        result["error_message"] = redact_secret_text(retrieval.error_message)[:500]
    return result


def _post_writer_plan_error_payload(
    exc: DirectLlmJsonError, *, node: str, lane: str
) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "node": node,
        "lane": lane,
        "failure_class": type(exc).__name__,
        "parse_error_type": exc.parse_error_type,
    }
    if exc.attempt_count is not None:
        payload["attempt_count"] = int(exc.attempt_count)
    if exc.validation_summary:
        payload["validation_summary"] = exc.validation_summary
    diagnostics = getattr(exc, "json_error_diagnostics", None)
    if diagnostics:
        payload["json_error_diagnostics"] = diagnostics
    return payload


async def _call_post_writer_planner(
    ctx: LangGraphResidentContext,
    tracker: RunLlmTracker,
    state: _ResidentGraphState,
    post_task: dict[str, Any],
) -> tuple[dict[str, Any], dict[str, Any]]:
    try:
        output = await _call_json(
            ctx,
            tracker,
            node="PostWriterPlanner",
            lane="post_writer_planner",
            system_prompt=_build_system_prompt(ctx),
            user_prompt=_build_post_writer_planner_user_prompt(state, post_task),
            response_schema=_PostWriterPlannerOutput,
            max_output_tokens=LANGGRAPH_POST_WRITER_PLANNER_OUTPUT_TOKENS,
        )
    except DirectLlmJsonError as exc:
        error = _post_writer_plan_error_payload(
            exc, node="PostWriterPlanner", lane="post_writer_planner"
        )
        return _fallback_post_writer_plan(
            post_task,
            status="fallback_json_failed",
            error=error,
        )
    return _normalize_post_writer_plan(output, post_task)


async def _call_reply_writer(
    ctx: LangGraphResidentContext,
    tracker: RunLlmTracker,
    state: _ResidentGraphState,
    reply_tasks: list[dict[str, Any]],
    *,
    repair: bool = False,
    prompt_reply_tasks: list[dict[str, Any]] | None = None,
) -> tuple[dict[str, Any], dict[str, Any]]:
    prompt_tasks = prompt_reply_tasks if prompt_reply_tasks is not None else reply_tasks
    writer_node = "ReplyWriterRepair" if repair else "ReplyWriter"
    if not prompt_tasks:
        writing = dict(state.get("writing", {}))
        return writing, {
            "writer_node": writer_node,
            "task_count": len(reply_tasks),
            "written_task_ids": [
                task_id
                for task_id, result in _reply_task_results_by_id(writing).items()
                if str(result.get("body") or "").strip()
            ],
            "missing_task_ids": _missing_reply_task_ids(writing, reply_tasks),
            "repair_attempted": repair,
            "batches": [],
        }

    writing = dict(state.get("writing", {}))
    output = await _call_json(
        ctx,
        tracker,
        node=writer_node,
        lane="reply_writer_repair" if repair else "reply_writer",
        system_prompt=_build_system_prompt(ctx),
        user_prompt=_build_reply_writer_user_prompt(state, prompt_tasks, repair=repair),
        response_schema=_ReplyWriterOutput,
        max_output_tokens=(
            LANGGRAPH_REPLY_WRITER_REPAIR_OUTPUT_TOKENS
            if repair
            else LANGGRAPH_REPLY_WRITER_OUTPUT_TOKENS
        ),
    )
    writing, _ = _apply_reply_writer_output(
        writing,
        reply_tasks,
        output,
        repair_attempted=repair,
        writer_node=writer_node,
    )
    prompt_task_ids = [str(task.get("task_id") or "") for task in prompt_tasks]
    prompt_task_id_set = set(prompt_task_ids)
    batch_results: list[dict[str, Any]] = [
        {
            "batch_index": 0,
            "writer_node": writer_node,
            "task_count": len(prompt_tasks),
            "task_ids": prompt_task_ids,
            "written_task_ids": [
                task_id
                for task_id, result in _reply_task_results_by_id(writing).items()
                if task_id in prompt_task_id_set
                and str(result.get("body") or "").strip()
            ],
            "missing_task_ids": _missing_reply_task_ids(writing, prompt_tasks),
            "repair_attempted": repair,
        }
    ]

    reply_results = _reply_task_results_by_id(writing)
    return writing, {
        "writer_node": writer_node,
        "task_count": len(reply_tasks),
        "written_task_ids": [
            task_id
            for task_id, result in reply_results.items()
            if str(result.get("body") or "").strip()
        ],
        "missing_task_ids": _missing_reply_task_ids(writing, reply_tasks),
        "repair_attempted": repair,
        "batches": batch_results,
    }


async def _call_post_writer(
    ctx: LangGraphResidentContext,
    tracker: RunLlmTracker,
    state: _ResidentGraphState,
    post_task: dict[str, Any],
    *,
    repair: bool = False,
) -> tuple[dict[str, Any], dict[str, Any]]:
    writer_node = "PostWriterRepair" if repair else "PostWriter"
    output = await _call_json(
        ctx,
        tracker,
        node=writer_node,
        lane="post_writer_repair" if repair else "post_writer",
        system_prompt=_build_system_prompt(ctx),
        user_prompt=_build_post_writer_user_prompt(state, post_task, repair=repair),
        response_schema=_PostWriterOutput,
        max_output_tokens=LANGGRAPH_POST_WRITER_OUTPUT_TOKENS,
    )
    return _apply_post_writer_output(
        state.get("action_plan", {}),
        state.get("writing", {}),
        post_task,
        output,
        repair_attempted=repair,
        writer_node=writer_node,
    )


def _state_recorder_provider_error_hint(exc: BaseException) -> str:
    existing = getattr(exc, "provider_error_hint", None)
    if isinstance(existing, str) and existing.strip():
        return existing.strip()[:120]
    text = str(exc).lower()
    if "timeout" in text or "timed out" in text:
        return "provider_timeout"
    if "429" in text or "resource_exhausted" in text or "rate_limit" in text:
        return "provider_rate_limit"
    if "503" in text or "unavailable" in text or "high demand" in text:
        return "provider_unavailable"
    return "provider_error"


def _state_recorder_failure_meta(exc: BaseException) -> dict[str, Any]:
    meta: dict[str, Any] = {"failure_class": type(exc).__name__}
    if isinstance(exc, DirectLlmJsonError):
        parse_error_type = getattr(exc, "parse_error_type", None)
        if parse_error_type:
            meta["parse_error_type"] = parse_error_type
        attempt_count = getattr(exc, "attempt_count", None)
        if attempt_count is not None:
            meta["attempt_count"] = int(attempt_count)
        validation_summary = getattr(exc, "validation_summary", None)
        if validation_summary:
            meta["validation_summary"] = validation_summary
        diagnostics = getattr(exc, "json_error_diagnostics", None)
        if diagnostics:
            meta["json_error_diagnostics"] = diagnostics
    elif isinstance(exc, DirectLlmError):
        meta["provider_error_hint"] = _state_recorder_provider_error_hint(exc)
        provider_error = getattr(exc, "provider_error", None)
        if isinstance(provider_error, dict) and provider_error:
            meta["provider_error"] = provider_error
    else:
        validation_summary = _validation_summary_from_exception(exc)
        if validation_summary:
            meta["validation_summary"] = validation_summary
    return meta


def _llm_failure_meta(exc: BaseException) -> dict[str, Any]:
    meta = _state_recorder_failure_meta(exc)
    node = _clip(getattr(exc, "node", None), 120) or None
    lane = _clip(getattr(exc, "lane", None), 120) or None
    if node:
        meta["failure_node"] = node
    if lane:
        meta["failure_lane"] = lane
    return meta


def _state_recorder_length_validation_summary(
    exc: BaseException,
) -> list[dict[str, str]] | None:
    if isinstance(exc, DirectLlmJsonError):
        summary = getattr(exc, "validation_summary", None)
        return summary if isinstance(summary, list) else None
    return _validation_summary_from_exception(exc)


def _log_state_save_suppressed(
    ctx: LangGraphResidentContext, *, reason: str, result: str
) -> None:
    agent_crud.log_activity(
        ctx.db,
        user_id=ctx.user_id,
        character_id=ctx.character.id,
        action_type="state_save_suppressed",
        target_post_id=None,
        reason=reason,
        result=_clip(result, 1000),
    )


async def _run_state_recorder(
    ctx: LangGraphResidentContext,
    tracker: RunLlmTracker,
    state: _ResidentGraphState,
) -> dict[str, Any]:
    state_payload: dict[str, Any]
    fallback_failure_class: str | None = None
    fallback_failure_meta: dict[str, Any] = {}
    state_postprocess_status: str | None = None
    state_sanitized_fields: list[str] = []
    try:
        state_payload = await _call_json(
            ctx,
            tracker,
            node="StateRecorder",
            lane="state_recorder",
            system_prompt=_build_system_prompt(ctx),
            user_prompt=_build_state_recorder_user_prompt(ctx, state),
            response_schema=_StateWrite,
            max_output_tokens=LANGGRAPH_STATE_RECORDER_OUTPUT_TOKENS,
            should_retry_json_error=_state_recorder_should_retry_json_error,
        )
    except (DirectLlmJsonError, DirectLlmError, ValidationError) as exc:
        fallback_failure_class = type(exc).__name__
        fallback_failure_meta = _state_recorder_failure_meta(exc)
        sanitized_result = _state_recorder_sanitized_payload_from_failure(exc)
        if sanitized_result is not None:
            state_payload, state_sanitized_fields = sanitized_result
            state_postprocess_status = "sanitized_saved"
            logger.warning(
                "langgraph_state_recorder_sanitized run_id=%s character_id=%s "
                "failure_class=%s sanitized_fields=%s error=%s",
                ctx.run_id,
                ctx.character.id,
                fallback_failure_class,
                ",".join(state_sanitized_fields),
                redact_secret_text(str(exc))[:500],
            )
        else:
            state_postprocess_status = "fallback_saved"
            logger.warning(
                "langgraph_state_recorder_fallback run_id=%s character_id=%s "
                "failure_class=%s error=%s",
                ctx.run_id,
                ctx.character.id,
                fallback_failure_class,
                redact_secret_text(str(exc))[:500],
            )
            state_payload = _fallback_state_payload(ctx, state)

    blocked = _prompt_injection_output_block(
        {
            "summary": str(state_payload.get("summary") or ""),
            "memory_note": str(state_payload.get("memory_note") or ""),
            "observation_note": str(state_payload.get("observation_note") or ""),
        }
    )
    if blocked is not None:
        blocked_field, blocked_result = blocked
        state_result = {
            "status": "suppressed",
            "failure_class": "prompt_injection_output_blocked",
            "blocked_field": blocked_field,
            "blocked_category": blocked_result.category,
        }
        _record_daypart_event(
            ctx,
            event_type="langgraph_tick",
            summary="StateRecorder output was blocked before state save.",
            payload=_langgraph_tick_payload(state, state_result=state_result),
        )
        return {
            "state_result": state_result,
            "completed_nodes": _merge_completed(state, "StateRecorder"),
        }

    try:
        saved = agent_tool_state.save_agent_tool_character_state(
            ctx.db,
            ctx.session_key,
            ctx.character.id,
            character_schemas.AgentCharacterStateWrite(**state_payload),
        )
    except Exception as exc:
        if fallback_failure_class is None:
            raise
        ctx.db.rollback()
        suppressed_reason = (
            "state_recorder_sanitized_save_failed"
            if state_postprocess_status == "sanitized_saved"
            else "state_recorder_fallback_save_failed"
        )
        log_reason = (
            "langgraph_state_recorder_sanitized_save_failed"
            if state_postprocess_status == "sanitized_saved"
            else "langgraph_state_recorder_fallback_failed"
        )
        suppressed_result = (
            "Suppressed state save after StateRecorder postprocess failed: "
            f"{type(exc).__name__}"
        )
        _log_state_save_suppressed(
            ctx,
            reason=log_reason,
            result=suppressed_result,
        )
        state_result = {
            "status": "suppressed",
            "failure_class": fallback_failure_class,
            "suppressed_reason": suppressed_reason,
            "fallback_save_error_class": type(exc).__name__,
        }
        state_result.update(fallback_failure_meta)
        _record_daypart_event(
            ctx,
            event_type="langgraph_tick",
            summary=_fallback_state_payload(ctx, state)["memory_note"],
            payload=_langgraph_tick_payload(state, state_result=state_result),
        )
        return {
            "state_result": state_result,
            "completed_nodes": _merge_completed(state, "StateRecorder"),
        }

    state_result = {
        "status": (
            "succeeded"
            if fallback_failure_class is None
            else state_postprocess_status or "fallback_saved"
        ),
        "mood": saved.mood,
        "summary": _clip(saved.summary, 500),
    }
    if fallback_failure_class is not None:
        state_result.update(fallback_failure_meta)
        if state_postprocess_status == "sanitized_saved":
            state_result["sanitized_fields"] = state_sanitized_fields
        else:
            state_result["fallback_used"] = True
    _record_daypart_event(
        ctx,
        event_type="langgraph_tick",
        summary=state_payload.get("memory_note") or state_payload.get("summary") or "",
        payload=_langgraph_tick_payload(state, state_result=state_result),
    )
    return {
        "state_result": state_result,
        "completed_nodes": _merge_completed(state, "StateRecorder"),
    }


def _planner_error_payload(
    exc: DirectLlmJsonError, *, node: str, lane: str
) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "node": node,
        "lane": lane,
        "failure_class": type(exc).__name__,
        "parse_error_type": getattr(exc, "parse_error_type", None),
    }
    attempt_count = getattr(exc, "attempt_count", None)
    if attempt_count is not None:
        payload["attempt_count"] = int(attempt_count)
    validation_summary = getattr(exc, "validation_summary", None)
    if validation_summary:
        payload["validation_summary"] = validation_summary
    diagnostics = getattr(exc, "json_error_diagnostics", None)
    if diagnostics:
        payload["json_error_diagnostics"] = diagnostics
    return payload


def _planner_json_failed_plan(
    exc: DirectLlmJsonError, *, node: str, lane: str
) -> dict[str, Any]:
    plan = _empty_action_plan("planner_json_failed")
    plan["planner_error"] = _planner_error_payload(exc, node=node, lane=lane)
    plan["writing"]["skip_reason"] = "planner_json_failed"
    return plan


def _supervisor_route(state: _ResidentGraphState) -> str:
    return state.get("next_node", END)


def _merge_completed(state: _ResidentGraphState, node: str) -> list[str]:
    completed = list(state.get("completed_nodes", []))
    if node not in completed:
        completed.append(node)
    return completed


def _build_graph(ctx: LangGraphResidentContext, tracker: RunLlmTracker):
    workflow = StateGraph(_ResidentGraphState)

    async def supervisor(state: _ResidentGraphState) -> dict[str, Any]:
        steps = int(state.get("steps", 0)) + 1
        if steps > settings.langgraph_max_steps_per_run:
            return {"steps": steps, "next_node": END, "failure_class": "max_steps"}
        if "DaypartContextLoader" not in state.get("completed_nodes", []):
            return {"steps": steps, "next_node": "DaypartContextLoader"}
        if "FeedObserver" not in state.get("completed_nodes", []):
            return {"steps": steps, "next_node": "FeedObserver"}
        if "FeedSeedSelector" not in state.get("completed_nodes", []):
            return {"steps": steps, "next_node": "FeedSeedSelector"}
        if "InboxObserver" not in state.get("completed_nodes", []):
            return {"steps": steps, "next_node": "InboxObserver"}
        if "RelationshipPointLoader" not in state.get("completed_nodes", []):
            return {"steps": steps, "next_node": "RelationshipPointLoader"}
        if "RelationshipMemory" not in state.get("completed_nodes", []):
            return {"steps": steps, "next_node": "RelationshipMemory"}
        if "FeedActionPlanner" not in state.get("completed_nodes", []):
            return {"steps": steps, "next_node": "FeedActionPlanner"}
        if "InboxActionPlanner" not in state.get("completed_nodes", []):
            return {"steps": steps, "next_node": "InboxActionPlanner"}
        if "RelationshipActionPlanner" not in state.get("completed_nodes", []):
            return {"steps": steps, "next_node": "RelationshipActionPlanner"}
        if "IndependentTopicComposer" not in state.get("completed_nodes", []):
            return {"steps": steps, "next_node": "IndependentTopicComposer"}
        if "IndependentWritingPlanner" not in state.get("completed_nodes", []):
            return {"steps": steps, "next_node": "IndependentWritingPlanner"}
        if "BundleComposer" not in state.get("completed_nodes", []):
            return {"steps": steps, "next_node": "BundleComposer"}
        if "ActionBudgetTrimmer" not in state.get("completed_nodes", []):
            return {"steps": steps, "next_node": "ActionBudgetTrimmer"}
        if "LoreQueryRewriter" not in state.get("completed_nodes", []):
            return {"steps": steps, "next_node": "LoreQueryRewriter"}
        if "WriteTaskComposer" not in state.get("completed_nodes", []):
            return {"steps": steps, "next_node": "WriteTaskComposer"}
        write_tasks = state.get("write_tasks", {})
        reply_tasks = (
            write_tasks.get("reply_tasks", []) if isinstance(write_tasks, dict) else []
        )
        post_task = write_tasks.get("post_task") if isinstance(write_tasks, dict) else None
        if reply_tasks and "ReplyWriter" not in state.get("completed_nodes", []):
            return {"steps": steps, "next_node": "ReplyWriter"}
        if (
            isinstance(post_task, dict)
            and "PostWriterPlanner" not in state.get("completed_nodes", [])
        ):
            return {"steps": steps, "next_node": "PostWriterPlanner"}
        if isinstance(post_task, dict) and "PostWriter" not in state.get("completed_nodes", []):
            return {"steps": steps, "next_node": "PostWriter"}
        if (
            reply_tasks
            and _missing_reply_task_ids(state.get("writing", {}), reply_tasks)
            and "ReplyWriterRepair" not in state.get("completed_nodes", [])
        ):
            return {"steps": steps, "next_node": "ReplyWriterRepair"}
        if (
            isinstance(post_task, dict)
            and _post_task_needs_repair(state.get("writing", {}), post_task)
            and "PostWriterRepair" not in state.get("completed_nodes", [])
        ):
            return {"steps": steps, "next_node": "PostWriterRepair"}
        if "CommunityExecutor" not in state.get("completed_nodes", []):
            return {"steps": steps, "next_node": "CommunityExecutor"}
        if "RelationshipPointRecorder" not in state.get("completed_nodes", []):
            return {"steps": steps, "next_node": "RelationshipPointRecorder"}
        if "StateRecorder" not in state.get("completed_nodes", []):
            return {"steps": steps, "next_node": "StateRecorder"}
        return {"steps": steps, "next_node": END}

    async def daypart_context_loader(state: _ResidentGraphState) -> dict[str, Any]:
        daypart_end_result = _finalize_closed_dayparts(ctx)
        daypart_context = _current_daypart_context(ctx)
        daypart_context["daypart_end_result"] = daypart_end_result
        return {
            "daypart_context": daypart_context,
            "completed_nodes": _merge_completed(state, "DaypartContextLoader"),
        }

    async def feed_observer(state: _ResidentGraphState) -> dict[str, Any]:
        session_key = f"{ctx.session_key}:scratch:feed-scan:langgraph"
        feed_page = social_agent_tool_reads_runtime.agent_tool_reads.list_agent_tool_feed(ctx.db, session_key, limit=30)
        seen_post_ids = _seen_daypart_feed_post_ids(ctx)
        items: list[dict[str, Any]] = []
        seed_candidates: list[dict[str, Any]] = []
        relationship_candidates: list[dict[str, Any]] = []
        topics: list[str] = []
        excluded_reply_already_answered_count = 0
        for item in feed_page.items:
            if item.post_id in seen_post_ids:
                continue
            post = social_posts_repository.get_post(ctx.db, item.post_id)
            author_character_id = getattr(post, "author_character_id", None)
            author_character = (
                characters_profile_service.get_character(ctx.db, author_character_id)
                if author_character_id
                else None
            )
            author_handle = (
                _clip(getattr(author_character, "handle", ""), 80)
                if author_character is not None
                else None
            )
            topic = _clip(item.topic_signature or item.title, 160)
            if topic and topic not in topics:
                topics.append(topic)
            affordance = (
                social_resident_affordances_service.resident_feed_action_affordance(
                    ctx.db,
                    post=post,
                    character_id=ctx.character.id,
                    allowed_actions=ctx.activity_policy.allowed_actions,
                )
                if post is not None
                else {
                    "available_actions": [],
                    "blocked_actions": {"post": "not_found"},
                    "action_targets": {},
                }
            )
            affordance, reply_already_answered = (
                _suppress_already_answered_reply_affordance(
                    affordance,
                    db=ctx.db,
                    character_id=ctx.character.id,
                    post_id=item.post_id,
                )
            )
            if reply_already_answered:
                excluded_reply_already_answered_count += 1
            raw_compact = {
                "post_id": item.post_id,
                "author": _clip(item.author, 120),
                "author_character_id": author_character_id,
                "author_handle": author_handle,
                "author_name": _clip(getattr(author_character, "name", item.author), 120),
                "topic_signature": topic,
                "semantic_summary": _clip(item.body_preview or item.title, 500),
                "source_body": _clip(getattr(post, "body", ""), 1000),
                "why_it_mattered": "candidate returned by resident feed scan",
                **affordance,
            }
            if (
                author_character_id
                and author_character_id != ctx.character.id
                and author_handle
                and post is not None
                and post.deleted_at is None
                and post.report_hidden_at is None
                and post.visibility == "public"
            ):
                seed_candidates.append(
                    {
                        "post_id": item.post_id,
                        "author_character_id": author_character_id,
                        "author_handle": author_handle,
                        "author_name": _clip(
                            getattr(author_character, "name", item.author), 120
                        ),
                        "title": _clip(item.title, 160),
                        "body_summary": _clip(item.body_preview or item.title, 500),
                        "source_body": _clip(getattr(post, "body", ""), 1000),
                        "topic_signature": topic,
                        "relationship_signal": raw_compact.get("why_it_mattered"),
                    }
                )
            relationship_candidate = _relationship_candidate_from_item(
                ctx=ctx,
                source="feed",
                item=raw_compact,
                action_type="follow",
            )
            if relationship_candidate is not None:
                relationship_candidates.append(relationship_candidate)
            unfollow_candidate = _relationship_candidate_from_item(
                ctx=ctx,
                source="feed",
                item=raw_compact,
                action_type="unfollow_watch",
            )
            if unfollow_candidate is not None:
                relationship_candidates.append(unfollow_candidate)
            planner_affordance = _strip_action_from_affordance(affordance, "follow")
            compact = {
                "item_index": len(items),
                "post_id": item.post_id,
                "author": _clip(item.author, 120),
                "author_character_id": author_character_id,
                "author_handle": author_handle,
                "topic_signature": topic,
                "semantic_summary": _clip(item.body_preview or item.title, 500),
                "why_it_mattered": "candidate returned by resident feed scan",
                **planner_affordance,
            }
            if not compact["available_actions"]:
                planner_item_added = False
            else:
                planner_item_added = True
                items.append(compact)
            _record_daypart_event(
                ctx,
                event_type="observation_feed",
                source_post_id=item.post_id,
                topic_signature=topic or None,
                summary=compact["semantic_summary"] or topic or item.post_id,
                payload={
                    "post_id": item.post_id,
                    "author": compact["author"],
                    "author_character_id": compact["author_character_id"],
                    "topic_signature": compact["topic_signature"],
                    "available_actions": raw_compact["available_actions"],
                    "relationship_target": relationship_candidate,
                },
            )
            if not planner_item_added:
                continue
            if len(items) >= 30:
                break
        observation = {
            "selected_posts": items,
            "seed_candidates": seed_candidates[:30],
            "feed_theme_topics": topics[:3],
            "returned_count": len(items),
            "excluded_seen_count": len(feed_page.items) - len(items),
            "excluded_reply_already_answered_count": (
                excluded_reply_already_answered_count
            ),
        }
        return {
            "feed_observation": observation,
            "relationship_candidates": _dedupe_relationship_candidates(
                relationship_candidates
            ),
            "completed_nodes": _merge_completed(state, "FeedObserver"),
        }

    async def feed_seed_selector(state: _ResidentGraphState) -> dict[str, Any]:
        feed_observation = state.get("feed_observation", {})
        candidates = _feed_seed_candidates(feed_observation)
        if not candidates:
            selected = {"mode": "none", "mention_required": False}
            return {
                "selected_feed_seed": selected,
                "completed_nodes": _merge_completed(state, "FeedSeedSelector"),
            }
        user_prompt = "\n".join(
            [
                "FeedSeedSelector role: choose at most one character-authored feed post that can work only as background situation for today's root independent post.",
                "First judge whether each candidate matches this character's feed seed interest criteria.",
                "Do not choose user posts or self posts.",
                "Return mode='none' when candidates do not match the character's interests, worldview, emotional attention, or community-atmosphere criteria.",
                "The seed is not the topic. It can only be blended later if it naturally fits the selected independent topic.",
                "If selected, mention_required must be true because the source is another character.",
                "Do not copy source wording. Return mode='none' when no candidate is a good background.",
                "",
                f"current_time_reference: {_format_current_time_reference(ctx.run_started_at)}",
                f"feed_seed_interest_criteria: {_feed_seed_interest_criteria(ctx) or '(not available; use persona context only)'}",
                f"daypart_context: {_format_json_for_prompt(state.get('daypart_context', {}), max_chars=2500)}",
                f"seed_candidates: {_format_json_for_prompt(candidates, max_chars=7000)}",
            ]
        )
        try:
            raw = await _call_json(
                ctx,
                tracker,
                node="FeedSeedSelector",
                lane="feed_seed_selector",
                system_prompt=_build_system_prompt(ctx),
                user_prompt=user_prompt,
                response_schema=_FeedSeedSelection,
                max_output_tokens=LANGGRAPH_PLANNER_OUTPUT_TOKENS,
            )
        except DirectLlmJsonError as exc:
            raw = {
                "mode": "none",
                "mention_required": False,
                "planner_error": _planner_error_payload(
                    exc, node="FeedSeedSelector", lane="feed_seed_selector"
                ),
            }
        selected = _normalize_feed_seed_selection(raw, candidates=candidates)
        if isinstance(raw.get("planner_error"), dict):
            selected["planner_error"] = raw["planner_error"]
        try:
            _record_feed_seed_selected(ctx, selected)
        except Exception as exc:
            ctx.db.rollback()
            selected["record_error"] = type(exc).__name__
        return {
            "selected_feed_seed": selected,
            "completed_nodes": _merge_completed(state, "FeedSeedSelector"),
        }

    async def inbox_observer(state: _ResidentGraphState) -> dict[str, Any]:
        session_key = f"{ctx.session_key}:scratch:inbox:langgraph"
        notifications = social_agent_tool_reads_runtime.agent_tool_reads.list_agent_tool_notifications(
            ctx.db, session_key, limit=10
        )
        inbox_lane_only = bool(state.get("inbox_lane_only"))
        seen_notification_ids = (
            set() if inbox_lane_only else _seen_daypart_notification_ids(ctx)
        )
        active_inbox_world_character = None
        if inbox_lane_only:
            try:
                active_inbox_world_character = (
                    langgraph_social_apply.active_world_character(
                        ctx.db, character_id=ctx.character.id
                    )
                )
            except langgraph_social_apply.LangGraphSocialApplyError:
                active_inbox_world_character = None
        items: list[dict[str, Any]] = []
        relationship_candidates: list[dict[str, Any]] = list(
            state.get("relationship_candidates", [])
        )
        observed_notification_ids: list[int] = []
        blocked_notification_ids: list[int] = []
        excluded_reply_already_answered_count = 0
        for notification in notifications:
            if notification.id in seen_notification_ids:
                continue
            if inbox_lane_only and notification.notification_type not in {
                "reply",
                "mention",
                "joint_activity_started",
            }:
                continue
            source_post_id = notification.source_post_id or notification.post_id
            raw_notification = social_inbox_repository.get_notification_for_agent(
                ctx.db,
                user_id=ctx.user_id,
                character_id=ctx.character.id,
                notification_id=notification.id,
            )
            observation_receipt = None
            if inbox_lane_only:
                source_post = (
                    social_posts_repository.get_post(ctx.db, source_post_id)
                    if source_post_id
                    else None
                )
                if (
                    active_inbox_world_character is None
                    or raw_notification is None
                    or source_post is None
                    or source_post.world_id
                    != active_inbox_world_character.world_id
                    or (
                        raw_notification.world_id is not None
                        and raw_notification.world_id
                        != active_inbox_world_character.world_id
                    )
                    or (
                        raw_notification.recipient_world_character_id is not None
                        and raw_notification.recipient_world_character_id
                        != active_inbox_world_character.id
                    )
                ):
                    blocked_notification_ids.append(notification.id)
                    continue
                observation_receipt = observe_source(
                    ctx.db,
                    world_id=active_inbox_world_character.world_id,
                    observer_world_character_id=active_inbox_world_character.id,
                    source_social_event_id=raw_notification.source_social_event_id,
                    source_post_id=source_post.id,
                    lane="inbox",
                    observed_at=ctx.run_started_at,
                )
                # The InboxObserver is the actual context boundary. Persist it
                # before the planner can choose NO_ACTION or a follow-up can fail.
                ctx.db.commit()
            observed_notification_ids.append(notification.id)
            affordance = (
                social_resident_affordances_service.resident_inbox_action_affordance(
                    ctx.db,
                    notification=raw_notification,
                    character_id=ctx.character.id,
                    allowed_actions=ctx.activity_policy.allowed_actions,
                )
                if raw_notification is not None
                else {
                    "available_actions": [],
                    "blocked_actions": {"notification": "not_found"},
                    "action_targets": {},
                }
            )
            affordance, reply_already_answered = (
                _suppress_already_answered_reply_affordance(
                    affordance,
                    db=ctx.db,
                    character_id=ctx.character.id,
                    post_id=source_post_id,
                )
            )
            if reply_already_answered:
                excluded_reply_already_answered_count += 1
            conversation_context = _inbox_conversation_context(
                ctx.db,
                character_id=ctx.character.id,
                actor_character_id=notification.actor_character_id,
                source_post_id=source_post_id,
            )
            compact = {
                "item_index": len(items),
                "notification_id": notification.id,
                "notification_type": notification.notification_type,
                "source_post_id": source_post_id,
                "actor_character_id": notification.actor_character_id,
                "actor_name": _clip(notification.actor_name, 120),
                "semantic_summary": _clip(
                    notification.source_post_body or notification.post_body or "", 500
                ),
                "why_it_mattered": (
                    "unread mention notification"
                    if notification.notification_type == "mention"
                    else "unread reply notification"
                ),
                **affordance,
            }
            if observation_receipt is not None:
                compact["observation"] = {
                    "schema_version": observation_receipt.schema_version,
                    "source_social_event_id": (
                        observation_receipt.source_social_event_id
                    ),
                    "receipt_id": observation_receipt.receipt_id,
                    "relationship_state_id": (
                        observation_receipt.relationship_state_id
                    ),
                    "replayed": observation_receipt.replayed,
                }
            if source_post_id:
                proposal = langgraph_social_apply.proposal_for_notification(
                    ctx.db,
                    recipient_character_id=ctx.character.id,
                    source_post_id=source_post_id,
                )
                if proposal is not None:
                    compact["activity_proposal"] = {
                        "proposal_id": proposal.id,
                        "activity_seed": proposal.activity_seed,
                        "place_key": proposal.place_key,
                        "target_daypart": proposal.target_daypart,
                        "date_policy": proposal.date_policy,
                        "target_date": (
                            proposal.target_date.isoformat()
                            if proposal.target_date is not None
                            else None
                        ),
                    }
                    compact["why_it_mattered"] = "open shared-activity proposal"
            if conversation_context:
                compact["conversation_context"] = conversation_context
            relationship_candidate = None
            if not state.get("inbox_lane_only"):
                relationship_candidate = _relationship_candidate_from_item(
                    ctx=ctx,
                    source="inbox",
                    item=compact,
                    action_type="follow",
                )
                if relationship_candidate is not None:
                    relationship_candidates.append(relationship_candidate)
            unfollow_candidate = _relationship_candidate_from_item(
                ctx=ctx,
                source="inbox",
                item=compact,
                action_type="unfollow_watch",
            )
            if unfollow_candidate is not None:
                relationship_candidates.append(unfollow_candidate)
            if not state.get("inbox_lane_only"):
                compact = {
                    **compact,
                    **_strip_action_from_affordance(compact, "follow"),
                }
            if not compact["available_actions"]:
                planner_item_added = False
            else:
                planner_item_added = True
                items.append(compact)
            _record_daypart_event(
                ctx,
                event_type="observation_inbox",
                source_post_id=source_post_id,
                notification_id=notification.id,
                summary=compact["semantic_summary"] or f"notification:{notification.id}",
                payload={
                    "notification_id": notification.id,
                    "actor_name": compact["actor_name"],
                    "actor_character_id": compact["actor_character_id"],
                    "source_post_id": source_post_id,
                    "notification_type": notification.notification_type,
                    "available_actions": affordance.get("available_actions", []),
                    "conversation_context": conversation_context,
                    "relationship_target": relationship_candidate,
                },
            )
            if not planner_item_added:
                blocked_notification_ids.append(notification.id)
                continue
        return {
            "inbox_observation": {
                "items": items,
                "returned_count": len(items),
                "observed_count": len(observed_notification_ids),
                "observed_notification_ids": observed_notification_ids,
                "blocked_notification_ids": blocked_notification_ids,
                "excluded_seen_count": len(notifications) - len(items),
                "excluded_reply_already_answered_count": (
                    excluded_reply_already_answered_count
                ),
            },
            "relationship_candidates": _dedupe_relationship_candidates(
                relationship_candidates
            ),
            "completed_nodes": _merge_completed(state, "InboxObserver"),
        }

    async def relationship_point_loader(state: _ResidentGraphState) -> dict[str, Any]:
        relationship_points = _pending_relationship_points_for_state(ctx)
        return {
            "relationship_point_candidates": relationship_points,
            "completed_nodes": _merge_completed(state, "RelationshipPointLoader"),
        }

    async def relationship_memory(state: _ResidentGraphState) -> dict[str, Any]:
        logs = agent_crud.list_recent_activity(ctx.db, ctx.character.id, limit=12)
        active_topic_arc = state.get("active_topic_arc")
        memory = {
            "recent_activity": [
                {
                    "action_type": log.action_type,
                    "target_post_id": log.target_post_id,
                    "reason": _clip(log.reason, 240),
                    "result": _clip(log.result, 500),
                    "created_at": log.created_at.isoformat(),
                }
                for log in logs
            ],
            "daypart_history": _daypart_history_for_prompt(ctx),
            "relationship_daypart_memory": _relationship_daypart_memory(ctx),
            "relationship_point_candidates": state.get(
                "relationship_point_candidates", []
            ),
            "active_topic_arc": _topic_arc_for_prompt(
                active_topic_arc,
                current_date=_current_kst_date(ctx),
            ),
        }
        return {
            "relationship_memory": memory,
            "completed_nodes": _merge_completed(state, "RelationshipMemory"),
        }

    async def feed_action_planner(state: _ResidentGraphState) -> dict[str, Any]:
        feed_observation = state.get("feed_observation", {})
        active_topic_arc = state.get("active_topic_arc")
        selected_posts = feed_observation.get("selected_posts")
        if not isinstance(selected_posts, list) or not selected_posts:
            plan = _empty_action_plan("no feed candidates")
        else:
            feed_prompt_observation = _planner_feed_observation_for_prompt(
                feed_observation
            )
            user_prompt = "\n".join(
                [
                    "FeedActionPlanner role: independently decide feed actions for this tick.",
                    "For each feed item, judge like/reply/repost/follow independently against the character's public-action tendency notes.",
                    "Do not choose one representative action for the whole tick; multiple feed actions may coexist when each fits.",
                    "Do not choose an action only because it is available.",
                    "Choose only action_type values listed in each item's available_actions.",
                    "Select actions with item_index and action_type only; the backend resolves target ids.",
                    "For every selected action, also declare a short public-safe first-person motivation_kind/motivation_text and a coarse emotion_label at this decision moment. These are not hidden reasoning; never include deliberation, secrets, or chain-of-thought. Use unspecified with null emotion detail when unclear.",
                    "Do not decide standalone writing in this node. Feed post seeds are selected by FeedSeedSelector.",
                    "If no feed action fits, return no actions and writing.mode='none'.",
                    "",
                    f"current_time_reference: {_format_current_time_reference(ctx.run_started_at)}",
                    f"daypart_context: {_format_json_for_prompt(state.get('daypart_context', {}), max_chars=2000)}",
                    f"feed_observation: {_format_json_for_prompt(feed_prompt_observation, max_chars=6000)}",
                    f"today_root_writing_memory: {_format_json_for_prompt(_today_root_writing_memory_for_prompt(ctx), max_chars=4000)}",
                    f"relationship_memory: {_format_json_for_prompt(state.get('relationship_memory', {}), max_chars=4000)}",
                ]
            )
            try:
                plan = await _call_json(
                    ctx,
                    tracker,
                    node="FeedActionPlanner",
                    lane="feed_action_planner",
                    system_prompt=_build_system_prompt(ctx),
                    user_prompt=user_prompt,
                    response_schema=_FeedActionPlan,
                    max_output_tokens=LANGGRAPH_PLANNER_OUTPUT_TOKENS,
                )
            except DirectLlmJsonError as exc:
                plan = _planner_json_failed_plan(
                    exc, node="FeedActionPlanner", lane="feed_action_planner"
                )
            plan = _normalize_feed_action_plan(
                plan,
                ctx,
                feed_observation=feed_observation,
                active_topic_arc=active_topic_arc,
            )
        return {
            "feed_action_plan": plan,
            "completed_nodes": _merge_completed(state, "FeedActionPlanner"),
        }

    async def inbox_action_planner(state: _ResidentGraphState) -> dict[str, Any]:
        inbox_observation = state.get("inbox_observation", {})
        items = inbox_observation.get("items")
        if not isinstance(items, list) or not items:
            plan = _empty_action_plan("no inbox candidates")
        else:
            inbox_prompt_observation = _planner_inbox_observation_for_prompt(
                inbox_observation
            )
            user_prompt = "\n".join(
                [
                    "InboxActionPlanner role: independently decide inbox actions for this tick.",
                    "For each notification, judge reply/like/follow independently against the character's public-action tendency notes.",
                    "Before choosing an inbox action, read conversation_context and decide whether the thread naturally needs a reply, a short closing reply, only a lightweight acknowledgement, or no public action.",
                    "Do not choose one representative action for the whole tick; multiple inbox actions may coexist when each fits.",
                    "Do not choose an action only because it is available.",
                    "Choose only action_type values listed in each item's available_actions.",
                    "Mention notifications are social signals, not obligations; choose a mention reply only when it naturally fits the persona, community tendency, and conversation context.",
                    "Reply is optional even when available. If the conversation already feels complete, like/follow or no action can be more natural than another reply.",
                    "Return conversation_decisions for inbox items you judge: continue_reply, closing_reply, ack_without_reply, or no_action_closed.",
                    "Use ack_without_reply when reply would be repetitive but like or follow may still fit.",
                    "Use closing_reply only when a short final reply is more natural than silence; do not open a new topic in that reply.",
                    "Select actions with item_index and action_type only; the backend resolves notification and target ids.",
                    "For every selected action, also declare a short public-safe first-person motivation_kind/motivation_text and a coarse emotion_label at this decision moment. These are not hidden reasoning; never include deliberation, secrets, or chain-of-thought. Use unspecified with null emotion detail when unclear.",
                    "Do not decide standalone writing in this node.",
                    "If no inbox action fits, return no inbox actions.",
                    "",
                    f"tendency_summary: {getattr(ctx.activity_policy, 'tendency_summary', '') or '-'}",
                    f"reply_tendency_note: {_tendency_action_note(ctx, 'reply') or '-'}",
                    f"like_tendency_note: {_tendency_action_note(ctx, 'like') or '-'}",
                    f"follow_tendency_note: {_tendency_action_note(ctx, 'follow') or '-'}",
                    f"daypart_context: {_format_json_for_prompt(state.get('daypart_context', {}), max_chars=2000)}",
                    f"inbox_observation: {_format_json_for_prompt(inbox_prompt_observation, max_chars=8000)}",
                    f"relationship_memory: {_format_json_for_prompt(state.get('relationship_memory', {}), max_chars=4000)}",
                ]
            )
            try:
                plan = await _call_json(
                    ctx,
                    tracker,
                    node="InboxActionPlanner",
                    lane="inbox_action_planner",
                    system_prompt=_build_system_prompt(ctx),
                    user_prompt=user_prompt,
                    response_schema=_InboxActionPlan,
                    max_output_tokens=LANGGRAPH_PLANNER_OUTPUT_TOKENS,
                )
            except DirectLlmJsonError as exc:
                plan = _planner_json_failed_plan(
                    exc, node="InboxActionPlanner", lane="inbox_action_planner"
                )
            raw_actions = plan.get("inbox_actions")
            raw_selected_action_count = (
                len(raw_actions) if isinstance(raw_actions, list) else 0
            )
            plan = _normalize_inbox_action_plan(
                plan,
                ctx,
                inbox_observation=inbox_observation,
            )
            plan["raw_selected_action_count"] = raw_selected_action_count
        return {
            "inbox_action_plan": plan,
            "completed_nodes": _merge_completed(state, "InboxActionPlanner"),
        }

    async def relationship_action_planner(state: _ResidentGraphState) -> dict[str, Any]:
        allowed_relationship_actions = _relationship_allowed_actions(ctx)
        candidates = _dedupe_relationship_candidates(
            [
                *(state.get("relationship_candidates", []) or []),
                *_relationship_candidates_from_daypart_memory(ctx),
            ]
        )
        if not allowed_relationship_actions:
            plan = _empty_relationship_plan("relationship_actions_not_allowed")
        elif not candidates:
            plan = _empty_relationship_plan("no relationship candidates")
        else:
            relationship_context = {
                "allowed_relationship_actions": allowed_relationship_actions,
                "relationship_candidates": candidates,
                "relationship_daypart_memory": _relationship_daypart_memory(ctx),
                "tendency_summary": getattr(ctx.activity_policy, "tendency_summary", ""),
                "follow_tendency_note": _tendency_action_note(ctx, "follow"),
                "unfollow_tendency_note": _tendency_action_note(ctx, "unfollow"),
            }
            user_prompt = "\n".join(
                [
                    "RelationshipActionPlanner role: decide whether this tick has one rare relationship decision.",
                    "Default to decision='none'. Do not force follow or unfollow.",
                    "Use only allowed_relationship_actions. Follow and unfollow cannot both happen in one run.",
                    "For follow, require an unfollowed character and at least two independent positive daypart signals.",
                    "For unfollow_watch, require a followed character and strong relationship reconsideration signal.",
                    "For unfollow, require a prior matching unfollow_watch in this same memory_session_key.",
                    "Community tendency notes are character judgment weights, not hard-coded bans.",
                    "For a selected relationship action, include a public-safe first-person motivation and coarse emotion only; never provide hidden deliberation or chain-of-thought.",
                    "Return JSON only.",
                    "",
                    f"relationship_context: {_format_json_for_prompt(relationship_context, max_chars=9000)}",
                ]
            )
            try:
                raw_plan = await _call_json(
                    ctx,
                    tracker,
                    node="RelationshipActionPlanner",
                    lane="relationship_action_planner",
                    system_prompt=_build_system_prompt(ctx),
                    user_prompt=user_prompt,
                    response_schema=_RelationshipActionPlan,
                    max_output_tokens=LANGGRAPH_RELATIONSHIP_OUTPUT_TOKENS,
                )
            except DirectLlmJsonError as exc:
                raw_plan = _empty_relationship_plan("planner_json_failed")
                raw_plan["planner_error"] = _planner_error_payload(
                    exc,
                    node="RelationshipActionPlanner",
                    lane="relationship_action_planner",
                )
            plan = _normalize_relationship_action_plan(
                raw_plan,
                ctx,
                candidates=candidates,
                allowed_relationship_actions=allowed_relationship_actions,
            )
        review = dict(plan.get("relationship_review", {}))
        review["allowed_relationship_actions"] = allowed_relationship_actions
        review["candidate_count"] = len(candidates)
        review["candidates"] = candidates[:6]
        try:
            _record_daypart_event(
                ctx,
                event_type=(
                    "unfollow_watch"
                    if review.get("decision") == "unfollow_watch"
                    else "relationship_review"
                ),
                summary=_clip(
                    review.get("evidence_summary")
                    or review.get("blocked_reason")
                    or review.get("decision")
                    or "relationship review",
                    2000,
                ),
                payload=review,
            )
        except Exception as exc:
            ctx.db.rollback()
            review["record_error"] = type(exc).__name__
        plan["relationship_review"] = review
        return {
            "relationship_action_plan": plan,
            "relationship_review": review,
            "completed_nodes": _merge_completed(state, "RelationshipActionPlanner"),
        }

    async def independent_topic_composer(
        state: _ResidentGraphState,
    ) -> dict[str, Any]:
        relationship_points = state.get("relationship_point_candidates", [])
        if not isinstance(relationship_points, list):
            relationship_points = []
        selected_feed_seed = state.get("selected_feed_seed")
        mandatory_context = _mandatory_post_context(
            ctx,
            relationship_points=relationship_points,
            selected_feed_seed=selected_feed_seed
            if isinstance(selected_feed_seed, dict)
            else None,
        )
        owner_cue = mandatory_context.get("owner_feed_cue")
        if isinstance(owner_cue, dict) and _clip(owner_cue.get("topic"), 800):
            composition = _normalize_independent_topic_composition(
                ctx,
                {"source": "owner_feed_cue", "brief": owner_cue.get("topic")},
                mandatory_context=mandatory_context,
            )
        elif not mandatory_context.get("post_required"):
            composition = _normalize_independent_topic_composition(
                ctx,
                {"source": "base_topic"},
                mandatory_context=mandatory_context,
            )
        else:
            user_prompt = "\n".join(
                [
                    "IndependentTopicComposer role: choose the root independent writing topic for this tick.",
                    "Priority is fixed: owner_feed_cue is handled before this LLM call; otherwise base independent topics and relationship points compete in one candidate pool.",
                    "A relationship point is a one-shot topic from someone replying to this character.",
                    "Base topics are reusable; do not mark them consumed.",
                    "selected_feed_seed is optional background only, never the topic. Use it only when it naturally fits the chosen topic.",
                    "If selected_feed_seed is used, mention_target_handle must be the seed author handle.",
                    "For thought, community_observation, and monologue, action_step_count must be 1.",
                    "For action, action_step_count can be 1 to 3. Never exceed 3.",
                    "Do not force explicit time words. Adjust the brief to the current time without requiring the post to say the time.",
                    "For the selected root-post topic, declare a short public-safe first-person motivation_kind/motivation_text and coarse emotion_label at this decision moment. This is not hidden reasoning. Use unspecified with null emotion detail when unclear.",
                    "",
                    f"mandatory_post_context: {_format_json_for_prompt(mandatory_context, max_chars=10000)}",
                    f"relationship_memory: {_format_json_for_prompt(state.get('relationship_memory', {}), max_chars=4000)}",
                ]
            )
            try:
                raw = await _call_json(
                    ctx,
                    tracker,
                    node="IndependentTopicComposer",
                    lane="independent_topic_composer",
                    system_prompt=_build_system_prompt(ctx),
                    user_prompt=user_prompt,
                    response_schema=_IndependentTopicComposition,
                    max_output_tokens=LANGGRAPH_PLANNER_OUTPUT_TOKENS,
                )
            except DirectLlmJsonError as exc:
                fallback_topic = None
                topics = mandatory_context.get("base_topic_candidates")
                if isinstance(topics, list) and topics:
                    fallback_topic = topics[0]
                raw = {
                    "source": "base_topic",
                    "topic_key": (
                        fallback_topic.get("key")
                        if isinstance(fallback_topic, dict)
                        else None
                    ),
                    "brief": (
                        fallback_topic.get("prompt")
                        if isinstance(fallback_topic, dict)
                        else "캐릭터의 평소 독립 주제에서 지금 쓸 만한 글감을 고른다."
                    ),
                    "writing_form": "thought",
                    "action_step_count": 1,
                    "use_post_seed": False,
                    "planner_error": _planner_error_payload(
                        exc,
                        node="IndependentTopicComposer",
                        lane="independent_topic_composer",
                    ),
                }
            composition = _normalize_independent_topic_composition(
                ctx, raw, mandatory_context=mandatory_context
            )
            if isinstance(raw.get("planner_error"), dict):
                composition["planner_error"] = raw["planner_error"]
        selected_relationship_point = None
        relationship_point_selection = None
        point_id = composition.get("relationship_point_id")
        for point in relationship_points:
            if isinstance(point, dict) and point.get("id") == point_id:
                selected_relationship_point = point
                break
        if isinstance(selected_relationship_point, dict):
            try:
                db_point = ctx.db.get(
                    _model_AgentRelationshipPoint,
                    int(selected_relationship_point["id"]),
                )
                if (
                    db_point is not None
                    and db_point.status == relationship_point_constants.RELATIONSHIP_POINT_PENDING
                ):
                    relationship_points.mark_relationship_point_selected(
                        ctx.db,
                        db_point,
                        run_id=ctx.run_id,
                        now=ctx.run_started_at.astimezone(UTC),
                    )
                    relationship_point_selection = {
                        "point_id": db_point.id,
                        "status": "selected",
                    }
            except Exception as exc:
                ctx.db.rollback()
                relationship_point_selection = {
                    "point_id": selected_relationship_point.get("id"),
                    "status": "selection_failed",
                    "failure_class": type(exc).__name__,
                }
        return {
            "mandatory_post_context": mandatory_context,
            "independent_topic_composition": composition,
            "selected_relationship_point": selected_relationship_point,
            "relationship_point_selection": relationship_point_selection,
            "completed_nodes": _merge_completed(state, "IndependentTopicComposer"),
        }

    async def independent_writing_planner(
        state: _ResidentGraphState,
    ) -> dict[str, Any]:
        mandatory_context = state.get("mandatory_post_context")
        if not isinstance(mandatory_context, dict):
            mandatory_context = _mandatory_post_context(
                ctx,
                relationship_points=state.get("relationship_point_candidates", [])
                if isinstance(state.get("relationship_point_candidates"), list)
                else [],
                selected_feed_seed=state.get("selected_feed_seed")
                if isinstance(state.get("selected_feed_seed"), dict)
                else None,
            )
        composition = state.get("independent_topic_composition")
        if not isinstance(composition, dict):
            composition = _normalize_independent_topic_composition(
                ctx, {"source": "base_topic"}, mandatory_context=mandatory_context
            )
        independent_post_roll = {
            "available": bool(mandatory_context.get("post_required")),
            "level": "mandatory",
            "tick_probability": 1.0
            if mandatory_context.get("post_required")
            else None,
            "roll": 0.0 if mandatory_context.get("post_required") else None,
            "passed": bool(mandatory_context.get("post_required")),
            "topics": mandatory_context.get("base_topic_candidates") or [],
            "topic_pool_size": len(_independent_post_topics(ctx)),
            "topic_prompt_count": len(
                mandatory_context.get("base_topic_candidates") or []
            ),
            "used_topic_keys_today": sorted(independent_topic_queries._today_independent_topic_keys(ctx)),
            "blocked_reason": mandatory_context.get("blocked_reason"),
            "mandatory": True,
        }
        writing = _writing_from_topic_composition(
            composition,
            selected_feed_seed=state.get("selected_feed_seed")
            if isinstance(state.get("selected_feed_seed"), dict)
            else None,
        )
        plan = {
            "selection_reason": composition.get("selection_reason")
            or "independent topic composed",
            "feed_actions": [],
            "inbox_actions": [],
            "writing": writing,
            "planner_called": False,
        }
        plan = _filter_action_plan(
            plan,
            ctx,
            feed_observation={"selected_posts": []},
            inbox_observation={"items": []},
            independent_post_roll=independent_post_roll,
            active_topic_arc=None,
        )
        plan = _restore_mandatory_root_writing(
            ctx,
            plan,
            mandatory_context=mandatory_context,
            composition=composition,
            selected_feed_seed=state.get("selected_feed_seed")
            if isinstance(state.get("selected_feed_seed"), dict)
            else None,
        )
        decision = _independent_post_decision_meta(
            independent_post_roll,
            independent_writing_plan=plan,
        )
        return {
            "independent_post_roll": independent_post_roll,
            "independent_writing_plan": plan,
            "independent_post_decision": decision,
            "completed_nodes": _merge_completed(state, "IndependentWritingPlanner"),
        }

        independent_post_roll = state.get("independent_post_roll")
        if not isinstance(independent_post_roll, dict):
            independent_post_roll = _build_independent_post_roll(ctx)
        raw_active_topic_arc = state.get("active_topic_arc")
        active_topic_arc = _coerce_topic_arc_payload(raw_active_topic_arc)
        if (
            active_topic_arc
            and isinstance(raw_active_topic_arc, dict)
            and isinstance(raw_active_topic_arc.get("carryover_time_context"), dict)
        ):
            active_topic_arc["carryover_time_context"] = raw_active_topic_arc[
                "carryover_time_context"
            ]
        if active_topic_arc:
            writing = _writing_from_topic_arc(
                active_topic_arc,
                current_date=_current_kst_date(ctx),
            )
            if writing is None:
                plan = _empty_action_plan("active_topic_arc_invalid")
                plan["planner_called"] = False
                plan["writing"]["skip_reason"] = "active_topic_arc_invalid"
            elif "post" not in set(ctx.activity_policy.allowed_actions):
                plan = _empty_action_plan("post_not_allowed")
                plan["planner_called"] = False
                plan["writing"]["skip_reason"] = "post_not_allowed"
            else:
                plan = {
                    "selection_reason": "active topic arc continuation",
                    "feed_actions": [],
                    "inbox_actions": [],
                    "writing": writing,
                    "planner_called": False,
                }
                plan = _filter_action_plan(
                    plan,
                    ctx,
                    feed_observation={"selected_posts": []},
                    inbox_observation={"items": []},
                    independent_post_roll=independent_post_roll,
                    active_topic_arc=active_topic_arc,
                )
            decision = _independent_post_decision_meta(
                independent_post_roll,
                independent_writing_plan=plan,
            )
            return {
                "independent_post_roll": independent_post_roll,
                "independent_writing_plan": plan,
                "independent_post_decision": decision,
                "completed_nodes": _merge_completed(
                    state, "IndependentWritingPlanner"
                ),
            }
        skip_reason = _independent_writing_skip_reason(independent_post_roll)
        if skip_reason is not None:
            plan = _empty_action_plan(skip_reason)
            plan["planner_called"] = False
            plan["writing"]["skip_reason"] = skip_reason
            decision = _independent_post_decision_meta(
                independent_post_roll,
                independent_writing_plan=plan,
            )
            return {
                "independent_post_roll": independent_post_roll,
                "independent_writing_plan": plan,
                "independent_post_decision": decision,
                "completed_nodes": _merge_completed(
                    state, "IndependentWritingPlanner"
                ),
            }
        independent_post_context = _independent_post_context_for_prompt(
            ctx,
            feed_observation=state.get("feed_observation", {}),
            independent_post_roll=independent_post_roll,
            active_topic_arc=active_topic_arc,
        )
        user_prompt = "\n".join(
            [
                "IndependentWritingPlanner role: decide only the independent standalone writing axis.",
                "Social feed and inbox actions are planned elsewhere. Do not cancel, replace, or consider them mutually exclusive.",
                "The backend roll has already passed for this node.",
                "If the character should write independently now, set writing.mode='independent', choose one topic_key from independent_post_context.topics, and write a brief.",
                "When writing.mode='independent', include writing.topic_arc.",
                "topic_arc steps must use setup, optional development steps, then conclusion; total steps must be 2 to 5.",
                "Use at most three development steps.",
                "Build topic_arc from the selected topic and continuation intent, not from handoff memory alone.",
                "Use independent_post_context.yesterday_handoff_context as background memory with coverage status.",
                "Yesterday handoff context does not override the backend roll, allowed actions, active topic_arc, or selected topic.",
                "Write topic_arc step briefs as adaptable continuation intent, not a fixed script that assumes future ticks happen at a specific clock time or place.",
                "Avoid relative time claims in step briefs that would force a future post to contradict the actual current KST when it is written.",
                "If the character should still stay quiet despite the passed roll, set writing.mode='none'.",
                "",
                f"daypart_context: {_format_json_for_prompt(state.get('daypart_context', {}), max_chars=2000)}",
                f"relationship_memory: {_format_json_for_prompt(state.get('relationship_memory', {}), max_chars=5000)}",
                f"independent_post_context: {_format_json_for_prompt(independent_post_context, max_chars=6000)}",
            ]
        )
        try:
            plan = await _call_json(
                ctx,
                tracker,
                node="IndependentWritingPlanner",
                lane="independent_writing_planner",
                system_prompt=_build_system_prompt(ctx),
                user_prompt=user_prompt,
                response_schema=_IndependentWritingPlan,
                max_output_tokens=LANGGRAPH_PLANNER_OUTPUT_TOKENS,
            )
        except DirectLlmJsonError as exc:
            plan = _planner_json_failed_plan(
                exc,
                node="IndependentWritingPlanner",
                lane="independent_writing_planner",
            )
        plan = _normalize_independent_writing_plan(
            plan,
            ctx,
            independent_post_roll=independent_post_roll,
            active_topic_arc=active_topic_arc,
        )
        plan["planner_called"] = True
        decision = _independent_post_decision_meta(
            independent_post_roll,
            independent_writing_plan=plan,
        )
        return {
            "independent_post_roll": independent_post_roll,
            "independent_writing_plan": plan,
            "independent_post_decision": decision,
            "completed_nodes": _merge_completed(state, "IndependentWritingPlanner"),
        }

    async def bundle_composer(state: _ResidentGraphState) -> dict[str, Any]:
        action_plan = _compose_action_bundle(
            feed_action_plan=state.get("feed_action_plan", {}),
            inbox_action_plan=state.get("inbox_action_plan", {}),
            relationship_action_plan=state.get("relationship_action_plan", {}),
            independent_writing_plan=state.get("independent_writing_plan", {}),
            owner_feed_cue=None if state.get("inbox_lane_only") else ctx.feed_cue,
        )
        independent_post_roll = state.get("independent_post_roll")
        if not isinstance(independent_post_roll, dict):
            independent_post_roll = _build_independent_post_roll(ctx)
        action_plan = _filter_action_plan(
            action_plan,
            ctx,
            feed_observation=state.get("feed_observation", {}),
            inbox_observation=state.get("inbox_observation", {}),
            independent_post_roll=independent_post_roll,
            active_topic_arc=state.get("active_topic_arc"),
        )
        updated_state = dict(state)
        updated_state["action_plan"] = action_plan
        planner_results = _planner_results_summary(updated_state)
        decision = _independent_post_decision_meta(
            independent_post_roll,
            independent_writing_plan=state.get("independent_writing_plan", {}),
            action_plan=action_plan,
        )
        return {
            "action_plan": action_plan,
            "planner_results": planner_results,
            "independent_post_decision": decision,
            "completed_nodes": _merge_completed(state, "BundleComposer"),
        }

    async def action_budget_trimmer(state: _ResidentGraphState) -> dict[str, Any]:
        action_plan, trim_summary = _trim_action_plan_to_budget(
            ctx, state.get("action_plan", {})
        )
        updated_state = dict(state)
        updated_state["action_plan"] = action_plan
        return {
            "action_plan": action_plan,
            "planner_results": _planner_results_summary(updated_state),
            "action_budget_trim_summary": trim_summary,
            "completed_nodes": _merge_completed(state, "ActionBudgetTrimmer"),
        }

    async def lore_query_rewriter(state: _ResidentGraphState) -> dict[str, Any]:
        lore_query_result = await _build_lore_query_result(ctx, tracker, state)
        return {
            "lore_query_result": lore_query_result,
            "completed_nodes": _merge_completed(state, "LoreQueryRewriter"),
        }

    async def write_task_composer(state: _ResidentGraphState) -> dict[str, Any]:
        action_plan = state.get("action_plan", {})
        write_tasks = _compile_write_tasks(
            ctx,
            action_plan,
            lore_query_result=state.get("lore_query_result"),
        )
        plan_writing = action_plan.get("writing") if isinstance(action_plan, dict) else None
        writing = dict(plan_writing if isinstance(plan_writing, dict) else state.get("writing", {}))
        write_summary = _write_task_summary(write_tasks, writing)
        result = {
            "write_tasks": write_tasks,
            "write_task_summary": write_summary,
            "writing": writing,
            "completed_nodes": _merge_completed(state, "WriteTaskComposer"),
        }
        if (
            _mandatory_post_required(state.get("mandatory_post_context"))
            and not isinstance(write_tasks.get("post_task"), dict)
        ):
            missing_reason = _mandatory_post_missing_reason(
                writing,
                state.get("action_budget_trim_summary"),
            )
            write_summary["mandatory_post_required"] = True
            write_summary["mandatory_post_missing_reason"] = missing_reason
            if missing_reason not in _MANDATORY_POST_ALLOWED_SKIP_REASONS:
                result["failure_class"] = "mandatory_post_task_missing"
        return result

    async def reply_writer(state: _ResidentGraphState) -> dict[str, Any]:
        write_tasks = state.get("write_tasks", {})
        reply_tasks = (
            write_tasks.get("reply_tasks", []) if isinstance(write_tasks, dict) else []
        )
        writing, writer_result = await _call_reply_writer(
            ctx, tracker, state, reply_tasks
        )
        writer_batches = list(writer_result.pop("batches", []))
        writer_results = dict(state.get("writer_results", {}))
        writer_results["reply_writer"] = writer_result
        writer_results["reply_writer_batches"] = writer_batches
        return {
            "writing": writing,
            "writer_results": writer_results,
            "write_task_summary": _write_task_summary(write_tasks, writing),
            "completed_nodes": _merge_completed(state, "ReplyWriter"),
        }

    async def post_writer_planner(state: _ResidentGraphState) -> dict[str, Any]:
        write_tasks = state.get("write_tasks", {})
        post_task = write_tasks.get("post_task") if isinstance(write_tasks, dict) else None
        if not isinstance(post_task, dict):
            return {"completed_nodes": _merge_completed(state, "PostWriterPlanner")}
        plan, writer_result = await _call_post_writer_planner(
            ctx, tracker, state, post_task
        )
        writer_results = dict(state.get("writer_results", {}))
        writer_results["post_writer_plan"] = writer_result
        return {
            "post_writer_plan": plan,
            "writer_results": writer_results,
            "completed_nodes": _merge_completed(state, "PostWriterPlanner"),
        }

    async def post_writer(state: _ResidentGraphState) -> dict[str, Any]:
        write_tasks = state.get("write_tasks", {})
        post_task = write_tasks.get("post_task") if isinstance(write_tasks, dict) else None
        if not isinstance(post_task, dict):
            return {"completed_nodes": _merge_completed(state, "PostWriter")}
        writing, writer_result = await _call_post_writer(ctx, tracker, state, post_task)
        writer_results = dict(state.get("writer_results", {}))
        writer_results["post_writer"] = writer_result
        return {
            "writing": writing,
            "writer_results": writer_results,
            "write_task_summary": _write_task_summary(write_tasks, writing),
            "completed_nodes": _merge_completed(state, "PostWriter"),
        }

    async def reply_writer_repair(state: _ResidentGraphState) -> dict[str, Any]:
        write_tasks = state.get("write_tasks", {})
        reply_tasks = (
            write_tasks.get("reply_tasks", []) if isinstance(write_tasks, dict) else []
        )
        missing = set(_missing_reply_task_ids(state.get("writing", {}), reply_tasks))
        repair_tasks = [
            task for task in reply_tasks if str(task.get("task_id") or "") in missing
        ]
        writing, writer_result = await _call_reply_writer(
            ctx,
            tracker,
            state,
            reply_tasks,
            repair=True,
            prompt_reply_tasks=repair_tasks,
        )
        writer_batches = list(writer_result.pop("batches", []))
        writer_results = dict(state.get("writer_results", {}))
        writer_results["reply_writer_repair"] = writer_result
        writer_results["reply_writer_repair_batches"] = writer_batches
        return {
            "writing": writing,
            "writer_results": writer_results,
            "write_task_summary": _write_task_summary(write_tasks, writing),
            "completed_nodes": _merge_completed(state, "ReplyWriterRepair"),
        }

    async def post_writer_repair(state: _ResidentGraphState) -> dict[str, Any]:
        write_tasks = state.get("write_tasks", {})
        post_task = write_tasks.get("post_task") if isinstance(write_tasks, dict) else None
        if not isinstance(post_task, dict):
            return {"completed_nodes": _merge_completed(state, "PostWriterRepair")}
        writing, writer_result = await _call_post_writer(
            ctx, tracker, state, post_task, repair=True
        )
        writer_results = dict(state.get("writer_results", {}))
        writer_results["post_writer_repair"] = writer_result
        return {
            "writing": writing,
            "writer_results": writer_results,
            "write_task_summary": _write_task_summary(write_tasks, writing),
            "completed_nodes": _merge_completed(state, "PostWriterRepair"),
        }

    async def community_executor(state: _ResidentGraphState) -> dict[str, Any]:
        plan = state.get("action_plan", {})
        writing = state.get("writing", {})
        results: list[dict[str, Any]] = []
        topic_arc_result: dict[str, Any] | None = None
        used_reply_bodies: dict[str, str] = {}
        for scope, key in (
            ("feed", "feed_actions"),
            ("inbox", "inbox_actions"),
            ("relationship", "relationship_actions"),
        ):
            actions = plan.get(key, []) if isinstance(plan, dict) else []
            for index, action in enumerate(actions):
                if isinstance(action, dict):
                    result = _execute_planned_action(
                        ctx,
                        action=action,
                        scope=scope,
                        index=index,
                        writing=writing,
                        used_reply_bodies=used_reply_bodies,
                    )
                    results.append(result)
        writing_plan = plan.get("writing") if isinstance(plan, dict) else None
        if isinstance(writing_plan, dict) and writing_plan.get("mode") != "none":
            prepared_image = await _prepare_writing_image(
                ctx,
                tracker,
                writing_plan=writing_plan,
                writing=writing,
            )
            writing_result = _execute_writing_plan(
                ctx,
                writing_plan,
                writing,
                prepared_image=prepared_image,
            )
            if isinstance(writing_result.get("topic_arc_result"), dict):
                topic_arc_result = writing_result["topic_arc_result"]
            results.append(writing_result)
        publish_result = {
            "actions": results,
            "public_action_count": sum(
                1 for item in results if item.get("status") in {"succeeded", "reused"}
            ),
        }
        return {
            "publish_result": publish_result,
            "topic_arc_result": topic_arc_result or {},
            "completed_nodes": _merge_completed(state, "CommunityExecutor"),
        }

    async def relationship_point_recorder(state: _ResidentGraphState) -> dict[str, Any]:
        result = _record_relationship_points_after_publish(ctx, state)
        return {
            "relationship_point_result": result,
            "completed_nodes": _merge_completed(state, "RelationshipPointRecorder"),
        }

    async def state_recorder(state: _ResidentGraphState) -> dict[str, Any]:
        return await _run_state_recorder(ctx, tracker, state)

    workflow.add_node("Supervisor", supervisor)
    workflow.add_node("DaypartContextLoader", daypart_context_loader)
    workflow.add_node("FeedObserver", feed_observer)
    workflow.add_node("FeedSeedSelector", feed_seed_selector)
    workflow.add_node("InboxObserver", inbox_observer)
    workflow.add_node("RelationshipPointLoader", relationship_point_loader)
    workflow.add_node("RelationshipMemory", relationship_memory)
    workflow.add_node("FeedActionPlanner", feed_action_planner)
    workflow.add_node("InboxActionPlanner", inbox_action_planner)
    workflow.add_node("RelationshipActionPlanner", relationship_action_planner)
    workflow.add_node("IndependentTopicComposer", independent_topic_composer)
    workflow.add_node("IndependentWritingPlanner", independent_writing_planner)
    workflow.add_node("BundleComposer", bundle_composer)
    workflow.add_node("ActionBudgetTrimmer", action_budget_trimmer)
    workflow.add_node("LoreQueryRewriter", lore_query_rewriter)
    workflow.add_node("WriteTaskComposer", write_task_composer)
    workflow.add_node("ReplyWriter", reply_writer)
    workflow.add_node("PostWriterPlanner", post_writer_planner)
    workflow.add_node("PostWriter", post_writer)
    workflow.add_node("ReplyWriterRepair", reply_writer_repair)
    workflow.add_node("PostWriterRepair", post_writer_repair)
    workflow.add_node("CommunityExecutor", community_executor)
    workflow.add_node("RelationshipPointRecorder", relationship_point_recorder)
    workflow.add_node("StateRecorder", state_recorder)
    workflow.add_edge(START, "Supervisor")
    workflow.add_conditional_edges(
        "Supervisor",
        _supervisor_route,
        {
            "DaypartContextLoader": "DaypartContextLoader",
            "FeedObserver": "FeedObserver",
            "FeedSeedSelector": "FeedSeedSelector",
            "InboxObserver": "InboxObserver",
            "RelationshipPointLoader": "RelationshipPointLoader",
            "RelationshipMemory": "RelationshipMemory",
            "FeedActionPlanner": "FeedActionPlanner",
            "InboxActionPlanner": "InboxActionPlanner",
            "RelationshipActionPlanner": "RelationshipActionPlanner",
            "IndependentTopicComposer": "IndependentTopicComposer",
            "IndependentWritingPlanner": "IndependentWritingPlanner",
            "BundleComposer": "BundleComposer",
            "ActionBudgetTrimmer": "ActionBudgetTrimmer",
            "LoreQueryRewriter": "LoreQueryRewriter",
            "WriteTaskComposer": "WriteTaskComposer",
            "ReplyWriter": "ReplyWriter",
            "PostWriterPlanner": "PostWriterPlanner",
            "PostWriter": "PostWriter",
            "ReplyWriterRepair": "ReplyWriterRepair",
            "PostWriterRepair": "PostWriterRepair",
            "CommunityExecutor": "CommunityExecutor",
            "RelationshipPointRecorder": "RelationshipPointRecorder",
            "StateRecorder": "StateRecorder",
            END: END,
        },
    )
    for node in (
        "DaypartContextLoader",
        "FeedObserver",
        "FeedSeedSelector",
        "InboxObserver",
        "RelationshipPointLoader",
        "RelationshipMemory",
        "FeedActionPlanner",
        "InboxActionPlanner",
        "RelationshipActionPlanner",
        "IndependentTopicComposer",
        "IndependentWritingPlanner",
        "BundleComposer",
        "ActionBudgetTrimmer",
        "LoreQueryRewriter",
        "WriteTaskComposer",
        "ReplyWriter",
        "PostWriterPlanner",
        "PostWriter",
        "ReplyWriterRepair",
        "PostWriterRepair",
        "CommunityExecutor",
        "RelationshipPointRecorder",
        "StateRecorder",
    ):
        workflow.add_edge(node, "Supervisor")
    return workflow.compile()


def _reserve_public_action(
    ctx: LangGraphResidentContext,
    *,
    scope: str,
    action_type: str,
    target_post_id: str | None = None,
    target_profile_type: str | None = None,
    target_profile_id: str | None = None,
    brief_hash: str | None = None,
) -> tuple[_model_AgentPublicActionExecution | None, dict[str, Any] | None]:
    target_id = target_post_id or (
        f"{target_profile_type}:{target_profile_id}" if target_profile_id else None
    )
    signature = _action_signature(
        run_id=ctx.run_id,
        scope=scope,
        action_type=action_type,
        target_id=target_id,
        brief_hash=brief_hash,
    )
    existing = public_action_queries.get_public_action_execution_by_signature(
        ctx.db, signature
    )
    if existing is not None:
        if existing.status == "succeeded":
            return None, {
                "status": "reused",
                "action_type": action_type,
                "signature": signature,
                "result": existing.result or {},
            }
        return None, {
            "status": "blocked",
            "action_type": action_type,
            "signature": signature,
            "failure_class": existing.failure_class or "signature_not_retriable",
        }
    try:
        return public_action_executions.create_public_action_execution(
            ctx.db,
            run_id=ctx.run_id,
            character_id=ctx.character.id,
            signature=signature,
            scope=scope,
            action_type=action_type,
            target_post_id=target_post_id,
            target_profile_type=target_profile_type,
            target_profile_id=target_profile_id,
            brief_hash=brief_hash,
        ), None
    except IntegrityError:
        ctx.db.rollback()
        existing = public_action_queries.get_public_action_execution_by_signature(
            ctx.db, signature
        )
        return None, {
            "status": "blocked",
            "action_type": action_type,
            "signature": signature,
            "failure_class": getattr(existing, "failure_class", None)
            or "signature_race",
        }


def _finish_execution(
    ctx: LangGraphResidentContext,
    execution: _model_AgentPublicActionExecution,
    *,
    status: str,
    result: dict[str, Any] | None = None,
    failure_class: str | None = None,
) -> dict[str, Any]:
    public_action_executions.mark_public_action_execution_finished(
        ctx.db,
        execution,
        status=status,
        result=result,
        failure_class=failure_class,
    )
    return {
        "status": status,
        "action_type": execution.action_type,
        "signature": execution.signature,
        "result": result or {},
        "failure_class": failure_class,
    }


def _declared_action_subjective_context(
    _action_type: str,
    plan: dict[str, Any],
) -> ActionSubjectiveContextV1 | None:
    """Convert only decision-time public fields into the persisted contract."""

    motivation_text = _clip(plan.get("motivation_text"), 280)
    raw_kind = str(plan.get("motivation_kind") or "").strip()
    if not motivation_text or not raw_kind:
        return None
    try:
        motivation_kind = ActionMotivationKind(raw_kind)
    except ValueError:
        return None
    raw_emotion = str(plan.get("emotion_label") or "unspecified").strip()
    try:
        emotion_label = ActionEmotionLabel(raw_emotion)
    except ValueError:
        emotion_label = ActionEmotionLabel.UNSPECIFIED
    emotion_text = _clip(plan.get("emotion_text"), 280) or None
    raw_intensity = plan.get("emotion_intensity")
    emotion_intensity = (
        raw_intensity
        if isinstance(raw_intensity, int) and not isinstance(raw_intensity, bool)
        else None
    )
    if emotion_label is ActionEmotionLabel.UNSPECIFIED:
        emotion_text = None
        emotion_intensity = None
    return ActionSubjectiveContextV1(
        motivation_kind=motivation_kind,
        motivation_text=motivation_text,
        emotion_label=emotion_label,
        emotion_text=emotion_text,
        emotion_intensity=emotion_intensity,
    )


def _prompt_injection_output_block(
    fields: dict[str, str],
) -> tuple[str, prompt_safety.PromptSafetyResult] | None:
    for field, text in fields.items():
        result = prompt_safety.contains_prompt_injection_output(text)
        if not result.allowed:
            return field, result
    return None


def _reply_proposal_response(
    writing: dict[str, Any], *, scope: str, index: int, post_id: str
) -> tuple[langgraph_social_apply.ProposalResponseInput | None, str | None]:
    task_id = _reply_task_id(scope=scope, index=index, post_id=post_id)
    task_result = _reply_task_results_by_id(writing).get(task_id)
    if not isinstance(task_result, dict):
        return None, None
    payload = task_result.get("proposal_response")
    if not isinstance(payload, dict):
        return None, None
    proposal_id = str(payload.get("proposal_id") or "").strip()
    decision = str(payload.get("decision") or "").strip()
    if not proposal_id or decision not in {"accept", "reject", "counter"}:
        return None, "proposal_response_invalid"
    raw_target_date = payload.get("counter_target_date")
    target_date = raw_target_date if isinstance(raw_target_date, date) else None
    if target_date is None and isinstance(raw_target_date, str) and raw_target_date:
        try:
            target_date = date.fromisoformat(raw_target_date)
        except ValueError:
            return None, "proposal_counter_date_invalid"
    return (
        langgraph_social_apply.ProposalResponseInput(
            proposal_id=proposal_id,
            decision=decision,
            counter_activity_seed=(
                str(payload.get("counter_activity_seed") or "").strip() or None
            ),
            counter_place_key=(
                str(payload.get("counter_place_key") or "").strip() or None
            ),
            counter_target_daypart=(
                str(payload.get("counter_target_daypart") or "").strip() or None
            ),
            counter_date_policy=(
                str(payload.get("counter_date_policy") or "").strip() or None
            ),
            counter_target_date=target_date,
        ),
        None,
    )


def _execute_planned_action(
    ctx: LangGraphResidentContext,
    *,
    action: dict[str, Any],
    scope: str,
    index: int,
    writing: dict[str, Any],
    used_reply_bodies: dict[str, str] | None = None,
) -> dict[str, Any]:
    action_type = str(action.get("action_type") or "")
    post_id = str(action.get("post_id") or "").strip() or None
    notification_id = action.get("notification_id")
    target_type = str(action.get("target_type") or "").strip() or None
    target_id = str(action.get("target_id") or "").strip() or None
    activity_policy = getattr(ctx, "activity_policy", None)
    allowed_actions = set(getattr(activity_policy, "allowed_actions", _PUBLIC_ACTIONS))
    if _action_name_for_policy(action_type) not in allowed_actions:
        return {
            "status": "skipped",
            "action_type": action_type,
            "failure_class": "action_not_allowed",
        }
    if action_type in {"like", "repost", "reply"} and post_id is None:
        return {
            "status": "skipped",
            "action_type": action_type,
            "failure_class": "missing_post_id",
        }
    if action_type == "follow" and target_id is None and post_id is not None:
        post = social_posts_repository.get_post(ctx.db, post_id)
        if post is not None and post.author_character_id:
            target_type = "character"
            target_id = post.author_character_id
    if action_type in {"follow", "unfollow"} and (target_type != "character" or not target_id):
        return {
            "status": "skipped",
            "action_type": action_type,
            "failure_class": "missing_follow_target",
        }
    body = ""
    writer_validation: dict[str, Any] | None = None
    proposal_response_input = None
    if action_type == "reply":
        if _character_already_replied_to_target(
            ctx.db, character_id=ctx.character.id, post_id=post_id
        ):
            return _skipped_public_action(
                action_type=action_type,
                target_post_id=post_id,
                failure_class=_REPLY_TARGET_ALREADY_ANSWERED,
                message="character already replied to this target post",
            )
        body, failure_class, writer_validation = _reply_body(
            writing,
            scope=scope,
            index=index,
            post_id=post_id or "",
        )
        if failure_class:
            return _skipped_public_action(
                action_type=action_type,
                target_post_id=post_id,
                failure_class=failure_class,
                writer_validation=writer_validation,
            )
        proposal_response_input, proposal_failure = _reply_proposal_response(
            writing,
            scope=scope,
            index=index,
            post_id=post_id or "",
        )
        if proposal_failure:
            return _skipped_public_action(
                action_type=action_type,
                target_post_id=post_id,
                failure_class=proposal_failure,
                writer_validation=writer_validation,
            )
        normalized_body = _normalize_reply_body_for_duplicate(body or "")
        if normalized_body:
            seen_reply_bodies = used_reply_bodies if used_reply_bodies is not None else {}
            previous_post_id = seen_reply_bodies.get(normalized_body)
            if previous_post_id is not None and previous_post_id != post_id:
                return _skipped_public_action(
                    action_type=action_type,
                    target_post_id=post_id,
                    failure_class="duplicate_reply_body_in_run",
                    writer_validation=writer_validation,
                )
            seen_reply_bodies[normalized_body] = post_id or ""
        blocked = _prompt_injection_output_block({"body": body})
        if blocked is not None:
            blocked_field, blocked_result = blocked
            return _skipped_public_action(
                action_type=action_type,
                target_post_id=post_id,
                failure_class="prompt_injection_output_blocked",
                writer_validation=writer_validation,
                blocked_field=blocked_field,
                blocked_category=blocked_result.category,
                message="writer output was blocked before publish",
            )
    brief_hash = _brief_hash(body or action.get("brief"), notification_id)
    execution, reused = _reserve_public_action(
        ctx,
        scope=scope,
        action_type=action_type,
        target_post_id=post_id,
        target_profile_type=target_type,
        target_profile_id=target_id,
        brief_hash=brief_hash,
    )
    if reused is not None:
        if writer_validation is not None:
            reused["writer_validation"] = writer_validation
        return reused
    assert execution is not None
    try:
        occurred_at = datetime.now(UTC)
        prepared_proposal_response = None
        if proposal_response_input is not None:
            prepared_proposal_response = (
                langgraph_social_apply.prepare_proposal_response(
                    ctx.db,
                    character_id=ctx.character.id,
                    response=proposal_response_input,
                    now=occurred_at,
                )
            )
        with unit_of_work.deferred_commits():
            if action_type == "reply":
                if not body:
                    raise ValueError("reply body missing")
                result = social_agent_tools_runtime.agent_tool_actions.reply_agent_tool_post(
                    ctx.db,
                    ctx.session_key,
                    post_id or "",
                    social_schemas.TimelineReplyCreate(
                        body=body, author_character_id=ctx.character.id
                    ),
                )
                payload = {"post_id": result.id, "reply_to_post_id": post_id}
            elif action_type == "like":
                result = social_agent_tools_runtime.agent_tool_actions.like_agent_tool_post(
                    ctx.db,
                    ctx.session_key,
                    post_id or "",
                    social_schemas.PostLikeCreate(character_id=ctx.character.id),
                )
                payload = {"post_id": result.id}
            elif action_type == "repost":
                result = social_agent_tools_runtime.agent_tool_actions.repost_agent_tool_post(
                    ctx.db,
                    ctx.session_key,
                    post_id or "",
                    social_schemas.PostLikeCreate(character_id=ctx.character.id),
                )
                payload = {"post_id": result.id}
            elif action_type == "follow":
                result = social_agent_tools_runtime.agent_tool_actions.follow_agent_tool_profile(
                    ctx.db,
                    ctx.session_key,
                    social_schemas.FollowCreate(
                        target_type="character",
                        target_id=target_id or "",
                        follower_character_id=ctx.character.id,
                    ),
                )
                payload = {
                    "target_type": result.target.profile_type,
                    "target_id": result.target.id,
                }
            elif action_type == "unfollow":
                social_agent_tools_runtime.agent_tool_actions.unfollow_agent_tool_profile(
                    ctx.db,
                    ctx.session_key,
                    social_schemas.FollowCreate(
                        target_type="character",
                        target_id=target_id or "",
                        follower_character_id=ctx.character.id,
                    ),
                )
                payload = {"target_type": "character", "target_id": target_id}
            else:
                raise ValueError(f"unsupported action_type={action_type}")
            social_result = langgraph_social_apply.apply_successful_public_action(
                ctx.db,
                actor_character_id=ctx.character.id,
                action_type=action_type,
                target_post_id=post_id,
                target_character_id=target_id,
                action_result=payload,
                execution=execution,
                occurred_at=occurred_at,
                notification_id=(
                    int(notification_id) if notification_id is not None else None
                ),
                source_text=body or None,
                proposal_response=prepared_proposal_response,
            )
            action_result = _finish_execution(
                ctx, execution, status="succeeded", result=payload
            )
            record_declared_subjective_context(
                ctx.db,
                execution=execution,
                event=social_result.event,
                source_post_id=(
                    str(payload.get("post_id"))
                    if payload.get("post_id") is not None
                    else post_id
                ),
                context=_declared_action_subjective_context(action_type, action),
                captured_at=occurred_at,
            )
            ctx.db.commit()
        action_result["social_event_id"] = social_result.event.id
        if writer_validation is not None:
            action_result["writer_validation"] = writer_validation
        return action_result
    except Exception as exc:
        ctx.db.rollback()
        failure_class = type(exc).__name__
        logger.warning(
            "langgraph_public_action_failed run_id=%s character_id=%s action=%s "
            "failure_class=%s error=%s",
            ctx.run_id,
            ctx.character.id,
            action_type,
            failure_class,
            redact_secret_text(str(exc))[:500],
        )
        action_result = _finish_execution(
            ctx,
            execution,
            status="failed",
            result=None,
            failure_class=failure_class,
        )
        if writer_validation is not None:
            action_result["writer_validation"] = writer_validation
        return action_result


async def _prepare_writing_image(
    ctx: LangGraphResidentContext,
    tracker: RunLlmTracker,
    *,
    writing_plan: dict[str, Any],
    writing: dict[str, Any],
) -> post_image_generation.PreparedPostImage | None:
    title = str(writing.get("post_title") or "").strip() if isinstance(writing, dict) else ""
    body = str(writing.get("post_body") or "").strip() if isinstance(writing, dict) else ""
    if not title or not body:
        return None
    return await post_image_generation.prepare_post_image(
        db=ctx.db,
        character=ctx.character,
        credential=ctx.credential,
        run_id=ctx.run_id,
        tracker=tracker,
        writing_mode=str(writing_plan.get("mode") or ""),
        post_title=title,
        post_body=body,
        writing_plan=writing_plan,
        current_time_text=_format_current_time_reference(ctx.run_started_at),
        run_started_at=ctx.run_started_at,
        on_rate_limit_wait=ctx.on_rate_limit_wait,
    )


def _execute_writing_plan(
    ctx: LangGraphResidentContext,
    writing_plan: dict[str, Any],
    writing: dict[str, Any],
    *,
    prepared_image: post_image_generation.PreparedPostImage | None = None,
) -> dict[str, Any]:
    title = str(writing.get("post_title") or "").strip() if isinstance(writing, dict) else ""
    body = str(writing.get("post_body") or "").strip() if isinstance(writing, dict) else ""
    post_task_result = writing.get("post_task_result") if isinstance(writing, dict) else None
    writer_validation = (
        {
            "task_id": post_task_result.get("task_id"),
            "returned_task_id": post_task_result.get("returned_task_id"),
            "writer_node": post_task_result.get("writer_node"),
            "repair_attempted": bool(post_task_result.get("repair_attempted")),
            "repair_succeeded": bool(post_task_result.get("repair_succeeded")),
            "task_id_matched": bool(post_task_result.get("task_id_matched")),
        }
        if isinstance(post_task_result, dict)
        else None
    )
    validation = (
        writing.get("persona_writer_validation") if isinstance(writing, dict) else None
    )
    if not isinstance(validation, dict):
        validation = _persona_writer_validation_meta(
            {"writing": writing_plan},
            writing if isinstance(writing, dict) else {},
            repair_attempted=False,
            repair_succeeded=False,
        )
    if not title or not body:
        return {
            "status": "skipped",
            "action_type": "post",
            "failure_class": _PERSONA_WRITER_MISSING_POST_TEXT,
            "required_post_text": bool(validation.get("required_post_text")),
            "has_post_title": bool(validation.get("has_post_title")),
            "has_post_body": bool(validation.get("has_post_body")),
            "repair_attempted": bool(validation.get("repair_attempted")),
            "repair_succeeded": bool(validation.get("repair_succeeded")),
            "writer_validation": writer_validation,
        }
    if _post_body_missing_required_mention(writing_plan, body):
        return {
            "status": "skipped",
            "action_type": "post",
            "failure_class": "post_writer_missing_required_mention",
            "required_mention": _required_handle_text(writing_plan),
            "persona_writer_validation": validation,
            "writer_validation": writer_validation,
        }
    if _post_body_copies_source(writing_plan, body):
        return {
            "status": "skipped",
            "action_type": "post",
            "failure_class": "post_writer_source_copy_blocked",
            "persona_writer_validation": validation,
            "writer_validation": writer_validation,
        }
    if _post_body_has_forbidden_structure_label(body):
        return {
            "status": "skipped",
            "action_type": "post",
            "failure_class": "post_writer_structure_label_blocked",
            "persona_writer_validation": validation,
            "writer_validation": writer_validation,
        }
    blocked = _prompt_injection_output_block({"title": title, "body": body})
    if blocked is not None:
        blocked_field, blocked_result = blocked
        if prepared_image is not None:
            image_attachment.release_prepared_post_image_quota(
                db=ctx.db,
                prepared=prepared_image,
                status="failed",
            )
        return {
            "status": "skipped",
            "action_type": "post",
            "failure_class": "prompt_injection_output_blocked",
            "blocked_field": blocked_field,
            "blocked_category": blocked_result.category,
            "persona_writer_validation": validation,
            "writer_validation": writer_validation,
            "message": "writer output was blocked before publish",
        }
    source_post_id = str(writing_plan.get("source_post_id") or "").strip() or None
    topic_key = str(writing_plan.get("topic_key") or "").strip() or None
    feed_cue_id = writing_plan.get("feed_cue_id")
    topic_basis = writing_plan.get("brief")
    if _coerce_topic_arc_payload(writing_plan.get("topic_arc")):
        topic_basis = " ".join(part for part in (title, body) if part)
    topic_signature = _clip(topic_basis, 300) or None
    lore_chunk_ids = _clean_lore_chunk_ids(
        writing.get("lore_chunk_ids") if isinstance(writing, dict) else None
    )
    retrieval_mode = _clip(writing.get("retrieval_mode"), 80) or None
    lore_query_mode = _clip(writing.get("lore_query_mode"), 80) or None
    brief_hash = _brief_hash(title, body, source_post_id)
    execution, reused = _reserve_public_action(
        ctx,
        scope="writing",
        action_type="post",
        target_post_id=source_post_id,
        brief_hash=brief_hash,
    )
    if reused is not None:
        reused["persona_writer_validation"] = validation
        if writer_validation is not None:
            reused["writer_validation"] = writer_validation
        return reused
    assert execution is not None
    try:
        actor = langgraph_social_apply.active_world_character(
            ctx.db,
            character_id=ctx.character.id,
        )
        with unit_of_work.deferred_commits():
            result = social_agent_tools_runtime.agent_tool_actions.create_agent_tool_post(
                ctx.db,
                ctx.session_key,
                social_schemas.PostCreate(
                    title=title,
                    body=body,
                    author_character_id=ctx.character.id,
                ),
                topic_signature=topic_signature,
                novelty_basis=_clip(topic_basis, 500) or None,
                lore_chunk_ids=lore_chunk_ids,
                retrieval_mode=retrieval_mode,
                lore_query_mode=lore_query_mode,
                consume_pending_feed_cue=(
                    writing_plan.get("mode") == _OWNER_FEED_CUE_MODE
                ),
                feed_cue_id=(feed_cue_id if isinstance(feed_cue_id, int) else None),
                world_id=actor.world_id,
                author_world_character_id=actor.id,
            )
            image_attempt = (
                image_attachment.attach_prepared_post_image(
                    db=ctx.db,
                    post_id=result.id,
                    prepared=prepared_image,
                )
                if prepared_image is not None
                else None
            )
            social_result = langgraph_social_apply.apply_successful_root_post(
                ctx.db,
                actor_character_id=ctx.character.id,
                post_id=result.id,
                execution=execution,
                occurred_at=ctx.run_started_at,
            )
            execution_result = {
                "post_id": result.id,
                "title": result.title,
                "topic_key": topic_key,
                "social_event_id": social_result.event.id,
                "world_id": actor.world_id,
                "actor_world_character_id": actor.id,
            }
            if isinstance(feed_cue_id, int):
                execution_result["feed_cue_id"] = feed_cue_id
            if lore_chunk_ids:
                execution_result["lore_chunk_ids"] = lore_chunk_ids
            if retrieval_mode:
                execution_result["retrieval_mode"] = retrieval_mode
            if lore_query_mode:
                execution_result["lore_query_mode"] = lore_query_mode
            if image_attempt is not None:
                execution_result["image_attempt"] = image_attempt
            action_result = _finish_execution(
                ctx,
                execution,
                status="succeeded",
                result=execution_result,
            )
            record_declared_subjective_context(
                ctx.db,
                execution=execution,
                event=social_result.event,
                source_post_id=result.id,
                context=_declared_action_subjective_context("post", writing_plan),
                captured_at=ctx.run_started_at,
            )
        ctx.db.commit()
        if image_attempt is not None:
            action_result["image_attempt"] = image_attempt
        if topic_key:
            action_result["topic_key"] = topic_key
        action_result["persona_writer_validation"] = validation
        if writer_validation is not None:
            action_result["writer_validation"] = writer_validation
        if lore_chunk_ids:
            try:
                character_lore_service.mark_lore_chunks_used(
                    ctx.db, chunk_ids=lore_chunk_ids
                )
            except Exception:
                ctx.db.rollback()
                logger.exception(
                    "failed to mark character lore chunks as used",
                    extra={"run_id": ctx.run_id, "character_id": ctx.character.id},
                )
        return action_result
    except Exception as exc:
        ctx.db.rollback()
        failure_class = type(exc).__name__
        logger.warning(
            "langgraph_writing_action_failed run_id=%s character_id=%s "
            "failure_class=%s error=%s",
            ctx.run_id,
            ctx.character.id,
            failure_class,
            redact_secret_text(str(exc))[:500],
        )
        return _finish_execution(
            ctx,
            execution,
            status="failed",
            result=None,
            failure_class=failure_class,
        )


def _relationship_point_expiry(ctx: LangGraphResidentContext, kind: str) -> datetime:
    hours = 72
    if kind == "mention_received":
        hours = 72
    return ctx.run_started_at.astimezone(UTC) + timedelta(hours=hours)


def _relationship_pair_cap_window_start(ctx: LangGraphResidentContext) -> datetime:
    current = ctx.run_started_at.astimezone(agent_activity_policy.APP_TIMEZONE)
    return current.replace(hour=0, minute=0, second=0, microsecond=0).astimezone(UTC)


def _relationship_point_cap_allows(
    ctx: LangGraphResidentContext,
    *,
    source_character_id: str,
    recipient_character_id: str,
    chain_depth: int,
) -> tuple[bool, str | None]:
    if source_character_id == recipient_character_id:
        return False, "self_relationship_point"
    if chain_depth > 3:
        return False, "chain_depth_exceeded"
    pair_key = relationship_point_values.relationship_point_pair_key(
        source_character_id, recipient_character_id
    )
    try:
        count = relationship_point_queries.count_relationship_points_for_pair_since(
            ctx.db,
            pair_key=pair_key,
            since=_relationship_pair_cap_window_start(ctx),
        )
    except Exception:
        ctx.db.rollback()
        return False, "pair_cap_check_failed"
    if count >= 2:
        return False, "pair_daypart_cap_exceeded"
    return True, None


def _create_relationship_point_from_post(
    ctx: LangGraphResidentContext,
    *,
    kind: Literal["mention_received", "reply_received"],
    recipient_character_id: str | None,
    source_character_id: str,
    source_post_id: str,
    topic_brief: str,
    source_run_id: str | None = None,
    chain_id: str | None = None,
    chain_depth: int = 0,
    payload: dict[str, Any] | None = None,
) -> dict[str, Any]:
    if not recipient_character_id:
        return {"created": False, "reason": "recipient_not_character"}
    recipient = characters_profile_service.get_character(ctx.db, recipient_character_id)
    if recipient is None or recipient.deleted_at is not None:
        return {"created": False, "reason": "recipient_unavailable"}
    if recipient.moderation_status == "suspended":
        return {"created": False, "reason": "recipient_suspended"}
    source_post = _relationship_source_post_available(ctx, source_post_id)
    if source_post is None:
        return {"created": False, "reason": "source_post_unavailable"}
    allowed, reason = _relationship_point_cap_allows(
        ctx,
        source_character_id=source_character_id,
        recipient_character_id=recipient_character_id,
        chain_depth=chain_depth,
    )
    if not allowed:
        return {"created": False, "reason": reason}
    try:
        point, create_reason = relationship_points.create_relationship_point(
            ctx.db,
            kind=kind,
            recipient_character_id=recipient_character_id,
            source_character_id=source_character_id,
            source_post_id=source_post_id,
            source_run_id=source_run_id,
            topic_brief=_clip(topic_brief, 2000),
            chain_id=chain_id,
            chain_depth=chain_depth,
            expires_at=_relationship_point_expiry(ctx, kind),
            payload=payload,
        )
    except Exception as exc:
        ctx.db.rollback()
        return {"created": False, "reason": type(exc).__name__}
    return {
        "created": create_reason is None and point is not None,
        "reason": create_reason,
        "point_id": getattr(point, "id", None),
        "kind": kind,
        "recipient_character_id": recipient_character_id,
        "source_character_id": source_character_id,
        "source_post_id": source_post_id,
    }


def _record_relationship_points_after_publish(
    ctx: LangGraphResidentContext,
    state: _ResidentGraphState,
) -> dict[str, Any]:
    action_plan = state.get("action_plan", {})
    writing_plan = action_plan.get("writing") if isinstance(action_plan, dict) else {}
    if not isinstance(writing_plan, dict):
        writing_plan = {}
    created: list[dict[str, Any]] = []
    consumed: list[dict[str, Any]] = []
    skipped: list[dict[str, Any]] = []
    root_post_id = _writing_success_post_id(state)
    if root_post_id:
        point_id = writing_plan.get("relationship_point_id")
        if point_id:
            point = ctx.db.get(_model_AgentRelationshipPoint, int(point_id))
            if point is not None and point.status in {
                relationship_point_constants.RELATIONSHIP_POINT_PENDING,
                relationship_point_constants.RELATIONSHIP_POINT_SELECTED,
            }:
                try:
                    relationship_points.mark_relationship_point_consumed(
                        ctx.db,
                        point,
                        run_id=ctx.run_id,
                        post_id=root_post_id,
                        now=ctx.run_started_at.astimezone(UTC),
                    )
                    consumed.append(
                        {
                            "point_id": point.id,
                            "post_id": root_post_id,
                            "status": "consumed",
                        }
                    )
                except Exception as exc:
                    ctx.db.rollback()
                    skipped.append(
                        {
                            "point_id": point_id,
                            "reason": type(exc).__name__,
                            "stage": "consume",
                        }
                    )
    elif writing_plan.get("relationship_point_id"):
        point_id = writing_plan.get("relationship_point_id")
        try:
            point = ctx.db.get(_model_AgentRelationshipPoint, int(point_id))
            if (
                point is not None
                and point.status == relationship_point_constants.RELATIONSHIP_POINT_SELECTED
                and point.selected_run_id == ctx.run_id
            ):
                relationship_points.release_relationship_point_selection(
                    ctx.db,
                    point,
                    failure_class="publish_not_succeeded",
                )
        except Exception as exc:
            ctx.db.rollback()
            skipped.append(
                {
                    "point_id": point_id,
                    "reason": type(exc).__name__,
                    "stage": "release_selection",
                }
            )
        skipped.append(
            {
                "point_id": point_id,
                "reason": "publish_not_succeeded",
                "stage": "consume",
            }
        )
    for action in _successful_action_results(state, "reply"):
        result = action.get("result") if isinstance(action.get("result"), dict) else {}
        reply_post_id = str(result.get("post_id") or "").strip()
        parent_post_id = str(result.get("reply_to_post_id") or "").strip()
        parent = social_posts_repository.get_post(ctx.db, parent_post_id) if parent_post_id else None
        if parent is None or not parent.author_character_id:
            skipped.append(
                {
                    "reply_post_id": reply_post_id,
                    "reason": "reply_target_not_character",
                    "stage": "reply_received",
                }
            )
            continue
        created.append(
            _create_relationship_point_from_post(
                ctx,
                kind="reply_received",
                recipient_character_id=parent.author_character_id,
                source_character_id=ctx.character.id,
                source_post_id=reply_post_id,
                source_run_id=ctx.run_id,
                topic_brief=f"{ctx.character.name}이(가) 대꾸한 일",
                payload={
                    "source": "reply_publish",
                    "reply_to_post_id": parent_post_id,
                },
            )
        )
    try:
        _record_daypart_event(
            ctx,
            event_type="relationship_point_update",
            summary=f"created={len([item for item in created if item.get('created')])}; consumed={len(consumed)}",
            payload={"created": created, "consumed": consumed, "skipped": skipped},
        )
    except Exception:
        ctx.db.rollback()
    return {"created": created, "consumed": consumed, "skipped": skipped}


_INBOX_LANE_PRECOMPLETED_NODES = [
    "DaypartContextLoader",
    "FeedObserver",
    "FeedSeedSelector",
    "RelationshipPointLoader",
    "RelationshipMemory",
    "FeedActionPlanner",
    "RelationshipActionPlanner",
    "IndependentTopicComposer",
    "IndependentWritingPlanner",
    "LoreQueryRewriter",
    "PostWriterPlanner",
    "PostWriter",
    "PostWriterRepair",
    "RelationshipPointRecorder",
    "StateRecorder",
]


async def _run_combined_inbox_lane(
    ctx: LangGraphResidentContext,
) -> dict[str, Any]:
    tracker = RunLlmTracker()
    graph = _build_graph(ctx, tracker)
    initial_state: _ResidentGraphState = {
        "inbox_lane_only": True,
        "steps": 0,
        "completed_nodes": list(_INBOX_LANE_PRECOMPLETED_NODES),
        "next_node": "Supervisor",
        "daypart_context": _current_daypart_context(ctx),
        "relationship_memory": _inbox_lane_relationship_memory(ctx),
        "feed_observation": {"selected_posts": []},
        "feed_action_plan": _empty_action_plan("inbox lane has no feed plan"),
        "relationship_action_plan": _empty_relationship_plan(
            "inbox lane has no relationship-maintenance plan"
        ),
        "relationship_candidates": [],
        "independent_writing_plan": _empty_action_plan(
            "inbox lane has no independent writing plan"
        ),
        "independent_post_roll": {
            "available": False,
            "passed": False,
            "blocked_reason": "inbox_lane_only",
        },
    }
    try:
        final_state = await graph.ainvoke(
            initial_state,
            config={"recursion_limit": _langgraph_recursion_limit()},
        )
    except DirectLlmDeferred:
        raise
    except Exception as exc:
        ctx.db.rollback()
        usage = tracker.summary()
        logger.warning(
            "resident_inbox_lane_failed run_id=%s character_id=%s "
            "outcome=INBOX_RETRYABLE_FAILED failure_class=%s error=%s",
            ctx.run_id,
            ctx.character.id,
            type(exc).__name__,
            redact_secret_text(str(exc))[:500],
        )
        return {
            "engine": "inbox_lane_v1",
            "status": "failed",
            "summary": "Inbox lane failed before a durable decision.",
            "outcome": "INBOX_RETRYABLE_FAILED",
            "candidate_count": 0,
            "planner_invoked": _inbox_lane_planner_invoked(tracker),
            "decision_source": "code",
            "provider_call_count": int(usage.get("provider_call_count") or 0),
            "public_action_count": 0,
            "handled_notification_count": 0,
            "failure_class": type(exc).__name__,
            "publish_result": {"actions": [], "public_action_count": 0},
            "node_trace": [],
            "llm_usage_summary": usage,
        }

    completed_nodes = list(final_state.get("completed_nodes", []))
    usage = tracker.summary()
    planner_invoked = _inbox_lane_planner_invoked(tracker)
    observation = final_state.get("inbox_observation", {})
    if not isinstance(observation, dict):
        observation = {}
    observation_items = [
        item
        for item in (observation.get("items") or [])
        if isinstance(item, dict)
    ]
    candidate_count = len(observation_items)
    observed_count = int(observation.get("observed_count") or candidate_count)
    inbox_plan = final_state.get("inbox_action_plan", {})
    if not isinstance(inbox_plan, dict):
        inbox_plan = {}
    action_plan = final_state.get("action_plan", {})
    selected_actions = (
        [
            action
            for action in (action_plan.get("inbox_actions") or [])
            if isinstance(action, dict)
        ]
        if isinstance(action_plan, dict)
        else []
    )
    publish_result = final_state.get("publish_result", {})
    if not isinstance(publish_result, dict):
        publish_result = {"actions": [], "public_action_count": 0}
    action_results = [
        item
        for item in (publish_result.get("actions") or [])
        if isinstance(item, dict)
    ]
    public_action_count = int(publish_result.get("public_action_count") or 0)
    successful_notification_ids: set[int] = set()
    for index, result in enumerate(action_results):
        if result.get("status") not in {"succeeded", "reused"}:
            continue
        if index >= len(selected_actions):
            continue
        notification_id = selected_actions[index].get("notification_id")
        try:
            successful_notification_ids.add(int(notification_id))
        except (TypeError, ValueError):
            continue

    outcome = "INBOX_RETRYABLE_FAILED"
    status = "failed"
    decision_source = "code"
    summary = "Inbox lane did not reach a durable decision."
    no_action_notification_ids: list[int] = []
    failure_class = None
    raw_selected_action_count = int(
        inbox_plan.get("raw_selected_action_count") or 0
    )
    if "InboxObserver" not in completed_nodes:
        outcome = "INBOX_NOT_RUN"
        summary = "Inbox lane was invoked but the observer did not run."
        failure_class = str(final_state.get("failure_class") or "inbox_observer_not_run")
    elif final_state.get("failure_class") or isinstance(
        inbox_plan.get("planner_error"), dict
    ):
        outcome = "INBOX_RETRYABLE_FAILED"
        summary = "Inbox lane failed before a durable decision."
        failure_class = str(
            final_state.get("failure_class") or "inbox_planner_failed"
        )
    elif candidate_count == 0:
        if observed_count > 0:
            outcome = "NO_ALLOWED_ACTION"
            status = "observed"
            summary = "Unread inbox items existed, but code allowed no public action."
        else:
            outcome = "INBOX_EMPTY"
            status = "observed"
            summary = "Inbox lane ran and found no unread actionable notification."
    elif not planner_invoked:
        outcome = "INBOX_NOT_RUN"
        summary = "Inbox candidates existed, but the planner was not invoked."
        failure_class = "inbox_planner_not_run"
    elif raw_selected_action_count == 0:
        outcome = "LLM_DECIDED_NO_ACTION"
        status = "observed"
        decision_source = "llm"
        summary = "Inbox planner explicitly chose no public action."
        no_action_notification_ids = [
            int(item["notification_id"])
            for item in observation_items
            if item.get("notification_id") is not None
        ]
    elif not selected_actions:
        outcome = "NO_ALLOWED_ACTION"
        status = "observed"
        summary = "The planner proposed an inbox action, but code allowed none."
    elif public_action_count > 0:
        outcome = "INBOX_ACTION_SUCCEEDED"
        status = "completed"
        decision_source = "llm"
        summary = "Inbox lane completed at least one public action."
        selected_notification_ids = {
            int(action["notification_id"])
            for action in selected_actions
            if action.get("notification_id") is not None
        }
        no_action_notification_ids = [
            int(item["notification_id"])
            for item in observation_items
            if item.get("notification_id") is not None
            and int(item["notification_id"]) not in selected_notification_ids
        ]
    else:
        outcome = "INBOX_RETRYABLE_FAILED"
        decision_source = "llm"
        summary = "Inbox planner selected an action, but no public write succeeded."
        failure_class = "inbox_public_action_failed"

    handled_no_action_count = 0
    if no_action_notification_ids:
        try:
            handled_at = datetime.now(UTC)
            for notification_id in no_action_notification_ids:
                langgraph_social_apply.mark_notification_handled_without_public_action(
                    ctx.db,
                    actor_character_id=ctx.character.id,
                    notification_id=notification_id,
                    handling_outcome="LLM_DECIDED_NO_ACTION",
                    occurred_at=handled_at,
                )
            ctx.db.commit()
            handled_no_action_count = len(set(no_action_notification_ids))
        except Exception as exc:
            ctx.db.rollback()
            outcome = "INBOX_RETRYABLE_FAILED"
            status = "failed"
            summary = "Inbox no-action decision could not be persisted."
            failure_class = type(exc).__name__
            handled_no_action_count = 0

    target_post_id = _inbox_lane_target_post_id(
        selected_actions=selected_actions,
        action_results=action_results,
        observation_items=observation_items,
    )
    compact_publish_result = {
        **publish_result,
        "target_post_id": target_post_id,
    }
    result = {
        "engine": "inbox_lane_v1",
        "status": status,
        "summary": summary,
        "outcome": outcome,
        "candidate_count": candidate_count,
        "planner_invoked": planner_invoked,
        "decision_source": decision_source,
        "provider_call_count": int(usage.get("provider_call_count") or 0),
        "public_action_count": public_action_count,
        "handled_notification_count": (
            len(successful_notification_ids) + handled_no_action_count
        ),
        "publish_result": compact_publish_result,
        "node_trace": completed_nodes,
        "llm_usage_summary": usage,
    }
    if failure_class:
        result["failure_class"] = failure_class
    logger.info(
        "resident_inbox_lane_completed run_id=%s character_id=%s outcome=%s "
        "candidate_count=%s planner_invoked=%s decision_source=%s "
        "provider_call_count=%s public_action_count=%s handled_count=%s",
        ctx.run_id,
        ctx.character.id,
        outcome,
        candidate_count,
        planner_invoked,
        decision_source,
        result["provider_call_count"],
        public_action_count,
        result["handled_notification_count"],
    )
    return result


async def run_resident_langgraph(
    ctx: LangGraphResidentContext,
) -> dict[str, Any]:
    context_db = getattr(ctx, "db", None)
    routine_world_character = (
        routine_world_character_for_character(
            context_db, character_id=ctx.character.id
        )
        if context_db is not None
        else None
    )
    if routine_world_character is not None:
        if agent_activity_policy.is_imported_world_runtime_locked(
            context_db, routine_world_character
        ):
            return {
                "engine": "imported_world_activation_v1",
                "status": "observed",
                "summary": "Imported World autonomy is disabled; resident lanes were not run.",
                "outcome": "AUTONOMY_DISABLED",
                "publish_result": {"public_action_count": 0},
                "llm_usage_summary": RunLlmTracker(max_calls=3).summary(),
            }
        async with _GRAPH_SEMAPHORE:
            feed_runtime_mode = getattr(
                routine_world_character,
                "feed_runtime_mode",
                LEGACY_FEED_RUNTIME_MODE,
            )
            if feed_runtime_mode != AUTONOMOUS_FEED_RUNTIME_MODE:
                return await run_routine_post_runtime(ctx)
            inbox_result = await _run_combined_inbox_lane(ctx)
            routine_result = await run_routine_post_runtime(ctx)
            feed_result = await run_world_keyword_feed(ctx)
            inbox_publish = inbox_result.get("publish_result")
            routine_publish = routine_result.get("publish_result")
            feed_publish = feed_result.get("publish_result")
            inbox_action_count = (
                int(inbox_publish.get("public_action_count") or 0)
                if isinstance(inbox_publish, dict)
                else 0
            )
            routine_action_count = (
                int(routine_publish.get("public_action_count") or 0)
                if isinstance(routine_publish, dict)
                else 0
            )
            feed_action_count = (
                int(feed_publish.get("public_action_count") or 0)
                if isinstance(feed_publish, dict)
                else 0
            )
            statuses = {
                inbox_result.get("status"),
                routine_result.get("status"),
                feed_result.get("status"),
            }
            status = (
                "failed"
                if "failed" in statuses
                else "completed"
                if inbox_action_count + routine_action_count + feed_action_count > 0
                else "observed"
            )
            return {
                "engine": (
                    f"{AUTONOMOUS_ACTIVITY_RUNTIME_MODE}"
                    f"+{AUTONOMOUS_FEED_RUNTIME_MODE}"
                ),
                "status": status,
                "summary": (
                    "Inbox, routine continuous post, and World keyword feed cycle completed."
                ),
                "inbox_lane": inbox_result,
                "routine_result": routine_result,
                "feed_result": feed_result,
                "publish_result": {
                    "public_action_count": (
                        inbox_action_count
                        + routine_action_count
                        + feed_action_count
                    ),
                    "inbox": inbox_publish or {},
                    "routine": routine_publish or {},
                    "feed": feed_publish or {},
                },
                "llm_usage_summary": {
                    "inbox": inbox_result.get("llm_usage_summary", {}),
                    "routine": routine_result.get("llm_usage_summary", {}),
                    "feed": feed_result.get("llm_usage_summary", {}),
                },
            }
    tracker = RunLlmTracker()
    initial_active_topic_arc = None
    initial_independent_post_roll = {
        "available": "post" in set(ctx.activity_policy.allowed_actions),
        "level": "mandatory",
        "tick_probability": 1.0
        if "post" in set(ctx.activity_policy.allowed_actions)
        else None,
        "roll": 0.0 if "post" in set(ctx.activity_policy.allowed_actions) else None,
        "passed": "post" in set(ctx.activity_policy.allowed_actions),
        "topics": [],
        "topic_pool_size": len(_independent_post_topics(ctx)),
        "topic_prompt_count": 0,
        "blocked_reason": None
        if "post" in set(ctx.activity_policy.allowed_actions)
        else "post_not_allowed",
        "mandatory": True,
    }
    initial_independent_post_decision = _independent_post_decision_meta(
        initial_independent_post_roll
    )
    graph = _build_graph(ctx, tracker)
    try:
        async with _GRAPH_SEMAPHORE:
            final_state = await graph.ainvoke(
                {
                    "steps": 0,
                    "completed_nodes": [],
                    "next_node": "Supervisor",
                    "active_topic_arc": initial_active_topic_arc,
                    "independent_post_roll": initial_independent_post_roll,
                    "independent_post_decision": initial_independent_post_decision,
                },
                config={"recursion_limit": _langgraph_recursion_limit()},
            )
    except DirectLlmDeferred:
        raise
    except GraphRecursionError as exc:
        logger.warning(
            "langgraph_resident_failed run_id=%s character_id=%s failure_class=%s "
            "recursion_limit=%s error=%s",
            ctx.run_id,
            ctx.character.id,
            type(exc).__name__,
            _langgraph_recursion_limit(),
            redact_secret_text(str(exc))[:500],
        )
        return {
            "engine": "langgraph",
            "status": "failed",
            "summary": "LangGraph resident graph recursion limit reached.",
            "failure_class": type(exc).__name__,
            "node_trace": [],
            "active_topic_arc": _topic_arc_for_prompt(
                initial_active_topic_arc,
                current_date=_current_kst_date(ctx),
            ),
            "topic_arc_result": {},
            "independent_post_decision": initial_independent_post_decision,
            "independent_post_roll": initial_independent_post_roll.get("roll"),
            "independent_post_probability": initial_independent_post_roll.get(
                "tick_probability"
            ),
            "independent_post_roll_passed": bool(
                initial_independent_post_roll.get("passed")
            ),
            "independent_post_topic_key": None,
            "independent_post_topic_pool_size": initial_independent_post_roll.get(
                "topic_pool_size"
            ),
            "independent_post_topic_prompt_count": initial_independent_post_roll.get(
                "topic_prompt_count"
            ),
            "llm_usage_summary": tracker.summary(),
            "llm_rate_limit_waits": tracker.rate_limit_waits,
        }
    except (DirectLlmJsonError, DirectLlmError, ValidationError) as exc:
        failure_meta = _llm_failure_meta(exc)
        logger.warning(
            "langgraph_resident_failed run_id=%s character_id=%s failure_class=%s "
            "failure_node=%s failure_lane=%s error=%s",
            ctx.run_id,
            ctx.character.id,
            type(exc).__name__,
            failure_meta.get("failure_node"),
            failure_meta.get("failure_lane"),
            redact_secret_text(str(exc))[:500],
        )
        return {
            "engine": "langgraph",
            "status": "failed",
            "summary": "LangGraph resident run failed before public action.",
            **failure_meta,
            "node_trace": [],
            "active_topic_arc": _topic_arc_for_prompt(
                initial_active_topic_arc,
                current_date=_current_kst_date(ctx),
            ),
            "topic_arc_result": {},
            "independent_post_decision": initial_independent_post_decision,
            "independent_post_roll": initial_independent_post_roll.get("roll"),
            "independent_post_probability": initial_independent_post_roll.get(
                "tick_probability"
            ),
            "independent_post_roll_passed": bool(
                initial_independent_post_roll.get("passed")
            ),
            "independent_post_topic_key": None,
            "independent_post_topic_pool_size": initial_independent_post_roll.get(
                "topic_pool_size"
            ),
            "independent_post_topic_prompt_count": initial_independent_post_roll.get(
                "topic_prompt_count"
            ),
            "llm_usage_summary": tracker.summary(),
        }
    publish_result = final_state.get("publish_result", {})
    public_action_count = 0
    if isinstance(publish_result, dict):
        public_action_count = int(publish_result.get("public_action_count") or 0)
    status = "completed"
    if final_state.get("failure_class"):
        status = "failed"
    elif public_action_count == 0:
        status = "observed"
    independent_post_roll = final_state.get(
        "independent_post_roll", initial_independent_post_roll
    )
    if not isinstance(independent_post_roll, dict):
        independent_post_roll = initial_independent_post_roll
    action_plan = final_state.get("action_plan", {})
    writing_plan = action_plan.get("writing") if isinstance(action_plan, dict) else {}
    independent_post_decision = final_state.get("independent_post_decision")
    if not isinstance(independent_post_decision, dict):
        independent_post_decision = _independent_post_decision_meta(
            independent_post_roll,
            independent_writing_plan=final_state.get("independent_writing_plan"),
            action_plan=action_plan,
        )
    independent_post_topic_key = None
    if isinstance(writing_plan, dict) and writing_plan.get("mode") == "independent":
        independent_post_topic_key = (
            str(writing_plan.get("topic_key") or "").strip() or None
        )
    if independent_post_topic_key is None:
        independent_post_topic_key = (
            str(independent_post_decision.get("topic_key") or "").strip() or None
        )
    return {
        "engine": "langgraph",
        "status": status,
        "summary": "LangGraph resident supervisor run completed.",
        "node_trace": final_state.get("completed_nodes", []),
        "run_mode": getattr(ctx, "run_mode", "scheduled"),
        "daypart_context": final_state.get("daypart_context", {}),
        "selected_feed_seed": final_state.get("selected_feed_seed", {}),
        "relationship_point_candidates": final_state.get(
            "relationship_point_candidates", []
        ),
        "selected_relationship_point": final_state.get("selected_relationship_point"),
        "relationship_point_selection": final_state.get(
            "relationship_point_selection"
        ),
        "mandatory_post_context": final_state.get("mandatory_post_context", {}),
        "independent_topic_composition": final_state.get(
            "independent_topic_composition", {}
        ),
        "active_topic_arc": _topic_arc_for_prompt(
            final_state.get("active_topic_arc"),
            current_date=_current_kst_date(ctx),
        ),
        "selected_action_bundle": action_plan,
        "planner_results": final_state.get("planner_results", {}),
        "relationship_review": final_state.get("relationship_review", {}),
        "action_budget_trim_summary": final_state.get(
            "action_budget_trim_summary", {}
        ),
        "write_task_summary": final_state.get("write_task_summary", {}),
        "writer_results": final_state.get("writer_results", {}),
        "publish_result": publish_result,
        "topic_arc_result": final_state.get("topic_arc_result", {}),
        "relationship_point_result": final_state.get("relationship_point_result", {}),
        "state_result": final_state.get("state_result", {}),
        "failure_class": final_state.get("failure_class"),
        "independent_post_decision": independent_post_decision,
        "independent_post_roll": independent_post_roll.get("roll"),
        "independent_post_probability": independent_post_roll.get("tick_probability"),
        "independent_post_roll_passed": bool(independent_post_roll.get("passed")),
        "independent_post_topic_key": independent_post_topic_key,
        "independent_post_topic_pool_size": independent_post_roll.get(
            "topic_pool_size"
        ),
        "independent_post_topic_prompt_count": independent_post_roll.get(
            "topic_prompt_count"
        ),
        "llm_usage_summary": tracker.summary(),
        "llm_rate_limit_waits": tracker.rate_limit_waits,
    }
