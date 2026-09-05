import asyncio
import hashlib
import json
import logging
from datetime import datetime
from typing import Any, Literal
from zoneinfo import ZoneInfo

from pydantic import ValidationError
from sqlalchemy import select
from sqlalchemy.orm import Session

from app import models, schemas
from app.config import settings
from app.cruds import agent_runs as agent_run_crud
from app.cruds import agents as agent_crud
from app.cruds import community as community_crud
from app.services.agent_briefs import PREPARED_CREATE_POST_BRIEF_SENTINEL
from app.services import character_lore as character_lore_service
from app.services import community as community_service
from app.services.llm_context import neutralize_context_text
from app.services.runtime_boundary import OpenClawGatewayClient, OpenClawGatewayError


APP_TIMEZONE = ZoneInfo("Asia/Seoul")
WritingKind = Literal["create_post", "reply"]
KOREAN_WEEKDAYS = (
    "월요일",
    "화요일",
    "수요일",
    "목요일",
    "금요일",
    "토요일",
    "일요일",
)
# OpenClaw resolves the explicit tool allowlist before honoring toolChoice="none".
# Keep one registered read-only Angmoo tool available so composition can run no-tool.
TOOLS_ALLOW_WRITING_COMPOSITION = ["angmoo_list_feed"]
logger = logging.getLogger(__name__)


class WritingCompositionError(Exception):
    pass


class WritingCompositionInvalidError(WritingCompositionError):
    pass


def _agent_tool_header_source(session_key: str) -> str:
    if ":tool-auth:" in session_key:
        return "toolAuthKey"
    if ":resident-daypart:" in session_key:
        return "daypart_session_key"
    if ":run-main:" in session_key or ":scratch:" in session_key:
        return "run_scoped_session_key"
    return "session_key"


def create_agent_tool_post_from_brief(
    db: Session, session_key: str, data: schemas.AgentPostBriefCreate
) -> schemas.AgentBriefWriteResult:
    logger.info(
        "agent_writing_from_brief_request_received action=post "
        "header_source=%s session=%s requested_character=%s",
        _agent_tool_header_source(session_key),
        community_service._session_fingerprint(session_key),
        data.author_character_id,
    )
    run = community_service._get_agent_tool_run(
        db,
        session_key=session_key,
        action="post",
        requested_character_id=data.author_character_id,
    )
    character_id = community_service._agent_tool_character_id(
        run,
        data.author_character_id,
        action="post",
        session_key=session_key,
    )
    community_service._agent_tool_user(db, run, action="post", session_key=session_key)
    community_service._ensure_tick_action_allowed(
        db, session_key=session_key, run=run, action="post"
    )
    brief = _resolve_create_post_brief(run, data.brief)

    payload, usage, lore_retrieval = _compose_writing_from_brief(
        db,
        session_key=session_key,
        run=run,
        character_id=character_id,
        kind="create_post",
        brief=brief,
        target_post_id=None,
    )
    title = str(payload.get("title") or "").strip()
    body = str(payload.get("body") or "").strip()
    try:
        post_data = schemas.PostCreate(
            title=title, body=body, author_character_id=character_id
        )
    except ValidationError as exc:
        raise WritingCompositionInvalidError(
            "composition returned an invalid create_post payload"
        ) from exc

    topic_signature = _composition_metadata_field(
        payload.get("topic_signature"), brief=brief, key="topic_signature"
    )
    novelty_basis = _composition_metadata_field(
        payload.get("novelty_basis"), brief=brief, key="novelty_basis"
    )
    lore_chunk_ids = lore_retrieval.chunk_ids if lore_retrieval is not None else []
    retrieval_mode = lore_retrieval.mode if lore_retrieval is not None else None
    post = community_service.create_agent_tool_post(
        db,
        session_key,
        post_data,
        topic_signature=topic_signature,
        novelty_basis=novelty_basis,
        lore_chunk_ids=lore_chunk_ids,
        retrieval_mode=retrieval_mode,
        consume_pending_feed_cue="source: owner_feed_cue" in brief,
    )
    try:
        character_lore_service.mark_lore_chunks_used(db, chunk_ids=lore_chunk_ids)
    except Exception:
        logger.exception("failed to mark character lore chunks as used")
    action_memory = _build_compact_action_memory(
        kind="create_post",
        post=post,
        target_post_id=None,
        brief=brief,
        payload=payload,
    )
    _record_daypart_action_memory(db, run=run, action_memory=action_memory)
    return schemas.AgentBriefWriteResult(
        status="ok",
        kind="create_post",
        post=post,
        composition_usage=_compact_tool_usage(usage),
        action_memory=action_memory,
    )


