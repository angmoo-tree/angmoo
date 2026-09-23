"""SQLite checkpoint lifecycle independent of canonical domain transactions."""
from contextlib import asynccontextmanager
from pathlib import Path

from langgraph.checkpoint.sqlite.aio import AsyncSqliteSaver


@asynccontextmanager
async def activity_checkpointer(data_directory: Path):
    directory = (data_directory / "runtime" / "activity").resolve()
    directory.mkdir(parents=True, exist_ok=True)
    async with AsyncSqliteSaver.from_conn_string(str(directory / "activity-checkpoints.sqlite")) as saver:
        await saver.setup()
        yield saver


def checkpoint_config(*, activity_id: str) -> dict:
    return {"configurable": {"thread_id": f"activity:{activity_id}"}, "recursion_limit": 120}


async def prune_completed(saver, db, *, now, keep_activity_id):
    """Only completed canonical runs older than 30 days; unfinished never expire."""
    from datetime import timedelta
    from sqlalchemy import select
    from app.domains.world_characters.activity_models import ActivityGraphRun
    ids = db.scalars(select(ActivityGraphRun.activity_id).where(
        ActivityGraphRun.finished_at < now - timedelta(days=30),
        ActivityGraphRun.status.in_(("completed", "observed", "failed", "aborted")),
        ActivityGraphRun.activity_id != keep_activity_id,
    ).order_by(ActivityGraphRun.finished_at).limit(50)).all()
    for identifier in ids:
        await saver.adelete_thread(f"activity:{identifier}")
    return len(ids)


def backup_checkpoint(data_directory: Path, destination: Path):
    """SQLite snapshot for the local backup coordinator; preserve original WAL.

    Canonical and checkpoint backups must be paired while activity scheduling is
    quiesced. This function never resets data or deletes unfinished work.
    """
    import sqlite3
    source = data_directory.resolve() / "runtime" / "activity" / "activity-checkpoints.sqlite"
    if not source.is_file():
        return False
    if destination.exists():
        raise ValueError("checkpoint_backup_destination_exists")
    destination.parent.mkdir(parents=True, exist_ok=True)
    with sqlite3.connect(source.as_uri() + "?mode=ro", uri=True) as original:
        with sqlite3.connect(destination) as backup:
            original.backup(backup)
    return True
