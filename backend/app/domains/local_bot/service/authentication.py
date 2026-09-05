"""LocalBot token admission before the existing persisted last-used update."""

import logging

from sqlalchemy.orm import Session

from app.core import security
from app.domains.identity.service import demo_access as demo_lock
from app.domains.local_bot.constants import LOCAL_KEY_PREFIX
from app.domains.local_bot.contracts.authentication import (
    LocalBotAuthenticationWorkflows,
    LocalBotContext,
)
from app.domains.local_bot.exceptions import (
    LocalBotAuthError,
    LocalBotForbiddenError,
    LocalBotModeError,
)
from app.domains.local_bot.repository import keys as key_repository
from app.domains.local_bot.service import key_records

logger = logging.getLogger("app.services.local_bot")


def authenticate_local_bot(
    db: Session, token: str, *, workflows: LocalBotAuthenticationWorkflows
) -> LocalBotContext:
    token = token.strip()
    if not token.startswith(LOCAL_KEY_PREFIX):
        _log_auth_failure("invalid_prefix", token)
        raise LocalBotAuthError("Invalid local bot token.")
    local_key = key_repository.get_active_local_key_by_hash(
        db, security.hash_token(token)
    )
    if local_key is None:
        _log_auth_failure("not_found_or_revoked", token)
        raise LocalBotAuthError("Invalid local bot token.")
    character = workflows.get_character(db, local_key.character_id)
    if character is None or character.deleted_at is not None:
        raise LocalBotForbiddenError("Local bot character is not available.")
    if character.execution_mode != "local":
        raise LocalBotModeError("Only local mode characters can use bot API.")
    user = workflows.get_user(db, local_key.owner_id)
    if user is None or getattr(user, "deleted_at", None) is not None:
        raise LocalBotForbiddenError("Local bot owner is not available.")
    if demo_lock.is_locked_demo_user(user):
        raise LocalBotForbiddenError(demo_lock.DEMO_ACCOUNT_LOCKED_MESSAGE)
    local_key = key_records.mark_local_key_used(db, local_key)
    return LocalBotContext(user=user, character=character, local_key=local_key)


def _log_auth_failure(reason: str, token: str) -> None:
    logger.info(
        "local_bot_auth_failed reason=%s token_prefix=%s",
        reason,
        _redacted_token_prefix(token),
    )


def _redacted_token_prefix(token: str) -> str:
    if token.startswith(LOCAL_KEY_PREFIX):
        return f"{token[:24]}..."
    if not token:
        return "-"
    return f"{token[:8]}..."
