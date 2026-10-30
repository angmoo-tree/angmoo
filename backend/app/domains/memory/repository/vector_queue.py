"""Bounded durable claims and revision-conditional completion in caller UoW."""
from dataclasses import dataclass
from time import time
from uuid import uuid4
from sqlalchemy import select, text, tuple_
from app.domains.memory.models.vector_work import MemoryVectorWork, MemoryVectorMaintenance


@dataclass(frozen=True)
class VectorClaim:
    generation: str
    item_id: str
    revision: int
    token: str


def enqueue(session, generation, item_id, world_id, *, change=0, force=False):
    session.execute(text("""INSERT INTO memory_vector_work
        (generation,item_id,world_id,desired_revision,applied_revision,last_change,state,due_at,lease_until)
        VALUES (:generation,:item,:world,1,0,:change,'pending',0,0)
        ON CONFLICT(generation,item_id) DO UPDATE SET
        desired_revision=memory_vector_work.desired_revision+1,
        last_change=CASE WHEN excluded.last_change>memory_vector_work.last_change THEN excluded.last_change ELSE memory_vector_work.last_change END,
        world_id=CASE WHEN excluded.world_id!='' THEN excluded.world_id ELSE memory_vector_work.world_id END,
        state='pending',due_at=0,claim_token=NULL,lease_until=0
        WHERE :force OR excluded.last_change > memory_vector_work.last_change"""),
        dict(generation=generation, item=item_id, world=world_id, change=change, force=force))


def due_ids(session, generation, *, now=None, limit=64):
    return tuple(row.item_id for row in due_page(session, generation, now=now, limit=limit))


def due_page(session, generation, *, now=None, limit=64, after=None):
    now = time() if now is None else now
    # Running leases use the same indexed due time; no scan of completed rows.
    query = select(MemoryVectorWork.item_id, MemoryVectorWork.due_at,
        MemoryVectorWork.state, MemoryVectorWork.applied_revision, MemoryVectorWork.last_code).where(
        MemoryVectorWork.generation == generation,
        MemoryVectorWork.state.in_(("pending", "retry", "running", "scheduled")),
        MemoryVectorWork.due_at <= now,
    )
    if after is not None:
        query = query.where(tuple_(MemoryVectorWork.due_at, MemoryVectorWork.item_id) > after)
    return tuple(session.execute(query.order_by(MemoryVectorWork.due_at, MemoryVectorWork.item_id).limit(limit)))


def claim(session, generation, identifiers, *, now=None):
    now = time() if now is None else now
    claims = []
    for identifier in identifiers:
        row = session.get(MemoryVectorWork, (generation, identifier), populate_existing=True)
        if row is None or row.state not in {"pending", "retry", "running", "scheduled"} or row.due_at > now:
            continue
        if row.state == "scheduled":
            row.desired_revision += 1
        row.claim_token, row.state = uuid4().hex, "running"
        row.lease_until = row.due_at = now + 120
        claims.append(VectorClaim(generation, identifier, row.desired_revision, row.claim_token))
    session.flush()
    return tuple(claims)


def owns(session, value):
    if value is None:
        return True
    generation = session.get(MemoryVectorMaintenance, value.generation)
    if generation is not None and generation.phase == "retired":
        return False
    row = session.get(MemoryVectorWork, (value.generation, value.item_id), populate_existing=True)
    return bool(row and row.claim_token == value.token and row.desired_revision == value.revision
        and row.state == "running" and row.lease_until > time())


def finish(session, value, outcome, *, next_boundary=None):
    if not owns(session, value):
        return False
    row = session.get(MemoryVectorWork, (value.generation, value.item_id))
    completed = outcome in {"indexed", "current", "ineligible", "source_unavailable"} or (outcome == "disabled" and next_boundary is not None)
    row.last_code, row.claim_token, row.lease_until = outcome, None, 0
    if completed:
        row.applied_revision = value.revision
        row.state = "scheduled" if next_boundary is not None else "done"
        row.due_at = next_boundary or 0
    elif outcome in {"disabled", "world_closed", "local_result_invalid", "configuration_invalid", "budget_exhausted"}:
        row.state, row.due_at = "blocked", 0
    else:
        row.state, row.due_at = "retry", time() + (1 if outcome == "changed" else 30)
    return True
