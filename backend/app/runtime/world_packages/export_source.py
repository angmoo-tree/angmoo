"""Read-only SQLAlchemy snapshot adapter for deterministic package export."""

from __future__ import annotations

from app.domains.world_packages.service.export_projection import _portable_key, _portable_map, _text_list, _portable_local_profile

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.domains.characters.models import Character
from app.domains.world_characters.models import WorldCharacter
from app.domains.world_characters.service.setup_validation import character_contract_hash
from app.domains.world_packages.utils.canonical import canonical_sha256
from app.domains.world_packages.schemas.content import (
    AutonomousCharacterTemplate,
    PortableDaypartProfile,
    PortableGlossaryTerm,
    PortablePlace,
    PortableRole,
    PortableRule,
    PortableWorldCharacterSeed,
    PortableWorldDefinition,
)
from app.domains.world_packages.exceptions import (
    WorldPackageContractError,
    WorldPackageReasonCode,
)
from app.domains.world_packages.contracts.export import WorldPackageMediaCandidate
from app.domains.world_packages.contracts.seed import WorldPackageSourceSnapshot
from app.domains.worlds.contracts import NO_SPECIFIC_ROLE_KEY, is_canonical_no_specific_role
from app.domains.worlds.service.creator import WorldMembershipRequiredError, WorldNotFoundError, WorldOwnerRoleRequiredError, get_generation_context, require_owner_access
from app.domains.worlds.service.definition import world_contract_hash












