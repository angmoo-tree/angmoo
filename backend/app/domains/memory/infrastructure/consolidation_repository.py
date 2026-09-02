"""SQLAlchemy persistence for bounded consolidation and derived hot briefs."""

from __future__ import annotations

from datetime import datetime
from uuid import uuid4

from sqlalchemy import func, or_, select, update
from sqlalchemy.orm import Session

from app.domains.memory.domain.consolidation import (
    MAX_HOT_BRIEF_SOURCE_ITEMS,
    MAX_HOT_BRIEF_SUMMARY_LENGTH,
    MEMORY_HOT_BRIEF_CONTRACT_VERSION,
    MemoryHotBriefRecord,
    MemoryMaintenanceSnapshot,
    memory_item_high_watermark,
    memory_item_set_digest,
)
from app.domains.memory.domain.errors import (
    MemoryConflictError,
    MemoryNotFoundError,
)
from app.domains.memory.domain.lifecycle import MemoryItemRecord, as_utc
from app.domains.memory.domain.provenance import (
    MemoryCandidateStatus,
    MemoryHotBriefStatus,
    MemoryItemStatus,
)
from app.domains.memory.domain.scope import MemoryScopeSetting
from app.domains.memory.infrastructure.repository import SqlAlchemyMemoryRepository
from app.domains.memory.infrastructure.sqlalchemy_models import (
    MemoryCandidate,
    MemoryHotBrief,
    MemoryHotBriefItem,
    MemoryItem,
    MemoryScopeSettingModel,
)


