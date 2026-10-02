from __future__ import annotations
"""Test-owned injection ports for actual domain policies, not an SNS engine.

These bindings contain no SDK call, graph, dispatcher or public effects. Tests
exercise the defining services with explicit workflow dependencies.
"""
from app.runtime.social.subjective_composition import record_activity_thought
from app.domains.memory.service.daypart import history as _daypart_history, latest_summary as _latest_daypart_summary, seen_feed_post_ids as _seen_daypart_feed_post_ids, seen_notification_ids as _seen_daypart_notification_ids, record_event as _record_daypart_event
import app.domains.social.repository.posts as social_posts_repository
from app.runtime.resident import langgraph_queries
from app.domains.routines.policies import execution_results
from app.domains.routines.contracts.context_reads import RelationshipContextWorkflows, WritingContextWorkflows, ConversationWorkflows
from app.domains.routines.service import relationship_context as relationship_context_service
from app.domains.routines.service import writing_context as writing_context_service
from app.domains.routines.service import conversation_context as conversation_context_service
from app.domains.routines.service import resident_prompts as resident_prompts_service
from app.domains.routines.service import planner_results as planner_results_service
from app.domains.routines.service import writing_tasks as writing_tasks_service
from app.domains.routines.policies import writer_tasks as writer_tasks_service
from app.domains.routines.service import state_outputs as state_outputs_service
from app.domains.routines.contracts.action_planning import ActionPlanningWorkflows, ActionBudgetWorkflows
from app.domains.routines.service import activity_settings
from app.domains.routines.service import action_plans as action_plans_service
from app.domains.routines.service import writing_plans as writing_plans_service
from app.domains.routines.service import action_budgets as action_budgets_service
from app.domains.routines.service import independent_topics as independent_topic_service
from app.domains.routines.repository import independent_topics as independent_topic_queries
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
from app.domains.routines.repository import public_action_executions as public_action_queries
from app.domains.routines.service import public_action_executions as public_action_executions
from datetime import UTC, date, datetime, timedelta
from pydantic import BaseModel, ValidationError
from app.runtime.social.subjective_composition import record_declared_subjective_context
from app.runtime.routines import activity_policy as agent_activity_policy
from app.runtime.social import langgraph_actions as langgraph_social_apply
from app.runtime.social.planned_actions import _clip
from app.runtime.resident.history import _latest_topic_arc_event, _daypart_history_for_prompt, _yesterday_handoff_context, _daypart_start_utc, _finalize_closed_dayparts
from app.runtime.social import planned_actions
from app.runtime.social.planned_actions import _execute_planned_action, _reserve_public_action, _finish_execution, _declared_action_subjective_context, _prompt_injection_output_block, _reply_proposal_response
_topic_arc_last_post_created_at = langgraph_queries._topic_arc_last_post_created_at
_target_character_following = langgraph_queries._target_character_following
_today_own_root_posts_for_coverage = partial(langgraph_queries._today_own_root_posts_for_coverage, clip=_clip)
_today_root_writing_memory_for_prompt = partial(langgraph_queries._today_root_writing_memory_for_prompt, clip=_clip)
_recent_own_root_posts = partial(langgraph_queries._recent_own_root_posts, clip=_clip)
_conversation_context_post = langgraph_queries._conversation_context_post
_character_already_replied_to_target = langgraph_queries._character_already_replied_to_target
_record_topic_arc_progress = partial(execution_results._record_topic_arc_progress, coerce_topic_arc=lambda value: _coerce_topic_arc_payload(value))
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
_relationship_candidate_from_item = partial(relationship_context_service._relationship_candidate_from_item, workflows=_relationship_context_workflows)
_relationship_candidates_from_daypart_memory = partial(relationship_context_service._relationship_candidates_from_daypart_memory, workflows=_relationship_context_workflows)
_has_unfollow_watch = partial(relationship_context_service._has_unfollow_watch, workflows=_relationship_context_workflows)
_suppress_already_answered_reply_affordance = partial(relationship_context_service._suppress_already_answered_reply_affordance, workflows=_relationship_context_workflows)
_independent_post_context_for_prompt = partial(writing_context_service._independent_post_context_for_prompt, workflows=_writing_context_workflows)
_current_daypart_context = partial(writing_context_service._current_daypart_context, workflows=_writing_context_workflows)
_inbox_conversation_context = partial(conversation_context_service._inbox_conversation_context, workflows=_conversation_workflows)
_reply_task_id = partial(writer_tasks_service._reply_task_id, clip=_clip)
_state_recorder_should_retry_json_error = partial(state_outputs_service._state_recorder_should_retry_json_error, clip=_clip)
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
_normalize_inbox_action_plan = partial(action_plans_service._normalize_inbox_action_plan, workflows=_action_planning_workflows)
_normalize_relationship_action_plan = partial(action_plans_service._normalize_relationship_action_plan, workflows=_action_planning_workflows)
_compose_action_bundle = partial(action_plans_service._compose_action_bundle, workflows=_action_planning_workflows)
_feed_seed_candidates = writing_plans_service._feed_seed_candidates
_normalize_feed_seed_selection = partial(writing_plans_service._normalize_feed_seed_selection, clip=_clip)
_normalize_independent_topic_composition = partial(writing_plans_service._normalize_independent_topic_composition, clip=_clip)
_restore_mandatory_root_writing = partial(writing_plans_service._restore_mandatory_root_writing, clip=_clip)
_daily_action_budgets = partial(action_budgets_service._daily_action_budgets, workflows=_action_budget_workflows)
_apply_unfollow_conflict_suppression = partial(action_budgets_service._apply_unfollow_conflict_suppression, workflows=_action_budget_workflows)
_trim_action_plan_to_budget = partial(action_budgets_service._trim_action_plan_to_budget, workflows=_action_budget_workflows)
_feed_seed_interest_criteria = partial(independent_topic_service._feed_seed_interest_criteria, clip=_clip)
_select_independent_post_topics_for_tick = independent_topic_service._select_independent_post_topics_for_tick
_build_independent_post_roll = partial(independent_topic_service._build_independent_post_roll, clip=_clip)
_today_independent_topic_keys = independent_topic_queries._today_independent_topic_keys
_topic_arc_workflows = TopicArcWorkflows(
    clip=_clip,
    last_post_created_at=lambda ctx, last_post_id: _topic_arc_last_post_created_at(ctx, last_post_id),
    latest_event=lambda ctx, arc_id: _latest_topic_arc_event(ctx, arc_id),
)
_carryover_time_context = partial(topic_arc_service._carryover_time_context, workflows=_topic_arc_workflows)
_coerce_topic_arc_draft = partial(topic_arc_service._coerce_topic_arc_draft, workflows=_topic_arc_workflows)
_coerce_topic_arc_payload = partial(topic_arc_service._coerce_topic_arc_payload, workflows=_topic_arc_workflows)
_topic_arc_for_prompt = partial(topic_arc_service._topic_arc_for_prompt, workflows=_topic_arc_workflows)
_build_topic_arc_payload = partial(topic_arc_service._build_topic_arc_payload, workflows=_topic_arc_workflows)
_topic_arc_recovery_decision = partial(topic_arc_service._topic_arc_recovery_decision, workflows=_topic_arc_workflows)
_active_topic_arc = topic_arc_service._active_topic_arc
_writing_from_topic_arc = partial(topic_arc_service._writing_from_topic_arc, workflows=_topic_arc_workflows)
_topic_arc_continuity_context = partial(topic_arc_service._topic_arc_continuity_context, workflows=_topic_arc_workflows)
_persona_context = partial(resident_prompts_service._persona_context, clip=_clip)
_build_system_prompt = partial(resident_prompts_service._build_system_prompt, clip=_clip)
_build_reply_writer_user_prompt = partial(resident_prompts_service._build_reply_writer_user_prompt, clip=_clip)
_build_post_writer_planner_user_prompt = partial(resident_prompts_service._build_post_writer_planner_user_prompt, clip=_clip)
_build_post_writer_user_prompt = partial(resident_prompts_service._build_post_writer_user_prompt, clip=_clip)
_build_state_recorder_user_prompt = partial(resident_prompts_service._build_state_recorder_user_prompt, clip=_clip, topic_workflows=_topic_arc_workflows)
_planner_inbox_observation_for_prompt = planner_results_service._planner_inbox_observation_for_prompt
_independent_post_decision_meta = planner_results_service._independent_post_decision_meta
_planner_results_summary = partial(planner_results_service._planner_results_summary, clip=_clip, topic_workflows=_topic_arc_workflows)
_compile_write_tasks = partial(writing_tasks_service._compile_write_tasks, clip=_clip, topic_workflows=_topic_arc_workflows)
LANGGRAPH_DEFAULT_OUTPUT_TOKENS = 2000
LANGGRAPH_PLANNER_OUTPUT_TOKENS = 4000
LANGGRAPH_RELATIONSHIP_OUTPUT_TOKENS = 4000
LANGGRAPH_POST_WRITER_PLANNER_OUTPUT_TOKENS = 4000
LANGGRAPH_POST_WRITER_OUTPUT_TOKENS = 4000
LANGGRAPH_REPLY_WRITER_OUTPUT_TOKENS = 5000
LANGGRAPH_REPLY_WRITER_REPAIR_OUTPUT_TOKENS = 4000
LANGGRAPH_STATE_RECORDER_OUTPUT_TOKENS = 3000
