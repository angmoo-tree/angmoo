from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
import re
import unicodedata
from typing import Any, Callable, Protocol, TypeVar

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.ids import uuid7_string
from app.domains.worlds.api import schemas
from app.domains.worlds.infrastructure import definition_repository as world_definitions
from app.domains.worlds.infrastructure import generation_context as world_generation_context
from app.domains.worlds.infrastructure import sqlalchemy_models as models
from app.domains.worlds.infrastructure import world_banner_storage


CREATOR_ROLES = frozenset({"owner", "editor"})
_SLUG_SEPARATORS = re.compile(r"[^a-z0-9]+")
_T = TypeVar("_T")


class UserIdentity(Protocol):
    id: str


@dataclass(frozen=True, slots=True)
class WorldSeedOutcome:
    world: models.World
    membership: models.WorldMembership
    replayed: bool


class WorldServiceError(Exception):
    reason_code = "world_error"


class WorldNotFoundError(WorldServiceError):
    reason_code = "world_not_found"


class WorldArchivedError(WorldServiceError):
    reason_code = "world_archived"


class WorldMembershipRequiredError(WorldServiceError):
    reason_code = "membership_required"


class WorldCreatorRoleRequiredError(WorldServiceError):
    reason_code = "creator_role_required"


class WorldOwnerRoleRequiredError(WorldServiceError):
    reason_code = "creator_role_required"


class WorldRowVersionConflictError(WorldServiceError):
    reason_code = "row_version_conflict"


class WorldDefinitionIncompleteError(WorldServiceError):
    reason_code = "world_definition_incomplete"

    def __init__(self, readiness: schemas.WorldReadinessRead) -> None:
        self.readiness = readiness
        super().__init__(self.reason_code)


class WorldDefinitionValidationError(WorldServiceError):
    reason_code = "world_definition_incomplete"


class WorldBannerValidationError(WorldServiceError):
    reason_code = "unsafe_banner_reference"


def get_world(
    db: Session,
    world_id: str,
    *,
    lock_for_update: bool = False,
) -> models.World:
    statement = select(models.World).where(models.World.id == world_id)
    if lock_for_update:
        statement = statement.with_for_update()
    world = db.scalar(statement)
    if world is None:
        raise WorldNotFoundError(world_id)
    return world


def get_active_membership(
    db: Session,
    *,
    world_id: str,
    user_id: str,
) -> models.WorldMembership | None:
    return db.scalar(
        select(models.WorldMembership).where(
            models.WorldMembership.world_id == world_id,
            models.WorldMembership.user_id == user_id,
            models.WorldMembership.status == "active",
        )
    )


def is_enabled_world_role(
    db: Session,
    *,
    world_id: str,
    role_key: str,
) -> bool:
    return bool(
        db.scalar(
            select(models.WorldRole.id).where(
                models.WorldRole.world_id == world_id,
                models.WorldRole.role_key == role_key,
                models.WorldRole.status == "enabled",
            )
        )
    )


def require_world_read_access(
    db: Session,
    *,
    world_id: str,
    user: UserIdentity | None,
) -> models.World:
    world = get_world(db, world_id)
    membership = (
        get_active_membership(db, world_id=world.id, user_id=user.id)
        if user is not None
        else None
    )
    publicly_visible = world.status == "published" and world.visibility in {
        "public",
        "unlisted",
    }
    if not publicly_visible and membership is None:
        raise WorldNotFoundError(world_id)
    return world


def require_creator_access(
    db: Session,
    *,
    world_id: str,
    user: UserIdentity,
    lock_for_update: bool = False,
) -> tuple[models.World, models.WorldMembership]:
    world = get_world(db, world_id, lock_for_update=lock_for_update)
    if world.status == "archived":
        raise WorldArchivedError(world_id)
    membership = get_active_membership(db, world_id=world.id, user_id=user.id)
    if membership is None:
        if world.visibility == "private" or world.status != "published":
            raise WorldNotFoundError(world_id)
        raise WorldMembershipRequiredError(world_id)
    if membership.role not in CREATOR_ROLES:
        raise WorldCreatorRoleRequiredError(world_id)
    return world, membership


