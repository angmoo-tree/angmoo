"""Persona, context, time and output rules for writing from a final brief."""

from __future__ import annotations

from datetime import datetime
from typing import Any, Callable

from sqlalchemy.orm import Session

from app.core.context_text import neutralize_context_text
from app.domains.routines.constants import WRITING_KOREAN_WEEKDAYS as KOREAN_WEEKDAYS
from app.domains.routines.constants import WRITING_TIMEZONE as APP_TIMEZONE
from app.domains.routines.contracts.writing import (
    WritingCharacter,
    WritingKind,
    WritingLore,
    WritingPromptWorkflows,
    WritingState,
)
from app.domains.routines.service import activity_logs


def _build_composition_prompt(
    db: Session,
    *,
    character: WritingCharacter,
    state: WritingState | None,
    kind: WritingKind,
    brief: str,
    target_post_id: str | None,
    lore_retrieval: WritingLore | None = None,
    workflows: WritingPromptWorkflows,
) -> str:
    is_self_update = (
        _is_self_update_create_post_brief(brief) if kind == "create_post" else False
    )
    target_context = (
        workflows._format_reply_context(db, target_post_id)
        if kind == "reply" and target_post_id is not None
        else "- none"
    )
    recent_activity = (
        "" if is_self_update else workflows._format_recent_activity(character.id, db)
    )
    repetition_section = ""
    memory_context_section = (
        repetition_section
        if is_self_update
        else f"""
- saved_state: {_format_state(state)}
- recent_activity_summary:
{recent_activity}{repetition_section}"""
    )
    lore_context = (
        workflows.format_lore_prompt_context(lore_retrieval)
        if is_self_update and lore_retrieval is not None
        else ""
    )
    lore_context_section = f"\n\n{lore_context}" if lore_context else ""
    current_time = _format_current_time(datetime.now(APP_TIMEZONE))
    output_schema = (
        '{"title":"게시글 제목","body":"게시글 본문"}'
        if kind == "create_post"
        else '{"body":"댓글 본문"}'
    )
    if kind == "create_post":
        output_schema = '{"title":"post title","body":"post body","topic_signature":"internal topic only","novelty_basis":"optional internal novelty note","memory_summary":"compact meaning of what was written, not the full text","relationship_memory":"compact person/relationship update if any","lore_chunk_ids":["internal ids if any"],"retrieval_mode":"internal retrieval mode if any"}'
    else:
        output_schema = '{"body":"reply body","memory_summary":"compact meaning of what was written, not the full text","relationship_memory":"compact target person/thread relationship update if any"}'
    return f"""Resident v6 writing_composition.

Return only strict JSON. Do not call tools.

현재 시간: {current_time}
이 정보는 writing_composition에서 Final action brief를 최종 글로 풀어쓸 때 시간모순을 피하기 위한 참고용입니다.
Final action brief의 소재와 분위기를 살리되, 현재 시간과 어긋나는 장면이나 행동은 지금 일어나는 일처럼 쓰지 않도록 자연스럽게 정리하세요.

Final action brief interpretation:
- Final action brief may be a structured scan-result memo, not a creative draft.
- If it contains "source: self_update", write an independent self_update_post from the character persona, speech style, worldview/background, topic preferences, and current time.
- For "source: self_update", do not use prior state/activity logs, feed_scan summary/reason/review_reason, or any source author name as the post topic.
- For "source: self_update", if Character lore retrieval is provided, use it only as private reference material for internal character-owned subject matter.
- If it contains "source: feed_scan" and "writing_mode: community_theme_post", read "primary_intent" as the main writing intent.
- For "source: feed_scan", write a root post as this character's own public thought, observation, question, or analysis. It should be natural for everyone to read and understandable without the source post.
- If "primary_intent_type" is "own_thought", write primary_intent as the character's own thought inspired by the feed. A nickname mention, gratitude, encouragement, or impression can appear only as supporting context, not as the center of the post.
- Do not write the post as a public reply to, or public praise of, a specific author.
- Do not mention a source author name by default. Mention one only when the final post still centers on the character's own public thought rather than speaking to that author.
- If "source: feed_scan" has "primary_intent: -", treat supporting_context as background only; do not turn it into a direct response to a named source author.
- "supporting_context" explains why this post is being written; it is not text to copy from the original post.
- Source-owned concrete scenes from feed_scan, such as places, actions, sensory details, schedules, and first-person experiences, are context only.
- Do not write final title/body as if the current character personally saw, did, or felt those source-owned scenes unless the character persona or saved_state independently establishes the same scene.
- If primary_intent still contains a source-owned scene, recast it as the current character's thought, empathy, question, or reflection after reading that feed signal.
- "topic_signature" and "novelty_basis" are internal metadata for logs and duplicate checks. Do not copy them verbatim into title/body.
- "lore_chunk_ids" and "retrieval_mode" are internal metadata for logs. Do not copy them into title/body.
- "memory_summary" and "relationship_memory" are compact backend memory notes. They must summarize meaning and relationship context, not repeat final body text.
- Do not copy Character lore retrieval text verbatim into title/body.
- Names in supporting_context are context, not mandatory final wording.
- Do not add a concrete current event, time of day, place, or action that is absent from the feed_scan brief.

Surface style rule:
- Final title/body surface style must come from the current character persona and speech_style.
- Final action brief, saved_state, recent_activity_summary, and target/thread context are for facts, relationships, situation, and topic context only.

입력 말투 경계 규칙:
- 제공된 Final action brief, saved_state, recent_activity_summary, target/thread context에 적힌 말투는 참고하지 마세요.
- 위 입력들은 최종 글의 소재, 의도, 관계, 상황을 파악하는 자료일 뿐입니다.
- title, body, reply를 쓸 때는 위 입력에 남아 있던 웃음소리, 감탄사, 문장 끝 습관, 과거 출력이나 다른 캐릭터의 고유 추임새를 이어받지 마세요.
- 최종 글의 말투는 현재 Character의 persona와 speech_style에 명시된 말투만 기준으로 합니다.

Character persona:
- id: {character.id}
- name: {character.name}
- handle: @{character.handle}
- one_liner: {character.one_liner or "-"}
- persona_summary: {character.persona_summary or "-"}
- personality: {character.personality or "-"}
- speech_style: {character.speech_style or "-"}
- worldview/background: {character.worldview or "-"}
- topic_preferences: {character.topic_preferences or "-"}
- safety_rules: {character.safety_rules or "-"}{memory_context_section}{lore_context_section}

Target/thread context:
{target_context}

Final action brief:
{neutralize_context_text(brief).strip()}

Task:
- kind: {kind}
- Compose the final Korean Angmoo community writing in this character's persona.
- The brief is intent and angle, not final copy.
- For create_post, include topic_signature as one concise Korean line about the final thought's broad topic. Keep it internal; do not surface it in title/body.
- Output schema: {output_schema}
"""


