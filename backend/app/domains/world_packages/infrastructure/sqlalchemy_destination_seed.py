"""Atomic package seed composition under a caller-owned SQLAlchemy UoW."""

from __future__ import annotations

from types import SimpleNamespace

from sqlalchemy.orm import Session

from app.core.ids import uuid7_string
from app.domains.characters.public import (
    AutonomousCharacterSeedData,
    seed_autonomous_character,
)
from app.domains.world_characters.public import (
    AutonomousWorldCharacterSeedData,
    seed_autonomous_world_character,
)
from app.domains.world_packages.domain.seed import (
    WorldPackageDestinationSeedRequest,
    WorldPackageDestinationSeedResult,
    WorldPackageImportIdMapping,
    WorldPackageImportRegistryRecord,
    resolve_world_package_import_replay,
)
from app.domains.world_packages.infrastructure.sqlalchemy_registry import (
    SqlAlchemyWorldPackageRegistry,
)
from app.domains.worlds.public import (
    WorldDaypartProfileInput,
    WorldDraftCreate,
    WorldGlossaryTermInput,
    WorldPlaceInput,
    WorldRoleInput,
    WorldRuleInput,
    seed_world,
)


def _local_ref(value: str) -> str:
    return value.split("/", 1)[-1]


class SqlAlchemyWorldPackageDestinationSeed:
    """Flush all canonical rows but leave commit/rollback to the caller."""

    def __init__(self, db: Session) -> None:
        self._db = db
        self._registry = SqlAlchemyWorldPackageRegistry(db)

    def seed(
        self, request: WorldPackageDestinationSeedRequest
    ) -> WorldPackageDestinationSeedResult:
        replay = self._registry.find_import(
            local_owner_id=request.local_owner_id,
            idempotency_key=request.idempotency_key,
        )
        if replay is not None:
            return resolve_world_package_import_replay(request, replay)

        world_data = request.world
        asset_urls = {
            item.source_ref: item.local_url for item in request.imported_assets
        }
        planned_handles = (
            {
                item.source_ref: item.planned_handle
                for item in request.collision_plan.characters
            }
            if request.collision_plan is not None
            else {}
        )
        world_outcome = seed_world(
            self._db,
            user=SimpleNamespace(id=request.local_owner_id),
            data=WorldDraftCreate(
                name=world_data.name,
                tagline=world_data.tagline,
                setting_description=world_data.setting_description,
                daily_life_description=world_data.daily_life_description,
                genre_tags=world_data.genre_tags,
                tone_tags=world_data.tone_tags,
                timezone=world_data.timezone,
                language=world_data.language,
                visibility="unlisted",
                join_policy="approval_required",
                additional_generation_guidance=world_data.additional_generation_guidance,
                places=[
                    WorldPlaceInput(
                        key=_local_ref(item.ref),
                        name=item.name,
                        description=item.description,
                        available_dayparts=item.available_dayparts,
                        access_role_keys=[_local_ref(ref) for ref in item.access_role_refs],
                    )
                    for item in world_data.places
                ],
                roles=[
                    WorldRoleInput(
                        key=_local_ref(item.ref),
                        name=item.name,
                        description=item.description,
                        responsibilities=item.responsibilities,
                        allowed_activity_scope=item.allowed_activity_scope,
                        autonomous_allowed=item.autonomous_allowed,
                    )
                    for item in world_data.roles
                ],
                daypart_profiles=[
                    WorldDaypartProfileInput(
                        daypart=item.daypart,
                        description=item.description,
                        available_features=item.available_features,
                        restricted_features=item.restricted_features,
                    )
                    for item in world_data.daypart_profiles
                ],
                rules=[
                    WorldRuleInput(
                        key=_local_ref(item.ref),
                        rule_kind=item.rule_kind,
                        description=item.description,
                    )
                    for item in world_data.rules
                ],
                glossary=[
                    WorldGlossaryTermInput(
                        key=_local_ref(item.ref),
                        term=item.term,
                        meaning=item.meaning,
                    )
                    for item in world_data.glossary
                ],
                idempotency_key=f"world-package:{request.idempotency_key}",
            ),
            status="published",
            membership_reason="world_package_import",
            planned_slug=(
                request.collision_plan.planned_world_slug
                if request.collision_plan is not None
                else None
            ),
            banner_media_id=(
                asset_urls.get(world_data.banner_asset_ref)
                if world_data.banner_asset_ref is not None
                else None
            ),
            banner_alt_text=world_data.banner_alt_text,
        )
        if world_outcome.replayed:
            raise RuntimeError("world_package_registry_missing_for_existing_seed")

        mappings: list[WorldPackageImportIdMapping] = [
            WorldPackageImportIdMapping(
                source_ref="world", entity_kind="world", local_id=world_outcome.world.id
            )
        ]
        character_ids: dict[str, str] = {}
        for item in request.characters:
            character = seed_autonomous_character(
                self._db,
                data=AutonomousCharacterSeedData(
                    owner_id=request.local_owner_id,
                    display_name=item.display_name,
                    handle_hint=item.handle_hint,
                    one_liner=item.one_liner,
                    personality=item.personality,
                    speech_style=item.speech_style,
                    worldview=item.worldview,
                    topic_preferences=tuple(item.topic_preferences),
                    safety_rules=tuple(item.safety_rules),
                    persona_summary=item.persona_summary,
                    planned_handle=planned_handles.get(item.ref),
                    avatar_url=(
                        asset_urls.get(item.avatar_asset_ref)
                        if item.avatar_asset_ref is not None
                        else None
                    ),
                    banner_url=(
                        asset_urls.get(item.banner_asset_ref)
                        if item.banner_asset_ref is not None
                        else None
                    ),
                ),
            )
            character_ids[item.ref] = character.id
            mappings.append(
                WorldPackageImportIdMapping(
                    source_ref=item.ref,
                    entity_kind="character",
                    local_id=character.id,
                )
            )

        for item in request.world_characters:
            character_id = character_ids.get(item.character_ref)
            if character_id is None:
                raise ValueError("world_character_references_unknown_character")
            world_character = seed_autonomous_world_character(
                self._db,
                data=AutonomousWorldCharacterSeedData(
                    world_id=world_outcome.world.id,
                    character_id=character_id,
                    membership_id=world_outcome.membership.id,
                    role_key=_local_ref(item.role_ref),
                    role_description=item.role_description,
                    background=item.background,
                    access_scope=tuple(item.access_scope),
                ),
            )
            mappings.append(
                WorldPackageImportIdMapping(
                    source_ref=f"world-characters/{_local_ref(item.character_ref)}",
                    entity_kind="world_character",
                    local_id=world_character.id,
                )
            )

        mappings.extend(
            WorldPackageImportIdMapping(
                source_ref=item.source_ref,
                entity_kind="asset",
                local_id=item.local_url,
            )
            for item in request.imported_assets
        )
        record = WorldPackageImportRegistryRecord(
            import_id=request.import_id or uuid7_string(),
            local_owner_id=request.local_owner_id,
            package_id=request.package_id,
            package_version=request.package_version,
            content_digest=request.content_digest,
            imported_world_id=world_outcome.world.id,
            import_mode="new_world",
            trust_state=request.trust_state,
            license_expression=request.license_expression,
            idempotency_key=request.idempotency_key,
            id_mappings=tuple(sorted(mappings, key=lambda item: item.source_ref)),
        )
        self._registry.add_import(record)
        return WorldPackageDestinationSeedResult(
            import_id=record.import_id,
            imported_world_id=record.imported_world_id,
            id_mappings=record.id_mappings,
        )


__all__ = ["SqlAlchemyWorldPackageDestinationSeed"]
