from __future__ import annotations

from datetime import datetime, timezone
import hashlib
import json
import re
import unicodedata
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.domains.worlds import schemas
from app.domains.worlds import models


WORLD_CONTRACT_VERSION = "p0-contract-v1.1-world-creator"
DAYPARTS = ("dawn", "morning", "afternoon", "evening")
_LANGUAGE_PATTERN = re.compile(r"^[a-z]{2,3}(?:-[A-Z]{2})?$")


def canonical_text(value: str) -> str:
    return " ".join(unicodedata.normalize("NFKC", value).strip().split())


def canonical_tags(values: list[str]) -> list[str]:
    return sorted({canonical_text(value).casefold() for value in values if value.strip()})


def _active_rows(db: Session, model, world_id: str, *order_by):
    return list(
        db.scalars(
            select(model)
            .where(model.world_id == world_id, model.status == "enabled")
            .order_by(*order_by)
        )
    )


def load_definition_parts(
    db: Session, world: models.World
) -> tuple[
    list[models.WorldPlace],
    list[models.WorldRole],
    list[models.WorldDaypartProfile],
    list[models.WorldRule],
    list[models.WorldGlossaryTerm],
]:
    places = _active_rows(db, models.WorldPlace, world.id, models.WorldPlace.place_key)
    roles = _active_rows(db, models.WorldRole, world.id, models.WorldRole.role_key)
    dayparts = _active_rows(
        db,
        models.WorldDaypartProfile,
        world.id,
        models.WorldDaypartProfile.daypart,
    )
    rules = _active_rows(
        db,
        models.WorldRule,
        world.id,
        models.WorldRule.rule_key,
        models.WorldRule.rule_kind,
    )
    glossary = _active_rows(
        db,
        models.WorldGlossaryTerm,
        world.id,
        models.WorldGlossaryTerm.term_key,
    )
    return places, roles, dayparts, rules, glossary


def canonical_world_definition(db: Session, world: models.World) -> dict[str, object]:
    places, roles, dayparts, rules, glossary = load_definition_parts(db, world)
    return {
        "contract_version": world.contract_version,
        "name": canonical_text(world.name),
        "tagline": canonical_text(world.tagline),
        "setting_description": canonical_text(world.setting_description),
        "daily_life_description": canonical_text(world.daily_life_description),
        "genre_tags": canonical_tags(world.genre_tags),
        "tone_tags": canonical_tags(world.tone_tags),
        "timezone": world.timezone,
        "language": world.language,
        "additional_generation_guidance": canonical_text(
            world.additional_generation_guidance
        ),
        "places": [
            {
                "key": item.place_key,
                "version": item.version,
                "name": canonical_text(item.name),
                "description": canonical_text(item.description),
                "available_dayparts": sorted(set(item.available_dayparts)),
                "access_role_keys": sorted(set(item.access_role_keys)),
            }
            for item in places
        ],
        "roles": [
            {
                "key": item.role_key,
                "version": item.version,
                "name": canonical_text(item.name),
                "description": canonical_text(item.description),
                "responsibilities": sorted(
                    canonical_text(value) for value in item.responsibilities
                ),
                "allowed_activity_scope": sorted(
                    canonical_text(value) for value in item.allowed_activity_scope
                ),
                "autonomous_allowed": item.autonomous_allowed,
            }
            for item in roles
        ],
        "daypart_profiles": [
            {
                "daypart": item.daypart,
                "version": item.version,
                "description": canonical_text(item.description),
                "available_features": sorted(
                    canonical_text(value) for value in item.available_features
                ),
                "restricted_features": sorted(
                    canonical_text(value) for value in item.restricted_features
                ),
            }
            for item in dayparts
        ],
        "rules": [
            {
                "key": item.rule_key,
                "kind": item.rule_kind,
                "version": item.version,
                "description": canonical_text(item.description),
            }
            for item in rules
        ],
        "glossary": [
            {
                "key": item.term_key,
                "version": item.version,
                "term": canonical_text(item.term),
                "meaning": canonical_text(item.meaning),
            }
            for item in glossary
        ],
    }


