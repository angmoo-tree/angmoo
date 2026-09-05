"""Owner scope, consent, correction and item mutations with original transactions."""
from __future__ import annotations
from dataclasses import asdict
from datetime import UTC, datetime
from sqlalchemy.orm import Session

from app.domains.memory.contracts.management import MemoryWorkflows
from app.providers.registry import MESSAGE_GOOGLE_MODELS
from app.domains.memory.schemas import (
    MemoryCorrectionCreate,
    MemoryDeleteCreate,
    MemoryEvidenceRead,
    MemoryItemDetailRead,
    MemoryItemListRead,
    MemoryItemMutationRead,
    MemoryItemSummaryRead,
    MemoryPinUpdate,
    MemoryRelatedCharacterRead,
    MemoryScopeRead,
    MemorySettingMutationRead,
    MemorySettingRead,
    MemorySettingUpdate,
)
from app.domains.memory.exceptions import (
    MemoryConflictError,
    MemoryNotFoundError,
    MemoryScopeError,
    MemoryValidationError,
)
from app.domains.memory.contracts.provenance import MemoryProviderMode, MemorySourceTypeV1
from app.domains.memory.policies.retention import DEFAULT_MEMORY_RETENTION_DAYS
from app.domains.memory.contracts.scope import MemoryScope
from app.domains.memory.schemas.batch import (
    MemoryBatchRetry,
    MemoryBatchSettingRead,
    MemoryBatchSettingUpdate,
)
from app.domains.memory.service.presentation import (_scope_read, _setting_read, _item_summary, _evidence_read, _related_character, _canonical_href, _source_label)


def read_memory_batch_setting(
    *,
    scope: MemoryScope,
    db: Session,
    workflows: MemoryWorkflows,
) -> MemoryBatchSettingRead:
    try:
        value = workflows.batch_repository(db).settings(
            scope
        )
        return MemoryBatchSettingRead(
            **asdict(value),
            scope={"world_id": scope.world_id, "subject_world_character_id": scope.subject_world_character_id},
            available_models=list(MESSAGE_GOOGLE_MODELS),
        )
    except Exception as exc:
        raise



def update_memory_batch_setting(
    *,
    scope: MemoryScope,
    db: Session,
    workflows: MemoryWorkflows,
    data: MemoryBatchSettingUpdate,
) -> MemoryBatchSettingRead:
    try:
        repository = workflows.batch_repository(db)
        repository.memory.validate_scope(scope)
        if data.model_id is not None and data.model_id not in MESSAGE_GOOGLE_MODELS:
            raise MemoryValidationError("memory_selection_model_invalid")
        if data.ai_enabled:
            # Readiness/credential resolution only: never generates on Save.
            workflows.validate_provider(db, scope.owner_id, data.model_id or "")
        value = repository.save_settings(
            scope, **data.model_dump(), now=datetime.now(UTC)
        )
        db.commit()
        return MemoryBatchSettingRead(
            **asdict(value),
            scope={"world_id": scope.world_id, "subject_world_character_id": scope.subject_world_character_id},
            available_models=list(MESSAGE_GOOGLE_MODELS),
        )
    except Exception as exc:
        db.rollback()
        raise



def retry_memory_batch(
    *,
    scope: MemoryScope,
    db: Session,
    workflows: MemoryWorkflows,
    data: MemoryBatchRetry,
) -> MemoryBatchSettingRead:
    try:
        repository = workflows.batch_repository(db)
        repository.memory.validate_scope(scope)
        repository.retry_failed(
            scope, idempotency_key=data.idempotency_key, now=datetime.now(UTC)
        )
        db.commit()
        return MemoryBatchSettingRead(
            **asdict(repository.settings(scope)),
            scope={"world_id": scope.world_id, "subject_world_character_id": scope.subject_world_character_id},
            available_models=list(MESSAGE_GOOGLE_MODELS),
        )
    except Exception as exc:
        db.rollback()
        raise



def read_memory_setting(
    *,
    scope: MemoryScope,
    db: Session,
    workflows: MemoryWorkflows,
) -> MemorySettingRead:
    try:
        setting = workflows.read_service(db).setting(scope)
    except (MemoryScopeError, MemoryValidationError) as exc:
        raise
    return MemorySettingRead(
        scope=_scope_read(scope),
        configured=setting is not None,
        enabled=False if setting is None else setting.enabled,
        retention_days=(
            DEFAULT_MEMORY_RETENTION_DAYS if setting is None else setting.retention_days
        ),
        provider_mode=(
            MemoryProviderMode.NONE.value
            if setting is None
            else setting.provider_mode.value
        ),
        version=0 if setting is None else setting.version,
    )



def update_memory_setting(
    *,
    scope: MemoryScope,
    db: Session,
    workflows: MemoryWorkflows,
    data: MemorySettingUpdate,
) -> MemorySettingMutationRead:
    try:
        setting, changed = workflows.scope_service(db).set_enabled(
            scope,
            expected_version=data.expected_version,
            enabled=data.enabled,
            idempotency_key=data.idempotency_key,
        )
        db.commit()
    except Exception as exc:
        db.rollback()
        raise
    return MemorySettingMutationRead(
        outcome="updated" if changed else "reused",
        setting=_setting_read(scope, setting),
    )



