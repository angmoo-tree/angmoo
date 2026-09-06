"""Resident execution, provider calls, leases and same-Session failure compensation."""
import app.domains.routines.constants as routines_constants
import app.domains.routines.service.feed_history_values as routines_feed_history_values_service
import app.domains.social.service.posts as social_posts_service
import app.runtime.social.feed_history as social_feed_history_runtime
from app.config import settings
from app.database import SessionLocal
from app.core.redaction import redact_secret_text
from app.domains.identity.repository import credentials as agent_run_crud
from app.domains.characters.models import Character
from app.domains.characters.models import CharacterState
from app.domains.characters.service import state as character_state_service
from app.domains.identity.models import LlmCredential
from app.domains.identity.service import credential_cooldown
from app.domains.routines import constants as routine_constants
from app.domains.routines import models
from app.domains.routines import schemas
from app.domains.routines.constants import DEFAULT_ACTIVITY_ACTIONS
from app.domains.routines.constants import GEMINI_FREE_FEED_CANDIDATE_MAX
from app.domains.routines.constants import GEMINI_FREE_INBOX_CANDIDATE_MAX
from app.domains.routines.constants import GEMINI_FREE_POLICY_ID
from app.domains.routines.constants import GEMINI_FREE_WRITING_SEED_MAX
from app.domains.routines.constants import GENERIC_OBSERVATION_RESULT
from app.domains.routines.constants import TOOLS_ALLOW_COMMUNITY_ONCE
from app.domains.routines.constants import TOOLS_ALLOW_COMPLETE_TICK
from app.domains.routines.constants import TOOLS_ALLOW_SAVE_STATE
from app.domains.routines.constants import TOOLS_ALLOW_THREAD_OR_COMPLETE
from app.domains.routines.constants import TOOLS_ALLOW_V6_FEED_HISTORY_SANITIZE_LANE
from app.domains.routines.constants import TOOLS_ALLOW_V6_FEED_SCAN_LANE
from app.domains.routines.constants import TOOLS_ALLOW_V6_INBOX_LANE
from app.domains.routines.constants import TOOLS_ALLOW_V6_STATE_LANE
from app.domains.routines.constants import TOOL_CHOICE_COMPLETE_TICK
from app.domains.routines.constants import TOOL_CHOICE_SAVE_STATE
from app.domains.routines.constants import TOOL_CHOICE_THREAD_OR_COMPLETE
from app.domains.routines.exceptions import AgentRunConflictError
from app.domains.routines.exceptions import AgentSessionBusyError
from app.domains.routines.exceptions import AgentSlotUnavailableError
from app.domains.routines.exceptions import CredentialSyncError
from app.domains.routines.exceptions import OpenClawNotConfiguredError
from app.domains.routines.exceptions import ReadOnlyLaneDeferredError
from app.domains.routines.exceptions import ReadOnlyLaneRetryExhausted
from app.domains.routines.repository import feed_cues as feed_cue_queries
from app.domains.routines.repository import slots as slot_queries
from app.domains.routines.service import activity_logs
from app.domains.routines.service import activity_settings
from app.domains.routines.service import runs as routine_runs
from app.domains.routines.service import slot_assignments as slot_assignments
from app.domains.routines.service import slot_leases as slot_leases
from app.domains.routines.service import slot_pool as slot_pool
from app.domains.routines.service import slot_recovery as slot_recovery
from app.domains.routines.service import slot_requests
from app.domains.routines.service.action_briefs import _build_v6_prepared_create_post_brief
from app.domains.routines.service.action_candidates import _format_v6_inbox_compact_candidate
from app.domains.routines.service.action_candidates import _format_v6_inbox_scan_context
from app.domains.routines.service.action_menu import _format_v6_action_menu_table
from app.domains.routines.service.action_prompts import _action_decision_allows_thread
from app.domains.routines.service.action_prompts import _build_selected_mode_completion_message
from app.domains.routines.service.action_prompts import _build_selected_mode_completion_prompt
from app.domains.routines.service.action_prompts import _build_v6_final_action_prompt
from app.domains.routines.service.activity_evidence import _format_observation_result
from app.domains.routines.service.activity_evidence import _format_tick_activity_since
from app.domains.routines.service.activity_evidence import _format_tick_observation_context_since
from app.domains.routines.service.activity_evidence import _format_tick_public_action_ledger_since
from app.domains.routines.service.activity_evidence import _has_activity_since
from app.domains.routines.service.activity_evidence import _has_state_saved_since
from app.domains.routines.service.activity_evidence import _has_thread_viewed_since
from app.domains.routines.service.activity_evidence import _has_tick_completed_since
from app.domains.routines.service.activity_evidence import _latest_v6_feed_history_sanitize_payload
from app.domains.routines.service.activity_evidence import _latest_v6_feed_interest_payload
from app.domains.routines.service.activity_evidence import _latest_v6_inbox_review_payload
from app.domains.routines.service.execution_admission import _read_available_run_character
from app.domains.routines.service.execution_admission import _resolve_run_credential
from app.domains.routines.service.execution_admission import _resolve_run_owner
from app.domains.routines.service.execution_prompts import _build_agent_message
from app.domains.routines.service.execution_prompts import _build_extra_system_prompt
from app.domains.routines.service.execution_results import _combined_runtime_evidence_post_id
from app.domains.routines.service.execution_results import _is_success_status
from app.domains.routines.service.execution_results import _runtime_last_error
from app.domains.routines.service.feed_context import _collect_v6_inbox_candidates
from app.domains.routines.service.feed_context import _format_inbox_threads
from app.domains.routines.service.feed_context import _format_recent_activity_summary
from app.domains.routines.service.feed_context import _format_recent_feed_sections
from app.domains.routines.service.feed_context import _format_recent_own_posts_to_avoid
from app.domains.routines.service.feed_context import _format_v6_feed_interests
from app.domains.routines.service.feed_context import _v6_inbox_candidates_from_review
from app.domains.routines.service.perception_diagnostics import _log_feed_perception_debug
from app.domains.routines.service.perception_prompts import _build_v6_feed_history_sanitize_lane_prompt
from app.domains.routines.service.perception_prompts import _build_v6_feed_scan_lane_prompt
from app.domains.routines.service.perception_prompts import _build_v6_inbox_lane_prompt
from app.domains.routines.service.post_selection import _select_resident_run_post_id
from app.domains.routines.service.post_selection import _select_tick_post_id
from app.domains.routines.service.retry_schedule import _scheduled_retry_next_tick_at
from app.domains.routines.service.run_backoff import _runtime_error_backoff
from app.domains.routines.service.run_identity import _validate_character_and_credential
from app.domains.routines.service.run_results import _build_llm_usage_summary
from app.domains.routines.service.run_results import _pending_writing_composition_lanes
from app.domains.routines.service.run_results import _persist_agent_run_gateway_snapshot
from app.domains.routines.service.run_results import _safe_gateway_result
from app.domains.routines.service.run_results import _stored_gateway_result
from app.domains.routines.service.session_keys import _activity_daypart_window
from app.domains.routines.service.session_keys import _daypart_main_session_key
from app.domains.routines.service.session_keys import _daypart_persistent_session_allowed
from app.domains.routines.service.session_keys import _main_run_session_key
from app.domains.routines.service.session_keys import _scratch_session_key
from app.domains.routines.service.session_keys import _tool_auth_key
from app.domains.routines.service.slot_status import _resident_slot_is_due
from app.domains.routines.service.slot_status import list_resident_slots
from app.domains.routines.service.social_context import _format_relationship_review_candidate
from app.domains.routines.service.social_context import _format_social_connection_candidate
from app.domains.routines.service.social_context import _format_strong_social_connection_candidate
from app.domains.routines.service.state_prompts import _build_complete_tick_followup_message
from app.domains.routines.service.state_prompts import _build_complete_tick_followup_prompt
from app.domains.routines.service.state_prompts import _build_memory_note_refine_message
from app.domains.routines.service.state_prompts import _build_memory_note_refine_prompt
from app.domains.routines.service.state_prompts import _build_v6_state_lane_message
from app.domains.routines.service.state_prompts import _build_v6_state_lane_prompt
from app.domains.routines.service.state_prompts import _build_v6_state_recovery_message
from app.domains.routines.service.state_prompts import _build_v6_state_recovery_prompt
from app.domains.routines.service.tick_schedule import aware_utc as _aware_utc
from app.domains.routines.service.tool_policy import _gemini_free_effective_actions
from app.domains.routines.service.tool_policy import _policy_allows_observe
from app.domains.routines.service.tool_policy import _resident_public_tools_allow
from app.domains.routines.service.tool_policy import _should_allow_resident_thread_tool
from app.runtime.search.binding import current_social_search
from app.domains.world_characters.public import is_owner_controlled_character
from app.domains.world_characters.public import owner_controlled_character_ids
from app.domains.world_characters.service import readiness as activity_profile_readiness
from app.runtime.resident import activity_policy as agent_activity_policy
from app.runtime.resident import slots as resident_slots
from app.runtime.resident.context_references import SqlAlchemyResidentActionReferences
from app.runtime.resident.credential_profiles import _ensure_slot_auth_profile
from app.runtime.resident.credential_profiles import _release_slot_auth_profile
from app.runtime.resident.decision_lanes import _run_action_decision
from app.runtime.resident.decision_lanes import _run_feed_perception
from app.runtime.resident.feed_context_references import SqlAlchemyResidentContextReferences, resident_social_context
from app.runtime.resident.gateway_results import _build_llm_trace_context
from app.runtime.resident.identity_references import SqlAlchemyRunIdentityReferences
from app.runtime.resident.post_selection import SqlAlchemyPostSelectionReferences
from app.runtime.resident.read_only_lanes import FEED_HISTORY_SANITIZE_MAX_ATTEMPTS
from app.runtime.resident.read_only_lanes import FEED_HISTORY_SANITIZE_TIMEOUT_SECONDS
from app.runtime.resident.read_only_lanes import READ_ONLY_LANE_TIMEOUT_SECONDS
from app.runtime.resident.read_only_lanes import _build_read_only_lane_deferred_gateway_result
from app.runtime.resident.read_only_lanes import _feed_history_sanitize_metadata_fallback_reason
from app.runtime.resident.read_only_lanes import _read_only_lane_deferred_retry_at
from app.runtime.resident.read_only_lanes import _run_read_only_lane_with_retry
from app.runtime.resident.request_options import _feed_history_sanitize_stream_params
from app.runtime.resident.request_options import _feed_scan_stream_params
from app.runtime.resident.request_options import _tool_choice_any
from app.runtime.resident.slots import build_slot_request_workflows

from app.domains.operations.service import maintenance as maintenance_service
from app.services.agent_runs import _build_daypart_memory_note
from app.services.agent_runs import _filter_daypart_duplicate_feed_interest
from app.services.agent_runs import _filter_daypart_duplicate_inbox_candidates
from app.services.agent_runs import _purge_expired_daypart_memory_events
from app.services.agent_runs import _record_provided_daypart_observations
from app.integrations.direct_llm import DirectLlmDeferred
from app.runtime.resident.context import LangGraphResidentContext
from app.runtime.resident.langgraph import run_resident_langgraph
from app.services.runtime_boundary import OpenClawGatewayClient
from app.services.runtime_boundary import openclaw_auth_profiles
from datetime import UTC
from datetime import date
from datetime import datetime
from datetime import timedelta
from sqlalchemy.orm import Session
from typing import Any
from uuid import uuid4
import asyncio
import json
import logging

logger = logging.getLogger("app.services.agent_runs")


def assign_resident_slot(
    db: Session,
    *,
    user_id: str,
    character_id: str,
    credential_id: str,
    heartbeat_interval_seconds: int,
    next_tick_at: datetime | None = None,
    commit: bool = True,
) -> schemas.AgentSlotRead:
    return slot_requests.assign_resident_slot(
        db,
        user_id=user_id,
        character_id=character_id,
        credential_id=credential_id,
        heartbeat_interval_seconds=heartbeat_interval_seconds,
        next_tick_at=next_tick_at,
        commit=commit,
        workflows=build_slot_request_workflows(
            db, credential_lookup=agent_run_crud.get_credential,
            default_credential_lookup=agent_run_crud.get_default_credential,
            ensure_auto_ticks_available=maintenance_service.ensure_auto_ticks_available,
            ensure_run_now_available=maintenance_service.ensure_run_now_available,
            timezone_reader=agent_activity_policy.activity_timezone,
        ),
    )


