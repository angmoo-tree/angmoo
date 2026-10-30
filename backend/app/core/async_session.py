"""Exclusive, cancellation-safe handoff of an owned synchronous DB stage."""
import asyncio
from anyio import CancelScope

from sqlalchemy.orm import Session


async def release_request_read(session, snapshot, *, error_code):
    """Copy request identity and release a proven read before child-owned AI work.

    HTTP dependency reads belong to the request. Child workflows cannot roll
    them back; the HTTP caller explicitly ends them here after checking that
    neither ORM nor flushed/Core writes would be lost. SQLite keeps its existing
    request-session behavior.
    """
    if not isinstance(session, Session) or session.get_bind().dialect.name != "postgresql":
        return snapshot()
    from app.core.sqlite_concurrency import require_read_only_session

    def release():
        require_read_only_session(session, error_code=error_code)
        try:
            return snapshot()
        finally:
            session.rollback()

    return await session_call(session, release)


async def session_call(session, operation):
    """Await finite DB-only work; the caller must not use its Session meanwhile.

    A generation has one owner and one Session. This is a sequential handoff,
    not a shared Session pool: the worker finishes before caller cleanup,
    rollback, ORM access or another stage can resume, even on cancellation.
    Provider I/O and event publication stay in the async caller. SQLite's
    existing ownership and test doubles retain their synchronous path.
    """
    if not isinstance(session, Session) or session.get_bind().dialect.name != "postgresql":
        return operation()
    key = "_angmoo_async_session_stage"
    if session.info.get(key):
        raise RuntimeError("database_session_concurrent_stage")
    session.info[key] = True
    task = asyncio.create_task(asyncio.to_thread(operation))
    try:
        try:
            return await asyncio.shield(task)
        except asyncio.CancelledError:
            # Do not return the connection to the pool, or start cancellation
            # writes, while the previous stage can still commit on that Session.
            with CancelScope(shield=True):
                while not task.done():
                    try:
                        await asyncio.shield(task)
                    except asyncio.CancelledError:
                        continue
                    except Exception:
                        break
            if not task.cancelled():
                task.exception()
            raise
    finally:
        session.info.pop(key, None)
