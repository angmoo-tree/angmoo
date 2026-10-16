"""Consume persisted changes/claims and perform finite bootstrap/audit sweeps."""
from app.core import work_observation as observation
from time import time
from sqlalchemy import select, or_, text, func, case
from app.core.sqlite_concurrency import run_sqlite_session_immediate
from app.domains.memory.models.vector_work import MemoryVectorWork, MemoryVectorChange, MemoryVectorMaintenance
from app.domains.memory.models.embedding import MemoryVectorEligibility
from app.domains.memory.models.items import MemoryItem
from app.domains.memory.repository import vector_queue as queue
from app.runtime.memory.vector_changes import bootstrap_page, expand_page


@observation.observed("vector_claim")
def take(projection):
    from app.runtime.memory.vector_situation_batches import ready_page
    with projection._factory() as session:
        ids, enrollment = ready_page(projection, session)
        # One bounded read outside the writer only while observation is enabled.
        # This covers carry-in claims with no outbox event in the current session.
        scopes = {row.id: (row.world_id, row.subject_world_character_id) for row in session.execute(
            select(MemoryItem.id, MemoryItem.world_id, MemoryItem.subject_world_character_id)
            .where(MemoryItem.id.in_(ids)))} if ids and observation.enabled() else {}
    if not ids:
        return ()
    with projection._factory() as session:
        def claim_page():
            from app.domains.worlds.models_deletion import WorldDeletionRequest
            live = set(session.scalars(select(MemoryVectorEligibility.memory_item_id)
                .join(MemoryItem, MemoryItem.id == MemoryVectorEligibility.memory_item_id)
                .where(MemoryItem.id.in_(enrollment), MemoryItem.deleted_at.is_(None),
                    MemoryItem.status == "active", ~MemoryItem.world_id.in_(select(WorldDeletionRequest.world_id))))) if enrollment else set()
            for item_id, world_id in enrollment.items():
                if item_id in live:
                    queue.enqueue(session, projection.generation, item_id, world_id)
            return queue.claim(session, projection.generation,
                tuple(item_id for item_id in ids if item_id not in enrollment or item_id in live))
        claims = run_sqlite_session_immediate(session,
            claim_page, require_clean=True)
    for claim in claims:
        world_id, actor_id = scopes.get(claim.item_id, (None, None))
        observation.emit("queue", boundary="claimed", item_id=claim.item_id, generation=claim.generation,
            desired_revision=claim.revision, world_id=world_id, actor_id=actor_id)
    return claims


@observation.observed("vector_ack")
def acknowledge(projection, claim, outcome):
    with projection._factory() as session:
        key = projection._attempt_keys.get(claim.item_id)
        if outcome in {"failed", "attempts_exhausted"} and key:
            exhausted = session.execute(text("SELECT 1 FROM memory_vector_attempts WHERE item_id=:item AND profile=:profile AND content_hash=:digest AND credential_revision=:revision AND (attempts>=3 OR code='terminal')"),
                dict(item=claim.item_id, profile=key[0], digest=key[1], revision=key[2])).scalar_one_or_none()
            if exhausted:
                outcome = "budget_exhausted"
            session.rollback()
        def complete():
            finished = queue.finish(session, claim, outcome, next_boundary=projection._boundaries.get(claim.item_id))
            if finished and outcome == "ineligible":
                item = session.get(MemoryItem, claim.item_id)
                if item is None or item.deleted_at is not None or item.status == "deleted":
                    from app.domains.memory.repository.vector_erasure import erase
                    erase(session, (claim.item_id,))
            return finished
        accepted = run_sqlite_session_immediate(session, complete, require_clean=True)
        # Claim IDs are safe; claim tokens remain private. Scope is correlated
        # by the independent canonical snapshot when an item was erased.
        observation.emit("queue", boundary="ack", item_id=claim.item_id, generation=claim.generation,
            desired_revision=claim.revision, outcome=outcome, acknowledged=accepted)
        return accepted


def state(projection):
    with projection._factory() as session:
        maintenance = session.get(MemoryVectorMaintenance, projection.generation)
        change = session.scalar(select(MemoryVectorChange.sequence).where(MemoryVectorChange.state == "pending").limit(1))
        work = session.scalar(select(MemoryVectorWork.state).where(MemoryVectorWork.generation == projection.generation,
            MemoryVectorWork.state.in_(("pending", "running", "retry", "blocked")),
            or_(MemoryVectorWork.last_code.is_(None), MemoryVectorWork.last_code.not_in(("disabled", "world_closed"))))
            .order_by(case((MemoryVectorWork.state == "blocked", 0), (MemoryVectorWork.state == "retry", 1), else_=2)).limit(1))
        return maintenance.phase if maintenance else "bootstrap", change is not None, work


def settle(projection):
    phase, changes, work = state(projection)
    if phase != "settling" or changes or work:
        return False
    with projection._factory() as session:
        def complete():
            if session.scalar(select(MemoryVectorChange.sequence).where(MemoryVectorChange.state == "pending").limit(1)) is not None:
                return False
            if session.scalar(select(MemoryVectorWork.item_id).where(MemoryVectorWork.generation == projection.generation,
                MemoryVectorWork.state.in_(("pending", "running", "retry", "blocked")),
                or_(MemoryVectorWork.last_code.is_(None), MemoryVectorWork.last_code.not_in(("disabled", "world_closed")))).limit(1)) is not None:
                return False
            row = session.get(MemoryVectorMaintenance, projection.generation)
            if row is not None and row.phase == "settling":
                row.phase, row.due_at = "ready", time() + 86400
                return True
            return False
        return run_sqlite_session_immediate(session, complete, require_clean=True)


