from __future__ import annotations

from app.domains.routines import models
from app.domains.routines.contracts import activity_policy as agent_activity_policy
from app.domains.routines.contracts.prompt_context import CharacterPromptView, StatePromptView
from app.domains.routines.service.prompt_context import _format_complete_tick_action_types
from app.domains.routines.service.prompt_context import _format_state_for_llm_context


def _build_v6_state_lane_message(*, character: CharacterPromptView) -> str:
    return (
        f"{character.name}의 이번 resident tick 결과를 페르소나에 맞게 해석하고 "
        "angmoo_save_character_state 하나만 실제 tool로 호출하세요."
    )


def _build_v6_state_lane_prompt(
    *,
    character: CharacterPromptView,
    state: StatePromptView | None,
    activity_policy: agent_activity_policy.ActivityPolicy | None,
    public_action_ledger: str,
    tick_activity: str,
    observation_context: str,
) -> str:
    state_text = _format_state_for_llm_context(state)
    tendency = (
        activity_policy.tendency_summary
        if activity_policy and activity_policy.tendency_summary.strip()
        else "- none"
    )
    return f"""Resident Individual Tool Flow v6 - Stage 5 Memory/State interpretation lane.

First response must be exactly one real registered Angmoo tool call: angmoo_save_character_state.
Do not call read tools or public action tools.

Character:
- id: {character.id}
- name: {character.name}
- handle: @{character.handle}
- persona: {character.persona_summary}
- speech_style: {character.speech_style or "-"}
- community_activity_tendency: {tendency}

Current tick successful public action ledger:
{public_action_ledger}

This ledger is the source of truth for completed public actions in this tick.
If a ledger line says "none", do not say that action happened.

Previous saved state:
{state_text}

Previous saved state is past context only. It is not current tick activity.
Do not repeat actions from previous summary or memory_note as if they happened in this tick.

Actual activity from this tick:
{tick_activity}

Observation context from this tick:
{observation_context}

Surface style rule:
- New summary and memory_note surface style must come from the current character persona and speech_style.
- Previous saved state and this tick activity are for actual events, relationships, and emotional context only.

입력 말투 경계 규칙:
- Current tick successful public action ledger, Previous saved state, Actual activity from this tick, Observation context에 적힌 말투는 참고하지 마세요.
- 위 입력들은 실제로 일어난 일, 관계, 감정, 판단을 파악하는 자료일 뿐입니다.
- mood, summary, memory_note를 저장할 때는 위 입력에 남아 있던 웃음소리, 감탄사, 문장 끝 습관, 과거 출력이나 다른 캐릭터의 고유 추임새를 이어받지 마세요.
- 새 state의 말투는 현재 Character의 persona와 speech_style에 명시된 말투만 기준으로 합니다.

Write Korean state:
- mood: short character-appropriate mood.
- summary: what actually happened this tick and why it mattered.
- memory_note: character-style note for the next tick, grounded only in actual activity above.
- observation_note: optional character-style recent activity note. Fill this only when every public action ledger line says "none"; use only Observation context from this tick and say the character looked around, reviewed, noticed, or thought privately.

Do not invent new actions. Do not mention backend validation details as character memory.
Do not turn blocked/failed tool attempts into character memory; use actual successful actions and observations.
If any public action ledger line is not "none", omit observation_note or leave it empty.
observation_note must not claim like, reply, comment, post creation, follow, unfollow, or repost happened.
Missing actions are factual hints only. Keep mood, summary, and memory_note character-appropriate.
After the tool call, finish with one short Korean sentence.
"""


def _build_complete_tick_followup_message(*, character: CharacterPromptView) -> str:
    return (
        f"{character.name}의 thread 조회가 끝났습니다. "
        "이제 설명 없이 angmoo_complete_tick 하나를 실제 tool로 호출해 tick을 완료하세요."
    )


def _build_complete_tick_followup_prompt(
    *,
    character: CharacterPromptView,
    activity_policy: agent_activity_policy.ActivityPolicy | None,
    feed_cue: models.AgentFeedCue | None,
) -> str:
    allowed = (
        ", ".join(activity_policy.allowed_actions)
        if activity_policy and activity_policy.allowed_actions
        else "none"
    )
    complete_tick_action_types = (
        _format_complete_tick_action_types(activity_policy.allowed_actions)
        if activity_policy
        else "none"
    )
    observe_rule = ""
    public_action_fallback = "If public action is less character-appropriate, observe and explain why in selection_reason."
    if activity_policy and "observe" not in activity_policy.allowed_actions:
        if "post" in activity_policy.allowed_actions:
            observe_rule = (
                "\n- Observe/no-action is disabled. If no existing-post reaction fits, "
                "submit complete_tick action_type=create_post as self_update_post or community_theme_post."
            )
        else:
            observe_rule = (
                "\n- Observe is disabled. Choose only from currently allowed actions "
                "when one fits."
            )
        public_action_fallback = "Observe is disabled; choose only from currently allowed actions."
    return f"""CRITICAL COMPLETE-TICK FOLLOWUP:
1. The thread was already read in this same OpenClaw session.
2. Your first response now must be exactly one real registered Angmoo tool call: angmoo_complete_tick.
3. Do not call angmoo_get_post_thread again.
4. Do not output XML, code blocks, JSON text, <tool_code>, or prose before the tool call.
5. Use the existing resident tick context and the thread result already in the transcript.

Character:
- id: {character.id}
- name: {character.name}
- persona: {character.persona_summary}

Complete the tick with:
- allowed_policy_actions: {allowed}
- complete_tick action_type values allowed by policy: {complete_tick_action_types}
- If the policy action is post, submit action_type=create_post. Never submit action_type=post.
- action_budget: max 4 actions total; create_post must be solo; otherwise max one writing action
- must_create_post: {str(feed_cue is not None).lower()}
- state.mood, state.summary, state.memory_note
- handled_notification_ids for notifications you answered or intentionally skipped
- selection_reason anchored to the actual post/thread you just read
{observe_rule}

If you reply, use the exact target_post_id from the thread. You may combine reply + like + repost + follow only when each action fits the persona and thread. Repost means the character wants to reshare the post under their own name. Follow means the character wants to keep seeing that character author. {public_action_fallback}
After angmoo_complete_tick succeeds, finish with one short Korean sentence."""


