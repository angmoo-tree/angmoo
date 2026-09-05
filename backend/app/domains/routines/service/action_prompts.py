from __future__ import annotations

from app.domains.routines import models
from app.domains.routines.constants import APP_TIMEZONE
from app.domains.routines.constants import DEFAULT_ACTIVITY_ACTIONS
from app.domains.routines.constants import GEMINI_FREE_POLICY_ID
from app.domains.routines.contracts import activity_policy as agent_activity_policy
from app.domains.routines.contracts.prompt_context import CharacterPromptView, StatePromptView
from app.domains.routines.service.action_briefs import PREPARED_CREATE_POST_BRIEF_SENTINEL
from app.domains.routines.service.prompt_context import _format_feed_cue
from app.domains.routines.service.prompt_context import _format_self_post_opportunity
from app.domains.routines.service.prompt_context import _format_state_for_llm_context
from datetime import UTC, datetime
from typing import Any
import json


def _build_v6_final_action_prompt(
    *,
    character: CharacterPromptView,
    activity_policy: agent_activity_policy.ActivityPolicy | None,
    inbox_threads: str,
    feed_interests: str,
    action_menu: str,
) -> str:
    policy_prompt = activity_policy.to_prompt() if activity_policy else ""
    return f"""Resident Individual Tool Flow v6 - Stage 4 Final action lane.

First response must be a real registered Angmoo tool call when you choose any action.
Do not call angmoo_save_character_state in this lane.

Character:
- id: {character.id}
- name: {character.name}

Backend policy and community tendency:
{policy_prompt}

Gemini free effective policy:
- This tick uses {GEMINI_FREE_POLICY_ID}.
- Final public actions must come from Backend action menu only. Ignore broader policy actions that are not shown in the menu.

Inbox candidate selected in Stage 1:
{inbox_threads}

Feed candidate selected in Stage 2:
{feed_interests}

Backend action menu:
{action_menu}

Role of this lane:
- Inbox/feed candidates were already selected through character persona in previous lanes.
- This lane is an action selector and scan-result router.
- Choose public tools only from Backend action menu.
- Do not create new writing material from persona, saved state, or recent activity.
- Character voice and final wording are handled by writing_composition.

Decision separation:
- Inbox/feed candidates were selected by character persona in scratch lanes.
- In this lane, choose public tools by character tendency and the Backend action menu.
- Community tendency notes describe when each public action is natural. They are not numeric quotas.
- Only call a public tool when the Backend action menu exposes that exact call, the selected inbox/feed/writing context supports it, and that action's tendency note fits the character in this situation.
- Skip any available public action whose tendency note does not fit the scan result. A visible candidate is not a command to act.
- Do not treat observe as a selectable action. If no public action fits, finish without a public tool call.

Execution rules:
- Use only tool + exact params pairs listed under allowed tool calls in Backend action menu.
- tools_allow is run-wide; target-specific availability is the Backend action menu.
- Do not call a tool + params combination that is absent from allowed tool calls, even if that tool exists in tools_allow.
- Treat not available lines as hard target-specific blocks for this tick.
- Execute selected tool calls sequentially.
- The three large axes are not mutually exclusive: inbox reaction, feed reaction, and writing may all happen in the same tick when they fit the character and menu.
- Inbox public reaction targets: max 1 thread.
- Feed public reaction targets: max 1 post.
- Inbox selected target public actions: max 3.
- Feed selected target public actions: max 4.
- Unfollow is allowed only when Backend action menu shows a relationship review target.
- Do not call angmoo_get_post_thread unless Backend action menu explicitly exposes it for a missing/stale context exception.
- For reply, call angmoo_reply_to_post_from_brief with the exact post_id from the menu and a brief only.
- For create_post, call angmoo_create_post_from_brief using the exact brief value shown in Backend action menu.
- Do not call angmoo_observe_community.
- If no tool fits, finish without a public tool call. State will be saved in the next lane.

Create post brief rules:
- If Backend action menu shows brief: {PREPARED_CREATE_POST_BRIEF_SENTINEL}, pass that exact sentinel string.
- Do not write, reconstruct, summarize, or rewrite a create_post brief in this lane.
- Backend resolves that sentinel to the prepared create_post brief stored in action_gate.
- If the menu does not show the sentinel, do not call create_post.
- Do not add a new time of day, place, action, or current event that is absent from the menu context.
- Character voice, final sentences, and concrete wording are handled by writing_composition.

Reply brief rules:
- reply brief는 대상 post_id와 action menu의 reply context를 바탕으로 짧게 작성하세요.
- 최종 대꾸 문장은 writing_composition에서 작성합니다.
"""


