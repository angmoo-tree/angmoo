"""Read-only Memory scope composition in the caller's SQLAlchemy Session.

Queries read users, worlds and world_characters. The filters and three-query
order are preserved from Memory's original adapter. No independent Session,
commit, rollback, ownership decision or alternate authorization cache is added.
"""
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import Base
from app.domains.memory.contracts.scope import MemoryScope
from app.runtime.subject_scope import read_scope_presence


def read_consolidation_binding(session, scope, credential_id=None, revision=None):
    from app.domains.identity.service.world_credentials import find, find_revision, validate_profile
    from app.domains.identity.exceptions import CredentialResolutionError
    from app.domains.memory.contracts.scope_references import ConsolidationBinding
    if any(value is None for value in read_scope_presence(session, scope)):
        return None
    row = find(session, owner_id=scope.owner_id, world_id=scope.world_id,
        world_character_id=scope.subject_world_character_id, purpose="consolidation")
    if credential_id is not None:
        try:
            row = find_revision(session, owner_id=scope.owner_id, world_id=scope.world_id,
                world_character_id=scope.subject_world_character_id, purpose="consolidation",
                credential_id=credential_id, revision=revision)
        except CredentialResolutionError:
            return None
    if row is None or not row.encrypted_secret:
        return None
    validate_profile("consolidation", row.provider, row.model, row.thinking_level)
    return ConsolidationBinding(getattr(row, "credential_id", None) or row.id, row.revision, row.model, row.thinking_level)


def read_scope_timezone(session: Session, scope: MemoryScope) -> str | None:
    from app.domains.identity.service.environment import snapshot
    return snapshot(session, scope.owner_id).timezone


def read_due_batch_configs(session, *, consent, ready_source, now):
    """Read attached Memory config rows joined to World timezone in caller Session.

    Memory supplies its original consent/ready predicates. This join preserves
    the original scan ordering/cap without committing or deciding triggers.
    """
    from sqlalchemy import or_, select
    from app.domains.memory.models.batch import MemoryBatchSetting
    from app.domains.memory.models.items import MemoryScopeSettingModel
    from app.domains.identity.service.environment import installation_snapshot
    zone = installation_snapshot(session).timezone
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
                MemoryBatchSetting.timezone != zone,
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
