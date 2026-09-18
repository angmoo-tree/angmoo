"""Deterministic topic identity, source replacement and full-catalog matching.

No provider calls and no commits: the source command owns the transaction.
"""
from __future__ import annotations

from collections import OrderedDict
from datetime import UTC, datetime
import hashlib
import re
import unicodedata
from uuid import uuid4

from sqlalchemy import delete, select, update, or_
from sqlalchemy.orm import Session

from app.domains.social.models.posts import Post
from app.domains.social.models.topics import (
    RecommendationCatalog, RecommendationPost, RecommendationPostTopic,
    RecommendationTopic, RecommendationTopicSource,
    RecommendationPreparation,
)

MAX_POST_TOPICS = 6
MAX_CHARACTER_TOPICS = 24
_subject_reader = None


def configure_subject_reader(reader):
    """Composition installs a stateless reader; every call uses the caller's Session."""
    global _subject_reader
    _subject_reader = reader


def valid_interest_subjects(db: Session, world_id: str) -> tuple[str, ...]:
    if _subject_reader is None:
        return ()  # Unbound tools cannot grant access to character interest sources.
    return tuple(_subject_reader(db, world_id))


def normalize_topic(value: str) -> str:
    return re.sub(r"\s+", "", unicodedata.normalize("NFKC", value).casefold())


def body_digest(title: str, body: str) -> str:
    return hashlib.sha256((title + "\0" + body).encode("utf-8")).hexdigest()


def valid_final_signature(value: object) -> str | None:
    # Metadata is optional. Do not stringify objects or retry a valid body.
    if not isinstance(value, str) or not value.strip() or len(value) > 300:
        return None
    return value.strip()


def ensure_catalog(db: Session, world_id: str) -> RecommendationCatalog:
    catalog = db.get(RecommendationCatalog, world_id)
    if catalog is None:
        catalog = RecommendationCatalog(world_id=world_id, version=1)
        db.add(catalog)
        db.flush()
    return catalog


def mark_new_subject(db: Session, *, world_id: str, world_character_id: str | None = None):
    """Creation commands only. No read/startup/import caller may enroll a subject."""
    ensure_catalog(db, world_id)
    key = world_character_id or "world"
    existing = db.scalar(select(RecommendationPreparation.id).where(
        RecommendationPreparation.world_id == world_id, RecommendationPreparation.source_key == key,
    ))
    if existing is None:
        db.add(RecommendationPreparation(id=str(uuid4()), world_id=world_id,
            source_key=key, world_character_id=world_character_id, state="pending", request_id="initial"))
        db.flush()


def replace_source_topics(
    db: Session, *, world_id: str, world_character_id: str | None,
    topics: list[tuple[str, str]],
) -> list[str]:
    """Only authenticated World/profile preparation commands may call this.

    Each tuple is (name, common|world). Validate the entire result before writes.
    Historical topic IDs and post links are never deleted.
    """
    cleaned: dict[tuple[str, str], str] = {}
    limit = MAX_CHARACTER_TOPICS if world_character_id else 64
    if len(topics) > limit:
        raise ValueError("topic_preparation_limit")
    for name, scope in topics:
        if not isinstance(name, str) or not 2 <= len(name.strip()) <= 120 or scope not in {"common", "world"}:
            raise ValueError("invalid_topic_definition")
        normalized = normalize_topic(name)
        if len(normalized) < 2:
            raise ValueError("topic_name_too_short")
        cleaned[(scope, normalized)] = name.strip()
    catalog = ensure_catalog(db, world_id)
    source_key = world_character_id or "world"
    ids: list[str] = []
    for (scope, normalized), name in sorted(cleaned.items()):
        scope_key = "common" if scope == "common" else world_id
        topic = db.scalar(select(RecommendationTopic).where(
            RecommendationTopic.scope_key == scope_key,
            RecommendationTopic.normalized_name == normalized,
        ))
        if topic is None:
            topic = RecommendationTopic(id=str(uuid4()), scope_key=scope_key,
                                        world_id=None if scope == "common" else world_id,
                                        name=name, normalized_name=normalized)
            db.add(topic)
            db.flush()
        ids.append(topic.id)
    existing = set(db.scalars(select(RecommendationTopicSource.topic_id).where(
        RecommendationTopicSource.world_id == world_id,
        RecommendationTopicSource.source_key == source_key,
    )))
    if existing != set(ids):
        db.execute(delete(RecommendationTopicSource).where(
            RecommendationTopicSource.world_id == world_id,
            RecommendationTopicSource.source_key == source_key,
        ))
        db.add_all([RecommendationTopicSource(id=str(uuid4()), world_id=world_id,
                    source_key=source_key, world_character_id=world_character_id,
                    topic_id=topic_id) for topic_id in ids])
        db.execute(update(RecommendationCatalog).where(
            RecommendationCatalog.world_id == world_id,
        ).values(version=RecommendationCatalog.version + 1))
        db.flush()
    return ids