def require_owner_access(
    db: Session,
    *,
    world_id: str,
    user: UserIdentity,
    lock_for_update: bool = False,
) -> tuple[models.World, models.WorldMembership]:
    world, membership = require_creator_access(
        db,
        world_id=world_id,
        user=user,
        lock_for_update=lock_for_update,
    )
    if membership.role != "owner":
        raise WorldOwnerRoleRequiredError(world_id)
    return world, membership


def _slug_base(name: str) -> str:
    normalized = unicodedata.normalize("NFKD", name).encode("ascii", "ignore").decode()
    return _SLUG_SEPARATORS.sub("-", normalized.lower()).strip("-")[:72]


def _available_slug(db: Session, *, name: str, world_id: str) -> str:
    base = _slug_base(name) or f"world-{world_id.split('-', 1)[0]}"
    candidate = base
    suffix = 1
    while db.scalar(select(models.World.id).where(models.World.slug == candidate)):
        suffix += 1
        candidate = f"{base[: max(1, 88 - len(str(suffix)))]}-{suffix}"
    return candidate


def _assert_unique(items: list[Any], key: Callable[[Any], Any], label: str) -> None:
    values = [key(item) for item in items]
    if len(values) != len(set(values)):
        raise WorldDefinitionValidationError(f"duplicate_{label}")


def _sync_rows(
    db: Session,
    *,
    world_id: str,
    model,
    inputs: list[_T],
    identity: Callable[[_T], Any],
    row_identity: Callable[[Any], Any],
    create_values: Callable[[_T], dict[str, Any]],
    update_values: Callable[[_T], dict[str, Any]],
) -> None:
    _assert_unique(inputs, identity, model.__tablename__)
    existing = list(db.scalars(select(model).where(model.world_id == world_id)))
    by_key = {row_identity(row): row for row in existing}
    active_keys: set[Any] = set()
    for item in inputs:
        item_key = identity(item)
        active_keys.add(item_key)
        row = by_key.get(item_key)
        values = update_values(item)
        if row is None:
            row = model(
                id=uuid7_string(),
                world_id=world_id,
                version=1,
                status="enabled",
                **create_values(item),
            )
            db.add(row)
            continue
        semantic_changed = any(
            not _semantic_value_equal(getattr(row, field), value)
            for field, value in values.items()
        )
        for field, value in values.items():
            setattr(row, field, value)
        if semantic_changed or row.status != "enabled":
            row.version += 1
        row.status = "enabled"
    for row in existing:
        if row_identity(row) not in active_keys and row.status != "archived":
            row.status = "archived"
            row.version += 1


def _semantic_value_equal(current: Any, candidate: Any) -> bool:
    if isinstance(current, list) and isinstance(candidate, list):
        return sorted(set(current)) == sorted(set(candidate))
    return current == candidate