def claim_temporary_resident_slot(
    db: Session,
    *,
    user_id: str,
    character_id: str,
    credential_id: str,
    heartbeat_interval_seconds: int,
    timeout_seconds: int,
) -> models.AgentSlot:
    return slot_requests.claim_temporary_resident_slot(
        db,
        user_id=user_id,
        character_id=character_id,
        credential_id=credential_id,
        heartbeat_interval_seconds=heartbeat_interval_seconds,
        timeout_seconds=timeout_seconds,
        workflows=build_slot_request_workflows(
            db, credential_lookup=agent_run_crud.get_credential,
            default_credential_lookup=agent_run_crud.get_default_credential,
            ensure_auto_ticks_available=maintenance_service.ensure_auto_ticks_available,
            ensure_run_now_available=maintenance_service.ensure_run_now_available,
            timezone_reader=agent_activity_policy.activity_timezone,
        ),
    )


def release_temporary_resident_slot(
    db: Session,
    *,
    agent_id: str,
    user_id: str,
    character_id: str,
    credential_id: str,
) -> None:
    slot_assignments.release_temporary_resident_slot_assignment(
        db,
        agent_id=agent_id,
        user_id=user_id,
        character_id=character_id,
        credential_id=credential_id,
    )


async def run_community_once(
    db: Session,
    data: schemas.OpenClawCommunityRunCreate,
    *,
    require_public_action: bool = False,
    enforce_activity_policy: bool = False,
) -> schemas.OpenClawAgentRunRead:
    maintenance_service.ensure_run_now_available(db)
    use_langgraph_resident = (
        settings.agent_activity_engine == "langgraph" and enforce_activity_policy
    )
    token = settings.openclaw_gateway_token
    if not use_langgraph_resident and token is None:
        raise OpenClawNotConfiguredError("OPENCLAW_GATEWAY_TOKEN is missing")

    character = _read_available_run_character(
        SqlAlchemyRunIdentityReferences(db, credential_lookup=agent_run_crud.get_credential, default_credential_lookup=agent_run_crud.get_default_credential), data.character_id
    )
    post_id = _select_tick_post_id(
        SqlAlchemyPostSelectionReferences(db), preferred_post_id=data.post_id, character_id=character.id
    )
    post = social_posts_service.get_post(db, post_id) if post_id else None
    user_id = _resolve_run_owner(character, data.user_id)

    credential = _resolve_run_credential(
        SqlAlchemyRunIdentityReferences(db, credential_lookup=agent_run_crud.get_credential, default_credential_lookup=agent_run_crud.get_default_credential),
        user_id=user_id, character=character, credential_id=data.credential_id,
    )

    state = character_state_service.get_character_state(db, character.id)

    run_id = str(uuid4())
    timeout_seconds = data.timeout_seconds or settings.openclaw_timeout_seconds
    candidate_agent_ids = (
        [data.agent_id] if data.agent_id else settings.openclaw_agent_ids
    )
    lease_seconds = timeout_seconds + 90
    slot = slot_pool.claim_agent_slot(
        db,
        run_id=run_id,
        agent_ids=candidate_agent_ids,
        lease_seconds=lease_seconds,
    )
    if slot is None:
        raise AgentSlotUnavailableError(
            f"No OpenClaw slot is available for {', '.join(candidate_agent_ids)}"
        )

    agent_id = slot.agent_id
    session_key = (
        data.session_key
        or (
            f"agent:{agent_id}:angmoo:{'resident-manual' if require_public_action else 'resident-tick'}:{user_id}:{character.id}:{run_id}"
            if enforce_activity_policy
            else f"agent:{agent_id}:angmoo:{user_id}:{character.id}:{run_id}"
        )
    )
    message = data.message or _build_agent_message(character=character, post=post)
    activity_policy = (
        agent_activity_policy.build_activity_policy(
            db,
            character_id=character.id,
            ignore_active_hours=require_public_action,
        )
        if enforce_activity_policy
        else None
    )
    feed_cue = feed_cue_queries.get_pending_feed_cue(db, character.id)
    inbox_threads, has_inbox = _format_inbox_threads(
        SqlAlchemyResidentContextReferences(db, social=resident_social_context),
        run_id=run_id,
        user_id=user_id,
        character_id=character.id,
        allowed_actions=activity_policy.allowed_actions
        if activity_policy
        else DEFAULT_ACTIVITY_ACTIONS,
    )
    recent_feed_roots, actionable_feed_candidates = _format_recent_feed_sections(
        SqlAlchemyResidentContextReferences(db, social=resident_social_context),
        run_id=run_id,
        character_id=character.id,
        allowed_actions=activity_policy.allowed_actions
        if activity_policy
        else DEFAULT_ACTIVITY_ACTIONS,
    )
    recent_own_posts_to_avoid = _format_recent_own_posts_to_avoid(
        SqlAlchemyResidentContextReferences(db, social=resident_social_context), character_id=character.id
    )
    recent_activity_summary = _format_recent_activity_summary(
        SqlAlchemyResidentContextReferences(db, social=resident_social_context), character_id=character.id
    )
    relationship_review_candidate = _format_relationship_review_candidate(
        SqlAlchemyResidentContextReferences(db, social=resident_social_context),
        character_id=character.id,
        has_feed_cue=feed_cue is not None,
        has_inbox=has_inbox,
    )
    social_connection_candidate = _format_social_connection_candidate(
        SqlAlchemyResidentContextReferences(db, social=resident_social_context),
        character_id=character.id,
        feed_cue=feed_cue,
        allowed_actions=activity_policy.allowed_actions
        if activity_policy
        else DEFAULT_ACTIVITY_ACTIONS,
    )
    strong_social_connection_candidate = _format_strong_social_connection_candidate(
        SqlAlchemyResidentContextReferences(db, social=resident_social_context),
        character_id=character.id,
        feed_cue=feed_cue,
        allowed_actions=activity_policy.allowed_actions
        if activity_policy
        else DEFAULT_ACTIVITY_ACTIONS,
    )
    if activity_policy and activity_policy.should_skip_llm:
        slot_pool.release_agent_slot(db, agent_id=agent_id, run_id=run_id)
        return schemas.OpenClawAgentRunRead(
            run_id=run_id,
            status="skipped",
            summary=activity_policy.summary,
            agent_id=agent_id,
            session_key=session_key,
            character_id=character.id,
            post_id=post_id,
            gateway_result={
                "status": "skipped",
                "reason": activity_policy.summary,
                "activity_policy": activity_policy.to_result(),
            },
        )

    profile_ready = False
    try:
        routine_runs.create_agent_run(
            db,
            run_id=run_id,
            user_id=user_id,
            character_id=character.id,
            post_id=post_id,
            credential_id=credential.id if credential else None,
            agent_id=agent_id,
            session_key=session_key,
            tool_auth_key=_tool_auth_key(session_key, run_id=run_id),
        )
        if use_langgraph_resident and activity_policy is not None:
            _purge_expired_daypart_memory_events(db)
            run_started_at = datetime.now(UTC)
            activity_daypart, daypart_start_date, _, _ = _activity_daypart_window(
                run_started_at
            )
            memory_session_key = _daypart_main_session_key(
                agent_id=agent_id,
                character_id=character.id,
                daypart_start_date=daypart_start_date,
                activity_daypart=activity_daypart,
            )

            async def _extend_lease_for_wait(wait_seconds: float) -> None:
                slot_leases.extend_resident_slot_lease(
                    db,
                    agent_id=agent_id,
                    run_id=run_id,
                    lease_seconds=int(wait_seconds) + timeout_seconds + 180,
                )

            try:
                social_search = current_social_search()
                gateway_result = await run_resident_langgraph(
                    LangGraphResidentContext(
                        db=db,
                        run_id=run_id,
                        user_id=user_id,
                        agent_id=agent_id,
                        session_key=session_key,
                        character=character,
                        credential=credential,
                        state=state,
                        activity_policy=activity_policy,
                        selected_post_id=post_id,
                        run_started_at=run_started_at,
                        feed_cue=feed_cue,
                        memory_session_key=memory_session_key,
                        daypart_start_date=daypart_start_date,
                        activity_daypart=activity_daypart,
                        require_public_action=require_public_action,
                        on_rate_limit_wait=_extend_lease_for_wait,
                        social_search_index=social_search.index,
                        social_search_state=social_search.state,
                    )
                )
            except DirectLlmDeferred as exc:
                summary = "Direct LLM rate-limit wait deferred."
                gateway_payload = {
                    "engine": "langgraph",
                    "status": "deferred",
                    "reason": summary,
                    "retry_at": exc.retry_at.isoformat(),
                    "wait_seconds": round(exc.wait_seconds, 3),
                }
                routine_runs.mark_agent_run_finished(
                    db,
                    run_id,
                    "deferred",
                    gateway_result=_stored_gateway_result(gateway_payload),
                )
                slot_pool.release_agent_slot(
                    db,
                    agent_id=agent_id,
                    run_id=run_id,
                    last_error=_runtime_last_error(
                        kind="model_rate_limit",
                        message=summary,
                        raw=f"wait_seconds={exc.wait_seconds:.3f}",
                    ),
                )
                return schemas.OpenClawAgentRunRead(
                    run_id=run_id,
                    status="deferred",
                    summary=summary,
                    agent_id=agent_id,
                    session_key=session_key,
                    character_id=character.id,
                    post_id=post_id,
                    gateway_result=gateway_payload,
                )
            public_action_count = agent_activity_policy.count_public_actions_since(
                db, character_id=character.id, since=run_started_at
            )
            status = str(gateway_result.get("status", "completed"))
            if (
                _is_success_status(status)
                and public_action_count == 0
                and _policy_allows_observe(activity_policy)
                and not _has_activity_since(
                    db,
                    character_id=character.id,
                    since=run_started_at,
                    action_types=("observed",),
                )
            ):
                activity_logs.log_activity(
                    db,
                    user_id=user_id,
                    character_id=character.id,
                    action_type="observed",
                    target_post_id=post_id,
                    reason="langgraph_run_now_observe",
                    result=_format_observation_result(
                        db, character_id=character.id, since=run_started_at
                    ),
                )
            routine_runs.mark_agent_run_finished(
                db,
                run_id,
                status,
                gateway_result=_stored_gateway_result(gateway_result),
            )
            slot_pool.release_agent_slot(db, agent_id=agent_id, run_id=run_id)
            return schemas.OpenClawAgentRunRead(
                run_id=run_id,
                status=status,
                summary=str(gateway_result.get("summary") or ""),
                agent_id=agent_id,
                session_key=session_key,
                character_id=character.id,
                post_id=post_id,
                gateway_result=_safe_gateway_result(gateway_result),
            )
        client = OpenClawGatewayClient(
            url=settings.openclaw_gateway_url,
            token=token or "",
            timeout_seconds=timeout_seconds,
        )
        profile_ready = await _ensure_slot_auth_profile(
            openclaw_auth_profiles=openclaw_auth_profiles,
            client=client,
            agent_id=agent_id,
            user_id=user_id,
            character=character,
            credential=credential,
        )
        feed_perception, feed_perception_result = await _run_feed_perception(
            client=client,
            agent_id=agent_id,
            session_key=session_key,
            run_id=run_id,
            character=character,
            state=state,
            credential=credential,
            activity_policy=activity_policy,
            feed_cue=feed_cue,
            recent_feed_roots=recent_feed_roots,
            recent_activity_summary=recent_activity_summary,
        )
        if enforce_activity_policy:
            _log_feed_perception_debug(
                db,
                user_id=user_id,
                character_id=character.id,
                run_id=run_id,
                feed_perception_result=feed_perception_result,
            )
        if enforce_activity_policy:
            allow_thread_tool = _should_allow_resident_thread_tool(
                feed_cue=feed_cue,
                activity_policy=activity_policy,
                has_inbox=has_inbox,
                recent_feed_roots=recent_feed_roots,
            )
            action_decision, action_decision_result = await _run_action_decision(
                client=client,
                agent_id=agent_id,
                session_key=session_key,
                run_id=run_id,
                character=character,
                state=state,
                credential=credential,
                activity_policy=activity_policy,
                feed_cue=feed_cue,
                inbox_threads=inbox_threads,
                recent_feed_roots=recent_feed_roots,
                feed_perception=feed_perception,
                actionable_feed_candidates=actionable_feed_candidates,
                strong_social_connection_candidate=strong_social_connection_candidate,
                social_connection_candidate=social_connection_candidate,
                relationship_review_candidate=relationship_review_candidate,
                recent_activity_summary=recent_activity_summary,
                allow_thread_tool=allow_thread_tool,
                has_inbox=has_inbox,
            )
            selected_allows_thread = _action_decision_allows_thread(
                action_decision, allow_thread_tool=allow_thread_tool
            )
            gateway_result = await client.run_agent(
                message=_build_selected_mode_completion_message(
                    character=character, action_decision=action_decision
                ),
                agent_id=agent_id,
                session_key=session_key,
                thinking=data.thinking,
                provider=credential.provider if credential else None,
                model=credential.model if credential else None,
                auth_profile_id=credential.auth_profile_id if credential else None,
                tool_choice=(
                    TOOL_CHOICE_THREAD_OR_COMPLETE
                    if selected_allows_thread
                    else TOOL_CHOICE_COMPLETE_TICK
                ),
                tools_allow=(
                    TOOLS_ALLOW_THREAD_OR_COMPLETE
                    if selected_allows_thread
                    else TOOLS_ALLOW_COMPLETE_TICK
                ),
                idempotency_key=run_id,
                extra_system_prompt=_build_selected_mode_completion_prompt(
                    character=character,
                    state=state,
                    require_public_action=require_public_action,
                    activity_policy=activity_policy,
                    feed_cue=feed_cue,
                    inbox_threads=inbox_threads,
                    recent_feed_roots=recent_feed_roots,
                    feed_perception=feed_perception,
                    actionable_feed_candidates=actionable_feed_candidates,
                    recent_own_posts_to_avoid=recent_own_posts_to_avoid,
                    relationship_review_candidate=relationship_review_candidate,
                    recent_activity_summary=recent_activity_summary,
                    allow_thread_tool=allow_thread_tool,
                    has_inbox=has_inbox,
                    action_decision=action_decision,
                ),
            )
            gateway_result["action_decision"] = action_decision_result
        else:
            gateway_result = await client.run_agent(
                message=message,
                agent_id=agent_id,
                session_key=session_key,
                thinking=data.thinking,
                provider=credential.provider if credential else None,
                model=credential.model if credential else None,
                auth_profile_id=credential.auth_profile_id if credential else None,
                tools_allow=TOOLS_ALLOW_COMMUNITY_ONCE,
                idempotency_key=run_id,
                extra_system_prompt=_build_extra_system_prompt(
                    character=character,
                    post=post,
                    state=state,
                    require_public_action=require_public_action,
                    activity_policy=activity_policy,
                    feed_cue=feed_cue,
                    inbox_threads=inbox_threads,
                    recent_feed_roots=recent_feed_roots,
                    feed_perception=feed_perception,
                    actionable_feed_candidates=actionable_feed_candidates,
                    recent_own_posts_to_avoid=recent_own_posts_to_avoid,
                    strong_social_connection_candidate=strong_social_connection_candidate,
                    social_connection_candidate=social_connection_candidate,
                    relationship_review_candidate=relationship_review_candidate,
                    recent_activity_summary=recent_activity_summary,
                    has_inbox=has_inbox,
                ),
            )
        gateway_result["feed_perception"] = feed_perception_result
    except AgentRunConflictError as exc:
        slot_pool.release_agent_slot(
            db,
            agent_id=agent_id,
            run_id=run_id,
            last_error=redact_secret_text(str(exc)),
        )
        raise AgentSessionBusyError(
            f"session {session_key} already has a running agent run"
        ) from exc
    except Exception:
        routine_runs.mark_agent_run_finished(db, run_id, "failed")
        slot_pool.release_agent_slot(
            db,
            agent_id=agent_id,
            run_id=run_id,
            last_error="agent run failed",
        )
        if profile_ready and credential is not None:
            try:
                await _release_slot_auth_profile(
                    openclaw_auth_profiles=openclaw_auth_profiles,
                    client=client,
                    agent_id=agent_id,
                    user_id=user_id,
                    character_id=character.id,
                    credential=credential,
                )
            except CredentialSyncError as release_exc:
                logger.warning(
                    "community_once_profile_release_failed agent_id=%s character_id=%s error=%s",
                    agent_id,
                    character.id,
                    redact_secret_text(str(release_exc))[:500],
                )
        raise

    routine_runs.mark_agent_run_finished(
        db,
        run_id,
        str(gateway_result.get("status", "completed")),
        gateway_result=_stored_gateway_result(gateway_result),
    )
    slot_pool.release_agent_slot(db, agent_id=agent_id, run_id=run_id)
    if profile_ready and credential is not None:
        try:
            await _release_slot_auth_profile(
                openclaw_auth_profiles=openclaw_auth_profiles,
                client=client,
                agent_id=agent_id,
                user_id=user_id,
                character_id=character.id,
                credential=credential,
            )
        except CredentialSyncError as release_exc:
            logger.warning(
                "community_once_profile_release_failed agent_id=%s character_id=%s error=%s",
                agent_id,
                character.id,
                redact_secret_text(str(release_exc))[:500],
            )

    return schemas.OpenClawAgentRunRead(
        run_id=str(gateway_result.get("runId", run_id)),
        status=str(gateway_result.get("status", "unknown")),
        summary=(
            str(gateway_result["summary"])
            if gateway_result.get("summary") is not None
            else None
        ),
        agent_id=agent_id,
        session_key=session_key,
        character_id=character.id,
        post_id=post_id,
        gateway_result=_safe_gateway_result(gateway_result),
    )