class SqlAlchemyMemoryConsolidationRepository(SqlAlchemyMemoryRepository):
    """One canonical adapter that also satisfies the existing write port."""

    def __init__(self, session: Session) -> None:
        super().__init__(session)
        self._session = session

    def get_scope_setting_by_id(
        self,
        scope_setting_id: str,
    ) -> MemoryScopeSetting | None:
        row = self._session.scalar(
            select(MemoryScopeSettingModel).where(
                MemoryScopeSettingModel.id == scope_setting_id
            )
        )
        return None if row is None else self._to_scope(row)

    def maintenance_snapshot(
        self,
        *,
        scope_setting_id: str,
        now: datetime,
        candidate_limit: int,
    ) -> MemoryMaintenanceSnapshot:
        if candidate_limit < 1 or candidate_limit > 100:
            raise MemoryConflictError("memory_candidate_batch_limit_invalid")
        setting = self.get_scope_setting_by_id(scope_setting_id)
        if setting is None:
            raise MemoryNotFoundError("memory_scope_not_found")

        pending_predicates = (
            MemoryCandidate.scope_setting_id == scope_setting_id,
            MemoryCandidate.status == MemoryCandidateStatus.PENDING.value,
        )
        pending_count = int(
            self._session.scalar(
                select(func.count(MemoryCandidate.id)).where(*pending_predicates)
            )
            or 0
        )
        pending_rows = tuple(
            self._session.scalars(
                select(MemoryCandidate)
                .where(*pending_predicates)
                .order_by(MemoryCandidate.created_at, MemoryCandidate.id)
                .limit(candidate_limit)
            )
        )
        active_count = int(
            self._session.scalar(
                select(func.count(MemoryItem.id)).where(
                    *self._active_item_predicates(setting, now=now)
                )
            )
            or 0
        )
        latest_brief_at = self._session.scalar(
            select(func.max(MemoryHotBrief.generated_at)).where(
                MemoryHotBrief.scope_setting_id == scope_setting_id
            )
        )
        high_watermark = None
        if pending_rows:
            latest = max(
                pending_rows,
                key=lambda row: (as_utc(row.created_at), row.id),
            )
            high_watermark = f"{as_utc(latest.created_at).isoformat()}|{latest.id}"

        return MemoryMaintenanceSnapshot(
            setting=setting,
            pending_candidates=tuple(self._to_candidate(row) for row in pending_rows),
            pending_count=pending_count,
            active_item_count=active_count,
            pending_high_watermark=high_watermark,
            last_consolidated_at=(
                None if latest_brief_at is None else as_utc(latest_brief_at)
            ),
            active_hot_brief_valid=self._active_hot_brief_valid(
                setting=setting,
                now=now,
            ),
        )

    def hot_brief_source_items(
        self,
        *,
        setting: MemoryScopeSetting,
        now: datetime,
        limit: int,
    ) -> tuple[MemoryItemRecord, ...]:
        if limit < 1 or limit > MAX_HOT_BRIEF_SOURCE_ITEMS:
            raise MemoryConflictError("memory_hot_brief_limit_invalid")
        self._require_setting(setting)
        rows = self._hot_brief_rows(setting=setting, now=now, limit=limit)
        return tuple(self._to_item(row) for row in rows)

    def replace_hot_brief(
        self,
        *,
        setting: MemoryScopeSetting,
        expected_source_items: tuple[MemoryItemRecord, ...],
        summary: str,
        contract_version: str,
        now: datetime,
    ) -> MemoryHotBriefRecord:
        self._require_setting(setting)
        normalized_summary = summary.strip()
        if not normalized_summary or len(normalized_summary) > MAX_HOT_BRIEF_SUMMARY_LENGTH:
            raise MemoryConflictError("memory_hot_brief_summary_invalid")
        normalized_contract = contract_version.strip()
        if not normalized_contract or len(normalized_contract) > 40:
            raise MemoryConflictError("memory_hot_brief_contract_invalid")
        current_items = tuple(
            self._to_item(row)
            for row in self._hot_brief_rows(
                setting=setting,
                now=now,
                limit=MAX_HOT_BRIEF_SOURCE_ITEMS,
                for_update=True,
            )
        )
        expected_refs = tuple((item.id, item.version) for item in expected_source_items)
        current_refs = tuple((item.id, item.version) for item in current_items)
        if expected_refs != current_refs:
            raise MemoryConflictError("memory_hot_brief_source_version_conflict")

        source_digest = memory_item_set_digest(current_items)
        high_watermark = memory_item_high_watermark(current_items)
        active = self._session.scalar(
            select(MemoryHotBrief)
            .where(
                MemoryHotBrief.scope_setting_id == setting.id,
                MemoryHotBrief.status == MemoryHotBriefStatus.ACTIVE.value,
            )
            .order_by(MemoryHotBrief.generation.desc())
            .with_for_update()
            .execution_options(populate_existing=True)
        )
        if active is not None and self._brief_matches(
            active,
            source_refs=current_refs,
            summary=normalized_summary,
            source_digest=source_digest,
            high_watermark=high_watermark,
            contract_version=normalized_contract,
        ):
            return self._to_hot_brief(active)

        generation = int(
            self._session.scalar(
                select(func.max(MemoryHotBrief.generation)).where(
                    MemoryHotBrief.scope_setting_id == setting.id
                )
            )
            or 0
        ) + 1
        row = MemoryHotBrief(
            id=str(uuid4()),
            scope_setting_id=setting.id,
            summary=normalized_summary,
            generation=generation,
            source_item_high_watermark=high_watermark,
            source_item_set_digest=source_digest,
            contract_version=normalized_contract,
            status=MemoryHotBriefStatus.ACTIVE.value,
            generated_at=now,
        )
        with self._session.begin_nested():
            self._session.execute(
                update(MemoryHotBrief)
                .where(
                    MemoryHotBrief.scope_setting_id == setting.id,
                    MemoryHotBrief.status == MemoryHotBriefStatus.ACTIVE.value,
                )
                .values(
                    status=MemoryHotBriefStatus.SUPERSEDED.value,
                    superseded_at=now,
                )
            )
            self._session.add(row)
            self._session.flush()
            self._session.add_all(
                MemoryHotBriefItem(
                    brief_id=row.id,
                    memory_item_id=item.id,
                    memory_item_version=item.version,
                )
                for item in current_items
            )
            self._session.flush()
        return self._to_hot_brief(row)

    def _active_hot_brief_valid(
        self,
        *,
        setting: MemoryScopeSetting,
        now: datetime,
    ) -> bool:
        if not setting.enabled:
            return False
        active = self._session.scalar(
            select(MemoryHotBrief)
            .where(
                MemoryHotBrief.scope_setting_id == setting.id,
                MemoryHotBrief.status == MemoryHotBriefStatus.ACTIVE.value,
            )
            .order_by(MemoryHotBrief.generation.desc())
        )
        if active is None:
            return False
        items = tuple(
            self._to_item(row)
            for row in self._hot_brief_rows(
                setting=setting,
                now=now,
                limit=MAX_HOT_BRIEF_SOURCE_ITEMS,
            )
        )
        return self._brief_matches(
            active,
            source_refs=tuple((item.id, item.version) for item in items),
            summary=active.summary,
            source_digest=memory_item_set_digest(items),
            high_watermark=memory_item_high_watermark(items),
            contract_version=MEMORY_HOT_BRIEF_CONTRACT_VERSION,
        )

    def _brief_matches(
        self,
        row: MemoryHotBrief,
        *,
        source_refs: tuple[tuple[str, int], ...],
        summary: str,
        source_digest: str,
        high_watermark: str,
        contract_version: str,
    ) -> bool:
        stored_refs = tuple(
            self._session.execute(
                select(
                    MemoryHotBriefItem.memory_item_id,
                    MemoryHotBriefItem.memory_item_version,
                )
                .where(MemoryHotBriefItem.brief_id == row.id)
                .order_by(MemoryHotBriefItem.memory_item_id)
            )
        )
        return (
            row.summary == summary
            and row.source_item_set_digest == source_digest
            and row.source_item_high_watermark == high_watermark
            and row.contract_version == contract_version
            and sorted(stored_refs) == sorted(source_refs)
        )

    def _hot_brief_rows(
        self,
        *,
        setting: MemoryScopeSetting,
        now: datetime,
        limit: int,
        for_update: bool = False,
    ) -> tuple[MemoryItem, ...]:
        statement = (
            select(MemoryItem)
            .where(*self._active_item_predicates(setting, now=now))
            .order_by(
                MemoryItem.pinned_at.is_not(None).desc(),
                MemoryItem.salience.desc(),
                MemoryItem.updated_at.desc(),
                MemoryItem.id,
            )
            .limit(limit)
        )
        if for_update:
            statement = statement.with_for_update().execution_options(
                populate_existing=True
            )
        return tuple(self._session.scalars(statement))

    @staticmethod
    def _active_item_predicates(
        setting: MemoryScopeSetting,
        *,
        now: datetime,
    ):
        scope = setting.scope
        return (
            MemoryItem.owner_id == scope.owner_id,
            MemoryItem.world_id == scope.world_id,
            MemoryItem.subject_world_character_id == scope.subject_world_character_id,
            MemoryItem.status == MemoryItemStatus.ACTIVE.value,
            or_(
                MemoryItem.pinned_at.is_not(None),
                MemoryItem.valid_until.is_(None),
                MemoryItem.valid_until > now,
            ),
        )

    def _to_hot_brief(self, row: MemoryHotBrief) -> MemoryHotBriefRecord:
        refs = tuple(
            self._session.execute(
                select(
                    MemoryHotBriefItem.memory_item_id,
                    MemoryHotBriefItem.memory_item_version,
                )
                .where(MemoryHotBriefItem.brief_id == row.id)
                .order_by(MemoryHotBriefItem.memory_item_id)
            )
        )
        return MemoryHotBriefRecord(
            id=row.id,
            scope_setting_id=row.scope_setting_id,
            summary=row.summary,
            generation=row.generation,
            source_item_high_watermark=row.source_item_high_watermark,
            source_item_set_digest=row.source_item_set_digest,
            contract_version=row.contract_version,
            generated_at=as_utc(row.generated_at),
            source_items=refs,
        )


__all__ = ["SqlAlchemyMemoryConsolidationRepository"]
