"""SQLAlchemy persistence for bounded consolidation and derived hot briefs."""

from __future__ import annotations

from datetime import datetime
from uuid import uuid4

from sqlalchemy import func, or_, select, update
from sqlalchemy.orm import Session

from app.domains.memory.contracts.scope_references import MemoryScopeReferences

from app.domains.memory.policies.consolidation import (
    MAX_HOT_BRIEF_SOURCE_ITEMS,
    MAX_HOT_BRIEF_SUMMARY_LENGTH,
    MEMORY_HOT_BRIEF_CONTRACT_VERSION,
    MemoryHotBriefRecord,
    MemoryMaintenanceSnapshot,
    memory_item_high_watermark,
    memory_item_set_digest,
)
from app.domains.memory.exceptions import (
    MemoryConflictError,
    MemoryNotFoundError,
)
from app.domains.memory.contracts.items import MemoryItemRecord, as_utc
from app.domains.memory.contracts.provenance import (
    MemoryCandidateStatus,
    MemoryHotBriefStatus,
    MemoryItemStatus,
)
from app.domains.memory.contracts.scope import MemoryScopeSetting
from app.domains.memory.repository.items import SqlAlchemyMemoryRepository
from app.domains.memory.models.items import (
    MemoryCandidate,
    MemoryHotBrief,
    MemoryHotBriefItem,
    MemoryItem,
    MemoryScopeSettingModel,
)


class SqlAlchemyMemoryConsolidationRepository(SqlAlchemyMemoryRepository):
    """One canonical adapter that also satisfies the existing write port."""

    def __init__(self, session: Session, *, references: MemoryScopeReferences, source_reader=None) -> None:
        super().__init__(session, references=references)
        self._session = session
        self._source_reader = source_reader

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
        self._require_setting(setting, for_update=self._session.get_bind().dialect.name != 'postgresql')
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
        postgres = self._session.get_bind().dialect.name == 'postgresql'
        self._require_setting(setting, for_update=not postgres)
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
                for_update=not postgres,
            )
        )
        if postgres:
            # Expensive provenance validation above remains in this SERIALIZABLE
            # transaction, but does not hold the scope's exclusive writer.
            # Publish under a real MVCC fence: canonical writers also read this
            # scope, so an intervening insert (including an unselected phantom)
            # and this publication form an SSI conflict instead of a lost dirty
            # flag. A plain late SELECT FOR UPDATE would not establish it.
            self._session.execute(update(MemoryScopeSettingModel).where(
                MemoryScopeSettingModel.id == setting.id).values(
                    updated_at=MemoryScopeSettingModel.updated_at)
                .execution_options(memory_scope_lock_only=True))
            self._require_setting(setting)
            identifiers = tuple(item.id for item in current_items)
            locked = tuple(self._session.scalars(select(MemoryItem).where(
                MemoryItem.id.in_(identifiers)).with_for_update()
                .execution_options(populate_existing=True))) if identifiers else ()
            if sorted((row.id, row.version) for row in locked) != sorted(
                (item.id, item.version) for item in current_items):
                raise MemoryConflictError('memory_hot_brief_source_version_conflict')
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
        )
        if for_update:
            statement = statement.with_for_update().execution_options(
                populate_existing=True
            )
        from app.domains.memory.models.episode import MemoryEpisodeInfo
        from app.domains.memory.contracts.activity_batch import ACTIVITY_POLICY_VERSION
        from app.domains.memory.repository.episode_privacy import currently_accessible
        from app.domains.memory.contracts.access_validation import MemoryAccessValidation
        from app.domains.memory.repository.access_batch import prepare_access
        # All roots belong to this one synchronous read. Shared ancestors must
        # not be expanded again for each item. A subsequent read/write fence
        # creates a new context and rechecks permissions and versions.
        validation = MemoryAccessValidation(self._session, now)
        result, offset = [], 0
        while len(result) < limit:
            page = tuple(self._session.scalars(statement.offset(offset).limit(100)))
            if not page:
                break
            offset += len(page)
            prepare_access(self._session, page, now, reader=self._source_reader, validation=validation)
            for item in page:
                if not currently_accessible(self._session, self._source_reader, setting.scope, item, now, validation=validation):
                    continue
                result.append(item)
                if len(result) == limit:
                    break
        return tuple(result)

    @staticmethod
    def _active_item_predicates(
        setting: MemoryScopeSetting,
        *,
        now: datetime,
    ):
        from app.domains.memory.repository.capacity import current_item_predicates
        return current_item_predicates(setting.scope, now=now)

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
