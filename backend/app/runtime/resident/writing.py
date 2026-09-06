"""Same-session Social/Lore collaboration and actual gateway writer execution."""

from __future__ import annotations

import asyncio
import hashlib
import logging
from typing import Any

from pydantic import ValidationError
from sqlalchemy.orm import Session

from app.config import settings
from app.core.context_text import neutralize_context_text
from app.cruds import agent_runs as agent_run_crud
from app.cruds import community as community_crud
from app.domains.characters.service import profile as character_profile
from app.domains.characters.service import state as character_state
from app.domains.identity.models import LlmCredential
from app.domains.routines import models
from app.domains.routines.constants import (
    WRITING_TOOLS_ALLOWED as TOOLS_ALLOW_WRITING_COMPOSITION,
)
from app.domains.routines.contracts.writing import WritingKind, WritingPromptWorkflows
from app.domains.routines.exceptions import (
    WritingCompositionError,
    WritingCompositionInvalidError,
)
from app.domains.routines.service import activity_settings, writing_prompts
from app.domains.routines.service.writing_prompts import (
    _build_composition_prompt,
    _is_self_update_create_post_brief,
)
from app.domains.routines.service.writing_results import (
    _agent_tool_header_source,
    _append_writing_composition_lane,
    _build_compact_action_memory,
    _compact_tool_usage,
    _composition_metadata_field,
    _extract_gateway_llm_usage,
    _extract_gateway_result_text,
    _parse_json_object,
    _resolve_create_post_brief,
    _writing_stream_params,
)
from app.domains.social.schemas import community as schemas
from app.services import character_lore as character_lore_service
from app.services import community as community_service
from app.services.agent_writing import _record_daypart_action_memory
from app.services.runtime_boundary import OpenClawGatewayClient, OpenClawGatewayError

logger = logging.getLogger("app.services.agent_writing")


def prompt_workflows() -> WritingPromptWorkflows:
    return WritingPromptWorkflows(
        _format_reply_context=_format_reply_context,
        _format_recent_activity=lambda character_id, db: (
            writing_prompts._format_recent_activity(
                character_id,
                db,
                activity_result_text=community_service.activity_result_text_for_prompt,
            )
        ),
        format_lore_prompt_context=character_lore_service.format_lore_prompt_context,
    )


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

    post = community_service.reply_agent_tool_post(db, session_key, post_id, reply_data)
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
    character = character_profile.get_character(db, character_id)
    if character is None or character.deleted_at is not None:
        raise community_service.CharacterNotFoundError(character_id)
    credential = _run_credential(db, run)
    setting = activity_settings.ensure_setting(db, character_id)
    state = character_state.get_character_state(db, character_id)
    lore_retrieval = (
        character_lore_service.retrieve_lore_for_self_update(db, character=character)
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
        workflows=prompt_workflows(),
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


def _run_credential(db: Session, run: models.AgentRun) -> LlmCredential:
    if not run.credential_id:
        raise WritingCompositionError("active run has no credential")
    credential = agent_run_crud.get_credential(db, run.credential_id)
    if credential is None or not credential.enabled:
        raise WritingCompositionError("active run credential is not available")
    return credential


def _run_composition_gateway(
    *,
    run: models.AgentRun,
    credential: LlmCredential,
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
    lookup_session_key = _writing_scratch_base_session_key(
        run, fallback_session_key=session_key
    )
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
    raise WritingCompositionError(
        "writing composition cannot run inside an active event loop"
    )


def _writing_scratch_base_session_key(
    run: models.AgentRun, *, fallback_session_key: str
) -> str:
    gateway_result = run.gateway_result if isinstance(run.gateway_result, dict) else {}
    session_context = gateway_result.get("session_context")
    if isinstance(session_context, dict):
        memory_session_key = session_context.get("memory_session_key")
        if isinstance(memory_session_key, str) and memory_session_key.strip():
            return memory_session_key.strip()
    return community_service._agent_tool_lookup_session_key(
        run.session_key or fallback_session_key
    )


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