def list_memory_items(
    *,
    scope: MemoryScope,
    db: Session,
    workflows: MemoryWorkflows,
    cursor: str | None = None,
    limit: int = 20,
) -> MemoryItemListRead:
    service = workflows.read_service(db)
    try:
        setting = service.setting(scope)
        page = service.list_items(scope, cursor=cursor, limit=limit)
    except (MemoryNotFoundError, MemoryScopeError, MemoryValidationError) as exc:
        raise
    retention_days = (
        DEFAULT_MEMORY_RETENTION_DAYS if setting is None else setting.retention_days
    )
    character_names = workflows.character_names(db, scope)
    now = datetime.now(UTC)
    return MemoryItemListRead(
        scope=_scope_read(scope),
        memory_enabled=False if setting is None else setting.enabled,
        items=[
            _item_summary(
                item,
                scope=scope,
                character_names=character_names,
                retention_days=retention_days,
                now=now,
            )
            for item in page.items
        ],
        next_cursor=page.next_cursor,
    )



def read_memory_item(
    *,
    scope: MemoryScope,
    db: Session,
    workflows: MemoryWorkflows,
    memory_id: str,
) -> MemoryItemDetailRead:
    service = workflows.read_service(db)
    try:
        setting = service.setting(scope)
        detail = service.detail(scope, item_id=memory_id)
    except (MemoryNotFoundError, MemoryScopeError, MemoryValidationError) as exc:
        raise
    retention_days = (
        DEFAULT_MEMORY_RETENTION_DAYS if setting is None else setting.retention_days
    )
    character_names = workflows.character_names(db, scope)
    summary = _item_summary(
        detail.item,
        scope=scope,
        character_names=character_names,
        retention_days=retention_days,
        now=datetime.now(UTC),
    )
    evidence = [
        _evidence_read(scope, row, character_names=character_names)
        for row in detail.evidence
    ]
    available_count = sum(row.availability == "available" for row in evidence)
    return MemoryItemDetailRead(
        **summary.model_dump(),
        scope=_scope_read(scope),
        evidence=evidence,
        provenance_summary=(
            f"현재 확인 가능한 근거 {available_count}개 / 전체 {len(evidence)}개"
        ),
    )



def update_memory_pin(
    *,
    scope: MemoryScope,
    db: Session,
    workflows: MemoryWorkflows,
    memory_id: str,
    data: MemoryPinUpdate,
) -> MemoryItemMutationRead:
    try:
        result = workflows.write_service(db).set_pin(
            scope=scope,
            item_id=memory_id,
            expected_version=data.expected_version,
            pinned=data.pinned,
            idempotency_key=data.idempotency_key,
        )
        setting = workflows.scope_service(db).get_or_create(scope)
        assert result.item is not None
        summary = _item_summary(
            result.item,
            scope=scope,
            character_names=workflows.character_names(db, scope),
            retention_days=setting.retention_days,
            now=datetime.now(UTC),
        )
        db.commit()
    except Exception as exc:
        db.rollback()
        raise
    return MemoryItemMutationRead(
        operation="pin" if data.pinned else "unpin",
        outcome=result.outcome.value,
        scope=_scope_read(scope),
        item=summary,
    )



def correct_memory_item(
    *,
    scope: MemoryScope,
    db: Session,
    workflows: MemoryWorkflows,
    memory_id: str,
    data: MemoryCorrectionCreate,
) -> MemoryItemMutationRead:
    try:
        result = workflows.write_service(db).correct_summary(
            scope=scope,
            old_item_id=memory_id,
            expected_item_version=data.expected_item_version,
            expected_scope_version=data.expected_scope_version,
            summary=data.summary,
            idempotency_key=data.idempotency_key,
        )
        setting = workflows.scope_service(db).get_or_create(scope)
        assert result.item is not None
        summary = _item_summary(
            result.item,
            scope=scope,
            character_names=workflows.character_names(db, scope),
            retention_days=setting.retention_days,
            now=datetime.now(UTC),
        )
        db.commit()
    except Exception as exc:
        db.rollback()
        raise
    return MemoryItemMutationRead(
        operation="correct",
        outcome=result.outcome.value,
        scope=_scope_read(scope),
        item=summary,
        replaced_memory_id=memory_id,
    )



def delete_memory_item(
    *,
    scope: MemoryScope,
    db: Session,
    workflows: MemoryWorkflows,
    memory_id: str,
    data: MemoryDeleteCreate,
) -> MemoryItemMutationRead:
    try:
        result = workflows.write_service(db).delete_item(
            scope=scope,
            item_id=memory_id,
            expected_version=data.expected_version,
            idempotency_key=data.idempotency_key,
        )
        setting = workflows.scope_service(db).get_or_create(scope)
        assert result.item is not None
        summary = _item_summary(
            result.item,
            scope=scope,
            character_names=workflows.character_names(db, scope),
            retention_days=setting.retention_days,
            now=datetime.now(UTC),
        )
        db.commit()
    except Exception as exc:
        db.rollback()
        raise
    return MemoryItemMutationRead(
        operation="delete",
        outcome=result.outcome.value,
        scope=_scope_read(scope),
        item=summary,
    )