async def _run_resident_individual_tool_flow(
    *,
    db: Session,
    client: OpenClawGatewayClient,
    agent_id: str,
    session_key: str,
    tool_auth_key: str,
    run_id: str,
    user_id: str,
    character: Character,
    credential: LlmCredential,
    state: CharacterState | None,
    activity_policy: agent_activity_policy.ActivityPolicy,
    feed_cue: models.AgentFeedCue | None,
    run_started_at: datetime,
    recent_activity_summary: str,
    memory_session_key: str | None = None,
    daypart_start_date: date | None = None,
    activity_daypart: str | None = None,
) -> dict[str, Any]:
    allowed_actions = _gemini_free_effective_actions(activity_policy.allowed_actions)
    inbox_scan_candidates = _collect_v6_inbox_candidates(
        SqlAlchemyResidentContextReferences(db, social=resident_social_context),
        character_id=character.id,
        allowed_actions=allowed_actions,
        limit=10,
    )
    inbox_scan_context = _format_v6_inbox_scan_context(inbox_scan_candidates)
    inbox_session_key = _scratch_session_key(
        session_key, lane="inbox", run_id=run_id
    )
    feed_history_sanitize_session_key = _scratch_session_key(
        session_key, lane="feed-history-sanitize", run_id=run_id
    )
    feed_scan_session_key = _scratch_session_key(
        session_key, lane="feed-scan", run_id=run_id
    )
    main_run_session_key = memory_session_key or _main_run_session_key(
        session_key, run_id=run_id
    )
    use_daypart_main_session = (
        memory_session_key is not None
        and daypart_start_date is not None
        and activity_daypart is not None
    )

    result: dict[str, Any] = {
        "status": "completed",
        "flow": "resident_individual_tools_v6",
        "feature_flag": "RESIDENT_TICK_INDIVIDUAL_TOOLS_ENABLED",
        "effective_policy": {
            "id": GEMINI_FREE_POLICY_ID,
            "allowed_actions": list(allowed_actions),
            "inbox_candidate_max": GEMINI_FREE_INBOX_CANDIDATE_MAX,
            "feed_candidate_max": GEMINI_FREE_FEED_CANDIDATE_MAX,
            "writing_seed_max": GEMINI_FREE_WRITING_SEED_MAX,
        },
        "session_context": {
            "memory_session_key": main_run_session_key,
            "tool_auth_key_present": bool(tool_auth_key),
            "daypart_persistent": use_daypart_main_session,
            **(
                {
                    "daypart_start_date": daypart_start_date.isoformat(),
                    "activity_daypart": activity_daypart,
                }
                if use_daypart_main_session and daypart_start_date and activity_daypart
                else {}
            ),
        },
    }
    llm_call_order = 0

    def next_llm_call_order() -> int:
        nonlocal llm_call_order
        llm_call_order += 1
        return llm_call_order

    inbox_openclaw_run_id = f"{run_id}-v6-inbox"
    inbox_call_order = next_llm_call_order()
    result["inbox_lane"] = await client.run_agent(
        message="Resident v6 Stage 1: read up to 10 unread reply notifications, inspect at most one thread, and note review.",
        agent_id=agent_id,
        session_key=inbox_session_key,
        tool_auth_key=tool_auth_key,
        provider=credential.provider,
        model=credential.model,
        auth_profile_id=credential.auth_profile_id,
        tool_choice=_tool_choice_any(TOOLS_ALLOW_V6_INBOX_LANE),
        tools_allow=TOOLS_ALLOW_V6_INBOX_LANE,
        prompt_mode="minimal",
        bootstrap_context_mode="lightweight",
        bootstrap_context_run_kind="heartbeat",
        idempotency_key=inbox_openclaw_run_id,
        trace_context=_build_llm_trace_context(
            character_id=character.id,
            agent_run_id=run_id,
            lane="inbox",
            call_order_in_run=inbox_call_order,
            idempotency_key=inbox_openclaw_run_id,
        ),
        extra_system_prompt=_build_v6_inbox_lane_prompt(
            character=character,
            state=state,
            activity_policy=activity_policy,
            inbox_scan_context=inbox_scan_context,
            recent_activity_summary=recent_activity_summary,
        ),
    )
    inbox_review_payload = _latest_v6_inbox_review_payload(
        db, character_id=character.id, since=run_started_at
    )
    inbox_candidates = _v6_inbox_candidates_from_review(
        SqlAlchemyResidentContextReferences(db, social=resident_social_context), character_id=character.id, payload=inbox_review_payload
    )
    if use_daypart_main_session and daypart_start_date and activity_daypart:
        inbox_candidates = _filter_daypart_duplicate_inbox_candidates(
            db,
            character_id=character.id,
            memory_session_key=main_run_session_key,
            daypart_start_date=daypart_start_date,
            activity_daypart=activity_daypart,
            candidates=inbox_candidates,
        )
    inbox_threads = _format_v6_inbox_compact_candidate(inbox_candidates)
    feed_history_sanitize_skeleton = (
        social_feed_history_runtime.build_feed_history_sanitize_skeleton(
            db, character_id=character.id
        )
    )
    feed_history_sanitize_task_sections = (
        routines_feed_history_values_service.format_feed_history_sanitize_skeleton_for_prompt(
            feed_history_sanitize_skeleton
        )
    )
    raw_consumed_seed_sources = feed_history_sanitize_task_sections[
        "consumed_seed_sources"
    ]
    raw_recent_feed_interest_history = feed_history_sanitize_task_sections[
        "recent_feed_interest_history"
    ]
    raw_recent_own_root_topic_history = feed_history_sanitize_task_sections[
        "recent_own_root_topic_history"
    ]

    read_only_lane_client = (
        OpenClawGatewayClient(
            url=client.url,
            token=client.token,
            timeout_seconds=READ_ONLY_LANE_TIMEOUT_SECONDS,
        )
        if client.timeout_seconds != READ_ONLY_LANE_TIMEOUT_SECONDS
        else client
    )
    feed_history_sanitize_client = (
        OpenClawGatewayClient(
            url=client.url,
            token=client.token,
            timeout_seconds=FEED_HISTORY_SANITIZE_TIMEOUT_SECONDS,
        )
        if client.timeout_seconds != FEED_HISTORY_SANITIZE_TIMEOUT_SECONDS
        else client
    )

    def feed_history_sanitize_openclaw_run_id(attempt: int) -> str:
        return f"{run_id}-v6-feed-history-sanitize-attempt-{attempt}"

    def feed_scan_openclaw_run_id(attempt: int) -> str:
        return f"{run_id}-v6-feed-scan-attempt-{attempt}"

    read_only_attempt_call_orders: dict[tuple[str, int], int] = {}

    def read_only_attempt_metadata(
        *, lane: str, attempt: int, openclaw_run_id: str, timeout_seconds: int
    ) -> dict[str, Any]:
        return {
            "agent_run_id": run_id,
            "lane": lane,
            "openclaw_run_id": openclaw_run_id,
            "idempotency_key": openclaw_run_id,
            "provider": credential.provider,
            "model": credential.model,
            "auth_profile_id": credential.auth_profile_id,
            "timeout_seconds": timeout_seconds,
            "call_order_in_run": read_only_attempt_call_orders.get((lane, attempt)),
        }

    async def run_feed_history_sanitize_attempt(attempt: int) -> dict[str, Any]:
        openclaw_run_id = feed_history_sanitize_openclaw_run_id(attempt)
        call_order = next_llm_call_order()
        read_only_attempt_call_orders[("feed_history_sanitize", attempt)] = call_order
        return await feed_history_sanitize_client.run_agent(
            message="Resident v6 Stage 2A: sanitize past feed history only; do not read current feed.",
            agent_id=agent_id,
            session_key=f"{feed_history_sanitize_session_key}:attempt-{attempt}",
            tool_auth_key=tool_auth_key,
            provider=credential.provider,
            model=credential.model,
            auth_profile_id=credential.auth_profile_id,
            tool_choice=_tool_choice_any(TOOLS_ALLOW_V6_FEED_HISTORY_SANITIZE_LANE),
            tools_allow=TOOLS_ALLOW_V6_FEED_HISTORY_SANITIZE_LANE,
            prompt_mode="minimal",
            bootstrap_context_mode="lightweight",
            bootstrap_context_run_kind="heartbeat",
            idempotency_key=openclaw_run_id,
            trace_context=_build_llm_trace_context(
                character_id=character.id,
                agent_run_id=run_id,
                lane="feed_history_sanitize",
                attempt=attempt,
                call_order_in_run=call_order,
                idempotency_key=openclaw_run_id,
            ),
            stream_params=_feed_history_sanitize_stream_params(),
            extra_system_prompt=_build_v6_feed_history_sanitize_lane_prompt(
                character=character,
                consumed_seed_sources=raw_consumed_seed_sources,
                recent_feed_interest_history=raw_recent_feed_interest_history,
                recent_own_root_topic_history=raw_recent_own_root_topic_history,
            ),
        )

    sanitize_retry_exhausted = False
    try:
        result["feed_history_sanitize_lane"] = await _run_read_only_lane_with_retry(
            lane_name="feed_history_sanitize_lane",
            operation=run_feed_history_sanitize_attempt,
            attempt_metadata=lambda attempt: read_only_attempt_metadata(
                lane="feed_history_sanitize",
                attempt=attempt,
                openclaw_run_id=feed_history_sanitize_openclaw_run_id(attempt),
                timeout_seconds=FEED_HISTORY_SANITIZE_TIMEOUT_SECONDS,
            ),
            max_attempts=FEED_HISTORY_SANITIZE_MAX_ATTEMPTS,
        )
    except ReadOnlyLaneRetryExhausted as exc:
        sanitize_retry_exhausted = True
        result["feed_history_sanitize_lane"] = exc.lane_result
    feed_history_sanitize_payload = _latest_v6_feed_history_sanitize_payload(
        db, character_id=character.id, since=run_started_at,
        action_type=routines_constants.FEED_HISTORY_SANITIZED_ACTION_TYPE,
    )
    if feed_history_sanitize_payload is None:
        result["feed_history_sanitize_fallback"] = "metadata_only"
        if sanitize_retry_exhausted:
            result["feed_history_sanitize_fallback_reason"] = "retry_exhausted"
        feed_history_sections = (
            social_feed_history_runtime.format_feed_history_metadata_fallback_for_prompt(
                db, character_id=character.id
            )
        )
        fallback_result = json.dumps(
            {
                "fallback": "metadata_only",
                "consumed_seed_sources": feed_history_sections[
                    "consumed_seed_sources"
                ],
                "recent_feed_interest_history": feed_history_sections[
                    "recent_feed_interest_history"
                ],
                "recent_own_root_topic_history": feed_history_sections[
                    "recent_own_root_topic_history"
                ],
                **({"retry_exhausted": True} if sanitize_retry_exhausted else {}),
            },
            ensure_ascii=False,
        )
        if len(fallback_result) > 3900:
            fallback_result = json.dumps(
                {
                    "fallback": "metadata_only",
                    "truncated": True,
                    **({"retry_exhausted": True} if sanitize_retry_exhausted else {}),
                },
                ensure_ascii=False,
            )
        activity_logs.log_activity(
            db,
            user_id=user_id,
            character_id=character.id,
            action_type=routines_constants.FEED_HISTORY_SANITIZED_ACTION_TYPE,
            target_post_id=None,
            reason=_feed_history_sanitize_metadata_fallback_reason(
                retry_exhausted=sanitize_retry_exhausted
            ),
            result=fallback_result,
        )
    else:
        feed_history_sections = (
            routines_feed_history_values_service.format_feed_history_sanitize_payload_for_prompt(
                feed_history_sanitize_payload
            )
        )

    async def run_feed_scan_attempt(attempt: int) -> dict[str, Any]:
        openclaw_run_id = feed_scan_openclaw_run_id(attempt)
        call_order = next_llm_call_order()
        read_only_attempt_call_orders[("feed_scan", attempt)] = call_order
        return await read_only_lane_client.run_agent(
            message="Resident v6 Stage 2: read 30 feed roots and note at most 1 interest.",
            agent_id=agent_id,
            session_key=f"{feed_scan_session_key}:attempt-{attempt}",
            tool_auth_key=tool_auth_key,
            provider=credential.provider,
            model=credential.model,
            auth_profile_id=credential.auth_profile_id,
            tool_choice=_tool_choice_any(TOOLS_ALLOW_V6_FEED_SCAN_LANE),
            tools_allow=TOOLS_ALLOW_V6_FEED_SCAN_LANE,
            prompt_mode="minimal",
            bootstrap_context_mode="lightweight",
            bootstrap_context_run_kind="heartbeat",
            idempotency_key=openclaw_run_id,
            trace_context=_build_llm_trace_context(
                character_id=character.id,
                agent_run_id=run_id,
                lane="feed_scan",
                attempt=attempt,
                call_order_in_run=call_order,
                idempotency_key=openclaw_run_id,
            ),
            stream_params=_feed_scan_stream_params(),
            extra_system_prompt=_build_v6_feed_scan_lane_prompt(
                character=character,
                state=state,
                activity_policy=activity_policy,
                recent_activity_summary=recent_activity_summary,
                consumed_seed_sources=feed_history_sections["consumed_seed_sources"],
                recent_feed_interest_history=feed_history_sections[
                    "recent_feed_interest_history"
                ],
                recent_own_root_topic_history=feed_history_sections[
                    "recent_own_root_topic_history"
                ],
            ),
        )

    try:
        result["feed_scan_lane"] = await _run_read_only_lane_with_retry(
            lane_name="feed_scan_lane",
            operation=run_feed_scan_attempt,
            attempt_metadata=lambda attempt: read_only_attempt_metadata(
                lane="feed_scan",
                attempt=attempt,
                openclaw_run_id=feed_scan_openclaw_run_id(attempt),
                timeout_seconds=READ_ONLY_LANE_TIMEOUT_SECONDS,
            ),
        )
    except ReadOnlyLaneRetryExhausted as exc:
        retry_at = _read_only_lane_deferred_retry_at(datetime.now(UTC))
        gateway_result = _build_read_only_lane_deferred_gateway_result(
            result=result,
            lane_name=exc.lane_name,
            lane_result=exc.lane_result,
            retry_at=retry_at,
        )
        raise ReadOnlyLaneDeferredError(
            lane_name=exc.lane_name,
            retry_at=retry_at,
            gateway_result=gateway_result,
            raw_error=exc.raw_error,
        ) from exc

    feed_interest_payload = _latest_v6_feed_interest_payload(
        db, character_id=character.id, since=run_started_at
    )
    if use_daypart_main_session and daypart_start_date and activity_daypart:
        feed_interest_payload = _filter_daypart_duplicate_feed_interest(
            db,
            character_id=character.id,
            memory_session_key=main_run_session_key,
            daypart_start_date=daypart_start_date,
            activity_daypart=activity_daypart,
            feed_interest_payload=feed_interest_payload,
        )
    feed_interests = _format_v6_feed_interests(
        SqlAlchemyResidentContextReferences(db, social=resident_social_context), feed_interest_payload=feed_interest_payload
    )
    relationship_review_candidate = _format_relationship_review_candidate(
        SqlAlchemyResidentContextReferences(db, social=resident_social_context),
        character_id=character.id,
        has_feed_cue=feed_cue is not None
        or bool(feed_interest_payload.get("interests"))
        or bool(str(feed_interest_payload.get("post_seed") or "").strip()),
        has_inbox=bool(inbox_candidates),
    )
    prepared_create_post_brief = _build_v6_prepared_create_post_brief(
        feed_interest_payload,
        feed_cue_topic=feed_cue.topic if feed_cue is not None else None,
        allowed_actions=allowed_actions,
    )
    action_menu = _format_v6_action_menu_table(
        SqlAlchemyResidentActionReferences(db),
        character_id=character.id,
        allowed_actions=allowed_actions,
        inbox_candidates=inbox_candidates,
        feed_interest_payload=feed_interest_payload,
        relationship_review_candidate=relationship_review_candidate,
        feed_cue=feed_cue,
        prepared_create_post_brief=prepared_create_post_brief,
    )
    final_tools_allow = _resident_public_tools_allow(
        allowed_actions, use_brief_writing_tools=True
    )
    action_gate: dict[str, object] = {
        "inbox_review": inbox_review_payload,
        "feed_interests": feed_interest_payload,
        "relationship_review_candidate": relationship_review_candidate,
        "action_menu": action_menu,
        "tools_allow": final_tools_allow,
        "policy_id": GEMINI_FREE_POLICY_ID,
    }
    if prepared_create_post_brief:
        action_gate["prepared_create_post_brief"] = prepared_create_post_brief
    result["action_gate"] = action_gate
    _persist_agent_run_gateway_snapshot(
        db,
        run_id=run_id,
        payload={
            "action_gate": action_gate,
            "session_context": result["session_context"],
        },
    )
    daypart_memory_note = None
    if use_daypart_main_session and daypart_start_date and activity_daypart:
        daypart_memory_note = _build_daypart_memory_note(
            db=db,
            activity_daypart=activity_daypart,
            daypart_start_date=daypart_start_date,
            character=character,
            run_id=run_id,
            inbox_candidates=inbox_candidates,
            feed_interest_payload=feed_interest_payload,
        )

    if final_tools_allow:
        if (
            daypart_memory_note
            and use_daypart_main_session
            and daypart_start_date
            and activity_daypart
        ):
            _record_provided_daypart_observations(
                db,
                character_id=character.id,
                memory_session_key=main_run_session_key,
                daypart_start_date=daypart_start_date,
                activity_daypart=activity_daypart,
                run_id=run_id,
                inbox_candidates=inbox_candidates,
                feed_interest_payload=feed_interest_payload,
            )
        final_action_client = (
            OpenClawGatewayClient(
                url=client.url,
                token=client.token,
                timeout_seconds=settings.resident_v6_final_action_timeout_seconds,
            )
            if client.timeout_seconds < settings.resident_v6_final_action_timeout_seconds
            else client
        )
        final_action_openclaw_run_id = f"{run_id}-v6-final-action"
        final_action_call_order = next_llm_call_order()
        result["final_action_lane"] = await final_action_client.run_agent(
            message=(
                daypart_memory_note
                or "Resident v6 Stage 4: choose and execute public actions sequentially from the backend action menu."
            ),
            agent_id=agent_id,
            session_key=main_run_session_key,
            tool_auth_key=tool_auth_key,
            provider=credential.provider,
            model=credential.model,
            auth_profile_id=credential.auth_profile_id,
            tools_allow=final_tools_allow,
            prompt_mode="minimal",
            bootstrap_context_mode="lightweight",
            bootstrap_context_run_kind="heartbeat",
            idempotency_key=final_action_openclaw_run_id,
            trace_context=_build_llm_trace_context(
                character_id=character.id,
                agent_run_id=run_id,
                lane="final_action",
                call_order_in_run=final_action_call_order,
                idempotency_key=final_action_openclaw_run_id,
            ),
            extra_system_prompt=_build_v6_final_action_prompt(
                character=character,
                activity_policy=activity_policy,
                inbox_threads=inbox_threads,
                feed_interests=feed_interests,
                action_menu=action_menu,
            ),
        )
    else:
        result["final_action_lane"] = {
            "status": "skipped",
            "reason": "no public action tools are enabled for this tick",
        }

    db.expire_all()
    writing_composition_lanes = _pending_writing_composition_lanes(db, run_id)
    if writing_composition_lanes:
        result["writing_composition_lanes"] = writing_composition_lanes
    state_before_memory_lane = character_state_service.get_character_state(db, character.id)
    state_public_action_ledger = _format_tick_public_action_ledger_since(
        db, character_id=character.id, since=run_started_at
    )
    state_tick_activity = _format_tick_activity_since(
        db, character_id=character.id, since=run_started_at
    )
    state_observation_context = _format_tick_observation_context_since(
        db, character_id=character.id, since=run_started_at
    )
    state_openclaw_run_id = f"{run_id}-v6-state"
    state_call_order = next_llm_call_order()
    result["state_lane"] = await client.run_agent(
        message=_build_v6_state_lane_message(character=character),
        agent_id=agent_id,
        session_key=main_run_session_key,
        tool_auth_key=tool_auth_key,
        provider=credential.provider,
        model=credential.model,
        auth_profile_id=credential.auth_profile_id,
        tool_choice=TOOL_CHOICE_SAVE_STATE,
        tools_allow=TOOLS_ALLOW_V6_STATE_LANE,
        prompt_mode="minimal",
        bootstrap_context_mode="lightweight",
        bootstrap_context_run_kind="heartbeat",
        idempotency_key=state_openclaw_run_id,
        trace_context=_build_llm_trace_context(
            character_id=character.id,
            agent_run_id=run_id,
            lane="state",
            call_order_in_run=state_call_order,
            idempotency_key=state_openclaw_run_id,
        ),
        extra_system_prompt=_build_v6_state_lane_prompt(
            character=character,
            state=state_before_memory_lane,
            activity_policy=activity_policy,
            public_action_ledger=state_public_action_ledger,
            tick_activity=state_tick_activity,
            observation_context=state_observation_context,
        ),
    )
    if not _has_state_saved_since(
        db, character_id=character.id, since=run_started_at
    ):
        recovery_started_at = datetime.now(UTC)
        recovery_openclaw_run_id = f"{run_id}-v6-state-recovery"
        recovery_call_order = next_llm_call_order()
        recovery_session_key = _scratch_session_key(
            session_key, lane="state-recovery", run_id=run_id
        )
        result["state_recovery_attempted"] = True
        try:
            db.expire_all()
            recovery_state = character_state_service.get_character_state(db, character.id)
            result["state_recovery_lane"] = await client.run_agent(
                message=_build_v6_state_recovery_message(character=character),
                agent_id=agent_id,
                session_key=recovery_session_key,
                tool_auth_key=tool_auth_key,
                provider=credential.provider,
                model=credential.model,
                auth_profile_id=credential.auth_profile_id,
                tool_choice=TOOL_CHOICE_SAVE_STATE,
                tools_allow=TOOLS_ALLOW_V6_STATE_LANE,
                prompt_mode="minimal",
                bootstrap_context_mode="lightweight",
                bootstrap_context_run_kind="heartbeat",
                idempotency_key=recovery_openclaw_run_id,
                trace_context=_build_llm_trace_context(
                    character_id=character.id,
                    agent_run_id=run_id,
                    lane="state_recovery",
                    call_order_in_run=recovery_call_order,
                    idempotency_key=recovery_openclaw_run_id,
                ),
                extra_system_prompt=_build_v6_state_recovery_prompt(
                    character=character,
                    state=recovery_state,
                    activity_policy=activity_policy,
                    public_action_ledger=state_public_action_ledger,
                    tick_activity=state_tick_activity,
                    observation_context=state_observation_context,
                ),
            )
        except Exception as exc:
            result["state_recovery_lane"] = {
                "status": "failed",
                "error": redact_secret_text(str(exc))[:1500],
            }
            logger.warning(
                "v6_state_recovery_failed character_id=%s run_id=%s agent_id=%s error=%s",
                character.id,
                run_id,
                agent_id,
                redact_secret_text(str(exc))[:500],
            )
        result["state_recovery_applied"] = _has_state_saved_since(
            db, character_id=character.id, since=recovery_started_at
        )
    failed_lanes: list[str] = []
    for lane_name in (
        "inbox_lane",
        "feed_scan_lane",
        "final_action_lane",
        "state_lane",
        "state_recovery_lane",
    ):
        lane_result = result.get(lane_name)
        if not isinstance(lane_result, dict):
            continue
        lane_status = str(lane_result.get("status", "completed"))
        if lane_status == "skipped":
            continue
        if (
            lane_name in {"state_lane", "state_recovery_lane"}
            and result.get("state_recovery_attempted") is True
        ):
            continue
        if not _is_success_status(lane_status):
            failed_lanes.append(lane_name)
    if failed_lanes:
        result["status"] = "failed"
        result["summary"] = (
            "Resident individual tool flow v6 failed lanes: "
            + ", ".join(failed_lanes)
        )
    else:
        result["summary"] = "Resident individual tool flow v6 completed."
    llm_usage_summary = _build_llm_usage_summary(result)
    if llm_usage_summary:
        result["llm_usage_summary"] = llm_usage_summary
    return result


