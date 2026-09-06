"""Bounded conversation context built from same-Session nullable post reads."""

from __future__ import annotations

import logging
from typing import Any

from sqlalchemy.orm import Session

from app.domains.routines.contracts.context_reads import (
    ConversationPostView,
    ConversationWorkflows,
)

logger = logging.getLogger("app.services.langgraph_resident")


_INBOX_CONVERSATION_TURN_LIMIT = 6

_INBOX_DIRECT_EXCHANGE_TURN_LIMIT = 6


def _conversation_turn_for_prompt(
    post: ConversationPostView,
    *,
    current_character_id: str,
    actor_character_id: str | None,
    body_chars: int = 280,
    workflows: ConversationWorkflows,
) -> dict[str, Any]:
    return {
        "post_id": post.id,
        "author": workflows.clip(post.author_name, 80),
        "is_current_character": post.author_character_id == current_character_id,
        "is_notification_actor": (
            bool(actor_character_id) and post.author_character_id == actor_character_id
        ),
        "body": workflows.clip(post.body, body_chars),
    }


def _thread_root_post_for_conversation_context(
    db: Session, source_post: ConversationPostView, *, workflows: ConversationWorkflows
) -> ConversationPostView:
    post = source_post
    seen = {post.id}
    while post.reply_to_post_id is not None:
        parent = workflows.get_post(db, post.reply_to_post_id)
        if parent is None or parent.id in seen:
            break
        post = parent
        seen.add(post.id)
    return post


def _inbox_conversation_context(
    db: Session,
    *,
    character_id: str,
    actor_character_id: str | None,
    source_post_id: str | None,
    workflows: ConversationWorkflows,
) -> dict[str, Any] | None:
    source_post = workflows.get_post(db, source_post_id)
    if source_post is None:
        return None
    try:
        root_post = _thread_root_post_for_conversation_context(
            db, source_post, workflows=workflows
        )
        replies = workflows.thread_replies(db, root_post.id, limit=20)
    except Exception:
        logger.debug(
            "Failed to build inbox conversation context",
            exc_info=True,
            extra={"source_post_id": source_post_id},
        )
        return None

    replies = sorted(replies, key=lambda item: (item.created_at, item.id))
    recent_turns = replies[-_INBOX_CONVERSATION_TURN_LIMIT:]
    pair_character_ids = {
        character_id,
        actor_character_id or source_post.author_character_id,
    }
    pair_character_ids.discard(None)
    direct_turns = [
        post
        for post in [root_post, *replies]
        if post.author_character_id in pair_character_ids
    ][-_INBOX_DIRECT_EXCHANGE_TURN_LIMIT:]
    return {
        "root_post": _conversation_turn_for_prompt(
            root_post,
            current_character_id=character_id,
            actor_character_id=actor_character_id,
            body_chars=160,
            workflows=workflows,
        ),
        "target_post": _conversation_turn_for_prompt(
            source_post,
            current_character_id=character_id,
            actor_character_id=actor_character_id,
            body_chars=200,
            workflows=workflows,
        ),
        "recent_thread_turns": [
            _conversation_turn_for_prompt(
                post,
                current_character_id=character_id,
                actor_character_id=actor_character_id,
                body_chars=160,
                workflows=workflows,
            )
            for post in recent_turns
        ],
        "direct_exchange_turns": [
            _conversation_turn_for_prompt(
                post,
                current_character_id=character_id,
                actor_character_id=actor_character_id,
                body_chars=160,
                workflows=workflows,
            )
            for post in direct_turns
        ],
    }
