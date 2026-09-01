"""Memory-shape invariants that must be checked before persistence."""

from app.domains.memory.domain.errors import MemoryValidationError
from app.domains.memory.domain.provenance import MemoryKindV1


def validate_memory_item_shape(
    *,
    kind: MemoryKindV1,
    counterpart_world_character_id: str | None,
    thread_id: str | None,
) -> None:
    if kind in {
        MemoryKindV1.DIRECTIONAL_RELATIONSHIP,
        MemoryKindV1.ACCEPTED_JOINT_COMMITMENT,
    } and not counterpart_world_character_id:
        raise MemoryValidationError("memory_counterpart_required")
    if kind is MemoryKindV1.THREAD_SUMMARY and not thread_id:
        raise MemoryValidationError("memory_thread_required")


__all__ = ["validate_memory_item_shape"]
