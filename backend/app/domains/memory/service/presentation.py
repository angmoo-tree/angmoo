"""Memory inspector response values and evidence navigation."""
from __future__ import annotations
from datetime import datetime

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
from app.domains.memory.service.inspector import memory_lifecycle


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