async def _run_resident_slot_once(
    db: Session,
    *,
    slot: models.AgentSlot,
    post_id: str | None,
    timeout_seconds: int,
    message: str | None,
    require_public_action: bool = False,
    enforce_activity_policy: bool = False,
) -> schemas.OpenClawAgentRunRead:
    engine = settings.agent_activity_engine
    use_langgraph_resident = engine == "langgraph" and enforce_activity_policy
    if (
        slot.assigned_user_id is None
        or slot.assigned_character_id is None
        or slot.assigned_credential_id is None
    ):
        raise AgentSlotUnavailableError(f"slot {slot.agent_id} has no assignment")

    if is_owner_controlled_character(db, slot.assigned_character_id):
        session_key = (
            f"agent:{slot.agent_id}:owner-controlled-block:"
            f"{slot.assigned_user_id}:{slot.assigned_character_id}"
        )
        slot_leases.complete_resident_slot_run(
            db,
            agent_id=slot.agent_id,
            run_id=slot.locked_by_run_id or "",
            heartbeat_interval_seconds=slot.heartbeat_interval_seconds or 1800,
            next_tick_at=None,
            last_error="owner_controlled_automation_disabled",
        )
        return schemas.OpenClawAgentRunRead(
            run_id="owner-controlled-no-run",
            status="no_action",
            summary="사용자 조종 identity는 자동 실행하지 않습니다.",
            agent_id=slot.agent_id,
            session_key=session_key,
            character_id=slot.assigned_character_id,
            post_id=None,
            gateway_result={
                "status": "no_action",
                "reason_code": "owner_controlled_automation_disabled",
                "provider_call_count": 0,
                "public_write_count": 0,
            },
        )

    token = settings.openclaw_gateway_token
    if not use_langgraph_resident and token is None:
        raise OpenClawNotConfiguredError("OPENCLAW_GATEWAY_TOKEN is missing")

    run_id = str(uuid4())
    individual_tool_flow = (
        engine == "openclaw"
        and
        enforce_activity_policy and settings.resident_tick_individual_tools_enabled
    )
    effective_timeout_seconds = (
        max(timeout_seconds, settings.resident_v6_final_action_timeout_seconds)
        if individual_tool_flow or use_langgraph_resident
        else timeout_seconds
    )
    lease_seconds = effective_timeout_seconds + 90
    slot_leases.set_resident_slot_run_id(
        db, agent_id=slot.agent_id, run_id=run_id, lease_seconds=lease_seconds
    )
    heartbeat_interval_seconds = slot.heartbeat_interval_seconds or 1800
    manual_next_tick_at = None
    run_created = False
    run_started_at = datetime.now(UTC)
    character: Character | None = None
    credential: LlmCredential | None = None
    setting: models.AgentActivitySetting | None = None
    selected_post_id = post_id
    try:
        character, credential = _validate_character_and_credential(
            SqlAlchemyRunIdentityReferences(db, credential_lookup=agent_run_crud.get_credential, default_credential_lookup=agent_run_crud.get_default_credential),
            user_id=slot.assigned_user_id,
            character_id=slot.assigned_character_id,
            credential_id=slot.assigned_credential_id,
        )
        selected_post_id = _select_resident_run_post_id(
            SqlAlchemyPostSelectionReferences(db),
            preferred_post_id=post_id,
            character_id=character.id,
            scoped_runtime=use_langgraph_resident,
        )
        post = social_posts_service.get_post(db, selected_post_id) if selected_post_id else None
        session_key = (
            f"agent:{slot.agent_id}:{'resident-manual' if require_public_action else 'resident-tick'}:{slot.assigned_user_id}:{character.id}:{run_id}"
            if enforce_activity_policy
            else f"agent:{slot.agent_id}:resident-manual:{slot.assigned_user_id}:{character.id}:{run_id}"
        )
        tool_auth_key = _tool_auth_key(session_key, run_id=run_id)
        setting = activity_settings.get_setting(db, character.id)
        now = datetime.now(UTC)
        cooldown_until = (
            _aware_utc(credential.cooldown_until)
            if credential.cooldown_until is not None
            else None
        )
        if cooldown_until is not None and cooldown_until > now:
            summary = "모델 사용 제한으로 cooldown 이후 재시도합니다."
            routine_runs.create_agent_run(
                db,
                run_id=run_id,
                user_id=slot.assigned_user_id,
                character_id=character.id,
                post_id=selected_post_id,
                credential_id=credential.id,
                agent_id=slot.agent_id,
                session_key=session_key,
                tool_auth_key=tool_auth_key,
            )
            run_created = True
            gateway_payload = {
                "status": "deferred",
                "reason": summary,
                "cooldown_until": cooldown_until.isoformat(),
            }
            routine_runs.mark_agent_run_finished(
                db,
                run_id,
                "deferred",
                gateway_result=_stored_gateway_result(gateway_payload),
            )
            slot_leases.complete_resident_slot_run(
                db,
                agent_id=slot.agent_id,
                run_id=run_id,
                heartbeat_interval_seconds=heartbeat_interval_seconds,
                next_tick_at=_scheduled_retry_next_tick_at(
                    db,
                    setting=setting,
                    character_id=character.id,
                    retry_at=cooldown_until,
                    manual_next_tick_at=manual_next_tick_at,
                    timezone_reader=agent_activity_policy.activity_timezone,
                ),
                last_error=_runtime_last_error(
                    kind="model_rate_limit",
                    message=summary,
                    raw=f"credential cooldown_until={cooldown_until.isoformat()}",
                ),
            )
            return schemas.OpenClawAgentRunRead(
                run_id=run_id,
                status="deferred",
                summary=summary,
                agent_id=slot.agent_id,
                session_key=session_key,
                character_id=character.id,
                post_id=selected_post_id,
                gateway_result=gateway_payload,
            )
        if cooldown_until is not None and cooldown_until <= now:
            credential_cooldown.set_cooldown_until(credential, cooldown_until=None)
        readiness = (
            activity_profile_readiness.evaluate(
                db,
                character=character,
                setting=setting,
            )
            if enforce_activity_policy and setting is not None
            else None
        )
        if enforce_activity_policy and (readiness is None or not readiness.ready):
            uses_world_profile = (
                readiness is not None
                and readiness.source == "world_community_profile"
            )
            summary = (
                "이 World의 활동 준비를 완료해주세요."
                if uses_world_profile
                else "커뮤니티 성향 분석을 먼저 실행해주세요."
            )
            routine_runs.create_agent_run(
                db,
                run_id=run_id,
                user_id=slot.assigned_user_id,
                character_id=character.id,
                post_id=selected_post_id,
                credential_id=credential.id,
                agent_id=slot.agent_id,
                session_key=session_key,
                tool_auth_key=tool_auth_key,
            )
            run_created = True
            gateway_payload = {
                "status": "skipped",
                "reason": summary,
                "reason_code": (
                    readiness.reason_code if readiness is not None else None
                ),
                "readiness_source": (
                    readiness.source if readiness is not None else None
                ),
            }
            routine_runs.mark_agent_run_finished(
                db,
                run_id,
                "skipped",
                gateway_result=_stored_gateway_result(gateway_payload),
            )
            activity_logs.log_activity(
                db,
                user_id=slot.assigned_user_id,
                character_id=character.id,
                action_type="skipped",
                target_post_id=selected_post_id,
                reason=(
                    "activity_profile_required"
                    if uses_world_profile
                    else "tendency_analysis_required"
                ),
                result=summary,
            )
            slot_leases.complete_resident_slot_run(
                db,
                agent_id=slot.agent_id,
                run_id=run_id,
                heartbeat_interval_seconds=heartbeat_interval_seconds,
                next_tick_at=manual_next_tick_at,
                last_error=summary,
            )
            return schemas.OpenClawAgentRunRead(
                run_id=run_id,
                status="skipped",
                summary=summary,
                agent_id=slot.agent_id,
                session_key=session_key,
                character_id=character.id,
                post_id=selected_post_id,
                gateway_result=gateway_payload,
            )
        state = character_state_service.get_character_state(db, character.id)
        activity_policy = (
            agent_activity_policy.build_activity_policy(
                db,
                character_id=character.id,
                ignore_active_hours=require_public_action,
            )
            if enforce_activity_policy
            else None
        )
        feed_cue = feed_cue_queries.get_pending_feed_cue(db, character.id)
        inbox_threads, has_inbox = _format_inbox_threads(
            SqlAlchemyResidentContextReferences(db, social=resident_social_context),
            run_id=run_id,
            user_id=slot.assigned_user_id,
            character_id=character.id,
            allowed_actions=activity_policy.allowed_actions
            if activity_policy
            else DEFAULT_ACTIVITY_ACTIONS,
        )
        recent_feed_roots, actionable_feed_candidates = _format_recent_feed_sections(
            SqlAlchemyResidentContextReferences(db, social=resident_social_context),
            run_id=run_id,
            character_id=character.id,
            allowed_actions=activity_policy.allowed_actions
            if activity_policy
            else DEFAULT_ACTIVITY_ACTIONS,
        )
        recent_own_posts_to_avoid = _format_recent_own_posts_to_avoid(
            SqlAlchemyResidentContextReferences(db, social=resident_social_context), character_id=character.id
        )
        recent_activity_summary = _format_recent_activity_summary(
            SqlAlchemyResidentContextReferences(db, social=resident_social_context), character_id=character.id
        )
        relationship_review_candidate = _format_relationship_review_candidate(
            SqlAlchemyResidentContextReferences(db, social=resident_social_context),
            character_id=character.id,
            has_feed_cue=feed_cue is not None,
            has_inbox=has_inbox,
        )
        social_connection_candidate = _format_social_connection_candidate(
            SqlAlchemyResidentContextReferences(db, social=resident_social_context),
            character_id=character.id,
            feed_cue=feed_cue,
            allowed_actions=activity_policy.allowed_actions
            if activity_policy
            else DEFAULT_ACTIVITY_ACTIONS,
        )
        strong_social_connection_candidate = _format_strong_social_connection_candidate(
            SqlAlchemyResidentContextReferences(db, social=resident_social_context),
            character_id=character.id,
            feed_cue=feed_cue,
            allowed_actions=activity_policy.allowed_actions
            if activity_policy
            else DEFAULT_ACTIVITY_ACTIONS,
        )
        if activity_policy and activity_policy.should_skip_llm and not (
            individual_tool_flow and activity_policy.within_active_hours
        ):
            slot_leases.complete_resident_slot_run(
                db,
                agent_id=slot.agent_id,
                run_id=run_id,
                heartbeat_interval_seconds=heartbeat_interval_seconds,
                next_tick_at=manual_next_tick_at or activity_policy.next_tick_at,
            )
            return schemas.OpenClawAgentRunRead(
                run_id=run_id,
                status="skipped",
                summary=activity_policy.summary,
                agent_id=slot.agent_id,
                session_key=session_key,
                character_id=character.id,
                post_id=selected_post_id,
                gateway_result={
                    "status": "skipped",
                    "reason": activity_policy.summary,
                    "activity_policy": activity_policy.to_result(),
                },
            )
        run_message = message or (
            f"{character.name}의 resident heartbeat tick입니다. "
            "Angmoo community tools를 사용해 커뮤니티를 확인하고 "
            "답글, 새 글, 좋아요, 관찰 중 캐릭터다운 행동 하나를 선택한 뒤 "
            "캐릭터 상태를 저장해줘."
        )
        main_tool_choice: dict[str, object] | None = None
        main_tools_allow: list[str] | None = None
        allow_thread_tool = True
        if enforce_activity_policy:
            allow_thread_tool = _should_allow_resident_thread_tool(
                feed_cue=feed_cue,
                activity_policy=activity_policy,
                has_inbox=has_inbox,
                recent_feed_roots=recent_feed_roots,
            )
            main_tool_choice = (
                TOOL_CHOICE_THREAD_OR_COMPLETE
                if allow_thread_tool
                else TOOL_CHOICE_COMPLETE_TICK
            )
            main_tools_allow = (
                TOOLS_ALLOW_THREAD_OR_COMPLETE
                if allow_thread_tool
                else TOOLS_ALLOW_COMPLETE_TICK
            )
        routine_runs.create_agent_run(
            db,
            run_id=run_id,
            user_id=slot.assigned_user_id,
            character_id=character.id,
            post_id=selected_post_id,
            credential_id=credential.id,
            agent_id=slot.agent_id,
            session_key=session_key,
            tool_auth_key=tool_auth_key,
        )
        run_created = True
        if use_langgraph_resident and activity_policy is not None:
            _purge_expired_daypart_memory_events(db)
            activity_daypart, daypart_start_date, _, _ = _activity_daypart_window(
                run_started_at
            )
            memory_session_key = _daypart_main_session_key(
                agent_id=slot.agent_id,
                character_id=character.id,
                daypart_start_date=daypart_start_date,
                activity_daypart=activity_daypart,
            )

            async def _extend_lease_for_wait(wait_seconds: float) -> None:
                slot_leases.extend_resident_slot_lease(
                    db,
                    agent_id=slot.agent_id,
                    run_id=run_id,
                    lease_seconds=int(wait_seconds) + effective_timeout_seconds + 180,
                )

            try:
                social_search = current_social_search()
                gateway_result = await run_resident_langgraph(
                    LangGraphResidentContext(
                        db=db,
                        run_id=run_id,
                        user_id=slot.assigned_user_id,
                        agent_id=slot.agent_id,
                        session_key=session_key,
                        character=character,
                        credential=credential,
                        state=state,
                        activity_policy=activity_policy,
                        selected_post_id=selected_post_id,
                        run_started_at=run_started_at,
                        feed_cue=feed_cue,
                        memory_session_key=memory_session_key,
                        daypart_start_date=daypart_start_date,
                        activity_daypart=activity_daypart,
                        require_public_action=require_public_action,
                        on_rate_limit_wait=_extend_lease_for_wait,
                        social_search_index=social_search.index,
                        social_search_state=social_search.state,
                    )
                )
            except DirectLlmDeferred as exc:
                summary = "Direct LLM rate-limit wait deferred."
                gateway_payload = {
                    "engine": "langgraph",
                    "status": "deferred",
                    "reason": summary,
                    "retry_at": exc.retry_at.isoformat(),
                    "wait_seconds": round(exc.wait_seconds, 3),
                }
                routine_runs.mark_agent_run_finished(
                    db,
                    run_id,
                    "deferred",
                    gateway_result=_stored_gateway_result(gateway_payload),
                )
                slot_leases.complete_resident_slot_run(
                    db,
                    agent_id=slot.agent_id,
                    run_id=run_id,
                    heartbeat_interval_seconds=heartbeat_interval_seconds,
                    next_tick_at=_scheduled_retry_next_tick_at(
                        db,
                        setting=setting,
                        character_id=character.id,
                        retry_at=exc.retry_at,
                        manual_next_tick_at=manual_next_tick_at,
                        timezone_reader=agent_activity_policy.activity_timezone,
                    ),
                    last_error=_runtime_last_error(
                        kind="model_rate_limit",
                        message=summary,
                        raw=f"wait_seconds={exc.wait_seconds:.3f}",
                    ),
                )
                return schemas.OpenClawAgentRunRead(
                    run_id=run_id,
                    status="deferred",
                    summary=summary,
                    agent_id=slot.agent_id,
                    session_key=session_key,
                    character_id=character.id,
                    post_id=selected_post_id,
                    gateway_result=gateway_payload,
                )

            if (
                gateway_result.get("engine")
                == "routine_resident_v1+keyword_search_v1"
            ):
                selected_post_id = _combined_runtime_evidence_post_id(
                    gateway_result
                )
                routine_runs.set_agent_run_post_id(
                    db, run_id, selected_post_id
                )

            status = str(gateway_result.get("status", "completed"))
            gateway_result["activity_policy"] = activity_policy.to_result()
            public_action_count = agent_activity_policy.count_public_actions_since(
                db, character_id=character.id, since=run_started_at
            )
            if (
                _is_success_status(status)
                and public_action_count == 0
                and _policy_allows_observe(activity_policy)
                and not _has_activity_since(
                    db,
                    character_id=character.id,
                    since=run_started_at,
                    action_types=("observed",),
                )
            ):
                activity_logs.log_activity(
                    db,
                    user_id=slot.assigned_user_id,
                    character_id=character.id,
                    action_type="observed",
                    target_post_id=selected_post_id,
                    reason="langgraph_resident_tick_observe",
                    result=_format_observation_result(
                        db, character_id=character.id, since=run_started_at
                    ),
                )
            routine_runs.mark_agent_run_finished(
                db,
                run_id,
                status,
                gateway_result=_stored_gateway_result(gateway_result),
            )
            if credential.cooldown_until is not None:
                credential_cooldown.set_cooldown_until(credential, cooldown_until=None)
            slot_leases.complete_resident_slot_run(
                db,
                agent_id=slot.agent_id,
                run_id=run_id,
                heartbeat_interval_seconds=heartbeat_interval_seconds,
                next_tick_at=(
                    manual_next_tick_at
                    if manual_next_tick_at is not None
                    else activity_policy.next_tick_at
                ),
            )
            return schemas.OpenClawAgentRunRead(
                run_id=run_id,
                status=status,
                summary=str(gateway_result.get("summary") or ""),
                agent_id=slot.agent_id,
                session_key=session_key,
                character_id=character.id,
                post_id=selected_post_id,
                gateway_result=_safe_gateway_result(gateway_result),
            )
        client = OpenClawGatewayClient(
            url=settings.openclaw_gateway_url,
            token=token or "",
            timeout_seconds=effective_timeout_seconds,
        )
        await _ensure_slot_auth_profile(
            openclaw_auth_profiles=openclaw_auth_profiles,
            client=client,
            agent_id=slot.agent_id,
            user_id=slot.assigned_user_id,
            character=character,
            credential=credential,
        )
        memory_session_key: str | None = None
        activity_daypart: str | None = None
        daypart_start_date: date | None = None
        if _daypart_persistent_session_allowed(
            character_id=character.id,
            require_public_action=require_public_action,
            enforce_activity_policy=enforce_activity_policy,
        ):
            _purge_expired_daypart_memory_events(db)
            activity_daypart, daypart_start_date, _, _ = _activity_daypart_window(
                run_started_at
            )
            memory_session_key = _daypart_main_session_key(
                agent_id=slot.agent_id,
                character_id=character.id,
                daypart_start_date=daypart_start_date,
                activity_daypart=activity_daypart,
            )
        if individual_tool_flow and activity_policy is not None:
            gateway_result = await _run_resident_individual_tool_flow(
                db=db,
                client=client,
                agent_id=slot.agent_id,
                session_key=session_key,
                tool_auth_key=tool_auth_key,
                run_id=run_id,
                user_id=slot.assigned_user_id,
                character=character,
                credential=credential,
                state=state,
                activity_policy=activity_policy,
                feed_cue=feed_cue,
                run_started_at=run_started_at,
                recent_activity_summary=recent_activity_summary,
                memory_session_key=memory_session_key,
                daypart_start_date=daypart_start_date,
                activity_daypart=activity_daypart,
            )
        else:
            feed_perception, feed_perception_result = await _run_feed_perception(
                client=client,
                agent_id=slot.agent_id,
                session_key=session_key,
                run_id=run_id,
                character=character,
                state=state,
                credential=credential,
                activity_policy=activity_policy,
                feed_cue=feed_cue,
                recent_feed_roots=recent_feed_roots,
                recent_activity_summary=recent_activity_summary,
            )
            _log_feed_perception_debug(
                db,
                user_id=slot.assigned_user_id,
                character_id=character.id,
                run_id=run_id,
                feed_perception_result=feed_perception_result,
            )
        if enforce_activity_policy and not individual_tool_flow:
            action_decision, action_decision_result = await _run_action_decision(
                client=client,
                agent_id=slot.agent_id,
                session_key=session_key,
                run_id=run_id,
                character=character,
                state=state,
                credential=credential,
                activity_policy=activity_policy,
                feed_cue=feed_cue,
                inbox_threads=inbox_threads,
                recent_feed_roots=recent_feed_roots,
                feed_perception=feed_perception,
                actionable_feed_candidates=actionable_feed_candidates,
                strong_social_connection_candidate=strong_social_connection_candidate,
                social_connection_candidate=social_connection_candidate,
                relationship_review_candidate=relationship_review_candidate,
                recent_activity_summary=recent_activity_summary,
                allow_thread_tool=allow_thread_tool,
                has_inbox=has_inbox,
            )
            selected_allows_thread = _action_decision_allows_thread(
                action_decision, allow_thread_tool=allow_thread_tool
            )
            gateway_result = await client.run_agent(
                message=_build_selected_mode_completion_message(
                    character=character, action_decision=action_decision
                ),
                agent_id=slot.agent_id,
                session_key=session_key,
                provider=credential.provider,
                model=credential.model,
                auth_profile_id=credential.auth_profile_id,
                tool_choice=(
                    TOOL_CHOICE_THREAD_OR_COMPLETE
                    if selected_allows_thread
                    else TOOL_CHOICE_COMPLETE_TICK
                ),
                tools_allow=(
                    TOOLS_ALLOW_THREAD_OR_COMPLETE
                    if selected_allows_thread
                    else TOOLS_ALLOW_COMPLETE_TICK
                ),
                idempotency_key=run_id,
                extra_system_prompt=_build_selected_mode_completion_prompt(
                    character=character,
                    state=state,
                    require_public_action=require_public_action,
                    activity_policy=activity_policy,
                    feed_cue=feed_cue,
                    inbox_threads=inbox_threads,
                    recent_feed_roots=recent_feed_roots,
                    feed_perception=feed_perception,
                    actionable_feed_candidates=actionable_feed_candidates,
                    recent_own_posts_to_avoid=recent_own_posts_to_avoid,
                    relationship_review_candidate=relationship_review_candidate,
                    recent_activity_summary=recent_activity_summary,
                    allow_thread_tool=allow_thread_tool,
                    has_inbox=has_inbox,
                    action_decision=action_decision,
                ),
            )
            gateway_result["action_decision"] = action_decision_result
        elif not enforce_activity_policy:
            gateway_result = await client.run_agent(
                message=run_message,
                agent_id=slot.agent_id,
                session_key=session_key,
                provider=credential.provider,
                model=credential.model,
                auth_profile_id=credential.auth_profile_id,
                tool_choice=main_tool_choice,
                tools_allow=main_tools_allow,
                idempotency_key=run_id,
                extra_system_prompt=_build_extra_system_prompt(
                    character=character,
                    post=post,
                    state=state,
                    require_public_action=require_public_action,
                    activity_policy=activity_policy,
                    feed_cue=feed_cue,
                    inbox_threads=inbox_threads,
                    recent_feed_roots=recent_feed_roots,
                    feed_perception=feed_perception,
                    actionable_feed_candidates=actionable_feed_candidates,
                    recent_own_posts_to_avoid=recent_own_posts_to_avoid,
                    strong_social_connection_candidate=strong_social_connection_candidate,
                    social_connection_candidate=social_connection_candidate,
                    relationship_review_candidate=relationship_review_candidate,
                    recent_activity_summary=recent_activity_summary,
                    allow_thread_tool=allow_thread_tool,
                    has_inbox=has_inbox,
                ),
            )
        if not individual_tool_flow:
            gateway_result["feed_perception"] = feed_perception_result
    except asyncio.CancelledError:
        cancelled_at = datetime.now(UTC)
        try:
            if run_created:
                routine_runs.mark_agent_run_finished(
                    db,
                    run_id,
                    "cancelled",
                    gateway_result={
                        "status": "cancelled",
                        "reason": "runtime_shutdown",
                        "cancelled_at": cancelled_at.isoformat(),
                    },
                )
            slot_leases.complete_resident_slot_run(
                db,
                agent_id=slot.agent_id,
                run_id=run_id,
                heartbeat_interval_seconds=heartbeat_interval_seconds,
                next_tick_at=cancelled_at
                + timedelta(seconds=heartbeat_interval_seconds),
                last_error="runtime_shutdown",
            )
        except Exception:
            logger.exception(
                "resident slot shutdown cleanup failed agent_id=%s run_id=%s",
                slot.agent_id,
                run_id,
            )
        raise
    except AgentRunConflictError as exc:
        slot_leases.complete_resident_slot_run(
            db,
            agent_id=slot.agent_id,
            run_id=run_id,
            heartbeat_interval_seconds=heartbeat_interval_seconds,
            next_tick_at=manual_next_tick_at,
            last_error=redact_secret_text(str(exc)),
        )
        raise AgentSessionBusyError(
            f"session {session_key} already has a running agent run"
        ) from exc
    except ReadOnlyLaneDeferredError as exc:
        summary = "Read-only resident lane timed out twice; retry scheduled."
        last_error = _runtime_last_error(
            kind="provider_timeout",
            message=summary,
            raw=exc.raw_error,
        )
        gateway_payload = exc.gateway_result
        if run_created:
            routine_runs.mark_agent_run_finished(
                db,
                run_id,
                "deferred",
                gateway_result=_stored_gateway_result(gateway_payload),
            )
        slot_leases.complete_resident_slot_run(
            db,
            agent_id=slot.agent_id,
            run_id=run_id,
            heartbeat_interval_seconds=heartbeat_interval_seconds,
            next_tick_at=_scheduled_retry_next_tick_at(
                db,
                setting=setting,
                character_id=character.id,
                retry_at=exc.retry_at,
                manual_next_tick_at=manual_next_tick_at,
                timezone_reader=agent_activity_policy.activity_timezone,
            ),
            last_error=last_error,
        )
        return schemas.OpenClawAgentRunRead(
            run_id=run_id,
            status="deferred",
            summary=summary,
            agent_id=slot.agent_id,
            session_key=session_key,
            character_id=character.id,
            post_id=selected_post_id,
            gateway_result={
                **gateway_payload,
            },
        )
    except Exception as exc:
        runtime_backoff = _runtime_error_backoff(
            exc,
            now=datetime.now(UTC),
            db=db,
            character_id=character.id if character is not None else slot.assigned_character_id,
            credential_id=credential.id
            if credential is not None
            else slot.assigned_credential_id,
        )
        next_tick_after_error = manual_next_tick_at
        last_error = redact_secret_text(str(exc))
        finished_status = "failed"
        runtime_message: str | None = None
        runtime_retry_at: datetime | None = None
        if runtime_backoff is not None:
            kind = runtime_backoff.kind
            runtime_message = runtime_backoff.message
            runtime_retry_at = runtime_backoff.retry_at
            finished_status = "deferred"
            base_retry_at = runtime_retry_at
            if (
                enforce_activity_policy
                and kind != "model_overloaded"
            ):
                minimum_next_tick_at = run_started_at + timedelta(
                    seconds=heartbeat_interval_seconds
                )
                if base_retry_at < minimum_next_tick_at:
                    base_retry_at = minimum_next_tick_at
            next_tick_after_error = _scheduled_retry_next_tick_at(
                db,
                setting=setting,
                character_id=character.id
                if character is not None
                else slot.assigned_character_id or "",
                retry_at=base_retry_at,
                manual_next_tick_at=manual_next_tick_at,
                timezone_reader=agent_activity_policy.activity_timezone,
            )
            last_error = _runtime_last_error(
                kind=kind,
                message=runtime_message,
                raw=redact_secret_text(str(exc)),
            )
            if kind == "model_rate_limit" and credential is not None:
                credential_cooldown.set_cooldown_until(credential, cooldown_until=runtime_retry_at)
        if run_created:
            if enforce_activity_policy:
                try:
                    public_action_count = (
                        agent_activity_policy.count_public_actions_since(
                            db, character_id=character.id, since=run_started_at
                        )
                    )
                    state_saved_since = _has_state_saved_since(
                        db, character_id=character.id, since=run_started_at
                    )
                    if runtime_backoff is not None and (
                        public_action_count > 0 or state_saved_since
                    ):
                        finished_status = "partial_ok"
                    if (
                        public_action_count == 0
                        and state_saved_since
                        and _policy_allows_observe(activity_policy)
                        and not _has_activity_since(
                            db,
                            character_id=character.id,
                            since=run_started_at,
                            action_types=("observed",),
                        )
                    ):
                        observation_result = _format_observation_result(
                            db, character_id=character.id, since=run_started_at
                        )
                        if observation_result == GENERIC_OBSERVATION_RESULT:
                            logger.warning(
                                "observed_fallback_used character_id=%s run_id=%s agent_id=%s",
                                character.id,
                                run_id,
                                slot.agent_id,
                            )
                        activity_logs.log_activity(
                            db,
                            user_id=slot.assigned_user_id,
                            character_id=character.id,
                            action_type="observed",
                            target_post_id=selected_post_id,
                            reason="resident_tick_observe_after_failed_run",
                            result=observation_result,
                        )
                except Exception as log_exc:
                    logger.warning(
                        "observed_after_failed_run_log_failed character_id=%s run_id=%s agent_id=%s error=%s",
                        character.id,
                        run_id,
                        slot.agent_id,
                        redact_secret_text(str(log_exc))[:500],
                    )
            gateway_payload = None
            if runtime_backoff is not None:
                gateway_payload = {
                    "status": finished_status,
                    "reason": runtime_message,
                    "retry_at": next_tick_after_error.isoformat()
                    if next_tick_after_error is not None
                    else None,
                    "failure_class": runtime_backoff.kind,
                    "repeated_overload": runtime_backoff.repeated_overload,
                    "error": redact_secret_text(str(exc))[:1500],
                }
            routine_runs.mark_agent_run_finished(
                db,
                run_id,
                finished_status,
                gateway_result=_stored_gateway_result(gateway_payload)
                if gateway_payload is not None
                else None,
            )
        slot_leases.complete_resident_slot_run(
            db,
            agent_id=slot.agent_id,
            run_id=run_id,
            heartbeat_interval_seconds=heartbeat_interval_seconds,
            next_tick_at=next_tick_after_error,
            last_error=last_error,
        )
        if runtime_backoff is not None and run_created and character is not None:
            return schemas.OpenClawAgentRunRead(
                run_id=run_id,
                status=finished_status,
                summary=runtime_message,
                agent_id=slot.agent_id,
                session_key=session_key,
                character_id=character.id,
                post_id=selected_post_id,
                gateway_result={
                    **gateway_payload,
                },
            )
        raise

    status = str(gateway_result.get("status", "completed"))
    validation_last_error: str | None = None
    public_action_count: int | None = None
    if enforce_activity_policy and individual_tool_flow:
        public_action_count = agent_activity_policy.count_public_actions_since(
            db, character_id=character.id, since=run_started_at
        )
        state_saved_since = _has_state_saved_since(
            db, character_id=character.id, since=run_started_at
        )
        feed_viewed_since = _has_activity_since(
            db,
            character_id=character.id,
            since=run_started_at,
            action_types=("feed_viewed",),
        )
        inbox_reviewed_since = _has_activity_since(
            db,
            character_id=character.id,
            since=run_started_at,
            action_types=("inbox_reviewed",),
        )
        feed_interests_since = _has_activity_since(
            db,
            character_id=character.id,
            since=run_started_at,
            action_types=("feed_interests_noted",),
        )
        if _is_success_status(status) and state_saved_since:
            gateway_result["resident_success_validation"] = {
                "status": "ok",
                "flow": "resident_individual_tools_v6",
                "state_saved": state_saved_since,
                "feed_viewed": feed_viewed_since,
                "inbox_reviewed": inbox_reviewed_since,
                "feed_interests_noted": feed_interests_since,
                "state_recovery_attempted": bool(
                    gateway_result.get("state_recovery_attempted")
                ),
                "state_recovery_applied": bool(
                    gateway_result.get("state_recovery_applied")
                ),
            }
        elif _is_success_status(status):
            validation_message = (
                "Resident individual tool flow v6 did not execute required "
                "state save tool call."
            )
            status = "tool_call_missing"
            gateway_result["resident_success_validation"] = {
                "status": "failed",
                "flow": "resident_individual_tools_v6",
                "reason": validation_message,
                "state_saved": state_saved_since,
                "feed_viewed": feed_viewed_since,
                "inbox_reviewed": inbox_reviewed_since,
                "feed_interests_noted": feed_interests_since,
                "gateway_status": str(gateway_result.get("status", "completed")),
                "state_recovery_attempted": bool(
                    gateway_result.get("state_recovery_attempted")
                ),
                "state_recovery_applied": bool(
                    gateway_result.get("state_recovery_applied")
                ),
            }
            validation_last_error = _runtime_last_error(
                kind="tool_call_missing",
                message=validation_message,
                raw=json.dumps(gateway_result, ensure_ascii=False, default=str),
            )
            logger.warning(
                "v6_tool_call_missing_after_gateway_success character_id=%s run_id=%s agent_id=%s",
                character.id,
                run_id,
                slot.agent_id,
            )
    if enforce_activity_policy and not individual_tool_flow:
        public_action_count = agent_activity_policy.count_public_actions_since(
            db, character_id=character.id, since=run_started_at
        )
        tick_completed_since = _has_tick_completed_since(
            db, character_id=character.id, since=run_started_at
        )
        state_saved_since = _has_state_saved_since(
            db, character_id=character.id, since=run_started_at
        )
        if _is_success_status(status) and not tick_completed_since:
            thread_viewed_since = _has_thread_viewed_since(
                db, character_id=character.id, since=run_started_at
            )
            if thread_viewed_since:
                followup_started_at = datetime.now(UTC)
                logger.info(
                    "complete_tick_followup_attempted character_id=%s run_id=%s agent_id=%s",
                    character.id,
                    run_id,
                    slot.agent_id,
                )
                followup_client = OpenClawGatewayClient(
                    url=settings.openclaw_gateway_url,
                    token=token,
                    timeout_seconds=min(timeout_seconds, 90),
                )
                try:
                    gateway_result["complete_tick_followup"] = await followup_client.run_agent(
                        message=_build_complete_tick_followup_message(character=character),
                        agent_id=slot.agent_id,
                        session_key=session_key,
                        provider=credential.provider,
                        model=credential.model,
                        auth_profile_id=credential.auth_profile_id,
                        tool_choice=TOOL_CHOICE_COMPLETE_TICK,
                        tools_allow=TOOLS_ALLOW_COMPLETE_TICK,
                        idempotency_key=f"{run_id}-complete-tick-followup",
                        extra_system_prompt=_build_complete_tick_followup_prompt(
                            character=character,
                            activity_policy=activity_policy,
                            feed_cue=feed_cue,
                        ),
                    )
                except Exception as exc:
                    gateway_result["complete_tick_followup"] = {
                        "status": "failed",
                        "error": redact_secret_text(str(exc))[:500],
                    }
                    logger.warning(
                        "complete_tick_followup_failed character_id=%s run_id=%s agent_id=%s error=%s",
                        character.id,
                        run_id,
                        slot.agent_id,
                        redact_secret_text(str(exc))[:500],
                    )
                tick_completed_since = _has_tick_completed_since(
                    db, character_id=character.id, since=followup_started_at
                ) or _has_tick_completed_since(
                    db, character_id=character.id, since=run_started_at
                )
                state_saved_since = _has_state_saved_since(
                    db, character_id=character.id, since=run_started_at
                )
                public_action_count = agent_activity_policy.count_public_actions_since(
                    db, character_id=character.id, since=run_started_at
                )
        if _is_success_status(status) and tick_completed_since and state_saved_since:
            refine_started_at = datetime.now(UTC)
            try:
                db.expire_all()
                refined_state = character_state_service.get_character_state(db, character.id)
                refine_client = OpenClawGatewayClient(
                    url=settings.openclaw_gateway_url,
                    token=token,
                    timeout_seconds=min(timeout_seconds, 45),
                )
                gateway_result["memory_note_refine"] = await refine_client.run_agent(
                    message=_build_memory_note_refine_message(character=character),
                    agent_id=slot.agent_id,
                    session_key=session_key,
                    provider=credential.provider,
                    model=credential.model,
                    auth_profile_id=credential.auth_profile_id,
                    tool_choice=TOOL_CHOICE_SAVE_STATE,
                    tools_allow=TOOLS_ALLOW_SAVE_STATE,
                    prompt_mode="minimal",
                    bootstrap_context_mode="lightweight",
                    bootstrap_context_run_kind="heartbeat",
                    idempotency_key=f"{run_id}-memory-note-refine",
                    extra_system_prompt=_build_memory_note_refine_prompt(
                        character=character,
                        state=refined_state,
                        activity_policy=activity_policy,
                        tick_activity=_format_tick_activity_since(
                            db, character_id=character.id, since=run_started_at
                        ),
                    ),
                )
                if _has_state_saved_since(
                    db, character_id=character.id, since=refine_started_at
                ):
                    gateway_result["memory_note_refined"] = True
                    logger.info(
                        "memory_note_refined character_id=%s run_id=%s agent_id=%s",
                        character.id,
                        run_id,
                        slot.agent_id,
                    )
                else:
                    gateway_result["memory_note_refined"] = False
                    gateway_result["memory_note_refine_warning"] = (
                        "memory_note_refine_failed: no state save activity was created"
                    )
                    activity_logs.log_activity(
                        db,
                        user_id=slot.assigned_user_id,
                        character_id=character.id,
                        action_type="memory_note_refine_failed",
                        target_post_id=selected_post_id,
                        reason="memory_note_refine_missing_state_save",
                        result="Refinement run ended without a state save; kept first-pass state.",
                    )
            except Exception as exc:
                gateway_result["memory_note_refine"] = {
                    "status": "failed",
                    "error": redact_secret_text(str(exc))[:500],
                }
                gateway_result["memory_note_refined"] = False
                activity_logs.log_activity(
                    db,
                    user_id=slot.assigned_user_id,
                    character_id=character.id,
                    action_type="memory_note_refine_failed",
                    target_post_id=selected_post_id,
                    reason="memory_note_refine_exception",
                    result=f"Kept first-pass state. error={redact_secret_text(str(exc))[:700]}",
                )
                logger.warning(
                    "memory_note_refine_failed character_id=%s run_id=%s agent_id=%s error=%s",
                    character.id,
                    run_id,
                    slot.agent_id,
                    redact_secret_text(str(exc))[:500],
                )
        elif _is_success_status(status):
            missing_parts = []
            if not tick_completed_since:
                missing_parts.append("tick_completed")
            if not state_saved_since:
                missing_parts.append("state_saved")
            validation_message = (
                "Resident tick did not execute required registered tool calls: "
                + ", ".join(missing_parts)
            )
            status = "tool_call_missing"
            gateway_result["resident_success_validation"] = {
                "status": "failed",
                "reason": validation_message,
                "tick_completed": tick_completed_since,
                "state_saved": state_saved_since,
                "gateway_status": str(gateway_result.get("status", "completed")),
            }
            validation_last_error = _runtime_last_error(
                kind="tool_call_missing",
                message=validation_message,
                raw=json.dumps(gateway_result, ensure_ascii=False, default=str),
            )
            logger.warning(
                "tool_call_missing_after_gateway_success character_id=%s run_id=%s agent_id=%s missing=%s",
                character.id,
                run_id,
                slot.agent_id,
                ",".join(missing_parts),
            )
    if activity_policy is not None:
        gateway_result["activity_policy"] = activity_policy.to_result()
    routine_runs.mark_agent_run_finished(
        db,
        run_id,
        status,
        gateway_result=_stored_gateway_result(gateway_result),
    )
    if enforce_activity_policy:
        if public_action_count is None:
            public_action_count = agent_activity_policy.count_public_actions_since(
                db, character_id=character.id, since=run_started_at
            )
        if (
            public_action_count == 0
            and _policy_allows_observe(activity_policy)
            and not _has_activity_since(
                db,
                character_id=character.id,
                since=run_started_at,
                action_types=("observed",),
            )
        ):
            observation_result = _format_observation_result(
                db, character_id=character.id, since=run_started_at
            )
            if observation_result == GENERIC_OBSERVATION_RESULT:
                logger.warning(
                    "observed_fallback_used character_id=%s run_id=%s agent_id=%s",
                    character.id,
                    run_id,
                    slot.agent_id,
                )
            activity_logs.log_activity(
                db,
                user_id=slot.assigned_user_id,
                character_id=character.id,
                action_type="observed",
                target_post_id=selected_post_id,
                reason="resident_tick_observe",
                result=observation_result,
            )
    if credential.cooldown_until is not None:
        credential_cooldown.set_cooldown_until(credential, cooldown_until=None)
    slot_leases.complete_resident_slot_run(
        db,
        agent_id=slot.agent_id,
        run_id=run_id,
        heartbeat_interval_seconds=heartbeat_interval_seconds,
        next_tick_at=(
            manual_next_tick_at
            if manual_next_tick_at is not None
            else activity_policy.next_tick_at
            if activity_policy
            else None
        ),
        last_error=validation_last_error,
    )

    return schemas.OpenClawAgentRunRead(
        run_id=str(gateway_result.get("runId", run_id)),
        status=status,
        summary=(
            str(gateway_result["summary"])
            if gateway_result.get("summary") is not None
            else None
        ),
        agent_id=slot.agent_id,
        session_key=session_key,
        character_id=character.id,
        post_id=selected_post_id,
        gateway_result=_safe_gateway_result(gateway_result),
    )