def _sync_optional_definition(
    db: Session,
    *,
    world: models.World,
    data: schemas.WorldUpdate,
) -> None:
    fields = data.model_fields_set
    if "places" in fields:
        places = data.places or []
        _sync_rows(
            db,
            world_id=world.id,
            model=models.WorldPlace,
            inputs=places,
            identity=lambda item: item.key,
            row_identity=lambda row: row.place_key,
            create_values=lambda item: {
                "place_key": item.key,
                "name": item.name,
                "description": item.description,
                "available_dayparts": item.available_dayparts,
                "access_role_keys": item.access_role_keys,
            },
            update_values=lambda item: {
                "name": item.name,
                "description": item.description,
                "available_dayparts": item.available_dayparts,
                "access_role_keys": item.access_role_keys,
            },
        )
    if "roles" in fields:
        roles = data.roles or []
        _sync_rows(
            db,
            world_id=world.id,
            model=models.WorldRole,
            inputs=roles,
            identity=lambda item: item.key,
            row_identity=lambda row: row.role_key,
            create_values=lambda item: {
                "role_key": item.key,
                "name": item.name,
                "description": item.description,
                "responsibilities": item.responsibilities,
                "allowed_activity_scope": item.allowed_activity_scope,
                "autonomous_allowed": item.autonomous_allowed,
            },
            update_values=lambda item: {
                "name": item.name,
                "description": item.description,
                "responsibilities": item.responsibilities,
                "allowed_activity_scope": item.allowed_activity_scope,
                "autonomous_allowed": item.autonomous_allowed,
            },
        )
    if "daypart_profiles" in fields:
        profiles = data.daypart_profiles or []
        _sync_rows(
            db,
            world_id=world.id,
            model=models.WorldDaypartProfile,
            inputs=profiles,
            identity=lambda item: item.daypart,
            row_identity=lambda row: row.daypart,
            create_values=lambda item: {
                "daypart": item.daypart,
                "description": item.description,
                "available_features": item.available_features,
                "restricted_features": item.restricted_features,
            },
            update_values=lambda item: {
                "description": item.description,
                "available_features": item.available_features,
                "restricted_features": item.restricted_features,
            },
        )
    if "rules" in fields:
        rules = data.rules or []
        _sync_rows(
            db,
            world_id=world.id,
            model=models.WorldRule,
            inputs=rules,
            identity=lambda item: (item.key, item.rule_kind),
            row_identity=lambda row: (row.rule_key, row.rule_kind),
            create_values=lambda item: {
                "rule_key": item.key,
                "rule_kind": item.rule_kind,
                "description": item.description,
            },
            update_values=lambda item: {"description": item.description},
        )
    if "glossary" in fields:
        glossary = data.glossary or []
        _sync_rows(
            db,
            world_id=world.id,
            model=models.WorldGlossaryTerm,
            inputs=glossary,
            identity=lambda item: item.key,
            row_identity=lambda row: row.term_key,
            create_values=lambda item: {
                "term_key": item.key,
                "term": item.term,
                "meaning": item.meaning,
            },
            update_values=lambda item: {"term": item.term, "meaning": item.meaning},
        )
    db.flush()

    active_role_keys = set(
        db.scalars(
            select(models.WorldRole.role_key).where(
                models.WorldRole.world_id == world.id,
                models.WorldRole.status == "enabled",
            )
        )
    )
    for place in db.scalars(
        select(models.WorldPlace).where(
            models.WorldPlace.world_id == world.id,
            models.WorldPlace.status == "enabled",
        )
    ):
        if not set(place.access_role_keys).issubset(active_role_keys):
            raise WorldDefinitionValidationError("unknown_place_access_role")


def _creator_context(
    db: Session,
    *,
    world: models.World,
    membership: models.WorldMembership,
) -> schemas.WorldCreatorContextRead:
    return schemas.WorldCreatorContextRead(
        world=world_definitions.world_read(db, world),
        membership_role=membership.role,
        readiness=world_definitions.evaluate_world_readiness(db, world),
    )


