"""Authorize a Social tool against the current resident run and requested scope.

Run lookup and activity admission use the caller Session through lazy owner
collaborators. Social owns the denial detail and the original fail-closed order.
"""

from __future__ import annotations
import hashlib
import logging
from sqlalchemy.orm import Session
from app.domains.social.contracts.agent_tools import (
    AgentToolReferences,
    ToolRun,
    ToolUser,
)
from app.domains.social.exceptions import AgentRunAuthorizationError

logger = logging.getLogger("app.services.community")


def _session_fingerprint(session_key: str) -> str:
    return hashlib.sha256(session_key.encode("utf-8")).hexdigest()[:12]


def _agent_tool_lookup_session_key(session_key: str) -> str:
    for marker in (":scratch:", ":run-main:"):
        if marker in session_key:
            return session_key.split(marker, 1)[0]
    return session_key


def _is_daypart_memory_session_key(session_key: str) -> bool:
    return ":resident-daypart:" in session_key


def _agent_tool_scratch_lane(session_key: str) -> str | None:
    marker = ":scratch:"
    if marker not in session_key:
        return None
    suffix = session_key.split(marker, 1)[1]
    lane = suffix.split(":", 1)[0].strip()
    return lane or None


def _raise_agent_tool_authorization_error(
    *,
    action: str,
    reason: str,
    session_key: str,
    run,
    requested_post_id: str | None = None,
    requested_character_id: str | None = None,
) -> None:
    detail = (
        f"Agent run is not authorized for this {action} "
        f"(reason={reason}, session={_session_fingerprint(session_key)}, "
        f"requested_post={requested_post_id or '-'}, "
        f"requested_character={requested_character_id or '-'}, "
        f"run_id={getattr(run, 'id', '-') if run else '-'}, "
        f"run_status={getattr(run, 'status', '-') if run else '-'}, "
        f"run_post={getattr(run, 'post_id', '-') if run else '-'}, "
        f"run_character={getattr(run, 'character_id', '-') if run else '-'})"
    )
    logger.warning("agent tool authorization denied: %s", detail)
    raise AgentRunAuthorizationError(detail)


def _get_agent_tool_run(
    db: Session,
    *,
    references: AgentToolReferences,
    session_key: str,
    action: str,
    requested_post_id: str | None = None,
    requested_character_id: str | None = None,
) -> ToolRun:
    run = references.get_active_run_for_tool_auth_key(db, session_key)
    if run is not None:
        return run
    if _is_daypart_memory_session_key(session_key):
        _raise_agent_tool_authorization_error(
            action=action,
            reason="daypart_session_key_not_authorized",
            session_key=session_key,
            run=None,
            requested_post_id=requested_post_id,
            requested_character_id=requested_character_id,
        )
    lookup_session_key = _agent_tool_lookup_session_key(session_key)
    run = references.get_active_run_for_session(db, lookup_session_key)
    if run is None:
        latest_run = references.get_latest_run_for_tool_auth_key(
            db, session_key
        ) or references.get_latest_run_for_session(db, lookup_session_key)
        _raise_agent_tool_authorization_error(
            action=action,
            reason="no_active_run",
            session_key=session_key,
            run=latest_run,
            requested_post_id=requested_post_id,
            requested_character_id=requested_character_id,
        )
    return run


def _agent_tool_character_id(
    run: ToolRun,
    requested_character_id: str | None,
    *,
    action: str,
    session_key: str,
    post_id: str | None = None,
) -> str:
    character_id = requested_character_id or run.character_id
    if character_id != run.character_id:
        _raise_agent_tool_authorization_error(
            action=action,
            reason="character_mismatch",
            session_key=session_key,
            run=run,
            requested_post_id=post_id,
            requested_character_id=character_id,
        )
    return character_id


def _agent_tool_user(
    db: Session,
    run: ToolRun,
    *,
    references: AgentToolReferences,
    action: str,
    session_key: str,
) -> ToolUser:
    user = references.get_user(db, run.user_id)
    if user is None:
        _raise_agent_tool_authorization_error(
            action=action,
            reason="user_missing",
            session_key=session_key,
            run=run,
            requested_character_id=run.character_id,
        )
    return user


def _ensure_tick_action_allowed(
    db: Session,
    *,
    references: AgentToolReferences,
    session_key: str,
    run: ToolRun,
    action: str,
) -> None:
    try:
        references.assert_action_allowed(db, run=run, action=action)
    except references.activity_policy_denied as exc:
        _raise_agent_tool_authorization_error(
            action=action,
            reason=str(exc),
            session_key=session_key,
            run=run,
            requested_post_id=run.post_id,
            requested_character_id=run.character_id,
        )