@observation.observed("vector_audit")
def audit_page(projection):
    with projection._factory() as session:
        row = session.get(MemoryVectorMaintenance, projection.generation)
        if row is None or row.phase not in {"ready", "audit_work", "audit_index"} or row.due_at > time():
            return False
        cursor, phase, expected_phase = row.cursor, row.phase, row.phase
        phase = "audit_work" if phase == "ready" else phase
        if expected_phase == "ready":
            cursor = ""
            upper = session.scalar(select(func.max(MemoryVectorEligibility.memory_item_id))) or ""
        else:
            upper = row.upper_bound
        if phase == "audit_work":
            candidates = tuple(session.scalars(select(MemoryVectorWork.item_id).where(
                MemoryVectorWork.generation == projection.generation,
                MemoryVectorWork.item_id > cursor,
                MemoryVectorWork.item_id <= upper,
                MemoryVectorWork.last_code.in_(("indexed", "current")),
                MemoryVectorWork.state.in_(("done", "scheduled")))
                .order_by(MemoryVectorWork.item_id).limit(64)))
            documents = tuple((f"memory-item:{item}", item) for item in candidates)
        else:
            documents = tuple((doc, item) for doc, item in projection.index.document_page(after=cursor)
                if doc <= upper)
        mismatches = []
        for doc_id, item_id in documents:
            registration = session.get(MemoryVectorEligibility, item_id)
            version = session.scalar(select(MemoryItem.version).where(MemoryItem.id == item_id))
            identity = projection.index.identity(doc_id)
            from app.domains.memory.repository.vector_work import read_work
            work = read_work(session, item_id)
            if registration is None or identity is None or identity[:2] != (version, registration.content_hash) or (work and identity[2] != work[1].profile):
                mismatches.append(item_id)
        next_upper = projection.index.document_upper_bound() if phase == "audit_work" and len(documents) < 64 else upper
    with projection._factory() as session:
        def checkpoint():
            row = session.get(MemoryVectorMaintenance, projection.generation)
            if row is None or row.cursor != cursor or row.phase != expected_phase:
                return
            for item_id in mismatches:
                queue.enqueue(session, projection.generation, item_id, "", force=True)
            row.cursor = (documents[-1][1] if phase == "audit_work" else documents[-1][0]) if documents else ""
            row.phase = phase
            row.upper_bound = upper
            if len(documents) < 64:
                row.cursor = ""
                if phase == "audit_work":
                    row.phase = "audit_index"
                    row.upper_bound = next_upper
                else:
                    row.phase, row.due_at = "ready", time() + 86400
        run_sqlite_session_immediate(session, checkpoint, require_clean=True)
    return True


def retire_page(projection):
    with projection._factory() as session:
        rows = tuple(session.execute(select(MemoryVectorWork.generation, MemoryVectorWork.item_id)
            .join(MemoryVectorMaintenance, MemoryVectorMaintenance.generation == MemoryVectorWork.generation)
            .where(MemoryVectorMaintenance.phase == "retired").limit(64)))
    if not rows:
        return
    with projection._factory() as session:
        def remove():
            for generation, item in rows:
                session.execute(text("DELETE FROM memory_vector_work WHERE generation=:generation AND item_id=:item AND EXISTS "
                    "(SELECT 1 FROM memory_vector_maintenance WHERE generation=:generation AND phase='retired')"),
                    dict(generation=generation, item=item))
        run_sqlite_session_immediate(session, remove, require_clean=True)


async def tick(projection):
    await projection._prepare_page()
    await projection._canonical.call(bootstrap_page, projection)
    # Cap expansion per turn and interleave delivery so a hot producer cannot
    # starve already admitted work. Each root has a durable visited frontier.
    for _ in range(4):
        if not await projection._canonical.call(expand_page, projection):
            break
    claims = await projection._canonical.call(take, projection)
    projection._claims = {claim.item_id: claim for claim in claims}
    try:
        outcomes = await projection.sync_items(tuple(projection._claims))
        for claim in claims:
            await projection._canonical.call(acknowledge, projection, claim, outcomes[claim.item_id])
    finally:
        projection._claims.clear()
        projection._boundaries.clear()
        projection._attempt_keys.clear()
    await projection._canonical.call(settle, projection)
    phase, changes, work = await projection._canonical.call(state, projection)
    # Retry the filesystem promotion after a crash following the SQL barrier.
    if phase == "ready" and not changes and not work and projection._on_clean_cycle is not None:
        projection._on_clean_cycle(projection.index)
        projection._on_clean_cycle = None
    await projection._canonical.call(audit_page, projection)
    await projection._canonical.call(retire_page, projection)
    phase, changes, work = await projection._canonical.call(state, projection)
    projection._tick_failed = work in {"retry", "blocked"}
    projection.status = "degraded" if projection._tick_failed else "recovering" if phase in {"bootstrap", "settling"} else "ready"
    return bool(claims or changes or phase == "bootstrap")