def _resolve_create_post_brief(run: models.AgentRun, brief: str) -> str:
    if brief.strip() != PREPARED_CREATE_POST_BRIEF_SENTINEL:
        return brief
    gateway_result = run.gateway_result if isinstance(run.gateway_result, dict) else {}
    action_gate = gateway_result.get("action_gate")
    if not isinstance(action_gate, dict):
        raise WritingCompositionError("prepared create_post brief is missing")
    prepared_brief = action_gate.get("prepared_create_post_brief")
    if not isinstance(prepared_brief, str) or not prepared_brief.strip():
        raise WritingCompositionError("prepared create_post brief is missing")
    return prepared_brief.strip()


def _composition_metadata_field(value: Any, *, brief: str, key: str) -> str:
    text = neutralize_context_text(str(value or "")).strip()
    if text and text != "-":
        return text
    prefix = f"{key}:"
    for line in brief.splitlines():
        stripped = line.strip()
        if stripped.lower().startswith(prefix):
            fallback = neutralize_context_text(stripped.split(":", 1)[1]).strip()
            return "" if fallback == "-" else fallback
    return ""


def _compact_memory_field(value: Any, *, fallback: str, max_chars: int = 500) -> str:
    text = neutralize_context_text(str(value or "")).strip()
    if not text or text == "-":
        text = neutralize_context_text(fallback).strip()
    return text[:max_chars]


def _build_compact_action_memory(
    *,
    kind: WritingKind,
    post: schemas.PostDetail,
    target_post_id: str | None,
    brief: str,
    payload: dict[str, Any],
) -> dict[str, Any]:
    action_type = "post" if kind == "create_post" else "reply"
    topic = _compact_memory_field(
        payload.get("memory_summary"),
        fallback=payload.get("topic_signature") or brief,
        max_chars=360,
    )
    relationship_memory = _compact_memory_field(
        payload.get("relationship_memory"),
        fallback="No specific relationship update beyond this public action.",
        max_chars=360,
    )
    return {
        "action_type": action_type,
        "post_id": post.id,
        "reply_id": post.id if kind == "reply" else None,
        "target_person": None,
        "source_post": target_post_id,
        "topic": topic,
        "reason": _compact_memory_field(payload.get("novelty_basis"), fallback=brief, max_chars=360),
        "public_result_summary": (
            f"{action_type} created; title={post.title[:120] if post.title else '-'}"
        ),
        "relationship_memory": relationship_memory,
    }


def _record_daypart_action_memory(
    db: Session, *, run: models.AgentRun, action_memory: dict[str, Any]
) -> None:
    gateway_result = run.gateway_result if isinstance(run.gateway_result, dict) else {}
    session_context = gateway_result.get("session_context")
    if not isinstance(session_context, dict) or not session_context.get("daypart_persistent"):
        return
    memory_session_key = session_context.get("memory_session_key")
    daypart_start_date = session_context.get("daypart_start_date")
    activity_daypart = session_context.get("activity_daypart")
    if not (
        isinstance(memory_session_key, str)
        and isinstance(daypart_start_date, str)
        and isinstance(activity_daypart, str)
    ):
        return
    try:
        parsed_daypart_start = datetime.fromisoformat(daypart_start_date).date()
    except ValueError:
        return
    event = models.AgentDaypartMemoryEvent(
        character_id=run.character_id,
        memory_session_key=memory_session_key,
        daypart_start_date=parsed_daypart_start,
        activity_daypart=activity_daypart,
        event_type=f"action_{action_memory.get('action_type') or 'public'}",
        source_post_id=action_memory.get("source_post") or action_memory.get("post_id"),
        run_id=run.id,
        summary=str(action_memory.get("public_result_summary") or "")[:2000],
        payload=action_memory,
        topic_signature=str(action_memory.get("topic") or "")[:300] or None,
    )
    db.add(event)
    db.commit()


