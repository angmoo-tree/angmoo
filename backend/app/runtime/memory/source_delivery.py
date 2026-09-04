"""Transactional delivery markers for committed SNS/Chat; never calls a model."""

from datetime import UTC, datetime
import logging
from uuid import uuid4

from sqlalchemy import event, insert, inspect, select, update

from app.core.db import Base
from app.domains.memory.infrastructure.batch_models import (
    MemoryActivationEpoch,
    MemorySourceDelivery,
)
from app.domains.memory.infrastructure.sqlalchemy_models import MemoryScopeSettingModel


logger = logging.getLogger(__name__)
_PENDING = "angmoo_memory_batch_sources"


def sync_epoch(connection, setting_id: str, *, now: datetime) -> None:
    settings, epochs = (
        MemoryScopeSettingModel.__table__,
        MemoryActivationEpoch.__table__,
    )
    setting = (
        connection.execute(select(settings).where(settings.c.id == setting_id))
        .mappings()
        .one_or_none()
    )
    if setting is None:
        return
    connection.execute(
        update(epochs)
        .where(
            epochs.c.scope_setting_id == setting_id,
            epochs.c.closed_at.is_(None),
            epochs.c.scope_version != setting["version"],
        )
        .values(closed_at=now)
    )
    if (
        setting["enabled"]
        and connection.execute(
            select(epochs.c.id).where(
                epochs.c.scope_setting_id == setting_id,
                epochs.c.scope_version == setting["version"],
            )
        ).first()
        is None
    ):
        connection.execute(
            insert(epochs).values(
                id=str(uuid4()),
                scope_setting_id=setting_id,
                scope_version=setting["version"],
                opened_at=now,
            )
        )


def capture_delivery(connection, *, world_id, subjects, source_type, source_id, now):
    if not world_id or not source_id or not subjects:
        return
    settings, epochs, deliveries = (
        MemoryScopeSettingModel.__table__,
        MemoryActivationEpoch.__table__,
        MemorySourceDelivery.__table__,
    )
    scopes = (
        connection.execute(
            select(settings).where(
                settings.c.world_id == world_id,
                settings.c.subject_world_character_id.in_(subjects),
                settings.c.enabled.is_(True),
            )
        )
        .mappings()
        .all()
    )
    for scope in scopes:
        if connection.execute(
            select(deliveries.c.sequence).where(
                deliveries.c.scope_setting_id == scope["id"],
                deliveries.c.source_type == source_type,
                deliveries.c.source_id == str(source_id),
            )
        ).first():
            continue
        sync_epoch(connection, scope["id"], now=now)
        epoch = connection.execute(
            select(epochs.c.id).where(
                epochs.c.scope_setting_id == scope["id"],
                epochs.c.closed_at.is_(None),
                epochs.c.scope_version == scope["version"],
            )
        ).scalar_one()
        connection.execute(
            insert(deliveries).values(
                scope_setting_id=scope["id"],
                epoch_id=epoch,
                source_type=source_type,
                source_id=str(source_id),
                state="pending",
                captured_at=now,
            )
        )


def _capture_object(connection, obj, now):
    name = getattr(obj, "__tablename__", "")
    if name == "memory_scope_settings":
        sync_epoch(connection, obj.id, now=now)
        return
    world, subjects, kind, source_id = None, set(), None, getattr(obj, "id", None)
    if name == "posts":
        world, subjects = obj.world_id, {obj.author_world_character_id}
        kind = "REPLY" if obj.reply_to_post_id else "POST"
    elif name == "post_likes":
        world, subjects, kind = obj.world_id, {obj.actor_world_character_id}, "REACTION"
    elif name == "social_events":
        if (
            obj.result != "succeeded"
            or obj.retrieval_status != "eligible"
            or obj.invalidated_at is not None
        ):
            return
        # Post/reply/like rows are the single content source for those actions.
        if obj.event_type in {
            "post_published",
            "reply_created",
            "comment_created",
            "like_added",
        }:
            return
        world, subjects, kind = (
            obj.world_id,
            {obj.actor_world_character_id, obj.target_world_character_id},
            "SOCIAL_EVENT",
        )
    elif name == "message_messages":
        if obj.role != "assistant" or obj.status != "ok":
            return
        threads = Base.metadata.tables["message_threads"]
        thread = (
            connection.execute(select(threads).where(threads.c.id == obj.thread_id))
            .mappings()
            .one_or_none()
        )
        if (
            thread is None
            or thread["world_scope_status"] != "resolved"
            or thread["deleted_at"] is not None
        ):
            return
        world, subjects, kind = (
            thread["world_id"],
            {thread["responding_world_character_id"]},
            "CHAT_MESSAGE",
        )
    elif name == "world_character_feed_observations":
        if obj.status != "observed" or obj.observed_at is None:
            return
        posts = Base.metadata.tables["posts"]
        post = (
            connection.execute(select(posts).where(posts.c.id == obj.post_id))
            .mappings()
            .one_or_none()
        )
        if post is None:
            return
        world, subjects, kind, source_id = (
            post["world_id"],
            {obj.observer_world_character_id},
            "REPLY" if post["reply_to_post_id"] else "POST",
            obj.post_id,
        )
    if kind:
        capture_delivery(
            connection,
            world_id=world,
            subjects=subjects - {None},
            source_type=kind,
            source_id=source_id,
            now=now,
        )


def install_memory_delivery(session_factory) -> None:
    """Register on this runtime's factory only, not all SQLAlchemy sessions."""
    if event.contains(session_factory, "before_flush", _before_flush):
        return
    event.listen(session_factory, "before_flush", _before_flush)
    event.listen(session_factory, "after_flush_postexec", _after_flush)
    event.listen(session_factory, "after_rollback", _rollback)


def uninstall_memory_delivery(session_factory) -> None:
    for name, callback in (
        ("before_flush", _before_flush),
        ("after_flush_postexec", _after_flush),
        ("after_rollback", _rollback),
    ):
        if event.contains(session_factory, name, callback):
            event.remove(session_factory, name, callback)


def _before_flush(session, _context, _instances):
    pending = session.info.setdefault(_PENDING, [])
    source_names = {
        "posts",
        "post_likes",
        "social_events",
        "message_messages",
        "world_character_feed_observations",
        "memory_scope_settings",
    }
    for obj in list(session.new) + list(session.dirty):
        if getattr(obj, "__tablename__", "") in source_names:
            if (
                obj in session.new
                and hasattr(obj, "created_at")
                and obj.created_at is None
            ):
                # SQLite CURRENT_TIMESTAMP is second-granular. Preserve the
                # actual admission time so a lost marker just after ON is not
                # mistaken for a pre-ON source. Existing rows are untouched.
                obj.created_at = datetime.now(UTC)
            # Editing a post must not create a new admission after an OFF gap.
            if (
                getattr(obj, "__tablename__", "")
                in {"posts", "post_likes", "social_events"}
                and obj not in session.new
            ):
                if (
                    getattr(obj, "__tablename__", "") != "post_likes"
                    or None not in inspect(obj).attrs.world_id.history.deleted
                ):
                    continue
            pending.append(obj)


def _after_flush(session, _context):
    objects = session.info.pop(_PENDING, [])
    if not objects:
        return
    connection = session.connection()
    try:
        # A memory-only failure cannot roll back the successful social write.
        # Recovery scans the canonical ON-epoch interval later.
        with connection.begin_nested():
            now = datetime.now(UTC)
            for obj in objects:
                _capture_object(connection, obj, now)
    except Exception:
        logger.warning("memory_source_delivery_deferred")


def _rollback(session):
    session.info.pop(_PENDING, None)