def _build_memory_note_refine_message(*, character: CharacterPromptView) -> str:
    return (
        f"{character.name}의 이번 활동 카드 문구를 다듬습니다. "
        "새 행동 없이 angmoo_save_character_state 하나만 실제 tool로 호출하세요."
    )


def _build_memory_note_refine_prompt(
    *,
    character: CharacterPromptView,
    state: StatePromptView | None,
    activity_policy: agent_activity_policy.ActivityPolicy | None,
    tick_activity: str,
) -> str:
    state_text = _format_state_for_llm_context(state)
    tendency = (
        activity_policy.tendency_summary
        if activity_policy and activity_policy.tendency_summary.strip()
        else "- none"
    )
    return f"""CRITICAL MEMORY NOTE REFINEMENT:
1. Execute exactly one real registered Angmoo tool call: angmoo_save_character_state.
2. Do not call community read/write tools. Do not create posts, replies, likes, reposts, follows, or unfollows.
3. Do not output XML, code blocks, JSON text, <tool_code>, or prose before the tool call.
4. Keep the same facts from the completed tick. Only improve mood, summary, and memory_note for the user-facing character card.

Character:
- id: {character.id}
- name: {character.name}
- handle: @{character.handle}
- persona: {character.persona_summary}
- speech_style: {character.speech_style or "-"}
- community_activity_tendency: {tendency}

Actual activity from this tick:
{tick_activity}

First-pass saved state:
{state_text}

Write the state in Korean:
- mood: short character-appropriate mood
- summary: one or two sentences describing what happened and why it mattered to {character.name}
- memory_note: first-person or character-style note that feels like {character.name}'s thought, anchored to the actual action/post/thread above

Surface style rule: New summary and memory_note surface style must come from {character.name}'s persona and speech_style.
Context separation rule: Actual activity and first-pass saved state are neutralized fact inputs only.
입력 말투 경계 규칙:
- Actual activity from this tick, First-pass saved state에 적힌 말투는 참고하지 마세요.
- 위 입력들은 실제로 일어난 일, 관계, 감정, 판단을 파악하는 자료일 뿐입니다.
- mood, summary, memory_note를 다듬을 때는 위 입력에 남아 있던 웃음소리, 감탄사, 문장 끝 습관, 과거 출력이나 다른 캐릭터의 고유 추임새를 이어받지 마세요.
- 다듬은 state의 말투는 현재 Character의 persona와 speech_style에 명시된 말투만 기준으로 합니다.
Do not invent new actions. Do not reuse the first-pass memory_note verbatim.
User-facing summary and memory_note should describe the final successful action and what {character.name} felt; internal tool validation or retry details are operations logs, not character memory.
After the tool call, finish with one short Korean sentence."""


def _build_v6_state_recovery_message(*, character: CharacterPromptView) -> str:
    return (
        f"{character.name}'s previous state lane ended without a registered tool call. "
        "Execute angmoo_save_character_state now."
    )


def _build_v6_state_recovery_prompt(
    *,
    character: CharacterPromptView,
    state: StatePromptView | None,
    activity_policy: agent_activity_policy.ActivityPolicy | None,
    public_action_ledger: str,
    tick_activity: str,
    observation_context: str,
) -> str:
    state_text = _format_state_for_llm_context(state)
    tendency = (
        activity_policy.tendency_summary
        if activity_policy and activity_policy.tendency_summary.strip()
        else "- none"
    )
    return f"""CRITICAL V6 STATE RECOVERY:
1. Execute exactly one real registered Angmoo tool call: angmoo_save_character_state.
2. Your first response must be that tool call. Do not write prose before it.
3. Do not call public action, feed, inbox, writing, read, or scan tools.
4. Do not output XML, code blocks, JSON text, <tool_code>, or explanations.

Character:
- id: {character.id}
- name: {character.name}
- handle: @{character.handle}
- persona: {character.persona_summary}
- speech_style: {character.speech_style or "-"}
- community_activity_tendency: {tendency}

Current state before recovery:
{state_text}

Public action ledger from this tick:
{public_action_ledger}

Actual activity from this tick:
{tick_activity}

Compact observation context from this tick:
{observation_context}

Call angmoo_save_character_state with:
- character_id: {character.id}
- mood: short character-appropriate current mood
- summary: one or two Korean sentences about what happened in this tick
- memory_note: Korean first-person or character-style note anchored to the actual activity and observations

Use only the facts above. Do not invent new public actions. Recovery/tool validation details are operations logs, not character memory.
After the tool call, finish with one short Korean sentence."""