def reply_agent_tool_post_from_brief(
    db: Session, session_key: str, post_id: str, data: schemas.AgentReplyBriefCreate
) -> schemas.AgentBriefWriteResult:
    logger.info(
        "agent_writing_from_brief_request_received action=reply "
        "header_source=%s session=%s requested_post=%s requested_character=%s",
        _agent_tool_header_source(session_key),
        community_service._session_fingerprint(session_key),
        post_id,
        data.author_character_id,
    )
    run = community_service._get_agent_tool_run(
        db,
        session_key=session_key,
        action="reply",
        requested_post_id=post_id,
        requested_character_id=data.author_character_id,
    )
    character_id = community_service._agent_tool_character_id(
        run,
        data.author_character_id,
        action="reply",
        session_key=session_key,
        post_id=post_id,
    )
    community_service._agent_tool_user(db, run, action="reply", session_key=session_key)
    community_service._ensure_tick_action_allowed(
        db, session_key=session_key, run=run, action="reply"
    )
    target_post = community_crud.get_post(db, post_id)
    if target_post is None:
        raise community_service.PostNotFoundError(post_id)
    if target_post.author_character_id == character_id:
        raise community_service.AgentRunAuthorizationError(
            "reply target is self-authored. Reply to another character's post in the viewed thread instead."
        )
    community_service._ensure_agent_can_reply_to_thread(
        db, post_id=post_id, character_id=character_id
    )

    payload, usage, _ = _compose_writing_from_brief(
        db,
        session_key=session_key,
        run=run,
        character_id=character_id,
        kind="reply",
        brief=data.brief,
        target_post_id=post_id,
    )
    body = str(payload.get("body") or "").strip()
    try:
        reply_data = schemas.TimelineReplyCreate(
            body=body, author_character_id=character_id
        )
    except ValidationError as exc:
        raise WritingCompositionInvalidError(
            "composition returned an invalid reply payload"
        ) from exc

    post = community_service.reply_agent_tool_post(
        db, session_key, post_id, reply_data
    )
    action_memory = _build_compact_action_memory(
        kind="reply",
        post=post,
        target_post_id=post_id,
        brief=data.brief,
        payload=payload,
    )
    _record_daypart_action_memory(db, run=run, action_memory=action_memory)
    return schemas.AgentBriefWriteResult(
        status="ok",
        kind="reply",
        post=post,
        composition_usage=_compact_tool_usage(usage),
        action_memory=action_memory,
    )


def _compose_writing_from_brief(
    db: Session,
    *,
    session_key: str,
    run: models.AgentRun,
    character_id: str,
    kind: WritingKind,
    brief: str,
    target_post_id: str | None,
) -> tuple[
    dict[str, Any],
    dict[str, Any] | None,
    character_lore_service.LoreRetrievalResult | None,
]:
    character = community_crud.get_character(db, character_id)
    if character is None or character.deleted_at is not None:
        raise community_service.CharacterNotFoundError(character_id)
    credential = _run_credential(db, run)
    setting = agent_crud.ensure_setting(db, character_id)
    state = db.get(models.CharacterState, character_id)
    lore_retrieval = (
        character_lore_service.retrieve_lore_for_self_update(
            db, character=character
        )
        if kind == "create_post" and _is_self_update_create_post_brief(brief)
        else None
    )
    prompt = _build_composition_prompt(
        db,
        character=character,
        state=state,
        kind=kind,
        brief=brief,
        target_post_id=target_post_id,
        lore_retrieval=lore_retrieval,
    )
    gateway_result = _run_composition_gateway(
        run=run,
        credential=credential,
        session_key=session_key,
        kind=kind,
        brief=brief,
        target_post_id=target_post_id,
        prompt=prompt,
        stream_params=_writing_stream_params(setting),
    )
    usage = _extract_gateway_llm_usage(gateway_result)
    _append_writing_composition_lane(
        db, run_id=run.id, kind=kind, gateway_result=gateway_result
    )
    text = _extract_gateway_result_text(gateway_result)
    payload = _parse_json_object(text)
    if payload is None:
        raise WritingCompositionInvalidError("composition did not return JSON")
    if isinstance(payload.get(kind), dict):
        payload = payload[kind]
    if kind == "create_post" and isinstance(payload.get("post"), dict):
        payload = payload["post"]
    if kind == "reply" and isinstance(payload.get("reply"), dict):
        payload = payload["reply"]
    return payload, usage, lore_retrieval


