"""Owner-bound default SNS space. Mutations are explicit; no membership backfill."""
from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.ids import uuid7_string
from app.domains.identity.service.owner_context import is_claimed_local_owner
from app.domains.identity.service.environment import snapshot
from app.domains.identity.service.local_owner import read_ui_language
from app.domains.worlds.policies.default_content import default_content
from app.domains.worlds.models import OwnerDefaultWorld, World, WorldMembership
from app.domains.worlds.service.definition import refresh_world_contract
from app.domains.worlds.service.foundation import ANGMOO_GLOBAL_WORLD_ID, _new_global_world
from app.domains.worlds.exceptions import WorldCreatorRoleRequiredError, WorldDefinitionValidationError


def _active_owner_membership(db, *, world_id, user_id):
    return db.scalar(select(WorldMembership).where(WorldMembership.world_id == world_id,
        WorldMembership.user_id == user_id, WorldMembership.status == "active", WorldMembership.role == "owner"))


def ensure_default_space(db: Session, *, owner_id: str) -> World:
    if not is_claimed_local_owner(db, owner_id):
        raise WorldCreatorRoleRequiredError("local_owner_required")
    binding = db.get(OwnerDefaultWorld, owner_id)
    if binding is not None:
        world = db.get(World, binding.world_id)
        member = _active_owner_membership(db, world_id=binding.world_id, user_id=owner_id)
        if world is None or world.owner_user_id != owner_id or world.status == "archived" or member is None or member.role != "owner":
            raise WorldDefinitionValidationError("default_space_recovery_required")
        return world
    try:
        legacy = db.get(World, ANGMOO_GLOBAL_WORLD_ID)
        member = _active_owner_membership(db, world_id=legacy.id, user_id=owner_id) if legacy else None
        adopt = bool(legacy and legacy.owner_user_id == owner_id and legacy.status == "published"
                     and legacy.readiness_status == "publish_ready" and member and member.role == "owner"
                     and legacy.setting_description.strip() and legacy.daily_life_description.strip())
        if adopt:
            world = legacy
        else:
            world = _new_global_world(owner_id)
            world.id = uuid7_string()
            world.slug = f"sns-{world.id}"
            world.name = "SNS"
            env = snapshot(db, owner_id)
            language = read_ui_language(db, owner_id) or ("ko" if env.memory_search_locale.split("-")[0] == "ko" else "en")
            for key, value in default_content(language).items():
                setattr(world, key, value)
            world.timezone = env.timezone
            world.language = language
            world.visibility = "private"
            world.join_policy = "private"
            world.create_idempotency_key = f"default-sns:{owner_id}"
            db.add(world)
            db.flush()
            refresh_world_contract(db, world)
            db.add(WorldMembership(id=uuid7_string(), world_id=world.id, user_id=owner_id,
                                   role="owner", status="active", joined_at=datetime.now(UTC)))
        db.add(OwnerDefaultWorld(owner_id=owner_id, world_id=world.id))
        db.commit()
        return world
    except IntegrityError:
        db.rollback()
        binding = db.get(OwnerDefaultWorld, owner_id)
        if binding is None:
            raise
        return ensure_default_space(db, owner_id=owner_id)


def is_default_space(db: Session, world_id: str) -> bool:
    return db.scalar(select(OwnerDefaultWorld.owner_id).where(OwnerDefaultWorld.world_id == world_id)) is not None