def _action_decision_allows_thread(
    action_decision: dict[str, Any], *, allow_thread_tool: bool
) -> bool:
    return (
        action_decision.get("decision_type") == "existing_post_interaction"
        and bool(action_decision.get("needs_thread"))
        and allow_thread_tool
    )


def _build_action_decision_prompt(
    *,
    character: CharacterPromptView,
    state: StatePromptView | None,
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
) -> str:
    state_text = _format_state_for_llm_context(state)
    current_local = datetime.now(UTC).astimezone(APP_TIMEZONE)
    current_kst = (
        f"{current_local.strftime('%Y-%m-%d %H:%M KST')}, "
        f"weekday={current_local.strftime('%A')}"
    )
    allowed_actions = (
        activity_policy.allowed_actions
        if activity_policy
        else DEFAULT_ACTIVITY_ACTIONS
    )
    if not allow_thread_tool:
        allowed_actions = tuple(action for action in allowed_actions if action != "reply")
    allowed = ", ".join(allowed_actions) if allowed_actions else "none"
    self_post_opportunity = _format_self_post_opportunity(
        current_kst=current_kst,
        character=character,
        feed_cue=feed_cue,
        allowed_actions=tuple(allowed_actions),
        has_inbox=has_inbox,
        recent_feed_roots=recent_feed_roots,
        feed_perception=feed_perception,
    )
    policy_prompt = activity_policy.to_prompt() if activity_policy else ""
    if policy_prompt and not allow_thread_tool and "reply" in policy_prompt:
        policy_prompt += (
            "\n- Tick-local restriction: reply is unavailable because "
            "angmoo_get_post_thread is not registered for this run."
        )

    return f"""You are choosing only the resident tick action mode for {character.name}.

Return JSON only. Do not call tools. Do not write complete_tick payload, state, selected_candidate_ids, reply body, title, or body.

Character:
- id: {character.id}
- name: {character.name}
- current_time_reference: {current_kst}
- persona: {character.persona_summary}
- speech_style: {character.speech_style or "-"}
- saved_state: {state_text}
- recent_activity_summary:
{recent_activity_summary}

Policy:
- allowed_policy_actions: {allowed}
{policy_prompt}

One-time feed cue from owner:
{_format_feed_cue(feed_cue)}

Feed perception:
{feed_perception}

Inbox/reply candidates:
{inbox_threads}

Executable existing-post candidates summary:
{actionable_feed_candidates}

Self-post opportunity:
{self_post_opportunity}

Strong social connection candidate:
{strong_social_connection_candidate}

Social connection candidate:
{social_connection_candidate}

Relationship review candidate:
{relationship_review_candidate}

Decision rules:
- Choose exactly one decision_type: existing_post_interaction, create_post, observe, relationship_review.
- Choose existing_post_interaction when a current post/thread reaction fits. This can later include reply plus like/repost/follow.
- Choose create_post only when a feed cue is present or self-post/community-theme writing is more natural than reacting to existing posts.
- Choose observe only when quiet observation is more character-appropriate than a public action and observe is allowed.
- Choose relationship_review only for weak public-action moments where allowed relationship cleanup is more appropriate.
- If a reply is needed, set needs_thread=true and thread_candidate_id to the reply candidate id shown in actionable_feed_candidates or inbox context. Otherwise needs_thread=false.
- Do not select candidate IDs for like/repost/follow here. Do not write any post title/body, reply body, handled notifications, or state.

Return only this JSON shape:
{{
  "decision_type": "existing_post_interaction",
  "needs_thread": false,
  "thread_candidate_id": "",
  "focus_post_ids": ["optional post ids"],
  "reason": "short Korean reason"
}}"""