def seed_world(
    db: Session,
    *,
    user: UserIdentity,
    data: schemas.WorldDraftCreate,
    status: str = "draft",
    membership_reason: str = "world_created",
) -> WorldSeedOutcome:
    """Flush a World aggregate without owning commit or rollback."""

    existing = db.scalar(
        select(models.World).where(
            models.World.owner_user_id == user.id,
            models.World.create_idempotency_key == data.idempotency_key,
        )
    )
    if existing is not None:
        membership = get_active_membership(db, world_id=existing.id, user_id=user.id)
        if membership is None or membership.role != "owner":
            raise WorldMembershipRequiredError(existing.id)
        return WorldSeedOutcome(existing, membership, True)

    world_id = uuid7_string()
    world = models.World(
        id=world_id,
        slug=_available_slug(db, name=data.name, world_id=world_id),
        owner_user_id=user.id,
        name=data.name,
        tagline=data.tagline,
        setting_description=data.setting_description,
        daily_life_description=data.daily_life_description,
        genre_tags=data.genre_tags,
        tone_tags=data.tone_tags,
        banner_media_id=None,
        banner_alt_text="",
        timezone=data.timezone,
        language=data.language,
        visibility=data.visibility,
        join_policy=data.join_policy,
        status=status,
        definition_version=1,
        row_version=1,
        contract_version=world_definitions.WORLD_CONTRACT_VERSION,
        contract_hash="0" * 64,
        readiness_status="not_ready",
        additional_generation_guidance=data.additional_generation_guidance,
        create_idempotency_key=data.idempotency_key,
    )
    membership = models.WorldMembership(
        id=uuid7_string(),
        world_id=world.id,
        user_id=user.id,
        role="owner",
        status="active",
        requested_by_user_id=user.id,
        approved_by_user_id=user.id,
        joined_at=datetime.now(timezone.utc),
        reason=membership_reason,
    )
    db.add_all([world, membership])
    db.flush()
    _sync_optional_definition(
        db,
        world=world,
        data=schemas.WorldUpdate(
            row_version=1,
            places=data.places,
            roles=data.roles,
            daypart_profiles=data.daypart_profiles,
            rules=data.rules,
            glossary=data.glossary,
        ),
    )
    db.flush()
    world_definitions.refresh_world_contract(db, world)
    db.flush()
    return WorldSeedOutcome(world, membership, False)


def create_world(
    db: Session,
    *,
    user: UserIdentity,
    data: schemas.WorldDraftCreate,
) -> schemas.WorldCreatorContextRead:
    try:
        outcome = seed_world(db, user=user, data=data)
        if outcome.replayed:
            return _creator_context(
                db, world=outcome.world, membership=outcome.membership
            )
        db.commit()
    except IntegrityError as exc:
        db.rollback()
        replay = db.scalar(
            select(models.World).where(
                models.World.owner_user_id == user.id,
                models.World.create_idempotency_key == data.idempotency_key,
            )
        )
        if replay is not None:
            replay_membership = get_active_membership(
                db, world_id=replay.id, user_id=user.id
            )
            if replay_membership is not None:
                return _creator_context(
                    db, world=replay, membership=replay_membership
                )
        raise exc
    db.refresh(outcome.world)
    return _creator_context(
        db, world=outcome.world, membership=outcome.membership
    )


def get_creator_context(
    db: Session,
    *,
    world_id: str,
    user: UserIdentity,
) -> schemas.WorldCreatorContextRead:
    world, membership = require_creator_access(db, world_id=world_id, user=user)
    return _creator_context(db, world=world, membership=membership)


def get_world_read(
    db: Session,
    *,
    world_id: str,
    user: UserIdentity | None,
) -> schemas.WorldRead:
    world = require_world_read_access(db, world_id=world_id, user=user)
    return world_definitions.world_read(db, world)


def update_world(
    db: Session,
    *,
    world_id: str,
    user: UserIdentity,
    data: schemas.WorldUpdate,
) -> schemas.WorldCreatorContextRead:
    world, membership = require_creator_access(
        db,
        world_id=world_id,
        user=user,
        lock_for_update=True,
    )
    if world.row_version != data.row_version:
        raise WorldRowVersionConflictError(world_id)

    scalar_fields = {
        "name",
        "tagline",
        "setting_description",
        "daily_life_description",
        "genre_tags",
        "tone_tags",
        "timezone",
        "language",
        "visibility",
        "join_policy",
        "additional_generation_guidance",
    }
    for field in data.model_fields_set & scalar_fields:
        setattr(world, field, getattr(data, field))
    _sync_optional_definition(db, world=world, data=data)
    old_hash = world.contract_hash
    new_hash = world_definitions.world_contract_hash(db, world)
    if new_hash != old_hash:
        world.definition_version += 1
        world.contract_hash = new_hash
    world.row_version += 1
    readiness = world_definitions.evaluate_world_readiness(db, world)
    world.readiness_status = (
        "publish_ready" if readiness.ready_for_publish else "not_ready"
    )
    db.commit()
    db.refresh(world)
    return _creator_context(db, world=world, membership=membership)


