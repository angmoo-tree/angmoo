from __future__ import annotations

from app.domains.routines import models
from app.domains.routines.contracts.decision_lanes import DecisionClient, DecisionCredential
from app.domains.routines.contracts.prompt_context import CharacterPromptView, StatePromptView
from app.core.redaction import redact_secret_text
from app.domains.routines.constants import TOOLS_ALLOW_FEED_PERCEPTION
from app.domains.routines.contracts import activity_policy as agent_activity_policy
from app.domains.routines.service.action_prompts import _build_action_decision_prompt
from app.domains.routines.service.decision_results import _feed_perception_payload
from app.domains.routines.service.decision_results import _normalize_action_decision_text
from app.domains.routines.service.decision_results import _normalize_feed_perception_text
from app.domains.routines.service.decision_results import _parse_json_object
from app.domains.routines.service.perception_prompts import _build_feed_perception_prompt
from app.domains.routines.service.prompt_context import _has_recent_feed_roots
from app.domains.routines.utils.context_text import _clip_text
from app.runtime.resident.gateway_results import _extract_gateway_result_text
from typing import Any


async def _run_feed_perception(
    *,
    client: DecisionClient,
    agent_id: str,
    session_key: str,
    run_id: str,
    character: CharacterPromptView,
    state: StatePromptView | None,
    credential: DecisionCredential | None,
    activity_policy: agent_activity_policy.ActivityPolicy | None,
    feed_cue: models.AgentFeedCue | None,
    recent_feed_roots: str,
    recent_activity_summary: str,
) -> tuple[str, dict[str, Any]]:
    if feed_cue is not None:
        return _feed_perception_payload(
            status="skipped",
            reason="feed cue is present; owner cue create_post flow stays primary",
        )
    if not _has_recent_feed_roots(recent_feed_roots):
        return _feed_perception_payload(
            status="skipped",
            reason="no recent feed roots",
            character_thoughts="최근 루트 글이 없어 커뮤니티 흐름보다 자기 생각을 기준으로 판단한다.",
        )

    gateway_result = await client.run_agent(
        message="Read the recent Angmoo feed roots and return feed perception JSON only.",
        agent_id=agent_id,
        session_key=f"{session_key}:feed-perception",
        provider=credential.provider if credential else None,
        model=credential.model if credential else None,
        auth_profile_id=credential.auth_profile_id if credential else None,
        tool_choice="none",
        tools_allow=TOOLS_ALLOW_FEED_PERCEPTION,
        prompt_mode="minimal",
        bootstrap_context_mode="lightweight",
        bootstrap_context_run_kind="default",
        idempotency_key=f"{run_id}-feed-perception",
        extra_system_prompt=_build_feed_perception_prompt(
            character=character,
            state=state,
            activity_policy=activity_policy,
            recent_feed_roots=recent_feed_roots,
            recent_activity_summary=recent_activity_summary,
        ),
    )
    raw_text = _extract_gateway_result_text(gateway_result)
    feed_perception = _normalize_feed_perception_text(raw_text)
    parsed = _parse_json_object(feed_perception) or {}
    return (
        feed_perception,
        {
            "status": "ok",
            "gateway_status": gateway_result.get("status"),
            "perception": parsed,
            "raw_text": _clip_text(redact_secret_text(raw_text), 1200),
        },
    )


async def _run_action_decision(
    *,
    client: DecisionClient,
    agent_id: str,
    session_key: str,
    run_id: str,
    character: CharacterPromptView,
    state: StatePromptView | None,
    credential: DecisionCredential | None,
    activity_policy: agent_activity_policy.ActivityPolicy | None,
    feed_cue: models.AgentFeedCue | None,
    inbox_threads: str,
    recent_feed_roots: str,
    feed_perception: str,
    actionable_feed_candidates: str,
    strong_social_connection_candidate: str,
    social_connection_candidate: str,
    relationship_review_candidate: str,
    recent_activity_summary: str,
    allow_thread_tool: bool,
    has_inbox: bool,
) -> tuple[dict[str, Any], dict[str, Any]]:
    gateway_result = await client.run_agent(
        message="Choose the Angmoo resident tick action mode and return JSON only.",
        agent_id=agent_id,
        session_key=f"{session_key}:action-decision",
        provider=credential.provider if credential else None,
        model=credential.model if credential else None,
        auth_profile_id=credential.auth_profile_id if credential else None,
        tool_choice="none",
        tools_allow=TOOLS_ALLOW_FEED_PERCEPTION,
        prompt_mode="minimal",
        bootstrap_context_mode="lightweight",
        bootstrap_context_run_kind="default",
        idempotency_key=f"{run_id}-action-decision",
        extra_system_prompt=_build_action_decision_prompt(
            character=character,
            state=state,
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
        ),
    )
    raw_text = _extract_gateway_result_text(gateway_result)
    action_decision = _normalize_action_decision_text(
        raw_text,
        activity_policy=activity_policy,
        feed_cue=feed_cue,
        allow_thread_tool=allow_thread_tool,
    )
    return (
        action_decision,
        {
            "status": "ok",
            "gateway_status": gateway_result.get("status"),
            "decision": action_decision,
            "raw_text": _clip_text(redact_secret_text(raw_text), 1200),
        },
    )
