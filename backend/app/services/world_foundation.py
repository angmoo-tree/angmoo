from __future__ import annotations

import hashlib
from dataclasses import dataclass
from datetime import datetime, timezone
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session

from app import models
from app.services import world_definitions


ANGMOO_GLOBAL_WORLD_ID = "019fd7cd-8c00-721a-85f5-6b6cce3bed99"
ANGMOO_GLOBAL_WORLD_SLUG = "angmoo-global"
ANGMOO_GLOBAL_NAME = "Angmoo Global"
ANGMOO_GLOBAL_TAGLINE = "앵무 캐릭터들이 현대적인 일상을 공유하는 기본 통합 World"
ANGMOO_GLOBAL_SETTING_DESCRIPTION = (
    "Angmoo Global은 특정 판타지 설정에 속하지 않은 캐릭터들이 함께 머무는 현대형 기본 "
    "세계다. 도시의 주거지, 학교, 일터, 공원, 카페와 온라인 공간이 자연스럽게 이어지며, "
    "각 캐릭터는 자신의 성격과 관심사를 유지한 채 일상을 보낸다. 현실과 비슷한 기술과 "
    "생활 규칙을 따르지만 서로 다른 창작 캐릭터가 공존할 수 있도록 출신 배경은 폭넓게 "
    "허용한다. 다른 World의 고유 사건이나 관계는 자동으로 이곳에 섞이지 않는다."
)
ANGMOO_GLOBAL_DAILY_LIFE_DESCRIPTION = (
    "캐릭터들은 World의 현지 시간에 맞춰 잠에서 깨고, 공부하거나 일하고, 식사와 휴식을 "
    "즐기며 관심사에 맞는 장소를 찾는다. SNS에는 그날 직접 겪은 활동과 생각을 게시하고, "
    "다른 캐릭터의 글에 댓글·좋아요·답글로 반응한다. 특별한 사건이 없어도 산책, 독서, "
    "취미, 정리, 약속과 같은 작은 일상이 이어지며 실제로 성공한 상호작용만 관계와 기억의 "
    "근거가 된다."
)
ANGMOO_GLOBAL_GENRE_TAGS = ["modern", "social"]
ANGMOO_GLOBAL_TONE_TAGS = ["everyday", "warm"]
_BACKFILL_TIMESTAMP_MS = 1_786_032_000_000


@dataclass(frozen=True)
class GlobalFoundationReport:
    seeded: bool
    world_id: str | None
    owner_user_id: str | None
    membership_count: int
    world_character_count: int


def stable_backfill_uuid7(scope: str, value: str) -> str:
    digest = hashlib.sha256(f"{scope}:{value}".encode()).digest()
    random_bits = int.from_bytes(digest[:10], "big") & ((1 << 74) - 1)
    random_a = random_bits >> 62
    random_b = random_bits & ((1 << 62) - 1)
    result = (
        (_BACKFILL_TIMESTAMP_MS << 80)
        | (0x7 << 76)
        | (random_a << 64)
        | (0b10 << 62)
        | random_b
    )
    return str(UUID(int=result))


def choose_global_owner_user_id(db: Session) -> str | None:
    user_id = db.scalar(
        select(models.User.id)
        .where(models.User.deleted_at.is_(None), models.User.is_admin.is_(True))
        .order_by(models.User.created_at, models.User.id)
        .limit(1)
    )
    if user_id is not None:
        return user_id
    user_id = db.scalar(
        select(models.Character.owner_id)
        .join(models.User, models.User.id == models.Character.owner_id)
        .where(
            models.Character.deleted_at.is_(None),
            models.User.deleted_at.is_(None),
        )
        .order_by(models.Character.created_at, models.Character.owner_id)
        .limit(1)
    )
    if user_id is not None:
        return user_id
    return db.scalar(
        select(models.User.id)
        .where(models.User.deleted_at.is_(None))
        .order_by(models.User.created_at, models.User.id)
        .limit(1)
    )


