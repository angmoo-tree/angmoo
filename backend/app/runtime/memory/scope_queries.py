"""Read-only Memory scope composition in the caller's SQLAlchemy Session.

Queries read users, worlds and world_characters. The filters and three-query
order are preserved from Memory's original adapter. No independent Session,
commit, rollback, ownership decision or alternate authorization cache is added.
"""
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import Base
from app.domains.memory.contracts.scope import MemoryScope


def read_scope_presence(session: Session, scope: MemoryScope) -> tuple[str | None, str | None, str | None]:
    users = Base.metadata.tables["users"]
    worlds = Base.metadata.tables["worlds"]
    world_characters = Base.metadata.tables["world_characters"]
    owner_exists = session.scalar(
        select(users.c.id).where(
            users.c.id == scope.owner_id,
            users.c.deleted_at.is_(None),
        )
    )
    world_exists = session.scalar(
        select(worlds.c.id).where(
            worlds.c.id == scope.world_id,
            worlds.c.owner_user_id == scope.owner_id,
            worlds.c.archived_at.is_(None),
        )
    )
    subject_exists = session.scalar(
        select(world_characters.c.id).where(
            world_characters.c.id == scope.subject_world_character_id,
            world_characters.c.world_id == scope.world_id,
            world_characters.c.status == "active",
        )
    )
    return owner_exists, world_exists, subject_exists


def read_scope_timezone(session: Session, scope: MemoryScope) -> str | None:
    worlds = Base.metadata.tables["worlds"]
    zone = session.scalar(
        select(worlds.c.timezone).where(worlds.c.id == scope.world_id)
    )
    return zone


def read_due_batch_configs(session, *, consent, ready_source, now):
    """Read attached Memory config rows joined to World timezone in caller Session.

    Memory supplies its original consent/ready predicates. This join preserves
    the original scan ordering/cap without committing or deciding triggers.
    """
    from sqlalchemy import or_, select
    from app.domains.memory.models.batch import MemoryBatchSetting
    from app.domains.memory.models.items import MemoryScopeSettingModel
    worlds = Base.metadata.tables["worlds"]
    due_slot = (MemoryBatchSetting.schedule_enabled.is_(True)) & (
        MemoryBatchSetting.next_due_at <= now
    )
    configs = session.scalars(
        select(MemoryBatchSetting)
        .join(
            MemoryScopeSettingModel,
            MemoryScopeSettingModel.id == MemoryBatchSetting.scope_setting_id,
        )
        .join(worlds, worlds.c.id == MemoryScopeSettingModel.world_id)
        .where(
            consent,
            MemoryScopeSettingModel.enabled.is_(True),
            or_(
                due_slot,
                MemoryBatchSetting.timezone != worlds.c.timezone,
                ready_source & MemoryBatchSetting.trigger_kind.is_not(None),
            ),
        )
        .order_by(
            MemoryBatchSetting.last_claimed_at.asc().nullsfirst(),
            MemoryBatchSetting.scope_setting_id,
        )
        .limit(32)
    ).all()
    return configs
