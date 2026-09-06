"""Stable Social action candidate identifiers and tick completion value rules."""

import hashlib
from app.domains.social.schemas import community as schemas
from app.domains.social.contracts.agent_tools import ToolRun

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


def _complete_tick_representative_target(
    current: str | None, candidate: str | None
) -> str | None:
    return current or candidate


def _resident_action_candidate_id(
    *, run_id: str, character_id: str, action_type: str, target_key: str
) -> str:
    digest = hashlib.sha256(
        f"{run_id}:{character_id}:{action_type}:{target_key}".encode("utf-8")
    ).hexdigest()[:12]
    return f"cand_{action_type}_{digest}"


def _put_candidate_action(
    candidate_actions: dict[str, schemas.AgentCompleteTickAction],
    *,
    run: ToolRun,
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


def _has_effective_complete_tick_action(executed_actions: list[str]) -> bool:
    return any(
        (
            not action.startswith(NOOP_COMPLETE_TICK_ACTION_PREFIXES)
            for action in executed_actions
        )
    )
