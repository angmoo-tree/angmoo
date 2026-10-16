"""Coalesce initial situation delivery using the existing durable run ledger."""
from time import time

from app.domains.memory.repository import vector_queue as queue
from app.domains.memory.repository.situation_vector_delivery import delivery_runs, initial_members
from app.providers.registry import get_embedding_adapter, get_model_spec


def ready_page(projection, session):
    now = time()
    page = queue.due_page(session, projection.generation, now=now, after=projection._claim_cursor)
    if not page and projection._claim_cursor is not None:
        page = queue.due_page(session, projection.generation, now=now)
    runs = delivery_runs(session, tuple(row.item_id for row in page if row.state == "pending"
        and row.applied_revision == 0 and row.last_code is None))
    selected, enrollment, visited = [], {}, set()
    deferred = False
    for row in page:
        if len(selected) >= 64:
            deferred = True
            break
        if row.item_id in selected:
            continue
        run = runs.get(row.item_id)
        limit = _batch_limit(projection, run)
        if limit == 1:
            if len(selected) < 64:
                selected.append(row.item_id)
            continue
        if run.id in visited:
            continue
        visited.add(run.id)
        members = initial_members(session, projection.generation, run.id, now=now, limit=limit)
        # Wait only for work already accepted by this run's frozen cutoff.
        # Completion, a producer error or a full bounded group releases it.
        # A failed/expired vector claim bypasses this initial grouping above.
        preparing = run.state in {"pending", "running", "deferred"} and run.error_code is None
        if members and (len(members) == limit or not preparing) and len(selected) + len(members) <= 64:
            selected.extend(member.id for member in members)
            enrollment.update((member.id, member.world_id) for member in members if member.enqueued_id is None)
        elif not members:
            # Deleted or changed items must reach the ordinary fresh proof and
            # erasure path, even if their original situation run is unfinished.
            selected.append(row.item_id)
        else:
            deferred = True
    # A bounded page of waiting scopes must not hide unrelated ready work.
    # This is only a read cursor; claims and crash recovery remain durable SQL.
    projection._claim_cursor = (page[-1].due_at, page[-1].item_id) if page and deferred else None
    return tuple(selected), enrollment


def _batch_limit(projection, run):
    if run is None or not run.enabled:
        return 1
    try:
        spec = get_model_spec(run.provider, run.model)
        provider = projection._provider or get_embedding_adapter(run.provider, run.model)
    except ValueError:
        return 1  # The normal preparation path reports unsupported settings.
    limits = spec.embedding_batch_limits
    if not spec.capabilities.embedding_batch or limits is None or not callable(getattr(provider, "embed_batch_measured", None)):
        return 1
    return max(1, min(64, limits.max_items))
