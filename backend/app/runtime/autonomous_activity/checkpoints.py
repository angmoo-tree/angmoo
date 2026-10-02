"""SQLite checkpoint lifecycle independent of canonical domain transactions."""
from contextlib import asynccontextmanager
from pathlib import Path

from langgraph.checkpoint.sqlite.aio import AsyncSqliteSaver


@asynccontextmanager
async def activity_checkpointer(data_directory: Path, *, busy_ms: int | None = None):
    directory = (data_directory / "runtime" / "activity").resolve()
    directory.mkdir(parents=True, exist_ok=True)
    async with AsyncSqliteSaver.from_conn_string(str(directory / "activity-checkpoints.sqlite")) as saver:
        if busy_ms is not None:
            await saver.conn.execute(f"PRAGMA busy_timeout={int(busy_ms)}")
        await saver.setup()
        yield saver


def checkpoint_config(*, activity_id: str) -> dict:
    return {"configurable": {"thread_id": f"activity:{activity_id}"}, "recursion_limit": 120}


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
    from app.runtime.migrations.generation import EmbeddedUpgradeLock
    with EmbeddedUpgradeLock(data_directory.resolve() / "runtime" / "activity" / "checkpoint-maintenance.lock"):
        with sqlite3.connect(source.as_uri() + "?mode=ro", uri=True) as original:
            with sqlite3.connect(destination) as backup:
                original.backup(backup)
    return True