def available_topics(db: Session, world_id: str) -> list[RecommendationTopic]:
    return list(db.scalars(select(RecommendationTopic).join(
        RecommendationTopicSource, RecommendationTopicSource.topic_id == RecommendationTopic.id,
    ).where(RecommendationTopicSource.world_id == world_id,
            or_(RecommendationTopicSource.world_character_id.is_(None),
                RecommendationTopicSource.world_character_id.in_(valid_interest_subjects(db, world_id))),
    ).distinct().order_by(RecommendationTopic.id)))


class TopicMatcher:
    """One trie for a World/version, covering every name before the result cap."""
    def __init__(self, topics: list[tuple[str, str]]):
        self.root: dict = {}
        for identity, name in topics:
            normalized = normalize_topic(name)
            if len(normalized) < 2:
                continue
            node = self.root
            for char in normalized:
                node = node.setdefault(char, {})
            node.setdefault(None, []).append((identity, len(normalized)))

    def match(self, fields: list[str], limit: int = MAX_POST_TOPICS) -> list[str]:
        matches: dict[str, tuple[int, int, str]] = {}
        for field_index, raw in enumerate(fields):
            field = normalize_topic(raw)
            for start in range(len(field)):
                node = self.root
                for position in range(start, len(field)):
                    char = field[position]
                    node = node.get(char)
                    if node is None:
                        break
                    for identity, length in node.get(None, ()):
                        # Prefer more specific names, then earlier source field; stable ID tie.
                        rank = (-length, field_index, identity)
                        if identity not in matches or rank < matches[identity]:
                            matches[identity] = rank
        return sorted(matches, key=matches.__getitem__)[:limit]


def enroll_native_post(db: Session, post: Post) -> None:
    """Called only by native creation, never by edits/imports/schema migration."""
    if not post.world_id or db.get(RecommendationPost, post.id) is not None:
        return
    ensure_catalog(db, post.world_id)
    db.add(RecommendationPost(post_id=post.id, world_id=post.world_id,
                             created_at=post.created_at or datetime.now(UTC)))
    db.flush()
    match_post(db, post)


def match_post(db: Session, post: Post, *, final_signature: object = None) -> list[str]:
    receipt = db.get(RecommendationPost, post.id)
    if receipt is None:
        return []  # An edit cannot enroll historical/imported content.
    catalog = ensure_catalog(db, receipt.world_id)
    signature = valid_final_signature(final_signature)
    receipt.final_signature = signature
    receipt.signature_body_digest = body_digest(post.title, post.body) if signature else None
    fields = [post.title, post.body]
    if signature:
        fields.append(signature)
    # Per-transaction cache avoids publishing uncommitted catalog changes globally.
    cache = db.info.setdefault("recommendation_matchers", OrderedDict())
    valid_subjects = valid_interest_subjects(db, receipt.world_id)
    key = (db.get_transaction(), receipt.world_id, catalog.version, valid_subjects)
    matcher = cache.get(key)
    if matcher is None:
        matcher = TopicMatcher([(t.id, t.name) for t in available_topics(db, receipt.world_id)])
        cache[key] = matcher
        while len(cache) > 8:
            cache.popitem(last=False)
    ids = matcher.match(fields)
    db.execute(delete(RecommendationPostTopic).where(RecommendationPostTopic.post_id == post.id))
    db.add_all([RecommendationPostTopic(post_id=post.id, topic_id=identity,
                world_id=receipt.world_id, created_at=receipt.created_at) for identity in ids])
    receipt.matched_catalog_version = catalog.version
    db.flush()
    return ids
