"""Off-loop DB-only lane stages with worker-owned Sessions and ORM instances."""
import asyncio
from copy import copy
from dataclasses import fields

from sqlalchemy import inspect
from sqlalchemy.orm import Session

from app.core.sqlite_concurrency import require_read_only_session


async def run_db_stage(lane, method, state):
    if lane.ctx.db.get_bind().dialect.name != 'postgresql':
        return getattr(lane, method)(state)
    def operation(ctx, actor):
        local = copy(lane)
        local.ctx, local.actor = ctx, actor
        binder = getattr(getattr(lane, 'claim_validator', None), 'bind_context', None)
        if binder is not None:
            local.claim_validator = binder(ctx, actor)
        return getattr(local, method)(state)
    return await run_context_db_stage(lane.ctx, lane.actor, operation)


async def run_context_db_stage(source, actor, operation):
    """Only synchronous DB stages returning plain checkpoint data belong here.

    No provider request or asynchronous callback is dispatched to the worker.
    Cancellation drains the finite stage before parent cleanup may resume.
    """
    if source.db.get_bind().dialect.name != 'postgresql':
        return operation(source, actor)
    require_read_only_session(source.db, error_code='activity_stage_has_pending_writes')
    engine = source.db.get_bind()
    # Capture identities, never pass attached ORM objects into the worker.
    refs = {}
    values = {}
    for field in fields(source):
        if not field.init or field.name == 'db':
            continue
        value = getattr(source, field.name)
        mapped = inspect(value, raiseerr=False)
        if mapped is not None and getattr(mapped, 'mapper', None) is not None:
            if mapped.identity is None:
                raise RuntimeError('activity_stage_unpersisted_context')
            refs[field.name] = (mapped.mapper.class_, mapped.identity)
        else:
            values[field.name] = value
    actor_state = inspect(actor)
    actor_ref = (actor_state.mapper.class_, actor_state.identity)
    source.db.rollback()

    def work():
        with Session(engine, expire_on_commit=False) as db:
            loaded = {name: db.get(model, key) for name, (model, key) in refs.items()}
            if any(value is None for value in loaded.values()):
                raise ValueError('activity_stage_context_missing')
            local_ctx = type(source)(db=db, **values, **loaded)
            local_actor = db.get(*actor_ref)
            if local_actor is None:
                raise ValueError('activity_stage_actor_missing')
            result = operation(local_ctx, local_actor)
            # A stage owns its existing claim/receipt commits. It cannot leak
            # an unfinished write into the next asynchronous node.
            require_read_only_session(db, error_code='activity_stage_unfinished_write')
            return result

    task = asyncio.create_task(asyncio.to_thread(work))
    try:
        return await asyncio.shield(task)
    except asyncio.CancelledError:
        # Repeated parent cancellation cannot abandon a worker-owned Session.
        # The stage is bounded by its own DB deadline, not by this drain loop.
        while not task.done():
            try:
                await asyncio.shield(task)
            except asyncio.CancelledError:
                continue
            except Exception:
                break
        if not task.cancelled():
            task.exception()  # Retrieve any worker failure; cancellation wins.
        raise
    finally:
        source.db.expire_all()