def _new_global_world(owner_user_id: str) -> models.World:
    return models.World(
        id=ANGMOO_GLOBAL_WORLD_ID,
        slug=ANGMOO_GLOBAL_WORLD_SLUG,
        owner_user_id=owner_user_id,
        name=ANGMOO_GLOBAL_NAME,
        tagline=ANGMOO_GLOBAL_TAGLINE,
        setting_description=ANGMOO_GLOBAL_SETTING_DESCRIPTION,
        daily_life_description=ANGMOO_GLOBAL_DAILY_LIFE_DESCRIPTION,
        genre_tags=ANGMOO_GLOBAL_GENRE_TAGS,
        tone_tags=ANGMOO_GLOBAL_TONE_TAGS,
        banner_media_id=None,
        banner_alt_text="",
        timezone="Asia/Seoul",
        language="ko",
        visibility="public",
        join_policy="open",
        status="published",
        definition_version=1,
        row_version=1,
        contract_version=world_definitions.WORLD_CONTRACT_VERSION,
        contract_hash="0" * 64,
        readiness_status="not_ready",
        additional_generation_guidance="",
        create_idempotency_key="p1-angmoo-global-foundation",
    )


def ensure_angmoo_global_foundation(db: Session) -> GlobalFoundationReport:
    owner_user_id = choose_global_owner_user_id(db)
    if owner_user_id is None:
        return GlobalFoundationReport(False, None, None, 0, 0)

    world = db.scalar(
        select(models.World).where(models.World.slug == ANGMOO_GLOBAL_WORLD_SLUG)
    )
    if world is None:
        world = _new_global_world(owner_user_id)
        db.add(world)
        db.flush()
        world_definitions.refresh_world_contract(db, world)
    elif world.id != ANGMOO_GLOBAL_WORLD_ID:
        raise ValueError("angmoo-global slug is bound to an unexpected World ID")

    now = datetime.now(timezone.utc)
    owner_ids = list(
        db.scalars(
            select(models.Character.owner_id)
            .join(models.User, models.User.id == models.Character.owner_id)
            .where(
                models.Character.deleted_at.is_(None),
                models.User.deleted_at.is_(None),
            )
            .distinct()
            .order_by(models.Character.owner_id)
        )
    )
    if owner_user_id not in owner_ids:
        owner_ids.insert(0, owner_user_id)

    membership_by_user: dict[str, models.WorldMembership] = {}
    for user_id in owner_ids:
        membership = db.scalar(
            select(models.WorldMembership).where(
                models.WorldMembership.world_id == world.id,
                models.WorldMembership.user_id == user_id,
            )
        )
        if membership is None:
            membership = models.WorldMembership(
                id=stable_backfill_uuid7("angmoo-global-membership", user_id),
                world_id=world.id,
                user_id=user_id,
                role="owner" if user_id == owner_user_id else "member",
                status="active",
                requested_by_user_id=owner_user_id,
                approved_by_user_id=owner_user_id,
                joined_at=now,
                reason="p1_angmoo_global_backfill",
            )
            db.add(membership)
            db.flush()
        membership_by_user[user_id] = membership

    characters = list(
        db.scalars(
            select(models.Character)
            .where(models.Character.deleted_at.is_(None))
            .order_by(models.Character.id)
        )
    )
    for character in characters:
        existing = db.scalar(
            select(models.WorldCharacter.id).where(
                models.WorldCharacter.world_id == world.id,
                models.WorldCharacter.character_id == character.id,
            )
        )
        if existing is None:
            db.add(
                models.WorldCharacter(
                    id=stable_backfill_uuid7(
                        "angmoo-global-world-character", character.id
                    ),
                    world_id=world.id,
                    character_id=character.id,
                    membership_id=membership_by_user[character.owner_id].id,
                    status="inactive",
                    autonomous_enabled=False,
                    character_contract_hash=None,
                    world_contract_hash=world.contract_hash,
                    version=1,
                )
            )
    db.flush()
    membership_count = db.query(models.WorldMembership).filter_by(world_id=world.id).count()
    world_character_count = (
        db.query(models.WorldCharacter).filter_by(world_id=world.id).count()
    )
    return GlobalFoundationReport(
        True,
        world.id,
        owner_user_id,
        membership_count,
        world_character_count,
    )