async def run_assigned_resident_slot_once(
    db: Session,
    *,
    user_id: str,
    character_id: str,
    post_id: str | None = None,
    timeout_seconds: int | None = None,
    message: str | None = None,
    require_public_action: bool = False,
    enforce_activity_policy: bool = False,
) -> schemas.OpenClawAgentRunRead:
    maintenance_service.ensure_run_now_available(db)
    character = _read_available_run_character(
        SqlAlchemyRunIdentityReferences(db, credential_lookup=agent_run_crud.get_credential, default_credential_lookup=agent_run_crud.get_default_credential), character_id
    )
    timeout = timeout_seconds or settings.openclaw_timeout_seconds
    slot = resident_slots.claim_resident_slot_assignment(
        db,
        user_id=user_id,
        character_id=character_id,
        lease_seconds=timeout + 90,
    )
    if slot is None:
        raise AgentSlotUnavailableError(
            f"No assigned OpenClaw slot is available for character {character_id}"
        )
    return await _run_resident_slot_once(
        db,
        slot=slot,
        post_id=post_id,
        timeout_seconds=timeout,
        message=message,
        require_public_action=require_public_action,
        enforce_activity_policy=enforce_activity_policy,
    )


async def run_claimed_temporary_resident_slot_once(
    db: Session,
    *,
    agent_id: str,
    user_id: str,
    character_id: str,
    credential_id: str,
    post_id: str | None = None,
    timeout_seconds: int | None = None,
    message: str | None = None,
    require_public_action: bool = False,
    enforce_activity_policy: bool = False,
) -> schemas.OpenClawAgentRunRead:
    maintenance_service.ensure_run_now_available(db)
    timeout = timeout_seconds or settings.openclaw_timeout_seconds
    slot = slot_queries.get_agent_slot(db, agent_id)
    if (
        slot is None
        or slot.status != routine_constants.SLOT_STATUS_RUNNING
        or slot.assigned_user_id != user_id
        or slot.assigned_character_id != character_id
        or slot.assigned_credential_id != credential_id
        or not (slot.locked_by_run_id or "").startswith("pending:temporary:")
    ):
        raise AgentSlotUnavailableError(
            f"Temporary OpenClaw slot {agent_id} is not claimed for character {character_id}"
        )
    return await _run_resident_slot_once(
        db,
        slot=slot,
        post_id=post_id,
        timeout_seconds=timeout,
        message=message,
        require_public_action=require_public_action,
        enforce_activity_policy=enforce_activity_policy,
    )


