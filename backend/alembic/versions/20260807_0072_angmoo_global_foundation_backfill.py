"""seed the canonical angmoo-global World foundation

Revision ID: 20260807_0072
Revises: 20260807_0070
Create Date: 2026-08-07
"""

from __future__ import annotations

import hashlib
import json
import unicodedata
from collections.abc import Sequence
from datetime import datetime, timezone
from uuid import UUID

from alembic import op
import sqlalchemy as sa


revision: str = "20260807_0072"
down_revision: str | None = "20260807_0070"
branch_labels: str | Sequence[str] | None = None
depends_on: str | None = None

GLOBAL_WORLD_ID = "019fd7cd-8c00-721a-85f5-6b6cce3bed99"
GLOBAL_SLUG = "angmoo-global"
GLOBAL_NAME = "Angmoo Global"
GLOBAL_TAGLINE = "앵무 캐릭터들이 현대적인 일상을 공유하는 기본 통합 World"
GLOBAL_SETTING_DESCRIPTION = (
    "Angmoo Global은 특정 판타지 설정에 속하지 않은 캐릭터들이 함께 머무는 현대형 기본 "
    "세계다. 도시의 주거지, 학교, 일터, 공원, 카페와 온라인 공간이 자연스럽게 이어지며, "
    "각 캐릭터는 자신의 성격과 관심사를 유지한 채 일상을 보낸다. 현실과 비슷한 기술과 "
    "생활 규칙을 따르지만 서로 다른 창작 캐릭터가 공존할 수 있도록 출신 배경은 폭넓게 "
    "허용한다. 다른 World의 고유 사건이나 관계는 자동으로 이곳에 섞이지 않는다."
)
GLOBAL_DAILY_LIFE_DESCRIPTION = (
    "캐릭터들은 World의 현지 시간에 맞춰 잠에서 깨고, 공부하거나 일하고, 식사와 휴식을 "
    "즐기며 관심사에 맞는 장소를 찾는다. SNS에는 그날 직접 겪은 활동과 생각을 게시하고, "
    "다른 캐릭터의 글에 댓글·좋아요·답글로 반응한다. 특별한 사건이 없어도 산책, 독서, "
    "취미, 정리, 약속과 같은 작은 일상이 이어지며 실제로 성공한 상호작용만 관계와 기억의 "
    "근거가 된다."
)
GLOBAL_GENRE_TAGS = ["modern", "social"]
GLOBAL_TONE_TAGS = ["everyday", "warm"]
WORLD_CONTRACT_VERSION = "p0-contract-v1.1-world-creator"
BACKFILL_TIMESTAMP_MS = 1_786_032_000_000


def _canonical_text(value: str) -> str:
    return " ".join(unicodedata.normalize("NFKC", value).strip().split())


