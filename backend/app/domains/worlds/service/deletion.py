"""Owner-only atomic admission; receipts outlive the World and its membership."""
import hashlib
import json
from datetime import UTC, datetime
from sqlalchemy import select, update
from sqlalchemy.exc import IntegrityError
from app.core.ids import uuid7_string
from app.domains.worlds.models import World, WorldMembership, OwnerDefaultWorld
from app.domains.worlds.models_deletion import WorldDeletionRequest
from app.domains.worlds.contracts_deletion import WorldDeletionCommand, WorldDeletionError, WorldDeletionPreview, WorldDeletionReceipt


def receipt(row):
    return WorldDeletionReceipt(request_id=row.id, world_id=row.world_id, state=row.state,
        accepted_at=row.accepted_at, completed_at=row.completed_at, can_retry=row.state == "failed")


def deletion_for_world(db, world_id):
    return db.scalar(select(WorldDeletionRequest).where(WorldDeletionRequest.world_id == world_id))


def is_deleting(db, world_id):
    return deletion_for_world(db, world_id) is not None


def idempotency_digest(key: str) -> str:
    """Do not retain arbitrary confirmation/request text as an operational key."""
    return hashlib.sha256(key.encode()).hexdigest()


def _require_default_binding(db, world):
    from app.domains.worlds.service.foundation import ANGMOO_GLOBAL_WORLD_ID
    binding = db.scalar(select(OwnerDefaultWorld).where(OwnerDefaultWorld.world_id == world.id))
    if binding is None and (world.id == ANGMOO_GLOBAL_WORLD_ID or
        world.create_idempotency_key == f"default-sns:{world.owner_user_id}"):
        raise WorldDeletionError("default_space_recovery_required", 409)
    return binding


def require_live_world(db, world_id):
    if is_deleting(db, world_id):
        raise WorldDeletionError("world_deleting", 409)


def _owned(db, world_id, owner_id):
    from app.domains.identity.service.owner_context import is_claimed_local_owner
    if not is_claimed_local_owner(db, owner_id):
        raise WorldDeletionError("world_not_found", 404)
    world = db.get(World, world_id)
    if world is None:
        raise WorldDeletionError("world_not_found", 404)
    member = db.scalar(select(WorldMembership).where(WorldMembership.world_id == world_id,
        WorldMembership.user_id == owner_id, WorldMembership.status == "active"))
    if world.owner_user_id != owner_id or member is None or member.role != "owner":
        raise WorldDeletionError("world_not_found" if world.visibility == "private" else "owner_role_required", 404 if world.visibility == "private" else 403)
    return world


def preview(db, world_id, owner_id):
    world = _owned(db, world_id, owner_id)
    protected = _require_default_binding(db, world) is not None
    return WorldDeletionPreview(world_id=world.id, stored_name=world.name, row_version=world.row_version,
        can_delete=not protected and not is_deleting(db, world_id), is_default_space=protected,
        export_available=world.status == "published" and world.readiness_status == "publish_ready")


def accept(db, world_id: str, owner_id: str, command: WorldDeletionCommand, *, stop_admission):
    digest = hashlib.sha256(json.dumps({"world_id": world_id, **command.model_dump(exclude={"idempotency_key"})},
        ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode()).hexdigest()
    existing = db.scalar(select(WorldDeletionRequest).where(WorldDeletionRequest.owner_id == owner_id,
        WorldDeletionRequest.idempotency_key == idempotency_digest(command.idempotency_key)))
    if existing is not None:
        if existing.confirmation_digest != digest or existing.world_id != world_id:
            raise WorldDeletionError("deletion_idempotency_conflict", 409)
        return receipt(existing)
    world = _owned(db, world_id, owner_id)
    if _require_default_binding(db, world) is not None:
        raise WorldDeletionError("default_space_cannot_be_deleted", 409)
    if is_deleting(db, world_id):
        raise WorldDeletionError("world_deleting", 409)
    if world.name != command.confirmed_name:
        raise WorldDeletionError("confirmation_name_mismatch", 422)
    changed = db.execute(update(World).where(World.id == world_id, World.row_version == command.expected_row_version)
        .values(row_version=World.row_version + 1)).rowcount
    if not changed:
        db.rollback()
        raise WorldDeletionError("row_version_conflict", 409)
    stop_admission(db, world_id)  # Same UoW, before the durable fence becomes visible.
    row = WorldDeletionRequest(id=uuid7_string(), world_id=world_id, owner_id=owner_id,
        idempotency_key=idempotency_digest(command.idempotency_key), confirmation_digest=digest, state="accepted", stage="draining")
    db.add(row)
    try:
        db.commit()
    except IntegrityError as exc:
        db.rollback()
        raise WorldDeletionError("world_deleting", 409) from exc
    db.refresh(row)
    return receipt(row)


def owned_receipt(db, request_id, owner_id):
    row = db.get(WorldDeletionRequest, request_id)
    if row is None or row.owner_id != owner_id:
        raise WorldDeletionError("deletion_not_found", 404)
    return row


def unfinished(db, owner_id):
    return [receipt(row) for row in db.scalars(select(WorldDeletionRequest).where(
        WorldDeletionRequest.owner_id == owner_id, WorldDeletionRequest.state != "completed")
        .order_by(WorldDeletionRequest.accepted_at).limit(100))]


def retry(db, request_id, owner_id):
    row = owned_receipt(db, request_id, owner_id)
    if row.state != "failed":
        raise WorldDeletionError("deletion_not_retryable", 409)
    db.execute(update(WorldDeletionRequest).where(WorldDeletionRequest.id == row.id,
        WorldDeletionRequest.state == "failed").values(state="accepted", failures=0, failure_code=None,
        next_attempt_at=None, lease_until=None, lease_epoch=WorldDeletionRequest.lease_epoch + 1))
    db.commit()
    db.refresh(row)
    return receipt(row)
