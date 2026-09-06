"""Canonical post-topic metadata, public-history eligibility and source precedence."""

from __future__ import annotations
from sqlalchemy.orm import Session
from app.core import unit_of_work
from app.core.json_objects import _json_object
from app.core.bounded_text import _safe_topic_text
from app.core.search_text import build_post_search_document
from app.domains.social.models import posts as models
from app.domains.social.contracts.topic_history import TopicHistoryReferences
from app.domains.social.repository.topic_history import get_topic_post
from app.domains.social.service.visibility import _is_post_public_context_visible
from app.domains.social.service.activity_results import _fallback_topic_signature


def _topic_metadata_from_result(value: str | None) -> dict[str, str]:
    payload = _json_object(value)
    topic_signature = _safe_topic_text(payload.get("topic_signature"), 300)
    novelty_basis = _safe_topic_text(payload.get("novelty_basis"), 500)
    return {"topic_signature": topic_signature, "novelty_basis": novelty_basis}


def _topic_metadata_from_post_columns(post: models.Post | None) -> dict[str, str]:
    if post is None:
        return {"topic_signature": "", "novelty_basis": ""}
    return {
        "topic_signature": _safe_topic_text(
            getattr(post, "topic_signature", None), 300
        ),
        "novelty_basis": _safe_topic_text(getattr(post, "novelty_basis", None), 500),
    }


def _store_post_topic_metadata(
    db: Session, *, post_id: str, topic_signature: str | None, novelty_basis: str | None
) -> None:
    topic = _safe_topic_text(topic_signature, 300)
    novelty = _safe_topic_text(novelty_basis, 500)
    if not topic and (not novelty):
        return
    post = get_topic_post(db, post_id)
    if post is None:
        return
    post.topic_signature = topic or None
    post.novelty_basis = novelty or None
    post.search_document = build_post_search_document(
        title=post.title, body=post.body, topic_signature=post.topic_signature
    )
    db.add(post)
    unit_of_work.finish_write(db, post)


def _recent_feed_interest_post_is_eligible(
    db: Session, *, character_id: str, post: models.Post
) -> bool:
    if post.author_character_id == character_id:
        return False
    if post.reply_to_post_id is not None:
        return False
    if post.post_type != "post":
        return False
    return _is_post_public_context_visible(db, post)


def _latest_post_created_topic_metadata(
    db: Session,
    *,
    references: TopicHistoryReferences,
    character_id: str | None,
    post_id: str,
) -> dict[str, str]:
    if db is not None:
        column_metadata = _topic_metadata_from_post_columns(get_topic_post(db, post_id))
        if column_metadata["topic_signature"] or column_metadata["novelty_basis"]:
            return column_metadata
    if db is None or character_id is None:
        return {"topic_signature": "", "novelty_basis": ""}
    log = references.latest_creation_log(db, character_id=character_id, post_id=post_id)
    if log is None:
        return {"topic_signature": "", "novelty_basis": ""}
    return _topic_metadata_from_result(log.result)


def _topic_metadata_for_post(
    db: Session,
    *,
    references: TopicHistoryReferences,
    post: models.Post,
    character_id: str | None = None,
) -> dict[str, str]:
    column_metadata = _topic_metadata_from_post_columns(post)
    if column_metadata["topic_signature"] or column_metadata["novelty_basis"]:
        return column_metadata
    return _latest_post_created_topic_metadata(
        db,
        references=references,
        character_id=character_id
        if character_id is not None
        else post.author_character_id,
        post_id=post.id,
    )


def post_topic_signature_for_prompt(
    db: Session, post: models.Post, *, references: TopicHistoryReferences
) -> str:
    metadata = _topic_metadata_for_post(db, references=references, post=post)
    return metadata["topic_signature"] or _fallback_topic_signature(
        title=post.title, body=post.body
    )
