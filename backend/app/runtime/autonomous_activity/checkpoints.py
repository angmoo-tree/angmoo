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


def erase_activity_checkpoint(data_directory: Path, activity_id: str) -> None:
    """Use the SDK's exact-thread erasure and fence a late checkpoint writer."""
    from langgraph.checkpoint.sqlite import SqliteSaver
    from app.runtime.migrations.generation import EmbeddedUpgradeLock
    if not activity_id or len(activity_id) > 100:
        raise ValueError("checkpoint_activity_identity_invalid")
    root = data_directory.resolve()
    directory = root / "runtime" / "activity"
    for node in (directory, *directory.parents):
        if node == root:
            break
        if node.is_symlink() or node.is_junction():
            raise ValueError("checkpoint_erasure_path_link")
    directory.mkdir(parents=True, exist_ok=True)
    source = directory / "activity-checkpoints.sqlite"
    if directory.is_symlink() or directory.is_junction() or source.is_symlink() or source.is_junction():
        raise ValueError("checkpoint_erasure_path_link")
    thread_id = f"activity:{activity_id}"
    with EmbeddedUpgradeLock(directory / "checkpoint-maintenance.lock"):
        with SqliteSaver.from_conn_string(str(source)) as saver:
            saver.setup()
            with saver.cursor() as cursor:
                cursor.execute("CREATE TABLE IF NOT EXISTS angmoo_erased_checkpoint_threads(thread_id TEXT PRIMARY KEY)")
                for table in ("checkpoints", "writes"):
                    for event in ("INSERT", "UPDATE"):
                        scopes = "thread_id=NEW.thread_id" if event == "INSERT" else "thread_id IN (NEW.thread_id,OLD.thread_id)"
                        cursor.execute(f'CREATE TRIGGER IF NOT EXISTS angmoo_erased_{table}_{event.lower()} BEFORE {event} ON {table} '
                            f"WHEN EXISTS(SELECT 1 FROM angmoo_erased_checkpoint_threads WHERE {scopes}) "
                            "BEGIN SELECT RAISE(ABORT, 'world_deleting'); END")
                cursor.execute("INSERT INTO angmoo_erased_checkpoint_threads VALUES(?) ON CONFLICT DO NOTHING", (thread_id,))
            saver.delete_thread(thread_id)
            with saver.cursor(transaction=False) as cursor:
                for table in ("checkpoints", "writes"):
                    if cursor.execute(f"SELECT 1 FROM {table} WHERE thread_id=? LIMIT 1", (thread_id,)).fetchone():
                        raise ValueError("checkpoint_erasure_not_acknowledged")