def validate_world_definition(
    db: Session,
    *,
    world_id: str,
    user: UserIdentity,
) -> schemas.WorldReadinessRead:
    world, _ = require_creator_access(db, world_id=world_id, user=user)
    return world_definitions.evaluate_world_readiness(db, world)


def publish_world(
    db: Session,
    *,
    world_id: str,
    user: UserIdentity,
    data: schemas.WorldMutationRequest,
) -> schemas.WorldCreatorContextRead:
    world, membership = require_creator_access(
        db,
        world_id=world_id,
        user=user,
        lock_for_update=True,
    )
    if world.status == "published":
        return _creator_context(db, world=world, membership=membership)
    if world.row_version != data.row_version:
        raise WorldRowVersionConflictError(world_id)
    readiness = world_definitions.evaluate_world_readiness(db, world)
    if not readiness.ready_for_publish:
        raise WorldDefinitionIncompleteError(readiness)
    world.status = "published"
    world.readiness_status = "publish_ready"
    world.row_version += 1
    db.commit()
    db.refresh(world)
    return _creator_context(db, world=world, membership=membership)


def archive_world(
    db: Session,
    *,
    world_id: str,
    user: UserIdentity,
    data: schemas.WorldMutationRequest,
) -> schemas.WorldCreatorContextRead:
    world, membership = require_owner_access(
        db,
        world_id=world_id,
        user=user,
        lock_for_update=True,
    )
    if world.row_version != data.row_version:
        raise WorldRowVersionConflictError(world_id)
    world.status = "archived"
    world.readiness_status = "not_ready"
    world.archived_at = datetime.now(timezone.utc)
    world.row_version += 1
    db.commit()
    db.refresh(world)
    return _creator_context(db, world=world, membership=membership)


def upload_world_banner(
    db: Session,
    *,
    world_id: str,
    user: UserIdentity,
    data: schemas.WorldBannerUpload,
) -> schemas.WorldCreatorContextRead:
    world, membership = require_creator_access(
        db,
        world_id=world_id,
        user=user,
        lock_for_update=True,
    )
    if world.row_version != data.row_version:
        raise WorldRowVersionConflictError(world_id)
    old_media = world.banner_media_id
    try:
        new_media = world_banner_storage.save_world_banner(
            world_id=world.id,
            content_type=data.content_type,
            data_base64=data.data_base64,
        )
        schemas.validate_managed_world_banner(new_media)
    except (world_banner_storage.InvalidWorldBannerMediaError, ValueError) as exc:
        raise WorldBannerValidationError(str(exc)) from exc
    world.banner_media_id = new_media
    world.banner_alt_text = data.alt_text
    world.row_version += 1
    try:
        db.commit()
    except Exception:
        world_banner_storage.delete_media_url(new_media)
        raise
    if old_media and old_media != new_media:
        world_banner_storage.delete_media_url(old_media)
    db.refresh(world)
    return _creator_context(db, world=world, membership=membership)


def remove_world_banner(
    db: Session,
    *,
    world_id: str,
    user: UserIdentity,
    data: schemas.WorldMutationRequest,
) -> schemas.WorldCreatorContextRead:
    world, membership = require_creator_access(
        db,
        world_id=world_id,
        user=user,
        lock_for_update=True,
    )
    if world.row_version != data.row_version:
        raise WorldRowVersionConflictError(world_id)
    old_media = world.banner_media_id
    world.banner_media_id = None
    world.banner_alt_text = ""
    world.row_version += 1
    db.commit()
    if old_media:
        world_banner_storage.delete_media_url(old_media)
    db.refresh(world)
    return _creator_context(db, world=world, membership=membership)


def get_generation_context(
    db: Session,
    *,
    world_id: str,
    user: UserIdentity,
) -> schemas.WorldGenerationContextRead:
    world, _ = require_creator_access(db, world_id=world_id, user=user)
    readiness = world_definitions.evaluate_world_readiness(db, world)
    if not readiness.ready_for_publish:
        raise WorldDefinitionIncompleteError(readiness)
    return world_generation_context.build_world_generation_context(db, world)