def world_contract_hash(db: Session, world: models.World) -> str:
    payload = json.dumps(
        canonical_world_definition(db, world),
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    return hashlib.sha256(payload).hexdigest()


def _issue(
    reason_code: schemas.WorldValidationReason, field: str, message: str
) -> schemas.WorldValidationIssue:
    return schemas.WorldValidationIssue(
        reason_code=reason_code,
        field=field,
        message=message,
    )


def evaluate_world_readiness(
    db: Session, world: models.World
) -> schemas.WorldReadinessRead:
    required_fields = {
        "name": 2 <= len(world.name) <= 120,
        "tagline": 10 <= len(world.tagline) <= 160,
        "setting_description": 200 <= len(world.setting_description) <= 4000,
        "daily_life_description": 150 <= len(world.daily_life_description) <= 3000,
        "genre_tags": 1 <= len(world.genre_tags) <= 5,
        "tone_tags": 1 <= len(world.tone_tags) <= 5,
        "timezone": True,
        "language": bool(_LANGUAGE_PATTERN.fullmatch(world.language)),
    }
    try:
        ZoneInfo(world.timezone)
    except (ZoneInfoNotFoundError, ValueError):
        required_fields["timezone"] = False

    issues: list[schemas.WorldValidationIssue] = []
    issue_specs: tuple[tuple[str, schemas.WorldValidationReason, str], ...] = (
        ("name", "invalid_world_name", "World 이름은 2~120자로 작성해 주세요."),
        ("tagline", "invalid_tagline", "한 줄 소개는 10~160자로 작성해 주세요."),
        (
            "setting_description",
            "invalid_setting_description",
            "세계관 설명은 200~4,000자로 작성해 주세요.",
        ),
        (
            "daily_life_description",
            "invalid_daily_life_description",
            "일상 설명은 150~3,000자로 작성해 주세요.",
        ),
        ("genre_tags", "invalid_genre_tags", "장르 태그를 1~5개 선택해 주세요."),
        ("tone_tags", "invalid_tone_tags", "분위기 태그를 1~5개 선택해 주세요."),
        ("timezone", "invalid_timezone", "올바른 지역 시간대를 선택해 주세요."),
        ("language", "invalid_language", "올바른 언어 코드를 입력해 주세요."),
    )
    for field, reason_code, message in issue_specs:
        if not required_fields[field]:
            issues.append(_issue(reason_code, field, message))
    if world.status == "archived":
        issues.insert(0, _issue("world_archived", "status", "보관된 World입니다."))

    places, roles, dayparts, rules, glossary = load_definition_parts(db, world)
    optional_groups = sum(
        bool(value)
        for value in (
            world.banner_media_id,
            places,
            roles,
            dayparts,
            rules,
            glossary,
            world.additional_generation_guidance,
        )
    )
    quality_tier: schemas.WorldQualityTier
    if optional_groups == 0:
        quality_tier = "CORE"
    elif optional_groups < 4:
        quality_tier = "ENRICHED"
    else:
        quality_tier = "DETAILED"
    return schemas.WorldReadinessRead(
        world_id=world.id,
        definition_version=world.definition_version,
        row_version=world.row_version,
        contract_version=world.contract_version,
        contract_hash=world.contract_hash,
        required_fields=required_fields,
        optional_setting_count=optional_groups,
        quality_tier=quality_tier,
        issues=issues,
        ready_for_publish=not issues,
        evaluated_at=datetime.now(timezone.utc),
    )


def refresh_world_contract(db: Session, world: models.World) -> bool:
    new_hash = world_contract_hash(db, world)
    changed = new_hash != world.contract_hash
    world.contract_hash = new_hash
    readiness = evaluate_world_readiness(db, world)
    world.readiness_status = (
        "publish_ready" if readiness.ready_for_publish else "not_ready"
    )
    return changed


def place_read(item: models.WorldPlace) -> schemas.WorldPlaceRead:
    return schemas.WorldPlaceRead(
        id=item.id,
        key=item.place_key,
        version=item.version,
        name=item.name,
        description=item.description,
        available_dayparts=item.available_dayparts,
        access_role_keys=item.access_role_keys,
    )


def role_read(item: models.WorldRole) -> schemas.WorldRoleRead:
    return schemas.WorldRoleRead(
        id=item.id,
        key=item.role_key,
        version=item.version,
        name=item.name,
        description=item.description,
        responsibilities=item.responsibilities,
        allowed_activity_scope=item.allowed_activity_scope,
        autonomous_allowed=item.autonomous_allowed,
    )


def daypart_read(item: models.WorldDaypartProfile) -> schemas.WorldDaypartProfileRead:
    return schemas.WorldDaypartProfileRead(
        id=item.id,
        daypart=item.daypart,
        version=item.version,
        description=item.description,
        available_features=item.available_features,
        restricted_features=item.restricted_features,
    )


def rule_read(item: models.WorldRule) -> schemas.WorldRuleRead:
    return schemas.WorldRuleRead(
        id=item.id,
        key=item.rule_key,
        version=item.version,
        rule_kind=item.rule_kind,
        description=item.description,
    )


def glossary_read(item: models.WorldGlossaryTerm) -> schemas.WorldGlossaryTermRead:
    return schemas.WorldGlossaryTermRead(
        id=item.id,
        key=item.term_key,
        version=item.version,
        term=item.term,
        meaning=item.meaning,
    )


def world_read(db: Session, world: models.World) -> schemas.WorldRead:
    places, roles, dayparts, rules, glossary = load_definition_parts(db, world)
    return schemas.WorldRead(
        id=world.id,
        slug=world.slug,
        name=world.name,
        tagline=world.tagline,
        setting_description=world.setting_description,
        daily_life_description=world.daily_life_description,
        genre_tags=world.genre_tags,
        tone_tags=world.tone_tags,
        banner_media_id=world.banner_media_id,
        banner_alt_text=world.banner_alt_text,
        timezone=world.timezone,
        language=world.language,
        visibility=world.visibility,
        join_policy=world.join_policy,
        status=world.status,
        definition_version=world.definition_version,
        row_version=world.row_version,
        contract_version=world.contract_version,
        contract_hash=world.contract_hash,
        readiness_status=world.readiness_status,
        additional_generation_guidance=world.additional_generation_guidance,
        created_at=world.created_at,
        updated_at=world.updated_at,
        archived_at=world.archived_at,
        places=[place_read(item) for item in places],
        roles=[role_read(item) for item in roles],
        daypart_profiles=[daypart_read(item) for item in dayparts],
        rules=[rule_read(item) for item in rules],
        glossary=[glossary_read(item) for item in glossary],
    )
