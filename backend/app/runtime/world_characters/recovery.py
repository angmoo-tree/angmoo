"""Startup reconciliation with the existing caller factory and SQLite lock."""
from collections.abc import Callable, Collection
from sqlalchemy.orm import Session
from app.core.sqlite_concurrency import run_sqlite_session_immediate
from app.domains.world_characters.contracts.runtime_modes import AutonomousRuntimeModeRepairResult
from app.domains.world_characters.service.runtime_modes import repair_affected_local_autonomous_runtime_modes

def reconcile_local_autonomous_runtime_modes(
    session_factory: Callable[[], Session],
    *,
    excluded_world_ids: Collection[str] = (),
) -> AutonomousRuntimeModeRepairResult:
    """Repair only proven PR G local rows before embedded workers start."""

    with session_factory() as db:
        return run_sqlite_session_immediate(
            db,
            lambda: repair_affected_local_autonomous_runtime_modes(
                db,
                excluded_world_ids=excluded_world_ids,
            ),
        )
