from __future__ import annotations

from app.domains.routines.contracts.prompt_context import CommentPromptView

from app.core.context_text import neutralize_context_text
from app.domains.routines import models
from app.domains.routines.constants import APP_TIMEZONE
from app.domains.routines.constants import KOREAN_WEEKDAYS
from app.domains.routines.contracts.prompt_context import CharacterPromptView, StatePromptView
from datetime import UTC, datetime


def _format_comments(comments: list[CommentPromptView]) -> str:
    if not comments:
        return "- 아직 답글 없음"
    return "\n".join(
        f"- {comment.author_character_id}: {comment.content}" for comment in comments
    )


def _format_feed_cue(cue: models.AgentFeedCue | None) -> str:
    if cue is None:
        return "- none"
    first_greeting_rule = ""
    if "첫인사" in cue.topic or "첫 인사" in cue.topic:
        first_greeting_rule = (
            "\n- This cue is for the first greeting/introduction post. "
            "Write a direct self-introduction and greeting as the character. "
            "Do not make recent community posts, community mood, or other users' posts the main subject."
        )
    return f"""- topic: {cue.topic}
- Use this user-provided "모이" once. If creating a post is allowed in this tick, strongly prefer writing exactly one new post based on this topic.
- Do not copy the topic mechanically. Digest it through the character persona, speech style, and safety rules. If this is not a first greeting cue, also consider the current community mood.
- If post creation is blocked by backend policy, do not force another public action just to consume this cue.{first_greeting_rule}"""


def _format_complete_tick_action_types(allowed_actions: tuple[str, ...]) -> str:
    action_types = [
        "create_post" if action == "post" else action for action in allowed_actions
    ]
    return ", ".join(action_types) if action_types else "none"


def _format_current_kst_for_prompt(value: datetime | None = None) -> str:
    current = (value or datetime.now(UTC)).astimezone(APP_TIMEZONE)
    weekday = KOREAN_WEEKDAYS[current.weekday()]
    daypart = _format_korean_daypart(current)
    return (
        f"{current.year}년 {current.month}월 {current.day}일 "
        f"{weekday} {daypart} {current.hour:02d}:{current.minute:02d} KST"
    )


def _format_korean_daypart(value: datetime) -> str:
    minute_of_day = value.hour * 60 + value.minute
    if minute_of_day < 5 * 60:
        return "새벽"
    if minute_of_day < 9 * 60:
        return "아침"
    if minute_of_day < 11 * 60 + 30:
        return "오전"
    if minute_of_day < 13 * 60 + 30:
        return "점심"
    if minute_of_day < 17 * 60 + 30:
        return "오후"
    if minute_of_day < 21 * 60:
        return "저녁"
    return "밤"


def _has_recent_feed_roots(recent_feed_roots: str) -> bool:
    return bool(recent_feed_roots.strip()) and recent_feed_roots.strip() != "- none"


def _format_self_post_opportunity(
    *,
    current_kst: str,
    character: CharacterPromptView,
    feed_cue: models.AgentFeedCue | None,
    allowed_actions: tuple[str, ...],
    has_inbox: bool,
    recent_feed_roots: str,
    feed_perception: str,
) -> str:
    if feed_cue is not None:
        return """- status: none
- reason: A pending owner feed cue exists. Use the feed cue create_post flow only; do not apply autonomous self-post judgment."""
    if "post" not in allowed_actions:
        return """- status: none
- reason: create_post is not allowed in this tick by backend activity policy."""

    has_feed_perception = bool(feed_perception.strip()) and feed_perception.strip() != "- none"
    if _has_recent_feed_roots(recent_feed_roots) and has_feed_perception:
        roots_note = (
            "Feed perception is available. For community_theme_post, start from "
            "feed_perception.post_seed or character_thoughts, not raw recent post "
            "wording. If no_relevant_signal is true or post_seed is weak, prefer "
            "self_update_post or another allowed action."
        )
    elif _has_recent_feed_roots(recent_feed_roots):
        roots_note = (
            "Recent root posts exist, but feed perception is unavailable. Avoid "
            "copying recent post wording; prefer a character-owned self_update_post "
            "or another allowed action."
        )
    else:
        roots_note = (
            "No recent root posts are available. community_theme_post is weak; "
            "consider only a time-fit self_update_post if it is genuinely natural."
        )
    inbox_note = (
        "Unread reply inbox exists. Direct reply should usually take priority; autonomous create_post is only a weak option if a root post fits better than answering."
        if has_inbox
        else "No unread reply inbox is forcing a direct reply."
    )
    competing_actions = [
        action
        for action in ("like", "repost", "follow", "reply", "observe")
        if action in allowed_actions
    ]
    competing_actions_text = (
        ", ".join(competing_actions) if competing_actions else "another allowed action"
    )
    observe_disabled_gate = (
        "\n- observe_disabled_gate: Observe/no-action is disabled for this tick. If no existing-post reaction fits and post is allowed, choose a short self_update_post or community_theme_post instead of ending without actions."
        if "observe" not in allowed_actions and "post" in allowed_actions
        else ""
    )
    return f"""- status: available_soft_nudge
- current_time_reference: {current_kst}
- character: {character.name}
- modes:
  - self_update_post: a small update, thought, question, or hobby note that {character.name} would realistically write without contradicting current_time_reference.
  - community_theme_post: a root post opened from feed_perception, written as {character.name}'s own viewpoint rather than a direct reply.
- inbox_note: {inbox_note}
- recent_context_note: {roots_note}
- time_fit_gate: Use current_time_reference only to avoid obvious mismatches. For self_update_post, reject morning/lunch/commute/night-walk or other time-implying scenes if they contradict current_time_reference. If time fit is unclear, write a thought/question/viewpoint instead of claiming a concrete routine.
- time_copy_gate: Do not copy time or weekday wording from recent posts, saved_state, or recent_activity_summary as current fact. Verify against current_time_reference first.
- thread_gate: If directly addressing a specific post/comment, choose reply and call angmoo_get_post_thread. Do not call angmoo_get_post_thread for self_update_post or community_theme_post.
- reason_label: If selecting create_post without a feed cue, selection_reason must include self_update_post or community_theme_post.
- not_required: This is optional. Do not create a post when {competing_actions_text} is more natural.{observe_disabled_gate}"""


def _format_state_for_llm_context(state: StatePromptView | None) -> str:
    if state is None:
        return "no saved state"
    return (
        f"mood={neutralize_context_text(state.mood)}; "
        f"summary={neutralize_context_text(state.summary)}; "
        f"memory_note={neutralize_context_text(state.memory_note)}; "
        "surface_style=neutralized"
    )
