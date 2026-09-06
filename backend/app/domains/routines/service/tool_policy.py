from __future__ import annotations

from app.domains.routines import models
from app.domains.routines.constants import GEMINI_FREE_ALLOWED_ACTIONS
from app.domains.routines.constants import PUBLIC_ACTION_BRIEF_TOOLS_BY_POLICY
from app.domains.routines.constants import PUBLIC_ACTION_TOOLS_BY_POLICY
from app.domains.routines.contracts import activity_policy as agent_activity_policy
from app.domains.routines.service.prompt_context import _has_recent_feed_roots


def _resident_public_tools_allow(
    allowed_actions: tuple[str, ...],
    *,
    use_brief_writing_tools: bool = False,
) -> list[str]:
    tool_map = (
        PUBLIC_ACTION_BRIEF_TOOLS_BY_POLICY
        if use_brief_writing_tools
        else PUBLIC_ACTION_TOOLS_BY_POLICY
    )
    tools: list[str] = []
    for action in allowed_actions:
        if action == "observe":
            continue
        tool_name = tool_map.get(action)
        if tool_name and tool_name not in tools:
            tools.append(tool_name)
    return tools


def _gemini_free_effective_actions(
    allowed_actions: tuple[str, ...],
) -> tuple[str, ...]:
    allowed = set(allowed_actions)
    return tuple(action for action in GEMINI_FREE_ALLOWED_ACTIONS if action in allowed)


def _should_allow_resident_thread_tool(
    *,
    feed_cue: models.AgentFeedCue | None,
    activity_policy: agent_activity_policy.ActivityPolicy | None,
    has_inbox: bool,
    recent_feed_roots: str,
) -> bool:
    if feed_cue is not None:
        return False
    if activity_policy is not None and "reply" not in activity_policy.allowed_actions:
        return False
    return has_inbox or _has_recent_feed_roots(recent_feed_roots)


def _policy_allows_observe(
    activity_policy: agent_activity_policy.ActivityPolicy | None,
) -> bool:
    return activity_policy is not None and "observe" in activity_policy.allowed_actions
