"""Finite scheduler DB stages return IDs/DTOs; worker Sessions stay local."""
import asyncio
import logging
from sqlalchemy.orm import Session
from app.core.sqlite_concurrency import require_read_only_session


async def run_slot_db_stage(source, operation, *args, on_cancel=None):
    engine = source.get_bind()
    if engine.dialect.name != 'postgresql':
        return operation(source, *args)
    require_read_only_session(source, error_code='resident_stage_has_pending_writes')
    source.rollback()

    def work(call=operation, values=args):
        with Session(engine, expire_on_commit=False) as session:
            value = call(session, *values)
            require_read_only_session(session, error_code='resident_stage_unfinished_write')
            return value

    # to_thread propagates the scheduler fence and cancellation context. The
    # single fenced tick awaits each finite stage; provider work stays on-loop.
    task = asyncio.create_task(asyncio.to_thread(work))
    try:
        return await asyncio.shield(task)
    except asyncio.CancelledError:
        while not task.done():
            try:
                await asyncio.shield(task)
            except asyncio.CancelledError:
                continue
            except Exception:
                break
        if not task.cancelled() and task.exception() is None and on_cancel is not None:
            cleanup = asyncio.create_task(asyncio.to_thread(work, on_cancel, (task.result(),)))
            while not cleanup.done():
                try:
                    await asyncio.shield(cleanup)
                except asyncio.CancelledError:
                    continue
                except Exception:
                    break
            if not cleanup.cancelled() and cleanup.exception() is not None:
                logging.getLogger(__name__).warning(
                    'resident_stage_cancel_cleanup_failed code=%s', type(cleanup.exception()).__name__)
        raise
    finally:
        source.expire_all()
