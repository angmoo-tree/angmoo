"""Fenced, individually acknowledged effects; no automatic effect replay."""
from datetime import UTC, datetime

from sqlalchemy import select

from app.core.calendar import utc_instant
from app.core.sqlite_concurrency import sqlite_session_attempt
from app.core.database_transactions import database_write
from app.domains.worlds.models_deletion import WorldDeletionRequest, WorldDeletionCleanupItem as Item


class ErasureLeaseLost(RuntimeError):
    pass


def file_identity(path):
    try:
        info = path.stat()
    except FileNotFoundError:
        return None
    return [info.st_dev, info.st_ino, info.st_ctime_ns, info.st_mtime_ns, info.st_size]


def require_lease(db, request_id, epoch):
    row = db.get(WorldDeletionRequest, request_id, populate_existing=True)
    if (row is None or row.lease_epoch != epoch or row.state in {"failed", "completed"}
        or row.lease_until is None or utc_instant(row.lease_until) <= datetime.now(UTC)):
        raise ErasureLeaseLost("world_erasure_lease_lost")
    return row


def clean_step(sessions, ports, request_id, epoch):
    # Read-only preparation releases the canonical connection before slow graph,
    # index or checkpoint work. World admission is already permanently fenced.
    with sessions() as db:
        row = require_lease(db, request_id, epoch)
        item = db.scalar(select(Item).where(Item.request_id == request_id,
            Item.kind != "row", Item.state == "pending").order_by(Item.id).limit(1))
        if item is None:
            return True
        identifier, kind, ref, world_id = item.id, item.kind, dict(item.reference), row.world_id

    if kind == "file":
        # Shared references in OTHER Worlds are protected by this short final
        # SQLite serialization window, not by the deleted World's admission fence.
        with sessions() as db, sqlite_session_attempt(db):
            row = require_lease(db, request_id, epoch)
            item = db.get(Item, identifier)
            if item is None or item.state != "pending":
                return False
            relative = ref["path"]
            protected = ports._protected_files(db, row, {relative})
            path = ports._safe_path(relative)
            current = file_identity(path)
            if relative in protected or (current is not None and (
                "generation" not in ref or current != ref["generation"])):
                item.state = "retained"
            else:
                path.unlink(missing_ok=True)
                item.state = "done"
        return False

    if kind == "origin":
        def restore(db):
            from app.domains.world_characters.models import WorldCharacter
            from app.domains.characters.service.preserved_originals import restore_unregistered_original
            character_id = ref["character_id"]
            if db.scalar(select(WorldCharacter.id).where(WorldCharacter.character_id == character_id).limit(1)) is None:
                restore_unregistered_original(db, character_id)
        _ack(sessions, request_id, epoch, identifier, restore=restore)
        return False

    # Validate execution rights immediately before starting a new external
    # effect. Its IDs are immutable; each store fences the deleted World itself.
    with sessions() as db:
        require_lease(db, request_id, epoch)
    if kind == "memory_index":
        ports.index_cleanup((ref["item_id"],))
    elif kind == "checkpoint":
        if ports.checkpoint_cleanup is None:
            raise ValueError("world_erasure_checkpoint_unavailable")
        ports.checkpoint_cleanup(ref["activity_id"])
    elif kind == "graph":
        if ports.graph_cleanup(world_id) is False:
            return False
    else:
        raise ValueError("world_erasure_journal_kind_invalid")
    _ack(sessions, request_id, epoch, identifier)
    return False


def _ack(sessions, request_id, epoch, identifier, *, restore=None):
    with sessions() as db:
        def apply():
            require_lease(db, request_id, epoch)
            item = db.get(Item, identifier, populate_existing=True)
            if item is None or item.state != "pending":
                return
            if restore is not None:
                restore(db)
            item.state = "done"
        database_write(db, apply, require_clean=True)