async def tick_resident_slots(
    db: Session, data: schemas.ResidentSlotTickCreate
) -> schemas.ResidentSlotTickRead:
    timeout_seconds = data.timeout_seconds or settings.openclaw_timeout_seconds
    now = datetime.now(UTC)
    def _recovery_next_tick_at(slot: models.AgentSlot, recovered_at: datetime) -> datetime:
        if not slot.assigned_character_id:
            return recovered_at
        setting = activity_settings.get_setting(db, slot.assigned_character_id)
        if setting is None:
            return recovered_at
        return agent_activity_policy.recovery_tick_schedule(
            setting,
            character_id=slot.assigned_character_id,
            now=recovered_at,
            timezone=agent_activity_policy.activity_timezone(
                db, character_id=slot.assigned_character_id
            ),
        ).next_tick_at

    recovered_count = slot_recovery.recover_expired_resident_slot_runs(
        db,
        now=now,
        next_tick_at_factory=_recovery_next_tick_at,
    )
    if recovered_count:
        logger.warning(
            "expired_resident_slot_runs_recovered count=%s",
            recovered_count,
        )
    allowed_character_ids: set[str] | None = None
    if maintenance_service.agent_activity_blocks_auto_ticks(db):
        allowed_character_ids = (
            maintenance_service.agent_activity_auto_tick_allowed_character_ids()
        )
        if not allowed_character_ids:
            due_before = [
                slot
                for slot in slot_queries.list_agent_slots(db)
                if _resident_slot_is_due(slot, now=now)
                and slot.status in routine_constants.DUE_SLOT_STATUSES
            ]
            return schemas.ResidentSlotTickRead(
                due_count=len(due_before),
                started_count=0,
                results=[],
                slots=list_resident_slots(db),
            )
    candidate_character_ids = {
        slot.assigned_character_id
        for slot in slot_queries.list_agent_slots(db)
        if slot.assigned_character_id is not None
    }
    owner_controlled_ids = owner_controlled_character_ids(
        db, candidate_character_ids
    )
    due_before = [
        slot
        for slot in slot_queries.list_agent_slots(db)
        if _resident_slot_is_due(slot, now=now)
        and slot.status in routine_constants.DUE_SLOT_STATUSES
        and slot.assigned_character_id not in owner_controlled_ids
        and (
            allowed_character_ids is None
            or slot.assigned_character_id in allowed_character_ids
        )
    ]
    claimed_slots = resident_slots.claim_due_resident_slots(
        db,
        now=now,
        max_count=data.max_runs,
        lease_seconds=(
            timeout_seconds
            + 90
            + settings.resident_tick_batch_start_spacing_seconds
            * max(data.max_runs - 1, 0)
        ),
        allowed_character_ids=allowed_character_ids,
        single_flight=settings.resident_tick_single_flight_enabled,
    )

    spacing_seconds = settings.resident_tick_batch_start_spacing_seconds
    results = await asyncio.gather(
        *[
            _run_claimed_resident_slot_once(
                slot.agent_id,
                post_id=data.post_id,
                timeout_seconds=timeout_seconds,
                message=data.message,
                start_delay_seconds=index * spacing_seconds,
            )
            for index, slot in enumerate(claimed_slots)
        ]
    )
    db.expire_all()

    return schemas.ResidentSlotTickRead(
        due_count=len(due_before),
        started_count=len(claimed_slots),
        results=list(results),
        slots=list_resident_slots(db),
    )


async def _run_claimed_resident_slot_once(
    agent_id: str,
    *,
    post_id: str | None,
    timeout_seconds: int,
    message: str | None,
    start_delay_seconds: int = 0,
) -> schemas.OpenClawAgentRunRead:
    if start_delay_seconds > 0:
        await asyncio.sleep(start_delay_seconds)
    with SessionLocal() as db:
        slot = slot_queries.get_agent_slot(db, agent_id)
        if slot is None:
            raise AgentSlotUnavailableError(f"slot {agent_id} does not exist")
        return await _run_resident_slot_once(
            db,
            slot=slot,
            post_id=post_id,
            timeout_seconds=timeout_seconds,
            message=message,
            require_public_action=False,
            enforce_activity_policy=True,
        )