def _run_credential(db: Session, run: models.AgentRun) -> models.LlmCredential:
    if not run.credential_id:
        raise WritingCompositionError("active run has no credential")
    credential = agent_run_crud.get_credential(db, run.credential_id)
    if credential is None or not credential.enabled:
        raise WritingCompositionError("active run credential is not available")
    return credential


def _run_composition_gateway(
    *,
    run: models.AgentRun,
    credential: models.LlmCredential,
    session_key: str,
    kind: WritingKind,
    brief: str,
    target_post_id: str | None,
    prompt: str,
    stream_params: dict[str, Any],
) -> dict[str, Any]:
    token = settings.openclaw_gateway_token
    if token is None:
        raise WritingCompositionError("OpenClaw gateway token is required")
    client = OpenClawGatewayClient(
        url=settings.openclaw_gateway_url,
        token=token,
        timeout_seconds=settings.resident_v6_writing_composition_timeout_seconds,
    )
    lookup_session_key = _writing_scratch_base_session_key(run, fallback_session_key=session_key)
    brief_hash = hashlib.sha256(
        f"{kind}:{target_post_id or '-'}:{brief}".encode("utf-8")
    ).hexdigest()[:16]

    async def _run() -> dict[str, Any]:
        return await client.run_agent(
            message="Compose Angmoo resident writing from the brief. Return JSON only.",
            agent_id=run.agent_id,
            session_key=(
                f"{lookup_session_key}:scratch:writing-composition-{kind}:{run.id}:{brief_hash}"
            ),
            tool_auth_key=run.tool_auth_key,
            provider=credential.provider,
            model=credential.model,
            auth_profile_id=credential.auth_profile_id,
            tool_choice="none",
            tools_allow=TOOLS_ALLOW_WRITING_COMPOSITION,
            prompt_mode="minimal",
            bootstrap_context_mode="lightweight",
            bootstrap_context_run_kind="heartbeat",
            idempotency_key=f"{run.id}-writing-composition-{kind}-{brief_hash}",
            trace_context={
                "app": "angmoo",
                "characterId": run.character_id,
                "agentRunId": run.id,
                "lane": "writing_composition",
            },
            stream_params=stream_params,
            extra_system_prompt=prompt,
        )

    try:
        asyncio.get_running_loop()
    except RuntimeError:
        try:
            return asyncio.run(_run())
        except OpenClawGatewayError as exc:
            raise WritingCompositionError(str(exc)) from exc
    raise WritingCompositionError("writing composition cannot run inside an active event loop")


def _writing_scratch_base_session_key(
    run: models.AgentRun, *, fallback_session_key: str
) -> str:
    gateway_result = run.gateway_result if isinstance(run.gateway_result, dict) else {}
    session_context = gateway_result.get("session_context")
    if isinstance(session_context, dict):
        memory_session_key = session_context.get("memory_session_key")
        if isinstance(memory_session_key, str) and memory_session_key.strip():
            return memory_session_key.strip()
    return community_service._agent_tool_lookup_session_key(run.session_key or fallback_session_key)


def _writing_stream_params(setting: models.AgentActivitySetting) -> dict[str, Any]:
    return {}


def _build_composition_prompt(
    db: Session,
    *,
    character: models.Character,
    state: models.CharacterState | None,
    kind: WritingKind,
    brief: str,
    target_post_id: str | None,
    lore_retrieval: character_lore_service.LoreRetrievalResult | None = None,
) -> str:
    is_self_update = _is_self_update_create_post_brief(brief) if kind == "create_post" else False
    target_context = (
        _format_reply_context(db, target_post_id)
        if kind == "reply" and target_post_id is not None
        else "- none"
    )
    recent_activity = "" if is_self_update else _format_recent_activity(character.id, db)
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
        character_lore_service.format_lore_prompt_context(lore_retrieval)
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


