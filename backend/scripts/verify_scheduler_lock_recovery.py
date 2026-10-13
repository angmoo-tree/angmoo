"""Isolated Docker-only verification server; synthetic DB, fake tick, no AI.

Run via the dedicated compose file in scripts/diagnostics, never the app compose.
Its controls exist only in this test process and are not product routes.
"""
from __future__ import annotations

import asyncio
from contextlib import asynccontextmanager
import os
from pathlib import Path
import sqlite3
from threading import Event, Thread
from time import monotonic
from types import SimpleNamespace

from fastapi import FastAPI, HTTPException
from sqlalchemy import text
import uvicorn

from app.config import Settings
from app.main import runtime_health
from app.domains.identity.models import InstallationIdentity
from app.domains.identity.constants import LOCAL_INSTALLATION_KEY
from app.domains.runtime.service.components import component_observations
from app.runtime.persistence.sqlite_database import SqliteCanonicalDatabase
from app.runtime.persistence.runtime_data_path import StaticRuntimeDataPath
from app.runtime.resident.scheduler import run_resident_tick_scheduler
from app.runtime.single_backend_components import SingleBackendRuntimeComponents
from app.runtime import component_workers

ROOT = Path("/tmp/angmoo-creator-lock-test")
database = SqliteCanonicalDatabase(StaticRuntimeDataPath(ROOT))
started_at = monotonic()
locked, unlock = Event(), Event()
holder_thread: Thread | None = None
duplicate_count = 0
config = Settings().model_copy(update={"RESIDENT_TICK_INTERVAL_SECONDS": 10,
    "RESIDENT_TICK_HEARTBEAT_INTERVAL_SECONDS": 1, "RESIDENT_TICK_LEASE_TTL_SECONDS": 6,
    "LOCAL_RUNTIME_COMPONENT_MODE": "in_process", "RESIDENT_TICK_READY_PATH": str(ROOT / "ready"),
    "RESIDENT_TICK_PROCESS_LOCK_PATH": str(ROOT / "scheduler.lock")})


async def fake_tick():
    global duplicate_count
    with database.engine.begin() as connection:
        window = connection.execute(text("SELECT last_tick_window_at FROM runtime_scheduler_leases")).scalar_one()
        try:
            connection.execute(text("INSERT INTO test_tick_effects(window) VALUES(:window)"), {"window": window})
        except Exception:
            duplicate_count += 1
            raise
    return SimpleNamespace(started_count=1)


async def scheduler_runner(stop, listener):
    await run_resident_tick_scheduler(config=config, session_factory=database.session_factory,
        tick_runner=fake_tick, stop_event=stop, state_listener=listener)


def fake_projector(stop, listener):
    listener("ready"); stop.wait()


@asynccontextmanager
async def lifespan(app):
    database.open()
    with database.session() as session:
        session.add(InstallationIdentity(singleton_key=LOCAL_INSTALLATION_KEY,
            installation_id="synthetic-lock-test", bootstrap_state="unclaimed")); session.commit()
    with database.engine.begin() as connection:
        connection.exec_driver_sql("CREATE TABLE test_tick_effects(window TEXT PRIMARY KEY)")
    # Keep the real health policy; this test has no graph activity or providers.
    component_workers.borrow_runtime_graph_client = lambda _config: SimpleNamespace(verify_connectivity=lambda: None)
    app.state.runtime_composition = SimpleNamespace(session_factory=database.session_factory, settings=config)
    app.state.runtime_config = SimpleNamespace(profile=SimpleNamespace(value="public"))
    manager = SingleBackendRuntimeComponents(scheduler_runner=scheduler_runner, projector_runner=fake_projector,
        registry=component_observations, startup_timeout_seconds=5, shutdown_timeout_seconds=3)
    await manager.start()
    try: yield
    finally:
        unlock.set()
        if holder_thread: await asyncio.to_thread(holder_thread.join, 2)
        await manager.stop(); database.close()


app = FastAPI(lifespan=lifespan)
app.add_api_route("/health", runtime_health)


@app.post("/test/lock")
async def lock_database():
    global holder_thread
    if holder_thread and holder_thread.is_alive(): raise HTTPException(409, "already_locked")
    unlock.clear(); locked.clear()
    def hold():
        with sqlite3.connect(database.database_path) as connection:
            connection.execute("BEGIN IMMEDIATE"); locked.set()
            unlock.wait(30); connection.rollback()
    holder_thread = Thread(target=hold); holder_thread.start()
    if not await asyncio.to_thread(locked.wait, 2): raise HTTPException(503, "lock_not_acquired")
    return {"locked": True}


@app.post("/test/unlock")
async def unlock_database():
    unlock.set()
    if holder_thread: await asyncio.to_thread(holder_thread.join, 2)
    return {"locked": False}


@app.get("/test/observations")
def observations():
    with database.engine.connect() as connection:
        effects = connection.execute(text("SELECT window FROM test_tick_effects ORDER BY window")).scalars().all()
        epoch = connection.execute(text("SELECT fencing_epoch FROM runtime_scheduler_leases")).scalar_one()
    return {"pid": os.getpid(), "process_started_monotonic": started_at,
        "effects": effects, "duplicates": duplicate_count, "epoch": epoch,
        "states": {item.name: item.state.value for item in component_observations.snapshot()}}


if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=8080, log_level="info")