class SqlAlchemyWorldPackageSourceSnapshot:
    def __init__(self, db: Session) -> None:
        self._db = db

    def snapshot(
        self, *, source_world_id: str, local_owner_id: str
    ) -> WorldPackageSourceSnapshot:
        user = type("PackageOwner", (), {"id": local_owner_id})()
        try:
            world, _membership = require_owner_access(
                self._db,
                world_id=source_world_id,
                user=user,
            )
        except (
            WorldMembershipRequiredError,
            WorldNotFoundError,
            WorldOwnerRoleRequiredError,
        ) as exc:
            raise WorldPackageContractError(
                WorldPackageReasonCode.OWNER_REQUIRED
            ) from exc
        current_hash = world_contract_hash(self._db, world)
        if (
            world.status != "published"
            or world.readiness_status != "publish_ready"
            or current_hash != world.contract_hash
        ):
            raise WorldPackageContractError(
                WorldPackageReasonCode.WORLD_NOT_EXPORTABLE
            )
        context = get_generation_context(
            self._db,
            world_id=source_world_id,
            user=user,
        )
        if any(
            role.key == NO_SPECIFIC_ROLE_KEY
            and not is_canonical_no_specific_role(role)
            for role in context.roles
        ):
            raise WorldPackageContractError(
                WorldPackageReasonCode.REFERENCE_INVALID
            )
        role_refs = _portable_map(
            [item.key for item in context.roles], label="roles"
        )
        place_refs = _portable_map(
            [item.key for item in context.places], label="places"
        )
        rule_refs = _portable_map(
            [item.key for item in context.rules], label="rules"
        )
        glossary_refs = _portable_map(
            [item.key for item in context.glossary], label="glossary"
        )
        if any(
            not set(item.access_role_keys).issubset(role_refs)
            for item in context.places
        ):
            raise WorldPackageContractError(
                WorldPackageReasonCode.REFERENCE_INVALID
            )

        rows = list(
            self._db.execute(
                select(WorldCharacter, Character)
                .join(Character, Character.id == WorldCharacter.character_id)
                .where(WorldCharacter.world_id == source_world_id)
                .order_by(Character.handle, Character.id)
            ).all()
        )
        excluded_owner_controlled = sum(
            row.control_mode == "owner_controlled" for row, _character in rows
        )
        autonomous_rows = [
            (row, character)
            for row, character in rows
            if row.control_mode == "autonomous"
            and row.status in {"pending", "inactive", "active"}
        ]
        if len(autonomous_rows) > 50:
            raise WorldPackageContractError(
                WorldPackageReasonCode.ARCHIVE_LIMIT_EXCEEDED
            )

        characters: list[AutonomousCharacterTemplate] = []
        world_characters: list[PortableWorldCharacterSeed] = []
        media_candidates: list[WorldPackageMediaCandidate] = []
        character_hashes: list[dict[str, str]] = []
        for ordinal, (row, character) in enumerate(autonomous_rows, start=1):
            if (
                character.owner_id != local_owner_id
                or character.deleted_at is not None
                or character.moderation_status != "active"
                or row.role_key is None
                or row.role_key not in role_refs
            ):
                raise WorldPackageContractError(
                    WorldPackageReasonCode.WORLD_NOT_EXPORTABLE
                )
            character_ref = f"characters/char-{ordinal:04d}"
            characters.append(
                AutonomousCharacterTemplate(
                    ref=character_ref,
                    display_name=character.name,
                    handle_hint=character.handle,
                    one_liner=character.one_liner,
                    personality=character.personality,
                    speech_style=character.speech_style,
                    worldview=character.worldview,
                    topic_preferences=_text_list(
                        character.topic_preferences, separator=","
                    ),
                    safety_rules=_text_list(character.safety_rules, separator="\n"),
                    persona_summary=character.persona_summary,
                )
            )
            profile = _portable_local_profile(row.local_profile)
            world_characters.append(
                PortableWorldCharacterSeed(
                    character_ref=character_ref,
                    role_ref=role_refs[row.role_key],
                    role_description=str(profile["role_description"]),
                    background=str(profile["background"]),
                    access_scope=list(profile["access_scope"]),
                )
            )
            media_candidates.extend(
                (
                    WorldPackageMediaCandidate(
                        candidate_key=f"{character_ref}:avatar",
                        slot="character_avatar",
                        source_url=character.avatar_url,
                        source_entity_id=character.id,
                        alt_text=f"{character.name} avatar",
                    ),
                    WorldPackageMediaCandidate(
                        candidate_key=f"{character_ref}:banner",
                        slot="character_banner",
                        source_url=character.banner_url,
                        source_entity_id=character.id,
                        alt_text=f"{character.name} banner",
                    ),
                )
            )
            character_hashes.append(
                {"ref": character_ref, "hash": character_contract_hash(character)}
            )

        portable_world = PortableWorldDefinition(
            schema_version="world-content-v1",
            ref="world",
            name=context.name,
            tagline=context.tagline,
            setting_description=context.setting_description,
            daily_life_description=context.daily_life_description,
            genre_tags=context.genre_tags,
            tone_tags=context.tone_tags,
            timezone=context.timezone,
            language=context.language,
            additional_generation_guidance=context.additional_generation_guidance,
            places=[
                PortablePlace(
                    ref=place_refs[item.key],
                    name=item.name,
                    description=item.description,
                    available_dayparts=item.available_dayparts,
                    access_role_refs=[role_refs[key] for key in item.access_role_keys],
                )
                for item in context.places
            ],
            roles=[
                PortableRole(
                    ref=role_refs[item.key],
                    name=item.name,
                    description=item.description,
                    responsibilities=item.responsibilities,
                    allowed_activity_scope=item.allowed_activity_scope,
                    autonomous_allowed=item.autonomous_allowed,
                )
                for item in context.roles
            ],
            daypart_profiles=[
                PortableDaypartProfile(**item.model_dump())
                for item in context.daypart_profiles
            ],
            rules=[
                PortableRule(
                    ref=rule_refs[item.key],
                    rule_kind=item.rule_kind,
                    description=item.description,
                )
                for item in context.rules
            ],
            glossary=[
                PortableGlossaryTerm(
                    ref=glossary_refs[item.key],
                    term=item.term,
                    meaning=item.meaning,
                )
                for item in context.glossary
            ],
            banner_alt_text=world.banner_alt_text,
            source_world_contract_version=context.contract_version,
            source_world_definition_hash=current_hash,
        )
        media_candidates.insert(
            0,
            WorldPackageMediaCandidate(
                candidate_key="world:banner",
                slot="world_banner",
                source_url=world.banner_media_id,
                source_entity_id=world.id,
                alt_text=world.banner_alt_text,
            ),
        )
        fingerprint = canonical_sha256(
            {
                "world": portable_world,
                "characters": characters,
                "world_characters": world_characters,
                "media_references": [
                    {
                        "candidate_key": item.candidate_key,
                        "source_url": item.source_url,
                    }
                    for item in media_candidates
                ],
                "character_contracts": character_hashes,
            }
        )
        return WorldPackageSourceSnapshot(
            source_world_id=source_world_id,
            source_fingerprint=fingerprint,
            world=portable_world,
            characters=tuple(characters),
            world_characters=tuple(world_characters),
            media_candidates=tuple(media_candidates),
            excluded_owner_controlled_characters=excluded_owner_controlled,
        )


__all__ = ["SqlAlchemyWorldPackageSourceSnapshot"]