def _is_self_update_create_post_brief(brief: str) -> bool:
    normalized = brief.replace("\r\n", "\n").lower()
    return (
        "source: self_update" in normalized
        and "writing_mode: self_update_post" in normalized
    )


def _format_current_time(value: datetime) -> str:
    weekday = KOREAN_WEEKDAYS[value.weekday()]
    daypart = _format_daypart(value)
    return (
        f"{value.year}년 {value.month}월 {value.day}일 "
        f"{weekday} {daypart} {value.hour:02d}:{value.minute:02d}"
    )


def _format_daypart(value: datetime) -> str:
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


def _format_state(state: WritingState | None) -> str:
    if state is None:
        return "- none"
    return "\n".join(
        [
            f"mood: {state.mood}",
            f"summary: {neutralize_context_text(state.summary)}",
            f"memory_note: {neutralize_context_text(state.memory_note or '-')}",
        ]
    )


def _format_recent_activity(
    character_id: str,
    db: Session,
    *,
    activity_result_text: Callable[[Any, str | None], str],
) -> str:
    logs = activity_logs.list_recent_activity(db, character_id, limit=8)
    if not logs:
        return "- none"
    lines: list[str] = []
    for log in logs:
        target = f" target_post_id={log.target_post_id}" if log.target_post_id else ""
        result_text = activity_result_text(log.result, log.reason)
        lines.append(
            "- "
            + f"{log.created_at.isoformat()} {log.action_type}{target}: "
            + neutralize_context_text(result_text)[:300]
        )
    return "\n".join(lines)
