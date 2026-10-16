"""Read finite, already admitted situation runs for initial vector delivery.

The run/cursor/receipt ledger remains the recovery owner. No new queue, timer,
authorization cache or cross-receipt write transaction is introduced here.
"""
from sqlalchemy import select, and_, or_, exists

from app.domains.memory.models.activity_situation import (
    MemoryActivitySituationInfo, MemorySituationReceipt, MemorySituationApplyRun,
)
from app.domains.memory.models.embedding import MemoryEmbeddingSetting, MemoryVectorEligibility
from app.domains.memory.models.items import MemoryItem
from app.domains.memory.models.vector_work import MemoryVectorWork, MemoryVectorAttempt


def _unattempted():
    return ~exists().where(MemoryVectorAttempt.item_id == MemoryItem.id, MemoryVectorAttempt.attempts > 0)


def delivery_runs(session, item_ids):
    if not item_ids:
        return {}
    rows = session.execute(select(MemoryActivitySituationInfo.memory_item_id,
        MemorySituationApplyRun.id, MemorySituationApplyRun.state,
        MemorySituationApplyRun.error_code, MemoryEmbeddingSetting.enabled,
        MemoryEmbeddingSetting.provider, MemoryEmbeddingSetting.model)
        .select_from(MemoryActivitySituationInfo)
        .join(MemoryItem, MemoryItem.id == MemoryActivitySituationInfo.memory_item_id)
        .join(MemoryVectorEligibility, MemoryVectorEligibility.memory_item_id == MemoryItem.id)
        .join(MemorySituationReceipt, MemorySituationReceipt.sequence == MemoryActivitySituationInfo.receipt_sequence)
        .join(MemorySituationApplyRun, MemorySituationApplyRun.id == MemorySituationReceipt.run_id)
        .join(MemoryEmbeddingSetting, MemoryEmbeddingSetting.scope_setting_id == MemorySituationApplyRun.scope_setting_id)
        .where(MemoryActivitySituationInfo.memory_item_id.in_(item_ids),
            _unattempted(),
            MemoryItem.status == "active", MemoryItem.deleted_at.is_(None),
            MemorySituationReceipt.applied_item_id == MemoryActivitySituationInfo.memory_item_id,
            MemorySituationReceipt.state == "applied"))
    return {row.memory_item_id: row for row in rows}


def initial_members(session, generation, run_id, *, now, limit):
    """Include enrolled content whose outbox has not reached the worker yet.

Only a registration committed with a successfully applied receipt can enter.
Already attempted/delivered work keeps its independent recovery/erasure path.
Source, configuration, credential and final-effect guards still run afterwards.
"""
    return tuple(session.execute(select(MemoryItem.id, MemoryItem.world_id,
        MemoryVectorWork.item_id.label("enqueued_id"))
        .select_from(MemorySituationApplyRun)
        .join(MemorySituationReceipt, and_(MemorySituationReceipt.run_id == MemorySituationApplyRun.id,
            MemorySituationReceipt.scope_setting_id == MemorySituationApplyRun.scope_setting_id))
        .join(MemoryItem, MemoryItem.id == MemorySituationReceipt.applied_item_id)
        .join(MemoryVectorEligibility, MemoryVectorEligibility.memory_item_id == MemoryItem.id)
        .outerjoin(MemoryVectorWork, and_(MemoryVectorWork.generation == generation,
            MemoryVectorWork.item_id == MemoryItem.id))
        .where(MemorySituationApplyRun.id == run_id, MemorySituationReceipt.state == "applied",
            _unattempted(),
            MemorySituationReceipt.sequence <= MemorySituationApplyRun.cutoff_sequence,
            MemoryItem.deleted_at.is_(None), MemoryItem.status == "active",
            or_(MemoryVectorWork.item_id.is_(None), and_(
                MemoryVectorWork.state == "pending", MemoryVectorWork.applied_revision == 0,
                MemoryVectorWork.last_code.is_(None), MemoryVectorWork.due_at <= now)))
        .order_by(MemorySituationReceipt.sequence).limit(limit)))
