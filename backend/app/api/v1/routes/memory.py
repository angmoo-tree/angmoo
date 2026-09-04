"""Canonical owner-only Memory list, detail, and provenance routes.

Concrete persistence and source readers are composed at the outer HTTP layer;
the Memory domain itself remains independent from runtime adapters.
"""

from __future__ import annotations

from datetime import UTC, datetime
from dataclasses import asdict

from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from sqlalchemy.orm import Session

from app.api.v1.deps import get_current_user, get_db
from app.core import browser_session
from app.domains.identity.public import User
from app.domains.memory.api.schemas import (
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
from app.domains.memory.application.read_surface import (
    MemoryReadService,
    memory_lifecycle,
)
from app.domains.memory.application.scope_control import MemoryScopeService
from app.domains.memory.application.write_lifecycle import (
    MemoryWriteLifecycleService,
)
from app.domains.memory.domain.errors import (
    MemoryConflictError,
    MemoryNotFoundError,
    MemoryScopeError,
    MemoryValidationError,
)
from app.domains.memory.domain.provenance import MemoryProviderMode, MemorySourceTypeV1
from app.domains.memory.domain.retention import DEFAULT_MEMORY_RETENTION_DAYS
from app.domains.memory.domain.scope import MemoryScope
from app.domains.memory.infrastructure.repository import SqlAlchemyMemoryRepository
from app.domains.world_characters.public import (
    SqlAlchemyWorldCharacterPublicProfileReader,
)
from app.runtime.memory.sqlalchemy_source_reader import (
    SqlAlchemyMemorySourceEvidenceReader,
)
from app.domains.memory.api.batch_schemas import (
    MemoryBatchRetry,
    MemoryBatchSettingRead,
    MemoryBatchSettingUpdate,
)
from app.domains.memory.infrastructure.batch_repository import (
    SqlAlchemyMemoryBatchRepository,
)
from app.providers.registry import MESSAGE_GOOGLE_MODELS
from app.runtime.memory_selection_provider import memory_provider


router = APIRouter(
    prefix="/worlds/{world_id}/world-characters/{subject_id}",
    tags=["memory"],
)


def _service(db: Session) -> MemoryReadService:
    return MemoryReadService(
        SqlAlchemyMemoryRepository(db),
        SqlAlchemyMemorySourceEvidenceReader(db),
    )


@router.get("/memory/batch-settings", response_model=MemoryBatchSettingRead)
def read_memory_batch_setting(
    world_id: str,
    subject_id: str,
    request: Request,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> MemoryBatchSettingRead:
    browser_session.require_local_frontend_request(request, mutation=False)
    try:
        value = SqlAlchemyMemoryBatchRepository(db).settings(
            _scope(user, world_id, subject_id)
        )
        return MemoryBatchSettingRead(
            **asdict(value),
            scope={"world_id": world_id, "subject_world_character_id": subject_id},
            available_models=list(MESSAGE_GOOGLE_MODELS),
        )
    except Exception as exc:
        _raise_memory_read_error(exc)
        raise AssertionError("unreachable")


@router.put("/memory/batch-settings", response_model=MemoryBatchSettingRead)
def update_memory_batch_setting(
    world_id: str,
    subject_id: str,
    data: MemoryBatchSettingUpdate,
    request: Request,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> MemoryBatchSettingRead:
    browser_session.require_local_frontend_request(request, mutation=True)
    scope = _scope(user, world_id, subject_id)
    try:
        repository = SqlAlchemyMemoryBatchRepository(db)
        repository.memory.validate_scope(scope)
        if data.model_id is not None and data.model_id not in MESSAGE_GOOGLE_MODELS:
            raise MemoryValidationError("memory_selection_model_invalid")
        if data.ai_enabled:
            from contextlib import nullcontext

            # Readiness/credential resolution only: never generates on Save.
            memory_provider(lambda: nullcontext(db), user.id, data.model_id or "")
        value = repository.save_settings(
            scope, **data.model_dump(), now=datetime.now(UTC)
        )
        db.commit()
        return MemoryBatchSettingRead(
            **asdict(value),
            scope={"world_id": world_id, "subject_world_character_id": subject_id},
            available_models=list(MESSAGE_GOOGLE_MODELS),
        )
    except Exception as exc:
        db.rollback()
        _raise_memory_mutation_error(exc)
        raise AssertionError("unreachable")


def _scope_service(db: Session) -> MemoryScopeService:
    return MemoryScopeService(SqlAlchemyMemoryRepository(db))


@router.post("/memory/batch-retry", response_model=MemoryBatchSettingRead)
def retry_memory_batch(
    world_id: str,
    subject_id: str,
    data: MemoryBatchRetry,
    request: Request,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> MemoryBatchSettingRead:
    browser_session.require_local_frontend_request(request, mutation=True)
    scope = _scope(user, world_id, subject_id)
    try:
        repository = SqlAlchemyMemoryBatchRepository(db)
        repository.memory.validate_scope(scope)
        repository.retry_failed(
            scope, idempotency_key=data.idempotency_key, now=datetime.now(UTC)
        )
        db.commit()
        return MemoryBatchSettingRead(
            **asdict(repository.settings(scope)),
            scope={"world_id": world_id, "subject_world_character_id": subject_id},
            available_models=list(MESSAGE_GOOGLE_MODELS),
        )
    except Exception as exc:
        db.rollback()
        _raise_memory_mutation_error(exc)
        raise AssertionError("unreachable")


def _write_service(db: Session) -> MemoryWriteLifecycleService:
    return MemoryWriteLifecycleService(
        SqlAlchemyMemoryRepository(db),
        SqlAlchemyMemorySourceEvidenceReader(db),
    )


def _scope(user: User, world_id: str, subject_id: str) -> MemoryScope:
    return MemoryScope(
        owner_id=user.id,
        world_id=world_id,
        subject_world_character_id=subject_id,
    )


def _raise_memory_read_error(exc: Exception) -> None:
    if isinstance(exc, MemoryNotFoundError):
        code = status.HTTP_404_NOT_FOUND
    elif isinstance(exc, MemoryScopeError):
        # The URL never accepts an owner id.  Invalid owner/World/subject
        # combinations are therefore indistinguishable from missing resources.
        code = status.HTTP_404_NOT_FOUND
    elif isinstance(exc, MemoryValidationError):
        code = status.HTTP_422_UNPROCESSABLE_ENTITY
    else:
        code = status.HTTP_503_SERVICE_UNAVAILABLE
    detail = (
        "memory_service_unavailable"
        if code == status.HTTP_503_SERVICE_UNAVAILABLE
        else str(exc)
    )
    raise HTTPException(status_code=code, detail=detail) from None


def _raise_memory_mutation_error(exc: Exception) -> None:
    if isinstance(exc, MemoryNotFoundError):
        code = status.HTTP_404_NOT_FOUND
    elif isinstance(exc, MemoryScopeError):
        code = status.HTTP_404_NOT_FOUND
    elif isinstance(exc, MemoryConflictError):
        code = status.HTTP_409_CONFLICT
    elif isinstance(exc, MemoryValidationError):
        code = status.HTTP_422_UNPROCESSABLE_ENTITY
    else:
        code = status.HTTP_503_SERVICE_UNAVAILABLE
    detail = (
        "memory_service_unavailable"
        if code == status.HTTP_503_SERVICE_UNAVAILABLE
        else str(exc)
    )
    raise HTTPException(status_code=code, detail=detail) from None


@router.get("/memory/settings", response_model=MemorySettingRead)
def read_memory_setting(
    world_id: str,
    subject_id: str,
    request: Request,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> MemorySettingRead:
    browser_session.require_local_frontend_request(request, mutation=False)
    scope = _scope(user, world_id, subject_id)
    try:
        setting = _service(db).setting(scope)
    except (MemoryScopeError, MemoryValidationError) as exc:
        _raise_memory_read_error(exc)
        raise AssertionError("unreachable")
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


@router.put("/memory/settings", response_model=MemorySettingMutationRead)
def update_memory_setting(
    world_id: str,
    subject_id: str,
    data: MemorySettingUpdate,
    request: Request,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> MemorySettingMutationRead:
    browser_session.require_local_frontend_request(request, mutation=True)
    scope = _scope(user, world_id, subject_id)
    try:
        setting, changed = _scope_service(db).set_enabled(
            scope,
            expected_version=data.expected_version,
            enabled=data.enabled,
            idempotency_key=data.idempotency_key,
        )
        db.commit()
    except Exception as exc:
        db.rollback()
        _raise_memory_mutation_error(exc)
        raise AssertionError("unreachable")
    return MemorySettingMutationRead(
        outcome="updated" if changed else "reused",
        setting=_setting_read(scope, setting),
    )


@router.get("/memories", response_model=MemoryItemListRead)
def list_memory_items(
    world_id: str,
    subject_id: str,
    request: Request,
    cursor: str | None = Query(default=None, max_length=64),
    limit: int = Query(default=20, ge=1, le=50),
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> MemoryItemListRead:
    browser_session.require_local_frontend_request(request, mutation=False)
    scope = _scope(user, world_id, subject_id)
    service = _service(db)
    try:
        setting = service.setting(scope)
        page = service.list_items(scope, cursor=cursor, limit=limit)
    except (MemoryNotFoundError, MemoryScopeError, MemoryValidationError) as exc:
        _raise_memory_read_error(exc)
        raise AssertionError("unreachable")
    retention_days = (
        DEFAULT_MEMORY_RETENTION_DAYS if setting is None else setting.retention_days
    )
    character_names = _character_names(db, scope)
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


@router.get("/memories/{memory_id}", response_model=MemoryItemDetailRead)
def read_memory_item(
    world_id: str,
    subject_id: str,
    memory_id: str,
    request: Request,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> MemoryItemDetailRead:
    browser_session.require_local_frontend_request(request, mutation=False)
    scope = _scope(user, world_id, subject_id)
    service = _service(db)
    try:
        setting = service.setting(scope)
        detail = service.detail(scope, item_id=memory_id)
    except (MemoryNotFoundError, MemoryScopeError, MemoryValidationError) as exc:
        _raise_memory_read_error(exc)
        raise AssertionError("unreachable")
    retention_days = (
        DEFAULT_MEMORY_RETENTION_DAYS if setting is None else setting.retention_days
    )
    character_names = _character_names(db, scope)
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


@router.put("/memories/{memory_id}/pin", response_model=MemoryItemMutationRead)
def update_memory_pin(
    world_id: str,
    subject_id: str,
    memory_id: str,
    data: MemoryPinUpdate,
    request: Request,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> MemoryItemMutationRead:
    browser_session.require_local_frontend_request(request, mutation=True)
    scope = _scope(user, world_id, subject_id)
    try:
        result = _write_service(db).set_pin(
            scope=scope,
            item_id=memory_id,
            expected_version=data.expected_version,
            pinned=data.pinned,
            idempotency_key=data.idempotency_key,
        )
        setting = _scope_service(db).get_or_create(scope)
        assert result.item is not None
        summary = _item_summary(
            result.item,
            scope=scope,
            character_names=_character_names(db, scope),
            retention_days=setting.retention_days,
            now=datetime.now(UTC),
        )
        db.commit()
    except Exception as exc:
        db.rollback()
        _raise_memory_mutation_error(exc)
        raise AssertionError("unreachable")
    return MemoryItemMutationRead(
        operation="pin" if data.pinned else "unpin",
        outcome=result.outcome.value,
        scope=_scope_read(scope),
        item=summary,
    )


@router.post(
    "/memories/{memory_id}/corrections",
    response_model=MemoryItemMutationRead,
)
def correct_memory_item(
    world_id: str,
    subject_id: str,
    memory_id: str,
    data: MemoryCorrectionCreate,
    request: Request,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> MemoryItemMutationRead:
    browser_session.require_local_frontend_request(request, mutation=True)
    scope = _scope(user, world_id, subject_id)
    try:
        result = _write_service(db).correct_summary(
            scope=scope,
            old_item_id=memory_id,
            expected_item_version=data.expected_item_version,
            expected_scope_version=data.expected_scope_version,
            summary=data.summary,
            idempotency_key=data.idempotency_key,
        )
        setting = _scope_service(db).get_or_create(scope)
        assert result.item is not None
        summary = _item_summary(
            result.item,
            scope=scope,
            character_names=_character_names(db, scope),
            retention_days=setting.retention_days,
            now=datetime.now(UTC),
        )
        db.commit()
    except Exception as exc:
        db.rollback()
        _raise_memory_mutation_error(exc)
        raise AssertionError("unreachable")
    return MemoryItemMutationRead(
        operation="correct",
        outcome=result.outcome.value,
        scope=_scope_read(scope),
        item=summary,
        replaced_memory_id=memory_id,
    )


@router.delete("/memories/{memory_id}", response_model=MemoryItemMutationRead)
def delete_memory_item(
    world_id: str,
    subject_id: str,
    memory_id: str,
    data: MemoryDeleteCreate,
    request: Request,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> MemoryItemMutationRead:
    browser_session.require_local_frontend_request(request, mutation=True)
    scope = _scope(user, world_id, subject_id)
    try:
        result = _write_service(db).delete_item(
            scope=scope,
            item_id=memory_id,
            expected_version=data.expected_version,
            idempotency_key=data.idempotency_key,
        )
        setting = _scope_service(db).get_or_create(scope)
        assert result.item is not None
        summary = _item_summary(
            result.item,
            scope=scope,
            character_names=_character_names(db, scope),
            retention_days=setting.retention_days,
            now=datetime.now(UTC),
        )
        db.commit()
    except Exception as exc:
        db.rollback()
        _raise_memory_mutation_error(exc)
        raise AssertionError("unreachable")
    return MemoryItemMutationRead(
        operation="delete",
        outcome=result.outcome.value,
        scope=_scope_read(scope),
        item=summary,
    )


def _scope_read(scope: MemoryScope) -> MemoryScopeRead:
    return MemoryScopeRead(
        world_id=scope.world_id,
        subject_world_character_id=scope.subject_world_character_id,
    )


def _setting_read(
    scope: MemoryScope,
    setting,
) -> MemorySettingRead:
    return MemorySettingRead(
        scope=_scope_read(scope),
        configured=True,
        enabled=setting.enabled,
        retention_days=setting.retention_days,
        provider_mode=setting.provider_mode.value,
        version=setting.version,
    )


def _item_summary(
    item,
    *,
    scope: MemoryScope,
    character_names: dict[str, str],
    retention_days: int,
    now: datetime,
) -> MemoryItemSummaryRead:
    related = _related_character(
        scope,
        item.counterpart_world_character_id,
        character_names=character_names,
        direction="contextual",
    )
    return MemoryItemSummaryRead(
        id=item.id,
        memory_kind=item.memory_kind.value,
        summary=item.summary,
        lifecycle=memory_lifecycle(item, now=now).value,
        formed_at=item.created_at,
        valid_from=item.valid_from,
        valid_until=item.valid_until,
        pinned=item.pinned_at is not None,
        superseded_by_memory_id=item.superseded_by_id,
        retention_days=retention_days,
        related_character=related,
        version=item.version,
    )


def _evidence_read(
    scope: MemoryScope,
    evidence,
    *,
    character_names: dict[str, str],
) -> MemoryEvidenceRead:
    direction = "contextual"
    related_id = evidence.counterpart_world_character_id
    if evidence.actor_world_character_id == scope.subject_world_character_id:
        direction = "outgoing"
        related_id = evidence.target_world_character_id or related_id
    elif evidence.target_world_character_id == scope.subject_world_character_id:
        direction = "incoming"
        related_id = evidence.actor_world_character_id or related_id
    return MemoryEvidenceRead(
        source_kind=evidence.source_type.value,
        source_label=_source_label(evidence.source_type),
        source_created_at=evidence.source_created_at,
        availability=evidence.availability.value,
        excerpt=evidence.excerpt,
        related_character=_related_character(
            scope,
            related_id,
            character_names=character_names,
            direction=direction,
        ),
        canonical_href=_canonical_href(scope, evidence),
    )


def _related_character(
    scope: MemoryScope,
    world_character_id: str | None,
    *,
    character_names: dict[str, str],
    direction: str,
) -> MemoryRelatedCharacterRead | None:
    if world_character_id is None:
        return None
    if world_character_id == scope.subject_world_character_id:
        return None
    name = character_names.get(world_character_id)
    if name is None:
        return None
    return MemoryRelatedCharacterRead(display_name=name, direction=direction)


def _character_names(db: Session, scope: MemoryScope) -> dict[str, str]:
    profiles = SqlAlchemyWorldCharacterPublicProfileReader(db).list_for_world(
        world_id=scope.world_id,
        current_user_id=scope.owner_id,
    )
    return {profile.world_character_id: profile.display_name for profile in profiles}


def _canonical_href(scope: MemoryScope, evidence) -> str | None:
    if evidence.availability.value != "available":
        return None
    if evidence.source_type in {MemorySourceTypeV1.POST, MemorySourceTypeV1.REPLY}:
        return f"/worlds/{scope.world_id}/posts/{evidence.source_id}"
    if (
        evidence.source_type
        in {
            MemorySourceTypeV1.CHAT_MESSAGE,
            MemorySourceTypeV1.OWNER_MEMORY_REQUEST,
        }
        and evidence.thread_id
    ):
        return f"/worlds/{scope.world_id}/chat/{evidence.thread_id}"
    return None


def _source_label(source_type: MemorySourceTypeV1) -> str:
    return {
        MemorySourceTypeV1.CHAT_MESSAGE: "대화",
        MemorySourceTypeV1.OWNER_MEMORY_REQUEST: "기억 요청",
        MemorySourceTypeV1.POST: "지저귐",
        MemorySourceTypeV1.REPLY: "대꾸",
        MemorySourceTypeV1.REACTION: "좋아요",
        MemorySourceTypeV1.SOCIAL_EVENT: "World 사건",
        MemorySourceTypeV1.ACTIVITY_EVENT: "활동",
        MemorySourceTypeV1.RELATIONSHIP_EVENT: "관계 변화",
        MemorySourceTypeV1.JOINT_COMMITMENT: "함께한 약속",
    }[source_type]


__all__ = ["router"]