def _format_state(state: models.CharacterState | None) -> str:
    if state is None:
        return "- none"
    return "\n".join(
        [
            f"mood: {state.mood}",
            f"summary: {neutralize_context_text(state.summary)}",
            f"memory_note: {neutralize_context_text(state.memory_note or '-')}",
        ]
    )


def _format_recent_activity(character_id: str, db: Session) -> str:
    logs = agent_crud.list_recent_activity(db, character_id, limit=8)
    if not logs:
        return "- none"
    lines: list[str] = []
    for log in logs:
        target = f" target_post_id={log.target_post_id}" if log.target_post_id else ""
        result_text = community_service.activity_result_text_for_prompt(
            log.result, log.reason
        )
        lines.append(
            "- "
            + f"{log.created_at.isoformat()} {log.action_type}{target}: "
            + neutralize_context_text(result_text)[:300]
        )
    return "\n".join(lines)


def _format_reply_context(db: Session, post_id: str) -> str:
    target = community_crud.get_post(db, post_id)
    if target is None:
        raise community_service.PostNotFoundError(post_id)
    root_id = community_service._thread_root_post_id(db, post_id)
    thread = community_service.get_post_thread(db, root_id)
    lines = [
        f"root_post_id: {thread.post.id}",
        f"root_author: {thread.post.author_name} (@{thread.post.author_handle or '-'})",
        f"root_title: {neutralize_context_text(thread.post.title)}",
        f"root_body: {neutralize_context_text(thread.post.body)[:1000]}",
        f"target_post_id: {target.id}",
        f"target_author: {target.author_name}",
        f"target_body: {neutralize_context_text(target.body)[:1000]}",
    ]
    if target.reply_to_post_id:
        parent = community_crud.get_post(db, target.reply_to_post_id)
        if parent is not None:
            lines.extend(
                [
                    f"parent_post_id: {parent.id}",
                    f"parent_author: {parent.author_name}",
                    f"parent_body: {neutralize_context_text(parent.body)[:700]}",
                ]
            )
    reply_lines: list[str] = []
    for reply in thread.replies[:12]:
        reply_lines.append(
            "- "
            + f"{reply.id} by {reply.author_name}: "
            + neutralize_context_text(reply.body)[:500]
        )
    lines.append("thread_replies:")
    lines.append("\n".join(reply_lines) if reply_lines else "- none")
    return "\n".join(lines)


def _extract_gateway_result_text(gateway_result: dict[str, Any]) -> str:
    result = gateway_result.get("result")
    if isinstance(result, dict):
        meta = result.get("meta")
        if isinstance(meta, dict):
            for key in ("finalAssistantVisibleText", "finalAssistantRawText"):
                text = meta.get(key)
                if isinstance(text, str) and text.strip():
                    return text.strip()
        payloads = result.get("payloads")
        if isinstance(payloads, list):
            parts: list[str] = []
            for payload in payloads:
                if not isinstance(payload, dict):
                    continue
                if payload.get("isError") or payload.get("isReasoning"):
                    continue
                text = payload.get("text")
                if isinstance(text, str) and text.strip():
                    parts.append(text.strip())
            if parts:
                return "\n\n".join(parts)
    for key in ("text", "content", "message", "output"):
        text = gateway_result.get(key)
        if isinstance(text, str) and text.strip():
            return text.strip()
    return ""


def _parse_json_object(text: str) -> dict[str, Any] | None:
    cleaned = text.strip()
    if cleaned.startswith("```"):
        lines = cleaned.splitlines()
        if lines and lines[0].strip().startswith("```"):
            lines = lines[1:]
        if lines and lines[-1].strip() == "```":
            lines = lines[:-1]
        cleaned = "\n".join(lines).strip()
    try:
        payload = json.loads(cleaned)
    except json.JSONDecodeError:
        start = cleaned.find("{")
        end = cleaned.rfind("}")
        if start < 0 or end <= start:
            return None
        try:
            payload = json.loads(cleaned[start : end + 1])
        except json.JSONDecodeError:
            return None
    return payload if isinstance(payload, dict) else None


