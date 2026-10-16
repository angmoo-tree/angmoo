"""Bounded outbox fanout. No source hydration or provider calls under writer."""
from time import time
from sqlalchemy import select, text, func
from app.core.sqlite_concurrency import run_sqlite_session_immediate
from app.domains.memory.models.items import MemoryItem
from app.domains.memory.models.embedding import MemoryVectorEligibility
from app.domains.worlds.models_deletion import WorldDeletionRequest
from app.domains.memory.models.vector_work import MemoryVectorChange, MemoryVectorDependency, MemoryVectorMaintenance
from app.domains.memory.repository.vector_queue import enqueue


def bootstrap_page(projection):
    generation = projection.generation
    with projection._factory() as session:
        state = session.get(MemoryVectorMaintenance, generation)
        if state is not None and state.phase != "bootstrap":
            return False
        cursor = state.cursor if state else ""
        upper = state.upper_bound if state else session.scalar(select(func.max(MemoryVectorEligibility.memory_item_id))) or ""
        rows = tuple(session.execute(select(MemoryVectorEligibility.memory_item_id, MemoryItem.world_id)
            .join(MemoryItem, MemoryItem.id == MemoryVectorEligibility.memory_item_id)
            .where(MemoryVectorEligibility.memory_item_id > cursor, MemoryVectorEligibility.memory_item_id <= upper)
            .order_by(MemoryVectorEligibility.memory_item_id).limit(64)))
    with projection._factory() as session:
        def apply():
            state = session.get(MemoryVectorMaintenance, generation)
            if state and (state.phase != "bootstrap" or state.cursor != cursor):
                return
            if state is None:
                cutoff = session.execute(text("SELECT coalesce(max(sequence),0) FROM memory_vector_changes")).scalar_one()
                state = MemoryVectorMaintenance(generation=generation, phase="bootstrap", cursor="", upper_bound=upper, cutoff=cutoff)
                session.add(state)
                session.execute(text("UPDATE memory_vector_maintenance SET phase='retired' WHERE generation!=:generation"),
                    {"generation": generation})
            for item_id, world_id in rows:
                if not session.scalar(select(WorldDeletionRequest.id).where(WorldDeletionRequest.world_id == world_id)):
                    enqueue(session, generation, item_id, world_id)
            state.cursor = rows[-1][0] if rows else cursor
            if len(rows) < 64:
                state.phase, state.cursor, state.due_at = "settling", "", time() + 86400
        run_sqlite_session_immediate(session, apply, require_clean=True)
    return True


def expand_page(projection):
    with projection._factory() as session:
        change = session.scalar(select(MemoryVectorChange).where(MemoryVectorChange.state == "pending")
            .order_by(MemoryVectorChange.sequence).limit(1))
        if change is None:
            return False
        seq, root, kind, key, cursor = change.sequence, change.root_sequence or change.sequence, change.source_kind, change.source_key, change.cursor
        identifiers = set(session.scalars(select(MemoryVectorDependency.item_id).where(
            MemoryVectorDependency.source_kind == kind, MemoryVectorDependency.source_key == key,
            MemoryVectorDependency.item_id > cursor).order_by(MemoryVectorDependency.item_id).limit(64)))
        # Initial enrollment exists before any dependency snapshot has run.
        if kind == "memory" and key > cursor:
            identifiers.add(key)
        ids = tuple(sorted(identifiers)[:64])
        rows = dict(session.execute(select(MemoryItem.id, MemoryItem.world_id).where(MemoryItem.id.in_(ids))).all())
    with projection._factory() as session:
        def apply():
            change = session.get(MemoryVectorChange, seq)
            if change is None or change.cursor != cursor or change.state != "pending":
                return
            # Generations being rebuilt share intent. Historical retained files
            # are erased synchronously by the existing privacy path.
            generations = tuple(session.scalars(select(MemoryVectorMaintenance.generation)
                .where(MemoryVectorMaintenance.phase != "retired"))) or (projection.generation,)
            closed = set(session.scalars(select(WorldDeletionRequest.world_id).where(WorldDeletionRequest.world_id.in_(tuple(rows.values())))))
            for identifier in ids:
                if rows.get(identifier, "") not in closed:
                    for generation in generations:
                        enqueue(session, generation, identifier, rows.get(identifier, ""), change=root)
                session.execute(text("""INSERT OR IGNORE INTO memory_vector_changes
                    (root_sequence,source_kind,source_key) VALUES (:root,'memory',:item)"""), dict(root=root, item=identifier))
            change.cursor = ids[-1] if ids else cursor
            if len(ids) < 64:
                change.state = "done"
            session.flush()
            # Retain visited frontier until the whole root is drained (cycles
            # and diamonds cannot re-enqueue an already completed frontier).
            pending = session.scalar(select(MemoryVectorChange.sequence).where(
                (MemoryVectorChange.sequence == root) | (MemoryVectorChange.root_sequence == root),
                MemoryVectorChange.state == "pending").limit(1))
            if pending is None:
                session.execute(text("DELETE FROM memory_vector_changes WHERE sequence=:root OR root_sequence=:root"), {"root": root})
        run_sqlite_session_immediate(session, apply, require_clean=True)
    return True