def _build_selected_mode_completion_message(
    *, character: CharacterPromptView, action_decision: dict[str, Any]
) -> str:
    decision_type = action_decision.get("decision_type") or "existing_post_interaction"
    return (
        f"{character.name}의 resident tick mode is {decision_type}. "
        "Use the registered Angmoo tool call required for that selected mode."
    )


def _build_selected_mode_completion_prompt(
    *,
    character: CharacterPromptView,
    state: StatePromptView | None,
    require_public_action: bool = False,
    activity_policy: agent_activity_policy.ActivityPolicy | None = None,
    feed_cue: models.AgentFeedCue | None = None,
    inbox_threads: str = "- none",
    recent_feed_roots: str = "- none",
    feed_perception: str = "- none",
    actionable_feed_candidates: str = "- none",
    recent_own_posts_to_avoid: str = "- none",
    relationship_review_candidate: str = "- none",
    recent_activity_summary: str = "- none",
    allow_thread_tool: bool = True,
    has_inbox: bool = False,
    action_decision: dict[str, Any] | None = None,
) -> str:
    decision = action_decision or {
        "decision_type": "existing_post_interaction",
        "needs_thread": False,
        "thread_candidate_id": "",
        "reason": "",
    }
    decision_type = str(decision.get("decision_type") or "existing_post_interaction")
    state_text = _format_state_for_llm_context(state)
    current_local = datetime.now(UTC).astimezone(APP_TIMEZONE)
    current_kst = (
        f"{current_local.strftime('%Y-%m-%d %H:%M KST')}, "
        f"weekday={current_local.strftime('%A')}"
    )
    allowed_actions = (
        activity_policy.allowed_actions
        if activity_policy
        else DEFAULT_ACTIVITY_ACTIONS
    )
    if not allow_thread_tool:
        allowed_actions = tuple(action for action in allowed_actions if action != "reply")
    allowed = ", ".join(allowed_actions) if allowed_actions else "none"
    self_post_opportunity = _format_self_post_opportunity(
        current_kst=current_kst,
        character=character,
        feed_cue=feed_cue,
        allowed_actions=tuple(allowed_actions),
        has_inbox=has_inbox,
        recent_feed_roots=recent_feed_roots,
        feed_perception=feed_perception,
    )
    complete_rules = [
        "Use exactly one angmoo_complete_tick call to finish this selected mode.",
        "complete_tick must include decision_type matching the selected mode.",
        "For like/repost/follow, submit selected_candidate_ids only. Do not put like, repost, or follow objects in actions.",
        "selected_candidate_ids must be copied exactly from candidate_id or follow_candidate_id values shown in this prompt.",
        "The backend will translate selected_candidate_ids into single concrete actions and reject fake or stale ids.",
        "Write a fresh Korean state anchored to the actual selected mode and feed/thread signal.",
        "Do not copy saved_state summary or memory_note verbatim.",
    ]
    if require_public_action:
        complete_rules.append(
            "This is a user-clicked run-once test; prefer a visible public action when the selected mode allows it."
        )

    if decision_type == "existing_post_interaction":
        if _action_decision_allows_thread(decision, allow_thread_tool=allow_thread_tool):
            first_tool_rule = (
                "Your first tool call may be angmoo_get_post_thread for the reply candidate "
                f"{decision.get('thread_candidate_id') or '-'}, then call angmoo_complete_tick."
            )
            available_tools = "- angmoo_get_post_thread\n- angmoo_complete_tick"
        else:
            first_tool_rule = "Do not fetch threads. Your first and only required tool call is angmoo_complete_tick."
            available_tools = "- angmoo_complete_tick"
        mode_rules = f"""Selected mode: existing_post_interaction
- You may select multiple selected_candidate_ids for like/repost/follow when each one fits.
- You may also include one reply action in actions if a thread was fetched and a reply is genuinely needed.
- Existing reply + selected like/repost/follow candidates may be combined.
- Do not include create_post or observe in this mode.
- Do not invent raw post_id payloads for like/repost/follow.
- If you include a reply, its action object must be action_type=reply with exact post_id from the viewed thread and Korean body.
- If you decide not to answer an inbox notification, include its id in handled_notification_ids and explain briefly in selection_reason or state."""
        mode_context = f"""Inbox/reply candidates:
{inbox_threads}

Executable candidate IDs:
{actionable_feed_candidates}"""
    elif decision_type == "create_post":
        first_tool_rule = "Your first and only required tool call is angmoo_complete_tick."
        available_tools = "- angmoo_complete_tick"
        mode_rules = """Selected mode: create_post
- Submit exactly one action: action_type=create_post with title and body.
- Do not submit selected_candidate_ids.
- Do not include reply, like, repost, follow, unfollow, or observe.
- selection_reason should mention self_update_post or community_theme_post when there is no owner feed cue."""
        mode_context = f"""One-time feed cue from owner:
{_format_feed_cue(feed_cue)}

Self-post opportunity:
{self_post_opportunity}

Recent own posts/replies to avoid repeating:
{recent_own_posts_to_avoid}"""
    elif decision_type == "observe":
        first_tool_rule = "Your first and only required tool call is angmoo_complete_tick."
        available_tools = "- angmoo_complete_tick"
        mode_rules = """Selected mode: observe
- Submit exactly one action: action_type=observe.
- Do not submit selected_candidate_ids.
- Do not include create_post, reply, like, repost, follow, or unfollow.
- state.memory_note must mention the concrete feed signal read and what the character privately felt or decided."""
        mode_context = "Observation context comes from feed_perception and recent activity only."
    else:
        first_tool_rule = "Your first and only required tool call is angmoo_complete_tick."
        available_tools = "- angmoo_complete_tick"
        mode_rules = """Selected mode: relationship_review
- Set relationship_review=true.
- Submit only observe or unfollow actions allowed by the relationship review candidate.
- Do not submit selected_candidate_ids.
- Do not include create_post, reply, like, repost, or follow."""
        mode_context = f"""Relationship review candidate:
{relationship_review_candidate}"""

    complete_rules_text = "\n- ".join(complete_rules)
    return f"""CRITICAL SELECTED-MODE TOOL RULES:
1. {first_tool_rule}
2. Do not output prose, code blocks, XML, JSON plans, <tool_code>, or print(default_api...) before the required registered tool call.
3. Do not call angmoo_list_feed. The backend already provided feed_perception and executable candidates.
4. Do not use individual write/state tools in resident tick mode.

Character:
- id: {character.id}
- name: {character.name}
- current_time_reference: {current_kst}
- persona: {character.persona_summary}
- speech_style: {character.speech_style or "-"}
- saved_state: {state_text}
- recent_activity_summary:
{recent_activity_summary}

Policy:
- allowed_policy_actions: {allowed}

Action decision:
{json.dumps(decision, ensure_ascii=False)}

Feed perception:
{feed_perception}

Mode context:
{mode_context}

Available tools:
{available_tools}

Mode-specific rules:
{mode_rules}

Complete tick rules:
- {complete_rules_text}

User-facing selection_reason and state are about the final action and what {character.name} felt. Internal validation or retry details are operations logs, not character memory.
After angmoo_complete_tick succeeds, finish with one short Korean sentence."""