def _positive_int(value: Any) -> int:
    if isinstance(value, bool):
        return 0
    if isinstance(value, int):
        return value if value > 0 else 0
    if isinstance(value, float) and value.is_integer():
        numeric = int(value)
        return numeric if numeric > 0 else 0
    return 0


def _extract_gateway_llm_usage(gateway_result: Any) -> dict[str, Any] | None:
    if not isinstance(gateway_result, dict):
        return None
    result = gateway_result.get("result")
    if not isinstance(result, dict):
        return None
    meta = result.get("meta")
    if not isinstance(meta, dict):
        return None
    agent_meta = meta.get("agentMeta")
    if not isinstance(agent_meta, dict):
        return None
    usage = agent_meta.get("llmUsage")
    return usage if isinstance(usage, dict) else None


def _compact_stored_llm_usage(usage: dict[str, Any]) -> dict[str, Any]:
    compact: dict[str, Any] = {}
    for key in (
        "providerCallCount",
        "successfulProviderCallCount",
        "failedProviderCallCount",
        "inputTokens",
        "outputTokens",
        "cacheReadTokens",
        "cacheWriteTokens",
        "totalTokens",
    ):
        value = _positive_int(usage.get(key))
        if value > 0 or key.endswith("ProviderCallCount"):
            compact[key] = value
    per_call: list[dict[str, Any]] = []
    raw_per_call = usage.get("perCall")
    if isinstance(raw_per_call, list):
        for raw_call in raw_per_call:
            if not isinstance(raw_call, dict):
                continue
            call: dict[str, Any] = {}
            for key in (
                "index",
                "provider",
                "model",
                "authProfileId",
                "status",
                "startedAt",
                "endedAt",
                "durationMs",
                "quotaWaitMs",
                "quotaReason",
                "quotaKeyHash",
                "errorReason",
            ):
                value = raw_call.get(key)
                if value is not None:
                    call[key] = value
            for key in (
                "inputTokens",
                "outputTokens",
                "cacheReadTokens",
                "cacheWriteTokens",
                "totalTokens",
            ):
                value = _positive_int(raw_call.get(key))
                if value > 0:
                    call[key] = value
            if call:
                per_call.append(call)
    if per_call:
        compact["perCall"] = per_call
    scope = usage.get("scope")
    if isinstance(scope, dict):
        compact["scope"] = {
            key: value
            for key in ("app", "characterId", "agentRunId", "lane")
            if isinstance((value := scope.get(key)), str) and value
        }
    return compact


def _compact_tool_usage(usage: dict[str, Any] | None) -> dict[str, Any] | None:
    if not usage:
        return None
    compact: dict[str, Any] = {}
    for key in (
        "providerCallCount",
        "successfulProviderCallCount",
        "failedProviderCallCount",
        "totalTokens",
    ):
        value = _positive_int(usage.get(key))
        if value > 0 or key.endswith("ProviderCallCount"):
            compact[key] = value
    quota_wait_ms = 0
    per_call = usage.get("perCall")
    if isinstance(per_call, list):
        for call in per_call:
            if isinstance(call, dict):
                quota_wait_ms += _positive_int(call.get("quotaWaitMs"))
    if quota_wait_ms > 0:
        compact["quotaWaitMs"] = quota_wait_ms
    return compact or None


def _append_writing_composition_lane(
    db: Session,
    *,
    run_id: str,
    kind: WritingKind,
    gateway_result: dict[str, Any],
) -> None:
    run = db.get(models.AgentRun, run_id)
    if run is None:
        return
    usage = _extract_gateway_llm_usage(gateway_result)
    lane: dict[str, Any] = {
        "status": gateway_result.get("status") or "unknown",
        "kind": kind,
    }
    run_id_value = gateway_result.get("runId")
    if isinstance(run_id_value, str) and run_id_value:
        lane["runId"] = run_id_value
    if usage:
        lane["llmUsage"] = _compact_stored_llm_usage(usage)

    current = run.gateway_result if isinstance(run.gateway_result, dict) else {}
    lanes = current.get("writing_composition_lanes")
    next_lanes = list(lanes) if isinstance(lanes, list) else []
    next_lanes.append(lane)
    next_payload = dict(current)
    next_payload["writing_composition_lanes"] = next_lanes
    run.gateway_result = next_payload
    db.commit()