def _global_contract_hash() -> str:
    definition = {
        "contract_version": WORLD_CONTRACT_VERSION,
        "name": _canonical_text(GLOBAL_NAME),
        "tagline": _canonical_text(GLOBAL_TAGLINE),
        "setting_description": _canonical_text(GLOBAL_SETTING_DESCRIPTION),
        "daily_life_description": _canonical_text(
            GLOBAL_DAILY_LIFE_DESCRIPTION
        ),
        "genre_tags": sorted({value.casefold() for value in GLOBAL_GENRE_TAGS}),
        "tone_tags": sorted({value.casefold() for value in GLOBAL_TONE_TAGS}),
        "timezone": "Asia/Seoul",
        "language": "ko",
        "additional_generation_guidance": "",
        "places": [],
        "roles": [],
        "daypart_profiles": [],
        "rules": [],
        "glossary": [],
    }
    encoded = json.dumps(
        definition,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


GLOBAL_CONTRACT_HASH = _global_contract_hash()


def _stable_uuid7(scope: str, value: str) -> str:
    digest = hashlib.sha256(f"{scope}:{value}".encode()).digest()
    random_bits = int.from_bytes(digest[:10], "big") & ((1 << 74) - 1)
    random_a = random_bits >> 62
    random_b = random_bits & ((1 << 62) - 1)
    result = (
        (BACKFILL_TIMESTAMP_MS << 80)
        | (0x7 << 76)
        | (random_a << 64)
        | (0b10 << 62)
        | random_b
    )
    return str(UUID(int=result))


def upgrade() -> None:
    connection = op.get_bind()
    users = sa.table(
        "users",
        sa.column("id", sa.String()),
        sa.column("is_admin", sa.Boolean()),
        sa.column("deleted_at", sa.DateTime(timezone=True)),
        sa.column("created_at", sa.DateTime(timezone=True)),
    )
    characters = sa.table(
        "characters",
        sa.column("id", sa.String()),
        sa.column("owner_id", sa.String()),
        sa.column("deleted_at", sa.DateTime(timezone=True)),
        sa.column("created_at", sa.DateTime(timezone=True)),
    )
    worlds = sa.table(
        "worlds",
        sa.column("id", sa.String()),
        sa.column("slug", sa.String()),
        sa.column("owner_user_id", sa.String()),
        sa.column("name", sa.String()),
        sa.column("tagline", sa.String()),
        sa.column("setting_description", sa.Text()),
        sa.column("daily_life_description", sa.Text()),
        sa.column("genre_tags", sa.JSON()),
        sa.column("tone_tags", sa.JSON()),
        sa.column("banner_media_id", sa.String()),
        sa.column("banner_alt_text", sa.String()),
        sa.column("timezone", sa.String()),
        sa.column("language", sa.String()),
        sa.column("visibility", sa.String()),
        sa.column("join_policy", sa.String()),
        sa.column("status", sa.String()),
        sa.column("definition_version", sa.Integer()),
        sa.column("row_version", sa.Integer()),
        sa.column("contract_version", sa.String()),
        sa.column("contract_hash", sa.String()),
        sa.column("readiness_status", sa.String()),
        sa.column("additional_generation_guidance", sa.Text()),
        sa.column("create_idempotency_key", sa.String()),
        sa.column("created_at", sa.DateTime(timezone=True)),
        sa.column("updated_at", sa.DateTime(timezone=True)),
    )
    memberships = sa.table(
        "world_memberships",
        sa.column("id", sa.String()),
        sa.column("world_id", sa.String()),
        sa.column("user_id", sa.String()),
        sa.column("role", sa.String()),
        sa.column("status", sa.String()),
        sa.column("requested_by_user_id", sa.String()),
        sa.column("approved_by_user_id", sa.String()),
        sa.column("joined_at", sa.DateTime(timezone=True)),
        sa.column("reason", sa.String()),
        sa.column("created_at", sa.DateTime(timezone=True)),
        sa.column("updated_at", sa.DateTime(timezone=True)),
    )
    world_characters = sa.table(
        "world_characters",
        sa.column("id", sa.String()),
        sa.column("world_id", sa.String()),
        sa.column("character_id", sa.String()),
        sa.column("membership_id", sa.String()),
        sa.column("role_key", sa.String()),
        sa.column("status", sa.String()),
        sa.column("autonomous_enabled", sa.Boolean()),
        sa.column("local_profile", sa.JSON()),
        sa.column("character_contract_hash", sa.String()),
        sa.column("world_contract_hash", sa.String()),
        sa.column("version", sa.Integer()),
        sa.column("created_at", sa.DateTime(timezone=True)),
        sa.column("updated_at", sa.DateTime(timezone=True)),
    )

    owner_user_id = connection.scalar(
        sa.select(users.c.id)
        .where(users.c.deleted_at.is_(None), users.c.is_admin.is_(True))
        .order_by(users.c.created_at, users.c.id)
        .limit(1)
    )
    if owner_user_id is None:
        owner_user_id = connection.scalar(
            sa.select(characters.c.owner_id)
            .join(users, users.c.id == characters.c.owner_id)
            .where(
                characters.c.deleted_at.is_(None),
                users.c.deleted_at.is_(None),
            )
            .order_by(characters.c.created_at, characters.c.owner_id)
            .limit(1)
        )
    if owner_user_id is None:
        owner_user_id = connection.scalar(
            sa.select(users.c.id)
            .where(users.c.deleted_at.is_(None))
            .order_by(users.c.created_at, users.c.id)
            .limit(1)
        )
    # Fresh installs can run before the first user exists. Runtime foundation
    # creation uses the same canonical definition after onboarding.
    if owner_user_id is None:
        return

    backfill_at = datetime.fromtimestamp(
        BACKFILL_TIMESTAMP_MS / 1000,
        tz=timezone.utc,
    )
    existing_world_id = connection.scalar(
        sa.select(worlds.c.id).where(worlds.c.slug == GLOBAL_SLUG)
    )
    if existing_world_id is None:
        connection.execute(
            worlds.insert().values(
                id=GLOBAL_WORLD_ID,
                slug=GLOBAL_SLUG,
                owner_user_id=owner_user_id,
                name=GLOBAL_NAME,
                tagline=GLOBAL_TAGLINE,
                setting_description=GLOBAL_SETTING_DESCRIPTION,
                daily_life_description=GLOBAL_DAILY_LIFE_DESCRIPTION,
                genre_tags=GLOBAL_GENRE_TAGS,
                tone_tags=GLOBAL_TONE_TAGS,
                banner_media_id=None,
                banner_alt_text="",
                timezone="Asia/Seoul",
                language="ko",
                visibility="public",
                join_policy="open",
                status="published",
                definition_version=1,
                row_version=1,
                contract_version=WORLD_CONTRACT_VERSION,
                contract_hash=GLOBAL_CONTRACT_HASH,
                readiness_status="publish_ready",
                additional_generation_guidance="",
                create_idempotency_key="p1-angmoo-global-foundation",
                created_at=backfill_at,
                updated_at=backfill_at,
            )
        )
    elif existing_world_id != GLOBAL_WORLD_ID:
        raise RuntimeError("angmoo-global slug is bound to an unexpected World ID")

    owner_ids = list(
        connection.scalars(
            sa.select(characters.c.owner_id)
            .join(users, users.c.id == characters.c.owner_id)
            .where(
                characters.c.deleted_at.is_(None),
                users.c.deleted_at.is_(None),
            )
            .distinct()
            .order_by(characters.c.owner_id)
        )
    )
    if owner_user_id not in owner_ids:
        owner_ids.insert(0, owner_user_id)

    membership_ids: dict[str, str] = {}
    for user_id in owner_ids:
        membership_id = connection.scalar(
            sa.select(memberships.c.id).where(
                memberships.c.world_id == GLOBAL_WORLD_ID,
                memberships.c.user_id == user_id,
            )
        )
        if membership_id is None:
            membership_id = _stable_uuid7("angmoo-global-membership", user_id)
            connection.execute(
                memberships.insert().values(
                    id=membership_id,
                    world_id=GLOBAL_WORLD_ID,
                    user_id=user_id,
                    role="owner" if user_id == owner_user_id else "member",
                    status="active",
                    requested_by_user_id=owner_user_id,
                    approved_by_user_id=owner_user_id,
                    joined_at=backfill_at,
                    reason="p1_angmoo_global_backfill",
                    created_at=backfill_at,
                    updated_at=backfill_at,
                )
            )
        membership_ids[user_id] = membership_id

    character_rows = connection.execute(
        sa.select(characters.c.id, characters.c.owner_id)
        .where(characters.c.deleted_at.is_(None))
        .order_by(characters.c.id)
    ).all()
    for character_id, character_owner_id in character_rows:
        exists = connection.scalar(
            sa.select(world_characters.c.id).where(
                world_characters.c.world_id == GLOBAL_WORLD_ID,
                world_characters.c.character_id == character_id,
            )
        )
        if exists is None:
            connection.execute(
                world_characters.insert().values(
                    id=_stable_uuid7(
                        "angmoo-global-world-character",
                        character_id,
                    ),
                    world_id=GLOBAL_WORLD_ID,
                    character_id=character_id,
                    membership_id=membership_ids[character_owner_id],
                    role_key=None,
                    status="inactive",
                    autonomous_enabled=False,
                    local_profile=None,
                    character_contract_hash=None,
                    world_contract_hash=GLOBAL_CONTRACT_HASH,
                    version=1,
                    created_at=backfill_at,
                    updated_at=backfill_at,
                )
            )


def downgrade() -> None:
    connection = op.get_bind()
    active_worlds = sa.table(
        "character_active_worlds",
        sa.column("world_character_id", sa.String()),
    )
    world_characters = sa.table(
        "world_characters",
        sa.column("id", sa.String()),
        sa.column("world_id", sa.String()),
    )
    memberships = sa.table(
        "world_memberships",
        sa.column("world_id", sa.String()),
    )
    supporting_tables = [
        sa.table(name, sa.column("world_id", sa.String()))
        for name in (
            "world_glossary_terms",
            "world_rules",
            "world_daypart_profiles",
            "world_roles",
            "world_places",
        )
    ]
    worlds = sa.table("worlds", sa.column("id", sa.String()))
    world_character_ids = sa.select(world_characters.c.id).where(
        world_characters.c.world_id == GLOBAL_WORLD_ID
    )
    connection.execute(
        active_worlds.delete().where(
            active_worlds.c.world_character_id.in_(world_character_ids)
        )
    )
    connection.execute(
        world_characters.delete().where(
            world_characters.c.world_id == GLOBAL_WORLD_ID
        )
    )
    for table in supporting_tables:
        connection.execute(table.delete().where(table.c.world_id == GLOBAL_WORLD_ID))
    connection.execute(
        memberships.delete().where(memberships.c.world_id == GLOBAL_WORLD_ID)
    )
    connection.execute(worlds.delete().where(worlds.c.id == GLOBAL_WORLD_ID))
