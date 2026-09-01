"""SQLAlchemy adapter for opt-in memory scope control."""

from __future__ import annotations

from uuid import uuid4

from sqlalchemy import select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.db import Base
from app.domains.memory.domain.errors import (
    MemoryConflictError,
    MemoryScopeError,
)
from app.domains.memory.domain.provenance import MemoryProviderMode
from app.domains.memory.domain.retention import DEFAULT_MEMORY_RETENTION_DAYS
from app.domains.memory.domain.scope import MemoryScope, MemoryScopeSetting
from app.domains.memory.infrastructure.sqlalchemy_models import (
    MemoryScopeSettingModel,
)


class SqlAlchemyMemoryRepository:
    def __init__(self, session: Session) -> None:
        self._session = session

    def get_scope_setting(self, scope: MemoryScope) -> MemoryScopeSetting | None:
        row = self._find_scope(scope)
        return None if row is None else self._to_domain(row)

    def get_or_create_scope_setting(
        self,
        scope: MemoryScope,
    ) -> MemoryScopeSetting:
        self._validate_scope(scope)
        existing = self._find_scope(scope)
        if existing is not None:
            return self._to_domain(existing)
        row = MemoryScopeSettingModel(
            id=str(uuid4()),
            owner_id=scope.owner_id,
            world_id=scope.world_id,
            subject_world_character_id=scope.subject_world_character_id,
            enabled=False,
            retention_days=DEFAULT_MEMORY_RETENTION_DAYS,
            provider_mode=MemoryProviderMode.NONE.value,
            version=1,
        )
        try:
            with self._session.begin_nested():
                self._session.add(row)
                self._session.flush()
        except IntegrityError:
            existing = self._find_scope(scope)
            if existing is None:
                raise MemoryConflictError("memory_scope_create_conflict") from None
            return self._to_domain(existing)
        self._session.refresh(row)
        return self._to_domain(row)

    def update_scope_setting(
        self,
        scope: MemoryScope,
        *,
        expected_version: int,
        enabled: bool,
        retention_days: int,
        provider_mode: MemoryProviderMode,
    ) -> MemoryScopeSetting:
        self._validate_scope(scope)
        if expected_version < 1:
            raise MemoryConflictError("memory_scope_version_conflict")
        statement = (
            update(MemoryScopeSettingModel)
            .where(
                MemoryScopeSettingModel.owner_id == scope.owner_id,
                MemoryScopeSettingModel.world_id == scope.world_id,
                MemoryScopeSettingModel.subject_world_character_id
                == scope.subject_world_character_id,
                MemoryScopeSettingModel.version == expected_version,
            )
            .values(
                enabled=enabled,
                retention_days=retention_days,
                provider_mode=provider_mode.value,
                version=expected_version + 1,
            )
        )
        result = self._session.execute(statement)
        if result.rowcount != 1:
            raise MemoryConflictError("memory_scope_version_conflict")
        self._session.flush()
        updated = self._find_scope(scope, populate_existing=True)
        if updated is None:
            raise MemoryConflictError("memory_scope_update_missing")
        return self._to_domain(updated)

    def _find_scope(
        self,
        scope: MemoryScope,
        *,
        populate_existing: bool = False,
    ) -> MemoryScopeSettingModel | None:
        statement = select(MemoryScopeSettingModel).where(
            MemoryScopeSettingModel.owner_id == scope.owner_id,
            MemoryScopeSettingModel.world_id == scope.world_id,
            MemoryScopeSettingModel.subject_world_character_id
            == scope.subject_world_character_id,
        )
        if populate_existing:
            statement = statement.execution_options(populate_existing=True)
        return self._session.scalar(statement)

    def _validate_scope(self, scope: MemoryScope) -> None:
        users = Base.metadata.tables["users"]
        worlds = Base.metadata.tables["worlds"]
        world_characters = Base.metadata.tables["world_characters"]
        owner_exists = self._session.scalar(
            select(users.c.id).where(
                users.c.id == scope.owner_id,
                users.c.deleted_at.is_(None),
            )
        )
        world_exists = self._session.scalar(
            select(worlds.c.id).where(
                worlds.c.id == scope.world_id,
                worlds.c.owner_user_id == scope.owner_id,
                worlds.c.archived_at.is_(None),
            )
        )
        subject_exists = self._session.scalar(
            select(world_characters.c.id).where(
                world_characters.c.id == scope.subject_world_character_id,
                world_characters.c.world_id == scope.world_id,
                world_characters.c.status == "active",
            )
        )
        if owner_exists is None or world_exists is None or subject_exists is None:
            raise MemoryScopeError("memory_scope_invalid")

    @staticmethod
    def _to_domain(row: MemoryScopeSettingModel) -> MemoryScopeSetting:
        return MemoryScopeSetting(
            id=row.id,
            scope=MemoryScope(
                owner_id=row.owner_id,
                world_id=row.world_id,
                subject_world_character_id=row.subject_world_character_id,
            ),
            enabled=row.enabled,
            retention_days=row.retention_days,
            provider_mode=MemoryProviderMode(row.provider_mode),
            version=row.version,
            created_at=row.created_at,
            updated_at=row.updated_at,
        )


__all__ = ["SqlAlchemyMemoryRepository"]
