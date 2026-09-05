from __future__ import annotations

from sqlalchemy.orm import Session

from app.domains.worlds import schemas
from app.domains.worlds.service import definition as world_definitions
from app.domains.worlds import models


def build_world_generation_context(
    db: Session, world: models.World
) -> schemas.WorldGenerationContextRead:
    places, roles, dayparts, rules, glossary = world_definitions.load_definition_parts(
        db, world
    )
    return schemas.WorldGenerationContextRead(
        world_id=world.id,
        name=world.name,
        tagline=world.tagline,
        setting_description=world.setting_description,
        daily_life_description=world.daily_life_description,
        genre_tags=world.genre_tags,
        tone_tags=world.tone_tags,
        timezone=world.timezone,
        language=world.language,
        definition_version=world.definition_version,
        contract_version=world.contract_version,
        contract_hash=world.contract_hash,
        additional_generation_guidance=world.additional_generation_guidance,
        places=[
            schemas.WorldPlaceInput(
                key=item.place_key,
                name=item.name,
                description=item.description,
                available_dayparts=item.available_dayparts,
                access_role_keys=item.access_role_keys,
            )
            for item in places
        ],
        roles=[
            schemas.WorldRoleInput(
                key=item.role_key,
                name=item.name,
                description=item.description,
                responsibilities=item.responsibilities,
                allowed_activity_scope=item.allowed_activity_scope,
                autonomous_allowed=item.autonomous_allowed,
            )
            for item in roles
        ],
        daypart_profiles=[
            schemas.WorldDaypartProfileInput(
                daypart=item.daypart,
                description=item.description,
                available_features=item.available_features,
                restricted_features=item.restricted_features,
            )
            for item in dayparts
        ],
        rules=[
            schemas.WorldRuleInput(
                key=item.rule_key,
                rule_kind=item.rule_kind,
                description=item.description,
            )
            for item in rules
        ],
        glossary=[
            schemas.WorldGlossaryTermInput(
                key=item.term_key,
                term=item.term,
                meaning=item.meaning,
            )
            for item in glossary
        ],
    )
